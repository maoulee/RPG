#!/usr/bin/env python3
"""
COMB rollout (best-prefix tree continuation) — the paper's actual method.
Unlike prefix_rollout.py (replay-based, seed prefix), this does TRUE sequential
best-prefix continuation:

  decompose (once, shared)
    → sample K select_relations → score S_plan → pick best plan*
    → from best plan*: sample K expand_branches → score S_select → pick best explore*
    → from best explore*: sample K answer → score S_reason

Each stage's candidates SHARE the best-prefix of prior stages (comb structure).
The shared prefix is constant within a group → group-relative advantage only
flows to the current stage's tokens (implicit mask, no explicit masking needed).

Usage (smoke, 1 case):
  python scripts/comb_rollout.py --seed data/offline_grpo/resample_clean.jsonl --case-idx 0
"""
import argparse, asyncio, copy, json, os, pickle, statistics, sys, time
import aiohttp
sys.path.insert(0, os.path.dirname(__file__))
from prefix_rollout import (gen_k, score_variant, parse_react_output, parse_tool_call,
                            replay_to_stage, traj_to_prefix_msgs, build_context, agents_md,
                            STAGE_TOOL, URL, MODEL)
from kgqa.agent import tools as T
from kgqa.llm.batch import _call_many   # batch port (custom batch endpoint, >> per-call speed)

# Per-stage rollout-cost accumulator (wall-clock seconds + generated tokens),
# accumulated across all cases and printed in main() for the appendix cost table.
STAGE_STATS = {s: {"t": 0.0, "tok": 0, "n": 0} for s in ("plan", "select", "reason")}
_TOK = None
def _tok_count(text):
    global _TOK
    if _TOK is None:
        from transformers import AutoTokenizer
        _TOK = AutoTokenizer.from_pretrained("/zhaoshu/llm/Qwen3.5-9B", trust_remote_code=True)
    return len(_TOK(text or "", add_special_tokens=False).input_ids)


async def gen_k_batch(session, prefix, k, max_tokens, temp):
    """Sample K candidates via the BATCH PORT (_call_many), not per-call gen_k.
    _call_many packs multiple prompts into one request to the custom batch
    endpoint — far faster than K separate POSTs or asyncio.gather concurrency."""
    prompts = [prefix] * k
    results, reasoning = await _call_many(session, prompts, max_tokens, temp, 0.95)
    return [(r or "", reasoning[i] if i < len(reasoning) else "") for i, r in enumerate(results)]

K_DEFAULT = 8
MAX_TOKENS = 600
CORRECT = 0.95


async def execute_and_score(stage, content, ctx_base, session):
    """Execute one candidate; return (S_X, ok, ctx_executed, result_str)."""
    tool, args = parse_react_output(content)
    if tool != STAGE_TOOL[stage]:
        return None, False, None, None
    ctx = copy.deepcopy(ctx_base)
    try:
        if stage == "reason":
            s = score_variant(stage, ctx, args.get("entities") or [], ctx.gt_answers)
            return s, True, ctx, json.dumps({"entities": args.get("entities", [])})
        result_str = await T.dispatch(tool, args, ctx, session)
        if stage == "select":
            bids = args.get("branch_ids") or args.get("branch_id_list") or []
            if isinstance(bids, str): bids = [bids]
            ctx.last_expand = [str(b) for b in bids if str(b).strip()]
        s = score_variant(stage, ctx, None, ctx.gt_answers)
        return s, True, ctx, result_str
    except Exception as e:
        return None, False, None, str(e)


def _asst(content, reasoning):
    m = {"role": "assistant", "content": content}
    if reasoning: m["reasoning_content"] = reasoning
    return m

def _tool_msg(name, result_str):
    return {"role": "user", "content": f"Tool result ({name}): {result_str}"}


async def comb_stage(stage, prefix, ctx_base, session, k, temps=(0.7, 1.2, 1.5)):
    """Sample K candidates with TEMP ESCALATION; return (scored, best_ctx, prefix_ext, cls).
    Escalation: try 0.7; if no correct(≥0.95) AND no variance, try 1.2, then 1.5.
    Classification: grpo (variance) / sft (no variance + high) / skip (no variance + low)."""
    scored = []
    t0 = time.monotonic(); gen_tok = 0
    for temp in temps:
        gens = await gen_k(session, prefix, k, MAX_TOKENS, temp)  # n=K shares prefix KV cache (>> batch endpoint for identical prompts)
        gen_tok += sum(_tok_count(c) for c, _ in gens)
        # CONCURRENT execution of K candidates (each independent deepcopy, no shared state)
        async def _exec(content, reasoning):
            if not content: return None
            s, ok, ctx_exec, result_str = await execute_and_score(stage, content, ctx_base, session)
            return (s, content, reasoning, ctx_exec, result_str) if ok else None
        results = await asyncio.gather(*[_exec(c, r) for c, r in gens])
        scored = [r for r in results if r is not None]
        if not scored:
            continue
        ss = [x[0] for x in scored]
        has_correct = any(s >= CORRECT for s in ss)
        has_var = len(ss) >= 2 and (max(ss) - min(ss)) > 0.01
        if has_correct or has_var:
            break
    STAGE_STATS[stage]["t"] += time.monotonic() - t0
    STAGE_STATS[stage]["tok"] += gen_tok
    STAGE_STATS[stage]["n"] += 1
    if not scored:
        return [], None, None, "skip"
    best = max(scored, key=lambda x: x[0])
    tool_name = STAGE_TOOL[stage]
    prefix_ext = [_asst(best[1], best[2]), _tool_msg(tool_name, best[4])]
    # classify: grpo / sft / skip
    ss = [x[0] for x in scored]
    std = statistics.pstdev(ss) if len(ss) > 1 else 0.0
    if std > 0.01:
        cls = "grpo"
    elif max(ss) >= CORRECT:
        cls = "sft"           # no variance but all high → SFT positive
    else:
        cls = "skip"          # no variance + low → no signal
    return scored, best[3], prefix_ext, cls


def build_group_records(cid, stage, scored, cls, prefix_msgs):
    """Build output records for one stage group based on classification."""
    ss = [x[0] for x in scored]
    mu = statistics.mean(ss)
    sigma = (statistics.pstdev(ss) + 1e-6) if len(ss) > 1 else 1.0
    records = []
    if cls == "grpo":
        for s, content, reasoning, _, _ in scored:
            adv = (s - mu) / sigma
            asst = {"role": "assistant", "content": content}
            if reasoning: asst["reasoning_content"] = reasoning
            records.append({"case_id": cid, "stage": stage, "route": "grpo",
                            "messages": list(prefix_msgs) + [asst],
                            "advantage": round(adv, 6), "S_X": round(s, 4)})
    elif cls == "sft":
        # only the best candidate, advantage=1.0
        best = max(scored, key=lambda x: x[0])
        asst = {"role": "assistant", "content": best[1]}
        if best[2]: asst["reasoning_content"] = best[2]
        records.append({"case_id": cid, "stage": stage, "route": "sft",
                        "messages": list(prefix_msgs) + [asst],
                        "advantage": 1.0, "S_X": round(best[0], 4)})
    # cls == "skip": no records
    return records


async def comb_rollout_case(seed_rec, sample, session, k=K_DEFAULT):
    """Run the full comb rollout for one case. Returns (records, classes, err)."""
    cid = seed_rec["case_id"]
    sys_prompt = agents_md()
    ctx0, err = await replay_to_stage(seed_rec, "plan", sample, session)
    if ctx0 is None:
        return [], {}, f"replay_fail: {err}"
    prefix, _ = traj_to_prefix_msgs(seed_rec, sys_prompt, "select_relations")

    records = []
    classes = {}

    # STAGE 1: plan (select_relations)
    scored_p, ctx_p, ext_p, cls_p = await comb_stage("plan", prefix, ctx0, session, k)
    classes["plan"] = cls_p
    if cls_p == "skip" or ctx_p is None:
        return records, classes, f"plan_{cls_p}"
    records += build_group_records(cid, "plan", scored_p, cls_p, prefix)
    prefix_p = prefix + ext_p

    # STAGE 2: explore (expand_branches) — from best plan
    scored_e, ctx_e, ext_e, cls_e = await comb_stage("select", prefix_p, ctx_p, session, k)
    classes["select"] = cls_e
    if cls_e == "skip" or ctx_e is None:
        return records, classes, f"select_{cls_e}"
    records += build_group_records(cid, "select", scored_e, cls_e, prefix_p)
    prefix_e = prefix_p + ext_e

    # STAGE 3: reason (answer) — from best explore
    scored_r, _, _, cls_r = await comb_stage("reason", prefix_e, ctx_e, session, k)
    classes["reason"] = cls_r
    if cls_r != "skip":
        records += build_group_records(cid, "reason", scored_r, cls_r, prefix_e)

    return records, classes, None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="data/offline_grpo/resample_clean.jsonl")
    ap.add_argument("--pkl", default="data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl",
                    help="case subgraph pkl (must contain the seed case_ids). Use train_sparql_patched.pkl for the real training rollout.")
    ap.add_argument("--case-idx", type=int, default=0)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--n-cases", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=16,
                    help="cases processed concurrently (vLLM continuous batching)")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    seeds = [json.loads(l) for l in open(args.seed) if l.strip()]
    pkl = {x["id"]: x for x in pickle.loads(open(args.pkl, "rb").read())}

    from collections import Counter
    import time as _time
    route_counts = Counter()
    all_records = []
    sem = asyncio.Semaphore(args.concurrency)

    async def run_one(idx, session):
        srec = seeds[idx]
        sample = pkl.get(srec["case_id"])
        if sample is None:
            return idx, [], {}, "no_sample"
        async with sem:
            records, classes, err = await comb_rollout_case(srec, sample, session, args.k)
        return idx, records, classes, err

    t0 = _time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [run_one(idx, session) for idx in range(args.case_idx, args.case_idx + args.n_cases)]
        for coro in asyncio.as_completed(tasks):
            idx, records, classes, err = await coro
            cls_str = " ".join(f"{s}={classes.get(s,'?')}" for s in ["plan","select","reason"])
            for r in records: route_counts[r["route"]] += 1
            all_records += records
            tag = f" ERR={err}" if err else ""
            print(f"[{idx}] {seeds[idx]['case_id'][:24]}  {cls_str}  records={len(records)}{tag}", flush=True)
    dt = _time.time() - t0
    print(f"\n=== summary ({args.n_cases} cases, {dt:.0f}s, conc={args.concurrency}) ===")
    print(f"  records: {len(all_records)} | routes: {dict(route_counts)} | "
          f"throughput: {args.n_cases/dt*60:.1f} cases/min")
    # Per-stage rollout cost (appendix table): wall-clock / case + generated tokens / case.
    print("  per-stage rollout cost:")
    for s, name in (("plan", "Planning"), ("select", "Exploration"), ("reason", "Reasoning")):
        st = STAGE_STATS[s]; n = st["n"] or 1
        print(f"    {name:11} {st['t']/n:6.2f} s/case   {st['tok']/n:8.0f} gen-tok/case   (n={st['n']})")
    tot_t = sum(STAGE_STATS[s]["t"] for s in STAGE_STATS)
    tot_tok = sum(STAGE_STATS[s]["tok"] for s in STAGE_STATS)
    if tot_t > 0:
        print(f"    total model throughput: {tot_tok/tot_t:.0f} gen-tokens/s")
    if args.output and all_records:
        with open(args.output, "w") as f:
            for r in all_records: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  wrote {args.output} ({len(all_records)} records)")


if __name__ == "__main__":
    asyncio.run(main())
