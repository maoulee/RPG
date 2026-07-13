#!/usr/bin/env python3
"""Eval the trained LoRA on the 45 held-out cases.

Runs the 4-tool ReAct agent on the held-out case_ids (greedy), model = the LoRA
module served by vLLM (set LLM_MODEL / KGQA_MODEL_NAME = the --lora-modules name,
e.g. routed256). Scores llm_f1 / llm_hit vs the base-model baseline.

Base baseline on these 45 (multi-sample mean, from full_sample_3k): F1 0.7425.

Usage:
  LLM_MODEL=routed256 KGQA_MODEL_NAME=routed256 \
    python scripts/eval_heldout.py --output reports/eval_routed256_heldout.jsonl
"""
import asyncio, json, pickle, os, sys, argparse, statistics
from pathlib import Path
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kgqa.core.config import DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.agent.react_loop import run_react_case as run_agent_case


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--heldout", default="data/offline_grpo/full3k_split/heldout.jsonl")
    p.add_argument("--output", default="reports/eval_routed256_heldout.jsonl")
    p.add_argument("--parallel", type=int, default=16)
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--temp", type=float, default=0.0, help="greedy=0")
    args = p.parse_args()

    held_ids = set(json.loads(l)["case_id"].split("_")[0]
                   for l in open(args.heldout) if l.strip())
    samples = pickle.loads(Path(DEFAULT_CWQ).read_bytes())
    masked = set()
    if MASK_WRONG_TYPE and Path(MASK_WRONG_TYPE).exists():
        masked = set(json.loads(Path(MASK_WRONG_TYPE).read_text()))
    # test-pkl ids carry a per-sample hash (WebQTest-832_<hash>); match on the
    # base id and take ONE sample per held-out case.
    pool, seen = [], set()
    for s in samples:
        base = (s.get("id", "") or "").split("_")[0]
        if base in held_ids and base not in seen \
                and s.get("id") not in masked and s.get("a_entity"):
            pool.append(s); seen.add(base)
    print(f"held-out cases to eval: {len(pool)} (model={os.environ.get('KGQA_MODEL_NAME','Qwen3.5-9B')})")

    cases = []
    for run_i in range(args.runs):
        for i, s in enumerate(pool):
            pr = {"case_id": s["id"], "question": s["question"], "gt_answers": s["a_entity"]}
            cases.append((s, pr, i + 1, run_i))

    class A:
        agent_max_iters = 16
        agent_max_tokens = 1024
        agent_temperature = args.temp

    sem = asyncio.Semaphore(args.parallel)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out = open(args.output, "w")
    done = [0]

    async def run():
        async def one(session, sample, pr, idx, run_i):
            async with sem:
                try:
                    r = await run_agent_case(session, sample, pr, idx, A())
                except Exception as e:
                    r = {"case_id": pr["case_id"], "error": str(e)[:200],
                         "llm_f1": 0.0, "llm_hit": False, "agent_failed": True}
                r["run"] = run_i
                async with asyncio.Lock():
                    out.write(json.dumps(r, ensure_ascii=False) + "\n"); out.flush()
                    done[0] += 1
                    if done[0] % 5 == 0:
                        print(f"  {done[0]}/{len(cases)} done", flush=True)
        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[one(session, s, p, i, ri) for s, p, i, ri in cases])
    asyncio.run(run())
    out.close()

    rs = [json.loads(l) for l in open(args.output) if l.strip()]
    valid = [r for r in rs if not r.get("agent_failed")]
    f1 = [r.get("llm_f1", 0) or 0 for r in valid]
    hit = [1 if r.get("llm_hit") else 0 for r in valid]
    print(f"\n=== {os.environ.get('KGQA_MODEL_NAME','Qwen3.5-9B')} on {len(valid)} held-out (greedy) ===")
    print(f"  mean llm_f1 = {statistics.mean(f1):.4f}   llm_hit = {sum(hit)/len(hit):.4f}")
    print(f"  (base multi-sample baseline = 0.7425; full-342 base = 0.703)")
    print(f"  failed: {len(rs)-len(valid)}")


if __name__ == "__main__":
    main()
