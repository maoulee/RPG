#!/usr/bin/env python3
"""A/B test: thinking_token_budget on the react content-only path.

Runs the SAME N cases under 3 thinking-budget settings and prints a comparison
table. Goal: see whether letting the model <think> (with a hard vLLM-side cap)
changes gt_hit / llm_hit on the react path.

Settings (set as env at runtime):
  - budget=0    : thinking OFF (current production default)        [control]
  - budget=512  : short reasoning                                 [test]
  - budget=2048 : longer reasoning                                [test]

max_tokens is raised to 3072 so reasoning (≤budget) can't starve the tool-JSON
output (the original probe failure cause).

Usage:
    # WebQSP
    python scripts/ab_thinking_budget.py --dataset webqsp            # 100 cases
    python scripts/ab_thinking_budget.py --dataset webqsp --end 20   # quick

    # CWQ
    python scripts/ab_thinking_budget.py --dataset cwq
"""
import argparse
import asyncio
import json
import os
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from kgqa.agent.react_loop import run_react_case

# When thinking is ON, the reasoning tokens come out of max_tokens, so raise it.
MAX_TOKENS_THINKING = 3072
MAX_TOKENS_BASELINE = 1024  # unchanged for the no-thinking control

SETTINGS = [
    ("budget000", 0,    MAX_TOKENS_BASELINE),
    ("budget512", 512,  MAX_TOKENS_THINKING),
    ("budget2048", 2048, MAX_TOKENS_THINKING),
]


def load_cases(dataset: str, start: int, end: int):
    """Load (samples, case_id_fn) for the given dataset."""
    if dataset == "webqsp":
        import scripts.run_webqsp_agent_eval as ev
        samples = pickle.loads(ev.WEBQSP_PKL.read_bytes())[start:end]
        return samples, ev.make_case_id
    elif dataset == "cwq":
        CWQ_PKL = Path("/zhaoshu/subgraph/data/cwq_processed/"
                       "test_literal_and_language_fixed_path_completed.pkl")

        def cwq_cid(sample):
            return sample.get("id") or sample.get("question_id", "")
        samples = pickle.loads(CWQ_PKL.read_bytes())[start:end]
        return samples, cwq_cid
    raise ValueError(f"unknown dataset {dataset}")


async def run_one_setting(label: str, budget: int, max_tokens: int,
                          samples, cid_fn, parallel: int, out_dir: str) -> list:
    """Run all samples under one thinking-budget setting. Returns results list."""
    os.environ["KGQA_THINKING_TOKEN_BUDGET"] = str(budget)
    # Reload client so module-level constants pick up the env change.
    import importlib
    import kgqa.llm.client as client
    importlib.reload(client)

    class Args:
        agent_max_iters = 16
        agent_max_tokens = max_tokens
        agent_temperature = 0.3

    print(f"\n{'='*70}", flush=True)
    print(f"=== Setting {label}: thinking_token_budget={budget} "
          f"max_tokens={max_tokens} ===", flush=True)
    print(f"{'='*70}", flush=True)

    sem = asyncio.Semaphore(parallel)
    t0 = time.perf_counter()

    async def one(session, sample, idx):
        cid = cid_fn(sample)
        pr = {"case_id": cid, "question": sample.get("question", ""),
              "gt": sample.get("a_entity", [])}
        async with sem:
            try:
                r = await run_react_case(session, sample, pr, idx, Args())
            except Exception as e:
                r = {"agent_failed": True, "agent_failure_reason": f"exc: {e}",
                     "llm_hit": False, "llm_f1": 0.0, "gt_answers": pr["gt"],
                     "case_num": idx, "question": pr["question"]}
        r["case_id"] = cid
        return r

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[
            one(session, s, i + 1) for i, s in enumerate(samples)
        ])
    results.sort(key=lambda x: x.get("case_num", 0))
    dt = time.perf_counter() - t0

    n = len(results)
    llm_hit = sum(1 for r in results if r.get("llm_hit"))
    gt_hit = sum(1 for r in results if r.get("gt_hit"))
    failed = sum(1 for r in results if r.get("agent_failed"))
    f1 = sum(r.get("llm_f1", 0) for r in results) / n if n else 0
    print(f"\n--- {label}: llm_hit={llm_hit}/{n} ({100*llm_hit/n:.1f}%) | "
          f"gt_hit={gt_hit}/{n} ({100*gt_hit/n:.1f}%) | failed={failed} | "
          f"mean_f1={f1:.4f} | {dt:.0f}s ---", flush=True)

    # Persist per-setting results for later trajectory inspection.
    out = Path(f"{out_dir}/{label}_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return results


def print_comparison(all_results: dict):
    print(f"\n{'='*70}\n=== A/B COMPARISON ===\n{'='*70}")
    print(f"{'setting':<14} {'llm_hit':>10} {'gt_hit':>10} {'failed':>9} "
          f"{'mean_f1':>9}")
    print("-" * 56)
    base_llm = None
    for label, results in all_results.items():
        n = len(results)
        lh = sum(1 for r in results if r.get("llm_hit"))
        gh = sum(1 for r in results if r.get("gt_hit"))
        fl = sum(1 for r in results if r.get("agent_failed"))
        f1 = sum(r.get("llm_f1", 0) for r in results) / n if n else 0
        delta = ""
        if base_llm is not None and label != "budget000":
            d = lh - base_llm
            delta = f" ({'+' if d>=0 else ''}{d})"
        print(f"{label:<14} {lh:>7}/{n:<3} {gh:>7}/{n:<3} {fl:>9} "
              f"{f1:>9.4f}{delta}")
        if label == "budget000":
            base_llm = lh

    # Per-case delta vs control
    print(f"\n--- per-case llm_hit movement vs budget000 ---")
    base = {r["case_id"]: r.get("llm_hit", False)
            for r in all_results["budget000"]}
    for label, results in all_results.items():
        if label == "budget000":
            continue
        imp = reg = 0
        for r in results:
            cid = r["case_id"]
            if cid in base:
                if r.get("llm_hit") and not base[cid]:
                    imp += 1
                elif (not r.get("llm_hit")) and base[cid]:
                    reg += 1
        print(f"  {label}: improved +{imp}, regressed -{reg}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["webqsp", "cwq"], default="webqsp")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=100)
    ap.add_argument("--parallel", type=int, default=16)
    args = ap.parse_args()

    samples, cid_fn = load_cases(args.dataset, args.start, args.end)
    out_dir = f"reports/{args.dataset}_think_ab"
    print(f"Loaded {len(samples)} {args.dataset} cases "
          f"[{args.start}:{args.end}] -> {out_dir}", flush=True)

    all_results = {}
    for label, budget, max_tokens in SETTINGS:
        results = await run_one_setting(label, budget, max_tokens, samples,
                                        cid_fn, args.parallel, out_dir)
        all_results[label] = results

    print_comparison(all_results)
    # Save comparison summary too
    Path(f"{out_dir}/comparison.json").write_text(
        json.dumps(all_results, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
