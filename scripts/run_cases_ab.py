#!/usr/bin/env python3
"""Run agent on explicit case_ids for prompt A/B — bypasses the wrong-type mask
(so masked cases like Libya/WebQTest-590 can still be run).

Usage:
  python scripts/run_cases_ab.py \
    --case-ids WebQTest-590,WebQTrn-372,WebQTrn-2286,WebQTrn-2209,WebQTest-12,WebQTrn-634 \
    --output reports/ab_new/results.json

case-ids match by prefix (so "WebQTest-590" matches the full WebQTest-590_<hash>).
Reuses run_react_case from react_loop — same code path as run_agent_batch, only
the case selection differs (explicit ids, no mask filter).
"""
import asyncio, json, pickle, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import aiohttp
from kgqa.core.config import DEFAULT_CWQ
from kgqa.agent.react_loop import run_react_case as run_agent_case
import argparse

PILOT = "reports/cwq_gte_bridge_100/results.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case-ids", default="",
                   help="comma-separated case_ids or prefixes (e.g. WebQTest-590,WebQTrn-372)")
    p.add_argument("--output", required=True)
    p.add_argument("--parallel", type=int, default=8)
    p.add_argument("--runs", type=int, default=1,
                   help="run each case N times (multi-sampling) to measure variance")
    p.add_argument("--start", type=int, default=None, help="pilot slice start (alt to --case-ids)")
    p.add_argument("--end", type=int, default=None, help="pilot slice end")
    args = p.parse_args()

    pilot_rows = json.loads(Path(PILOT).read_text())
    if args.start is not None or args.end is not None:
        sl = pilot_rows[args.start or 0:args.end]
        prefixes = [pr["case_id"] for pr in sl]  # full case_ids
    else:
        prefixes = [c.strip() for c in args.case_ids.split(",") if c.strip()]
    if isinstance(pilot_rows, dict):
        pilot_rows = pilot_rows.get("results", [])
    samples = pickle.loads(Path(DEFAULT_CWQ).read_bytes())
    sample_map = {}
    for s in samples:
        sid = s.get("id") or s.get("question_id")
        if sid:
            sample_map[sid] = s

    base_cases = []
    for idx, pr in enumerate(pilot_rows):
        cid = pr.get("case_id", "")
        if any(cid.startswith(pref) or pref in cid for pref in prefixes):
            sample = sample_map.get(cid)
            if not sample:
                for s in samples:
                    if s.get("question", "") == pr.get("question", ""):
                        sample = s
                        break
            if sample:
                base_cases.append((sample, pr, idx + 1))

    # replicate for multi-sampling
    cases = []
    for run_i in range(args.runs):
        for sample, pr, idx in base_cases:
            cases.append((sample, pr, idx, run_i))

    matched = [c[1]["case_id"].split("_")[0] for c in base_cases]
    print(f"Matched {len(base_cases)} cases × {args.runs} runs = {len(cases)} runs: {matched}", flush=True)
    if not base_cases:
        print("No cases matched. Check --case-ids prefixes.", flush=True)
        return

    class A:
        agent_max_iters = 16
        agent_max_tokens = 1024
        agent_temperature = 0.3

    sem = asyncio.Semaphore(args.parallel)

    async def run():
        results = []

        async def one(session, sample, pr, idx, run_i):
            async with sem:
                r = await run_agent_case(session, sample, pr, idx, A())
                r["run"] = run_i
                results.append(r)
                ans = str(r.get("llm_answer", ""))[:55]
                print(f"  [{idx}.r{run_i}] {pr['case_id'].split('_')[0]:14} "
                      f"f1={r.get('llm_f1', 0):.2f} hit={r.get('llm_hit')} ans={ans}", flush=True)

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[one(session, s, p, i, ri) for s, p, i, ri in cases])

        # aggregate per case
        from collections import defaultdict
        by_case = defaultdict(list)
        for r in results:
            by_case[r["case_id"].split("_")[0]].append(r)
        print("\n=== per-case summary (multi-sample) ===", flush=True)
        for cid, rs in by_case.items():
            f1s = [r.get("llm_f1", 0) for r in rs]
            hits = [int(r.get("llm_hit", False)) for r in rs]
            ans_set = [str(r.get("llm_answer", ""))[:45] for r in rs]
            print(f"  {cid:14} n={len(rs)} f1={sum(f1s)/len(f1s):.2f} "
                  f"(min {min(f1s):.2f}/max {max(f1s):.2f}) hit_rate={sum(hits)}/{len(rs)}", flush=True)
            for a in ans_set:
                print(f"      - {a}", flush=True)

        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\nwrote {len(results)} -> {args.output}", flush=True)

    asyncio.run(run())


if __name__ == "__main__":
    main()
