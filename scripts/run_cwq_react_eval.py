#!/usr/bin/env python3
"""Run the ReAct agent (hybrid LoRA) on a slice of CWQ cases and write
results.json with full agent_trajectory, mirroring run_webqsp_agent_eval.py.

case_id alignment: CWQ pkl already stores "WebQTest-N_<md5>" style ids that
match reports/cwq_full_test (the stage-pipeline baseline, scored by gt_hit).
CWQ baseline has no llm_f1 (stage-pipeline only records gt_hit), so delta
reporting uses gt_hit.

Usage:
    # smoke (5 cases)
    python scripts/run_cwq_react_eval.py --start 0 --end 5 \
        --output reports/cwq_react_smoke/results.json

    # 100-case eval
    python scripts/run_cwq_react_eval.py --start 0 --end 100 \
        --output reports/cwq_gte_bridge_100/results.json
"""
import asyncio
import json
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
import argparse

from kgqa.agent.react_loop import run_react_case

CWQ_PKL = Path("/zhaoshu/subgraph/data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl")
BASELINE = Path("/zhaoshu/subgraph/reports/cwq_full_test/results.json")


class Args:
    """Default agent run params (mirrors run_agent_batch.py)."""
    agent_max_iters = 16
    agent_max_tokens = 1024
    agent_temperature = 0.3


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=100)
    ap.add_argument("--output", required=True)
    ap.add_argument("--parallel", type=int, default=16)
    args = ap.parse_args()

    samples = pickle.loads(CWQ_PKL.read_bytes())
    cases = samples[args.start:args.end]
    print(f"Loaded {len(samples)} CWQ samples, running [{args.start}:{args.end}] = {len(cases)} cases", flush=True)

    # baseline lookup for delta reporting (CWQ baseline scored by gt_hit)
    base_map = {}
    if BASELINE.exists():
        for r in json.loads(BASELINE.read_text()):
            base_map[r["case_id"]] = {
                "b_gt_hit": r.get("gt_hit", False),
            }
        print(f"  baseline joined: {len(base_map)} cases", flush=True)

    sem = asyncio.Semaphore(args.parallel)

    async def run():
        results = []

        async def one(session, sample, idx):
            cid = sample.get("id") or sample.get("question_id", "")
            pilot_row = {
                "case_id": cid,
                "question": sample.get("question", ""),
                "gt": sample.get("a_entity", []),
            }
            async with sem:
                try:
                    r = await run_react_case(session, sample, pilot_row, idx, Args())
                except Exception as e:
                    r = {"case_id": cid, "question": pilot_row["question"],
                         "agent_failed": True, "agent_failure_reason": f"exc: {e}",
                         "llm_hit": False, "llm_f1": 0.0,
                         "gt_answers": pilot_row["gt"], "case_num": idx}
                r["case_id"] = cid  # ensure aligned id
                results.append(r)
                b = base_map.get(cid, {})
                flag = ""
                if "b_gt_hit" in b:
                    if r.get("llm_hit") and not b.get("b_gt_hit"):
                        flag = " <IMPROVED>"
                    elif (not r.get("llm_hit")) and b.get("b_gt_hit"):
                        flag = " <REGRESSED>"
                print(f"  [{idx}] f1={r.get('llm_f1',0):.2f} "
                      f"{'OK' if r.get('llm_hit') else 'MISS'}"
                      f"{flag} {r.get('question','')[:40]}", flush=True)

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[one(session, s, i + 1)
                                   for i, s in enumerate(cases)])
        results.sort(key=lambda x: x.get("case_num", 0))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        json.dump(results, open(args.output, "w"), indent=2, ensure_ascii=False)
        n = len(results)
        hit = sum(1 for r in results if r.get("llm_hit"))
        f1 = sum(r.get("llm_f1", 0) for r in results) / n if n else 0
        gt = sum(1 for r in results if r.get("gt_hit"))
        failed = sum(1 for r in results if r.get("agent_failed"))
        print(f"\n=== {n} cases | llm_hit={hit}/{n}={hit/n:.3f} | "
              f"mean_f1={f1:.4f} | gt_hit(retrieval)={gt}/{n}={gt/n:.3f} | "
              f"agent_failed={failed} ===", flush=True)
        if base_map:
            joined = [r for r in results if r["case_id"] in base_map]
            reg = [r for r in joined if (not r.get("llm_hit")) and
                   base_map[r["case_id"]].get("b_gt_hit")]
            imp = [r for r in joined if r.get("llm_hit") and
                   not base_map[r["case_id"]].get("b_gt_hit")]
            print(f"  vs baseline: {len(joined)} joined | "
                  f"regressed={len(reg)} | improved={len(imp)}", flush=True)

    await run()


if __name__ == "__main__":
    asyncio.run(main())
