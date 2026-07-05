#!/usr/bin/env python3
"""Run agent on a slice of cases [start:end] and write results.
Usage: python scripts/run_agent_batch.py --start 0 --end 25 --output-dir reports/cwq_dedup_b1
"""
import asyncio, json, pickle, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import aiohttp
from kgqa.core.config import DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.agent.react_loop import run_react_case as run_agent_case
import argparse

PILOT = "reports/cwq_gte_bridge_100/results.json"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=25)
    p.add_argument("--output", required=True)
    p.add_argument("--parallel", type=int, default=16)
    args = p.parse_args()

    pilot_rows = json.loads(Path(PILOT).read_text())
    samples = pickle.loads(Path(DEFAULT_CWQ).read_bytes())
    sample_map = {}
    for s in samples:
        sid = s.get("id") or s.get("question_id")
        if sid: sample_map[sid] = s
    masked = set()
    if MASK_WRONG_TYPE and Path(MASK_WRONG_TYPE).exists():
        masked = set(json.loads(Path(MASK_WRONG_TYPE).read_text()))

    cases = []
    for idx, pr in enumerate(pilot_rows[args.start:args.end], args.start):
        sample = sample_map.get(pr["case_id"])
        if not sample:
            for s in samples:
                if s.get("question", "") == pr.get("question", ""):
                    sample = s; break
        if sample and pr["case_id"] not in masked:
            cases.append((sample, pr, idx + 1))

    print(f"Running {len(cases)} cases [{args.start}:{args.end}]", flush=True)

    class A:
        agent_max_iters = 16; agent_max_tokens = 1024; agent_temperature = 0.3

    sem = asyncio.Semaphore(args.parallel)

    async def run():
        results = []
        async def one(session, sample, pr, idx):
            async with sem:
                r = await run_agent_case(session, sample, pr, idx, A())
                results.append(r)
                print(f"  [{idx}] f1={r.get('llm_f1',0):.2f} {r.get('question','')[:40]}", flush=True)
        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[one(session, s, p, i) for s, p, i in cases])
        results.sort(key=lambda x: x.get("case_num", 0))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        json.dump(results, open(args.output, "w"), indent=2, ensure_ascii=False)
        n = len(results)
        f1 = sum(r.get("llm_f1", 0) for r in results) / n if n else 0
        print(f"\n=== {n} cases, mean f1={f1:.4f} ===", flush=True)

    asyncio.run(run())

if __name__ == "__main__":
    main()
