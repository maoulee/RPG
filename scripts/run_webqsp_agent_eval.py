#!/usr/bin/env python3
"""Run the ReAct agent (hybrid LoRA) on a slice of WebQSP test cases and
write results.json with full agent_trajectory, for downstream stage-failure
diagnosis via scripts/agent_stage_scorer.py.

Uses the content-only ``tool:`` protocol (react_loop.run_react_case) — the SAME
format the model was trained on — NOT native tool_calls. This keeps the model's
CoT reasoning (which training data has 100%) intact during serving.

case_id alignment: pkl id "WebQTest-N" maps to baseline case_id
"WebQTest-N_<md5(question)[:20]>" so results can be joined against
reports/webqsp_full_test (the stage-pipeline baseline).

Usage:
    # smoke (5 cases) to validate the chain end-to-end
    python scripts/run_webqsp_agent_eval.py --start 0 --end 5 \
        --output reports/webqsp_react_hybrid_smoke/results.json

    # full 100-case eval
    python scripts/run_webqsp_agent_eval.py --start 0 --end 100 \
        --output reports/webqsp_react_hybrid_100/results.json
"""
import asyncio
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
import argparse

from kgqa.agent.react_loop import run_react_case

WEBQSP_PKL = Path("/zhaoshu/subgraph/data/webqsp/test_fixed_path_completed.pkl")
BASELINE = Path("/zhaoshu/subgraph/reports/webqsp_full_test/results.json")


def make_case_id(sample):
    """Reproduce the pipeline's case_id = base + md5(question)[:20]."""
    base = sample.get("id") or sample.get("question_id") or ""
    q = sample.get("question", "")
    return f"{base}_{hashlib.md5(q.encode()).hexdigest()[:20]}"


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

    samples = pickle.loads(WEBQSP_PKL.read_bytes())
    cases = samples[args.start:args.end]
    print(f"Loaded {len(samples)} WebQSP samples, running [{args.start}:{args.end}] = {len(cases)} cases", flush=True)

    # baseline lookup for delta reporting (optional, not required for scoring)
    base_map = {}
    if BASELINE.exists():
        for r in json.loads(BASELINE.read_text()):
            base_map[r["case_id"]] = {
                "b_llm_hit": r.get("llm_hit"),
                "b_llm_f1": r.get("llm_f1", 0),
                "b_gt_hit": r.get("gt_hit"),
            }
        print(f"  baseline joined: {len(base_map)} cases", flush=True)

    sem = asyncio.Semaphore(args.parallel)

    async def run():
        results = []

        async def one(session, sample, idx):
            cid = make_case_id(sample)
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
                bf = b.get("b_llm_f1")
                flag = ""
                if bf is not None:
                    if r.get("llm_hit") and not b.get("b_llm_hit"):
                        flag = " <IMPROVED>"
                    elif (not r.get("llm_hit")) and b.get("b_llm_hit"):
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
                   base_map[r["case_id"]].get("b_llm_hit")]
            imp = [r for r in joined if r.get("llm_hit") and
                   not base_map[r["case_id"]].get("b_llm_hit")]
            print(f"  vs baseline: {len(joined)} joined | "
                  f"regressed={len(reg)} | improved={len(imp)}", flush=True)

    await run()


if __name__ == "__main__":
    asyncio.run(main())
