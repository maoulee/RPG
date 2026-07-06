#!/usr/bin/env python3
"""ReAct batch agent entry point.

Usage:
    python scripts/run_react.py \
        --pilot-results reports/cwq_matfix_100/results.json \
        --cwq-pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \
        --output-dir reports/react_test --limit 5

    # With 9B model:
    KGQA_LLM_MODEL="Qwen3.5-9B" python scripts/run_react.py ...
"""
import sys
import os
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import asyncio
import argparse
import json
import pickle
from pathlib import Path

from kgqa.core.config import DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.agent.react_loop import run_react_batch


def _load_cases(args):
    pilot_rows = json.loads(Path(args.pilot_results).read_text())
    samples = pickle.loads(Path(args.cwq_pkl).read_bytes())
    sample_map = {}
    for s in samples:
        sid = s.get("id") or s.get("question_id")
        if sid:
            sample_map[sid] = s

    masked_ids = set()
    if args.mask_wrong_type and MASK_WRONG_TYPE and Path(MASK_WRONG_TYPE).exists():
        masked_ids = set(json.loads(Path(MASK_WRONG_TYPE).read_text()))

    cases = []
    for idx, pr in enumerate(pilot_rows[:args.limit], 1):
        sample = sample_map.get(pr["case_id"])
        if not sample:
            for s in samples:
                if s.get("question", "") == pr.get("question", ""):
                    sample = s
                    break
        if not sample:
            print(f"SKIP: {pr['case_id']}")
            continue
        if pr["case_id"] in masked_ids:
            continue
        cases.append((sample, pr, idx))
    return cases


def main():
    parser = argparse.ArgumentParser(description="ReAct batch agent runner")
    parser.add_argument("--pilot-results", default="reports/cwq_matfix_100/results.json")
    parser.add_argument("--cwq-pkl", default=str(DEFAULT_CWQ))
    parser.add_argument("--output-dir", default="reports/react_test")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mask-wrong-type", default=str(MASK_WRONG_TYPE))
    parser.add_argument("--agent-max-iters", type=int, default=16)
    parser.add_argument("--agent-max-tokens", type=int, default=1024)
    parser.add_argument("--batch-chunk", type=int, default=25)
    args = parser.parse_args()

    cases = _load_cases(args)
    print(f"Loaded {len(cases)} cases")
    asyncio.run(run_react_batch(cases, args, args.output_dir))


if __name__ == "__main__":
    main()
