#!/usr/bin/env python3
"""KGQA native tool-calling agent entry point.

Usage:
    python scripts/run_agent.py \
        --pilot-results reports/webqsp_full_test/results.json \
        --cwq-pkl data/webqsp/test_fixed_path_completed.pkl \
        --output-dir reports/agent_webqsp_test --limit 5 --parallel 4

Loads pilot/sample/mask exactly like run_pipeline.py, then runs
kgqa.agent.loop.run_agent_mode (the tool-calling agent). The stage pipeline
(run_stage_mode) stays untouched and remains the baseline.
"""

import sys
import os
# Ensure project root is on sys.path for kgqa imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import asyncio
import argparse
import json
import pickle
from pathlib import Path

from kgqa.core.config import DEFAULT_PILOT, DEFAULT_CWQ, DEFAULT_OUTPUT, MASK_WRONG_TYPE
from kgqa.agent.loop import run_agent_mode


def _load_cases(args):
    """Load (sample, pilot_row, idx) tuples — same shape as run_pipeline.py."""
    pilot_rows = json.loads(Path(args.pilot_results).read_text())
    samples = pickle.loads(Path(args.cwq_pkl).read_bytes())
    sample_map = {}
    for s in samples:
        if "id" in s:
            sample_map[s["id"]] = s
        elif "question_id" in s:
            sample_map[s["question_id"]] = s

    masked_ids = set()
    if MASK_WRONG_TYPE.exists():
        masked_ids = set(json.loads(MASK_WRONG_TYPE.read_text()))
        print(f"  Masked {len(masked_ids)} wrong-type cases")

    cases_to_run = []
    for idx, pilot_row in enumerate(pilot_rows[:args.limit], 1):
        sample = sample_map.get(pilot_row["case_id"])
        if not sample:
            for s in samples:
                if s.get("question", "") == pilot_row["question"]:
                    sample = s
                    break
        if not sample:
            print(f"SKIP: {pilot_row['case_id']}")
            continue
        if pilot_row["case_id"] in masked_ids:
            continue
        cases_to_run.append((sample, pilot_row, idx))
    return cases_to_run


async def amain():
    parser = argparse.ArgumentParser(description="KGQA native tool-calling agent runner")
    parser.add_argument("--pilot-results", default=str(DEFAULT_PILOT))
    parser.add_argument("--cwq-pkl", default=str(DEFAULT_CWQ))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--parallel", type=int, default=4,
                        help="Concurrent agent cases (default 4, max 32)")
    parser.add_argument("--dump-trajectories", action="store_true",
                        help="Write per-case tool-call trajectory files")
    # Agent loop knobs
    parser.add_argument("--agent-max-iters", type=int, default=16,
                        help="Max tool-call turns per case before marking failed "
                             "(16+ recommended for select→multi-expand→answer)")
    parser.add_argument("--agent-max-tokens", type=int, default=1024)
    parser.add_argument("--agent-temperature", type=float, default=0.3)
    args = parser.parse_args()

    # Honor the same env-driven model/endpoint config as the stage client.
    for var in ("KGQA_MODEL_NAME", "KGQA_LLM_API_URL", "GTE_API_URL"):
        if os.getenv(var):
            print(f"  env {var} = {os.getenv(var)}")
    print(f"  Model: {os.getenv('KGQA_MODEL_NAME', '(default from client)')}")

    cases_to_run = _load_cases(args)
    print(f"  Loaded {len(cases_to_run)} cases")
    await run_agent_mode(cases_to_run, args)


if __name__ == "__main__":
    asyncio.run(amain())
