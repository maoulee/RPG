#!/usr/bin/env python3
"""Offline rollout for GRPO training data: N cases × G samples at temp>0.

Reuses the production SEQ pieces (SeqReactCase, process_turn, _ctx_to_result_dict)
and swaps only the LLM call: llm.chat_batch (OfflineVLLM) instead of HTTP.
Each case is expanded into G independent trajectories; temp>0 makes them diverge
from round 1 → group-relative advantage signal for GRPO.

Env:
  SPLIT        = test | train        (default test)
  N_CASES      = cases to rollout    (default 3)
  N_SAMPLES    = G trajectories/case (default 2)
  TEMP         = sampling temperature(default 0.8)
  THINK_BUDGET = thinking tokens     (default 1000)
  MAX_ROUNDS   = agent turns cap     (default 16)
  OUT          = output json path    (default /tmp/rollout_<split>_<n>x<g>.json)
"""
import asyncio, json, os, pickle, time, sys
from pathlib import Path

sys.path.insert(0, "/zhaoshu/subgraph")
import aiohttp

from kgqa.llm.offline_vllm import OfflineVLLM
from kgqa.agent.seq_react_loop import SeqReactCase
from kgqa.agent.loop import _ctx_to_result_dict

TEST_PKL = "/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl"
# REPAIRED train pkls (SPARQL-driven Virtuoso repair — authoritative, see memory
# virtuoso-freebase-repair). Both share the SEQ-ready schema; no conversion needed.
PKLS = {
    "test": TEST_PKL,
    "train": "/zhaoshu/subgraph/data/cwq_processed/train_sparql_patched.pkl",   # CWQ repaired (gap 45→11%)
    "webqsp": "/zhaoshu/subgraph/data/webqsp/train_sparql_patched.pkl",          # WebQSP repaired (gap 15→7%, 98% single-SG)
    # v4-repaired (CVT value-attr flooding on top of sparql_patched — see memory
    # subgraph-value-attr-repair). Use for rollout after the repair-v4 data fix.
    "train_v4": "/zhaoshu/subgraph/data/cwq_processed/train_v4_repaired.pkl",
    "test_v4": "/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl",
    # v5 = v4 + 98 stem-only TYPE repairs (structure-frozen rewording; see
    # SESSION_MEMORY 2026-08-19). Paired-eval split for the stemfix A/B.
    "test_v5": "/zhaoshu/subgraph/data/cwq_processed/test_v5_stemfix.pkl",
}


def _load(split, n):
    pkl = PKLS.get(split, TEST_PKL)
    samples = pickle.loads(Path(pkl).read_bytes())
    pool = [s for s in samples if s.get("a_entity")]
    # optional case-id filter (CASE_FILTER env: file with one id per line) — for
    # rolling out only the clean 935 cases (drop 65 GT-noise) on repaired data.
    cf = os.environ.get("CASE_FILTER", "").strip()
    if cf:
        keep = {ln.strip() for ln in open(cf) if ln.strip()}
        pool = [s for s in pool if s["id"] in keep]
    if n > 0:
        pool = pool[:n]
    return pool


async def rollout(llm, cases, n_samples, temperature, thinking_budget, max_rounds,
                   base_case_idx=0, inflow_target=0):
    import time as _time_mod
    _T0 = _time_mod.time()
    pilot_rows = [{"case_id": s["id"], "question": s["question"],
                   "gt_answers": s.get("a_entity", [])} for s in cases]

    # expand to G trajectories per case. INFLOW MODE (inflow_target>0, user
    # design 2026-08-22 长尾拉满): trajectories are admitted progressively —
    # when active drops below the target, the next cases' trajectories join.
    # Kills the lockstep long tail (last rounds ran 2-5 cases at latency-
    # bound ~10s while the server idled).
    all_react = []
    for ci, (s, pr) in enumerate(zip(cases, pilot_rows)):
        gci = base_case_idx + ci
        for gi in range(n_samples):
            all_react.append((SeqReactCase(s, pr, gci), (gci, ci, gi)))
    if inflow_target and inflow_target > 0:
        react_cases = [rc for rc, _ in all_react[:inflow_target]]
        pending = [rc for rc, _ in all_react[inflow_target:]]
    else:
        react_cases = [rc for rc, _ in all_react]
        pending = []
    print(f"  expanded: {len(cases)} cases × {n_samples} = {len(all_react)} trajectories"
          f" (inflow_target={inflow_target or 'all'}, pending={len(pending)})",
          flush=True)

    max_tokens = thinking_budget + 2560
    top_p, top_k, presence = 0.8, 20, 1.5  # Qwen3.5 production sampling

    async with aiohttp.ClientSession() as session:
        # prelink (qentity injection; plan-contract v2: GTE-ranks the anchor
        # entities + their neighbor relations against the original question —
        # was alphabetical [:3], which anti-sampled the question's axis)
        pl_sem = asyncio.Semaphore(16)

        async def _pl(rc):
            async with pl_sem:
                await rc.prelink(session)

        await asyncio.gather(*[_pl(rc) for rc in react_cases])
        _t_admit = _time_mod.time()
        for rc in react_cases:
            rc._admit_t = _t_admit

        for rnd in range(max_rounds):
            # INFLOW top-up: admit pending trajectories to keep the batch full.
            # Batched (perf audit 2026-08-22): pop the WHOLE gap at once and
            # prelink it concurrently under pl_sem — the old serial per-case
            # await made a 100-trajectory top-up cost 100 × prelink latency.
            while pending:
                n_active = sum(1 for rc in react_cases if rc.is_active)
                if n_active >= inflow_target:
                    break
                batch = pending[:inflow_target - n_active]
                del pending[:len(batch)]
                react_cases.extend(batch)
                await asyncio.gather(*[_pl(rc) for rc in batch])
                _t_top = _time_mod.time()
                for rc in batch:
                    rc._admit_t = _t_top

            active = [rc for rc in react_cases if rc.is_active]
            if not active:
                if pending:
                    continue
                break

            prompts = []
            for rc in active:
                hint = rc.state_aware_hint() + rc.allowed_tools_hint()
                if rc._tool_repeat >= 2:
                    hint = rc.loop_nudge() + "\n" + hint
                msgs = list(rc.messages)
                msgs.append({"role": "user", "content": hint})
                prompts.append(msgs)

            # offline LLM batch (sync — vLLM continuous-batches all active prompts).
            # POLICY env: name of a registered LoRA adapter to sample from
            # (iterated RL — round-2 rollouts use the round-1 trained policy).
            from kgqa.core.utils import phase_timer
            with phase_timer("llm"):
                chats = llm.chat_batch(
                    prompts, thinking_budget=thinking_budget, temperature=temperature,
                    max_tokens=max_tokens, top_p=top_p, top_k=top_k,
                    presence_penalty=presence,
                    model=os.environ.get("POLICY") or None,
                )
            contents = [c.text for c in chats]
            reasoning = [c.reasoning for c in chats]

            # ROUND-LEVEL THREE-PHASE DISPATCH (perf-4, 2026-08-23): replaces the
            # per-case process_turn gather. A for all cases (one serial CPU loop)
            # → every GTE/walk request of the round fires together (the client
            # collectors coalesce them; GTE on the GPU server and the walk lanes
            # in CPU processes overlap on different resources) → C for all cases
            # (one serial CPU loop). Per-case semantics are IDENTICAL to
            # process_turn (see run_round_dispatch in seq_react_loop). The old
            # DISPATCH_CONCURRENCY semaphore bounded concurrent sync-CPU
            # dispatchers interleaving on the event loop — obsolete now that the
            # sync CPU runs in the A/C loops (kept on the ROUND_SCHED=0
            # fallback path only).
            with phase_timer("dispatch"):
                if os.environ.get("ROUND_SCHED", "1") != "0":
                    from kgqa.agent.seq_react_loop import run_round_dispatch
                    await run_round_dispatch(
                        list(zip(active, contents, reasoning)), session)
                else:
                    dsem = asyncio.Semaphore(
                        int(os.environ.get("DISPATCH_CONCURRENCY", "64")))

                    async def _proc(rc, raw, rsn):
                        async with dsem:
                            if not raw:
                                rc.messages.append({"role": "assistant", "content": ""})
                                rc.messages.append({"role": "user",
                                                    "content": rc.allowed_tools_hint()})
                                return
                            await rc.process_turn(session, raw, rsn)

                    await asyncio.gather(*[_proc(rc, raw, rsn)
                                           for rc, raw, rsn in zip(active, contents, reasoning)])

        # BUDGET+1 FINAL TURN (user ruling, 2026-08-26): cases that exhausted
        # the round budget without an accepted answer get ONE extra round
        # whose hint DEMANDS the final answer — replaces silent budget death
        # (all 9 empties in the v34 gate were budget-end no-answer, many
        # after the 2nd-refusal conversion message that the model answered
        # with MORE retrieval instead of an answer call).
        finalists = [rc for rc in react_cases if rc.is_active]
        if finalists:
            print(f"  final-turn +1 for {len(finalists)} cases", flush=True)
            prompts = []
            for rc in finalists:
                hint = ("FINAL TURN (budget extended by one): submit your final "
                        "answer NOW with `tool: answer` from the bindings you "
                        "hold — this is the LAST turn; further retrieval will "
                        "not be executed. " + rc.allowed_tools_hint())
                msgs = list(rc.messages)
                msgs.append({"role": "user", "content": hint})
                prompts.append(msgs)
            from kgqa.core.utils import phase_timer as _pt2
            with _pt2("llm"):
                chats = llm.chat_batch(
                    prompts, thinking_budget=thinking_budget, temperature=temperature,
                    max_tokens=max_tokens, top_p=top_p, top_k=top_k,
                    presence_penalty=presence,
                    model=os.environ.get("POLICY") or None,
                )
            _contents = [c.text for c in chats]
            from kgqa.agent.seq_react_loop import run_round_dispatch as _rrd
            with _pt2("dispatch"):
                await _rrd(list(zip(finalists, _contents, [None] * len(finalists))),
                           session)

            # per-case completion stamps (user metric 2026-08-23: wall time to
            # finish ONE case, not just batch totals — lockstep rounds couple
            # every active case to the round wall, so this needs its own clock)
            _t_rnd = _time_mod.time()
            for rc in active:
                if (rc.done or rc.failed) and getattr(rc, "_done_t", None) is None:
                    rc._done_t = _t_rnd
            done = sum(1 for rc in react_cases if rc.done)
            failed = sum(1 for rc in react_cases if rc.failed)
            print(f"  round {rnd+1}: {len(active)} active → done={done} failed={failed}"
                  f"  [t={time.time()-_T0:.0f}s]",
                  flush=True)

    # extract results + reward
    out = []
    _meta_by_id = {id(rc): m for rc, m in all_react}
    for m, rc in ((_meta_by_id.get(id(rc)), rc) for rc in react_cases):
        gci, ci, gi = m
        # ANSWER FLOOR (plan-contract v2, 2026-08-21): an episode that exhausted
        # rounds with NO accepted answer still has curated evidence — checkpoint
        # bindings / a trapped answer call / the checklist ANSWER line.
        # rescue_terminal_answer recovers it (never overwrites a real answer).
        # The per-call runner already did this (P4); the rollout path was missing
        # it — the Ramble/VP specimen scored empty despite ?attendee bound.
        rc.rescue_terminal_answer()
        if getattr(rc, "_done_t", None) is None:
            rc._done_t = _time_mod.time()      # budget-end stragglers: extraction time
        r = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
        traj = rc.ctx.trajectory
        answer = r.get("llm_answer_str", "") or r.get("llm_answer", "") or ""
        f1 = float(r.get("llm_f1", 0) or 0)
        hit = bool(r.get("llm_hit", False))
        failed = bool(rc.failed)
        n_turns = sum(1 for st in traj if st.get("role") == "assistant")
        n_reject = sum(1 for st in traj
                       if st.get("role") == "tool" and "REJECTED" in (st.get("content") or ""))
        format_ok = (n_reject == 0 and not failed)
        efficient = n_turns <= 8
        reward = round(f1 + 0.1 * format_ok + 0.1 * efficient, 3)
        # structured evidence/pred records for the v0 advantage recomputation
        # (authoritative 'display' mode): FULL evidence set incl. hidden leaves and
        # branch-ref expansions — accumulated at ctx level during dispatch, immune
        # to display truncation; pred = post-expansion answer entities.
        at = getattr(rc.ctx, "accumulated_triples", None) or set()
        ev_ents = set()
        for h, rl, t in at:
            ev_ents.add(str(h)); ev_ents.add(str(t))
        ev_ents.update(str(c) for c in (getattr(rc.ctx, "all_candidates", None) or []))
        out.append({
            "case_id": cases[ci]["id"], "case_idx": gci, "sample_idx": gi,
            "question": cases[ci]["question"], "gold": cases[ci].get("a_entity", []),
            "answer": answer, "f1": round(f1, 3), "hit": hit,
            "failed": failed, "failure_reason": rc.failure_reason,
            "n_turns": n_turns, "n_reject": n_reject,
            "wall_s": round(getattr(rc, "_done_t", 0) - getattr(rc, "_admit_t", 0), 1),
            "format_ok": format_ok, "efficient": efficient,
            "rescued": bool(getattr(rc, "_rescued", False)),
            "reward": reward, "trajectory": traj,
            "evidence_entities": sorted(ev_ents),
            "pred_entities": list(getattr(rc.ctx, "llm_answer_preds", None) or []),
            "result_keys": list(r.keys()),
        })
    # per-case wall distribution (user metric: time to complete ONE case).
    # Lockstep couples every active case to the round wall (llm decode of the
    # whole round + dispatch), so per-case time ≈ turns × round wall even when
    # amortized throughput is seconds/case.
    _walls = sorted(o["wall_s"] for o in out if o.get("wall_s", 0) > 0)
    if _walls:
        _n = len(_walls)
        print(f"  per-case wall: mean={sum(_walls)/_n:.0f}s "
              f"p50={_walls[_n//2]:.0f}s p90={_walls[int(_n*0.9)]:.0f}s "
              f"max={_walls[-1]:.0f}s "
              f"(mean turns={sum(o['n_turns'] for o in out)/len(out):.1f}, "
              f"implied round wall={sum(_walls)/max(sum(o['n_turns'] for o in out),1):.0f}s)",
              flush=True)
    return out


def main():
    split = os.environ.get("SPLIT", "test")
    n_cases = int(os.environ.get("N_CASES", "3"))
    n_samples = int(os.environ.get("N_SAMPLES", "2"))
    temp = float(os.environ.get("TEMP", "0.8"))
    tb = int(os.environ.get("THINK_BUDGET", "1000"))
    max_rounds = int(os.environ.get("MAX_ROUNDS", "16"))
    case_batch = int(os.environ.get("CASE_BATCH", "50"))   # cases per stage (concurrency cap)
    max_num_seqs = int(os.environ.get("MAX_NUM_SEQS", "128"))
    out_path = os.environ.get("OUT", f"/tmp/rollout_{split}_{n_cases}x{n_samples}.json")
    # The rollout is round-synchronized → enable the round-level walk
    # coordinator (adaptive batch window; per-case runners keep the legacy
    # per-call lane path with its WALK_BATCH_WINDOW default of 0).
    os.environ.setdefault("WALK_BATCH_WINDOW", "1.0")

    print(f"═══ offline rollout: {split} {n_cases} cases × {n_samples} samples, temp={temp} "
          f"(stage={case_batch} cases, max_num_seqs={max_num_seqs}) ═══", flush=True)
    cases = _load(split, n_cases)
    print(f"  loaded {len(cases)} cases", flush=True)

    # LLM_MODE=http (user design, 2026-08-22): batch-inject prompts into a
    # PERSISTENT vLLM server instead of spawning an in-process engine — kills
    # the ~2.5-min spawn/compile tax on every run. Server must already be up.
    _pol = os.environ.get("POLICY", "").strip()
    if os.environ.get("LLM_MODE", "").lower() == "http":
        if _pol:
            raise SystemExit("LoRA POLICY requires the in-process engine; "
                             "unset POLICY or LLM_MODE.")
        from kgqa.llm.http_batch import HTTPChatBatch
        llm = HTTPChatBatch(max_num_seqs=max_num_seqs)
        print("  LLM_MODE=http → persistent server (no engine load)", flush=True)
    else:
        print("loading OfflineVLLM ...", flush=True)
        t = time.time()
        _loras = {_pol: f"/zhaoshu/subgraph/checkpoint/{_pol}"} if _pol else None
        llm = OfflineVLLM(max_num_seqs=max_num_seqs, lora_modules=_loras)
        if _pol:
            print(f"  POLICY = {_pol} (LoRA {_loras[_pol]})", flush=True)
        print(f"  loaded in {time.time()-t:.0f}s", flush=True)

    # stage-by-stage: each stage runs the FULL multi-turn rollout for ≤ case_batch
    # cases (× n_samples), then the next stage. Bounds per-round concurrency so
    # decode doesn't thrash (the "case-level ceiling"); LLM is loaded once, reused.
    all_results = []
    # RESUME: OUT already holds incrementally-saved results (a watchdog or a
    # human killed a hung run — e.g. the 2026-08-20 stage-3 walk-pool deadlock).
    # Saves happen only at stage boundaries, so the done-case count is exact.
    done_cases = 0
    if Path(out_path).exists():
        try:
            prev = json.loads(Path(out_path).read_text())
            if prev:
                all_results = prev
                done_cases = len(prev) // n_samples
                print(f"  RESUME: {done_cases} cases already in {out_path}, "
                      f"skipping {done_cases // case_batch} stage(s)", flush=True)
        except Exception as e:
            print(f"  RESUME: unreadable checkpoint ({e}), starting fresh", flush=True)
    t0 = time.time()
    n_stages = (len(cases) + case_batch - 1) // case_batch
    for si in range(n_stages):
        if (si + 1) * case_batch <= done_cases:
            continue  # stage fully covered by the checkpoint
        chunk = cases[si * case_batch:(si + 1) * case_batch]
        print(f"\n── stage {si+1}/{n_stages}: {len(chunk)} cases "
              f"({len(chunk)*n_samples} trajectories) ──", flush=True)
        tc = time.time()
        _inflow = int(os.environ.get("INFLOW_TARGET", "0") or 0)
        res = asyncio.run(rollout(llm, chunk, n_samples, temp, tb, max_rounds,
                                   base_case_idx=si * case_batch,
                                   inflow_target=_inflow or (len(chunk) * n_samples if n_stages == 1 else 0)))
        all_results.extend(res)
        # incremental save (crash-safe checkpointing)
        Path(out_path).write_text(json.dumps(all_results, ensure_ascii=False))
        # phase attribution (perf): llm vs dispatch wall; walk/render/gte are
        # timed INSIDE dispatch (async-serialized, so their sum ≈ dispatch wall
        # only when the 16-semaphore keeps them non-overlapping).
        from kgqa.core.utils import PHASE_TIMES as _PT
        print(f"  phase: llm={_PT['llm']:.0f}s dispatch={_PT['dispatch']:.0f}s "
              f"| rd: A={_PT.get('rd_A', 0):.0f}s B={_PT.get('rd_B', 0):.0f}s "
              f"C={_PT.get('rd_C', 0):.0f}s "
              f"| inside-dispatch: walk={_PT['walk']:.0f}s "
              f"(collect={_PT['walk_collect']:.0f}s wait={_PT['walk_wait']:.0f}s "
              f"exec={_PT['walk_exec']:.0f}s) "
              f"render={_PT['render']:.0f}s gte={_PT['gte']:.0f}s "
              f"(n={_PT['gte_n']:.0f})", flush=True)
        # walk coordinator batch stats (window tuning evidence): singles pay
        # only the first slice; bursts extend to the full window; slots vs
        # reqs-steps = dedup+memo savings.
        from kgqa.agent import seq_tools as _st
        _ws = _st._WALK_BATCH_STATS
        if _ws["batches"]:
            print(f"  walk-batch: {_ws['batches']} flushes "
                  f"(single={_ws['single']} burst={_ws['burst']}) "
                  f"reqs={_ws['reqs']} slots={_ws['slots']} "
                  f"memo={_ws['memo_hits']} dedup={_ws['dedup_shares']} "
                  f"ipc={_ws['ipc_bytes']/1e6:.0f}MB "
                  f"collect={_ws['collect_s']:.1f}s span={_ws['burst_span_s']:.1f}s",
                  flush=True)
            for _k in _ws:
                if isinstance(_ws[_k], float):
                    _ws[_k] = 0.0
                else:
                    _ws[_k] = 0
        for _k in _PT:
            _PT[_k] = 0.0
        print(f"  stage {si+1} done in {time.time()-tc:.0f}s "
              f"({len(all_results)} trajectories total)", flush=True)
    dt = time.time() - t0
    # summary
    results = all_results
    n = len(results)
    if n == 0:
        print("  no trajectories produced", flush=True)
        return
    hits = sum(r["hit"] for r in results)
    mean_f1 = sum(r["f1"] for r in results) / n
    mean_reward = sum(r["reward"] for r in results) / n
    mean_turns = sum(r["n_turns"] for r in results) / n
    n_failed = sum(r["failed"] for r in results)
    # group stats (per case reward spread → GRPO signal)
    from collections import defaultdict
    by_case = defaultdict(list)
    for r in results:
        by_case[r["case_idx"]].append(r["reward"])
    nonzero_spread = sum(1 for v in by_case.values() if max(v) - min(v) > 0.01)

    print(f"\n═══ done: {n} trajectories in {dt:.0f}s ({dt/n:.1f}s/traj, "
          f"{dt/max(n_cases,1):.1f}s/case×{n_samples}) ═══", flush=True)
    print(f"  hit={hits}/{n}={hits/n:.1%}  mean_f1={mean_f1:.3f}  mean_reward={mean_reward:.3f}")
    print(f"  mean_turns={mean_turns:.1f}  failed={n_failed}/{n}")
    print(f"  GRPO signal: {nonzero_spread}/{len(by_case)} cases have intra-group reward spread")
    print(f"  → {out_path}", flush=True)
    # dump one trajectory's result_keys for verification
    if results:
        print(f"  result_dict keys: {results[0]['result_keys']}", flush=True)


if __name__ == "__main__":
    main()
