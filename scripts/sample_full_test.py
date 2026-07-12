#!/usr/bin/env python3
"""Large-scale multi-sampling from full test pkl (3531 cases).
Random N cases × R runs, high parallelism (vLLM batch). Incremental jsonl output
(crash-resilient: each result written immediately).

Usage:
  python scripts/sample_full_test.py --n-cases 300 --runs 4 \
    --output data/offline_grpo/full_sample.jsonl --parallel 48
"""
import asyncio, json, pickle, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import aiohttp
from kgqa.core.config import DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.agent.react_loop import run_react_case as run_agent_case
import argparse

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n-cases", type=int, default=300)
    p.add_argument("--runs", type=int, default=4)
    p.add_argument("--output", required=True)
    p.add_argument("--parallel", type=int, default=48)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start", type=int, default=0, help="offset into shuffled pool (batched sampling)")
    args = p.parse_args()

    samples = pickle.loads(Path(DEFAULT_CWQ).read_bytes())
    masked = set()
    if MASK_WRONG_TYPE and Path(MASK_WRONG_TYPE).exists():
        masked = set(json.loads(Path(MASK_WRONG_TYPE).read_text()))
    pool = [s for s in samples if s.get("id") and s.get("id") not in masked and s.get("a_entity")]
    random.seed(args.seed)
    random.shuffle(pool)
    selected = pool[args.start:args.start + args.n_cases]

    base_cases = []
    for i, s in enumerate(selected):
        pr = {"case_id": s["id"], "question": s["question"], "gt_answers": s["a_entity"]}
        base_cases.append((s, pr, i + 1))

    cases = []
    for run_i in range(args.runs):
        for sample, pr, idx in base_cases:
            cases.append((sample, pr, idx, run_i))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    # fresh file
    out.write_text("")
    print(f"Sampling {len(base_cases)} cases × {args.runs} = {len(cases)} runs "
          f"(parallel={args.parallel}, seed={args.seed}, start={args.start})", flush=True)

    class A:
        agent_max_iters = 16
        agent_max_tokens = 1024
        agent_temperature = 0.3

    sem = asyncio.Semaphore(args.parallel)
    done = [0]
    lock = asyncio.Lock()

    async def run():
        async def one(session, sample, pr, idx, run_i):
            async with sem:
                try:
                    r = await run_agent_case(session, sample, pr, idx, A())
                except Exception as e:
                    r = {"case_id": pr["case_id"], "run": run_i, "error": str(e)[:200],
                         "question": pr["question"], "gt_answers": pr["gt_answers"]}
                r["run"] = run_i
                # incremental flush (crash-resilient)
                async with lock:
                    with open(out, "a") as f:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    done[0] += 1
                    if done[0] % 50 == 0:
                        print(f"  {done[0]}/{len(cases)} done "
                              f"({100*done[0]/len(cases):.0f}%)", flush=True)

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[one(session, s, p, i, ri) for s, p, i, ri in cases])

    asyncio.run(run())
    print(f"\nDone. {done[0]}/{len(cases)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
