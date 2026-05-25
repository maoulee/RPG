#!/usr/bin/env python3
"""KGQA Pipeline entry point.

Usage:
    python scripts/run_pipeline.py --mode stage --limit 50 --reason-style v2 --skip-ner \
        --pilot-results reports/27b_50case_test/results.json \
        --output reports/v2_50case_test
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
import time
from pathlib import Path

from kgqa.core.config import (
    DEFAULT_PILOT, DEFAULT_CWQ, MASK_WRONG_TYPE, DEFAULT_OUTPUT,
    REASON_STYLE, SKIP_NER, ALLOW_1STEP,
)
from kgqa.stages.runner import run_stage_mode


async def amain():
    parser = argparse.ArgumentParser(description="KGQA Pipeline Runner")
    parser.add_argument("--pilot-results", default=str(DEFAULT_PILOT))
    parser.add_argument("--cwq-pkl", default=str(DEFAULT_CWQ))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of parallel cases to run (default: 1, max: 32)")
    parser.add_argument("--mode", choices=["case", "stage"], default="case",
                        help="Execution mode: 'case' for per-case parallel, 'stage' for stage-based batch")
    parser.add_argument("--gt-anchor", action="store_true",
                        help="Use ground-truth core_entities from CWQ as anchor (skip NER)")
    parser.add_argument("--prune", choices=["llm", "rerank"], default="llm",
                        help="Relation pruning method: 'llm' (default) or 'rerank' (Qwen3-Reranker)")
    parser.add_argument("--prune-top-k", type=int, default=5,
                        help="Number of relations to keep per step after pruning (default: 5)")
    parser.add_argument("--rerank-model", default=os.environ.get("RERANK_MODEL", "Qwen3-Reranker-0.6B"),
                        help="Reranker model path (Qwen3-Reranker-0.6B)")
    parser.add_argument("--reason-style", choices=["default", "check", "ecot", "entity", "entity-lite", "v2", "v3"], default="v2",
                        help="Stage 8 prompt style: 'v2' (fast 2-step), 'v3' (cardinality-aware over-output), 'default', 'check', 'ecot', 'entity', 'entity-lite'")
    parser.add_argument("--inject-decomp", default=None,
                        help="Path to golden results JSON. Injects Stage 0/1/1.5 outputs from golden, skipping LLM calls for those stages.")
    parser.add_argument("--skip-ner", action="store_true",
                        help="Skip NER GTE call, use q_entity directly as entities for faster processing")
    parser.add_argument("--allow-1step", action="store_true",
                        help="Allow 1-step decomposition without forcing retry to 2+ steps")
    parser.add_argument("--topk", type=int, default=3,
                        help="Max relations per step after LLM prune (default: 3)")
    parser.add_argument("--dump-trajectories", action="store_true",
                        help="Dump per-case trajectory files with full LLM I/O for manual auditing")
    parser.add_argument("--decomp", choices=["v2", "cascade"], default="cascade",
                        help="Decomposition mode: 'v2' (default chain), 'cascade' (two-step sub-q -> triples)")
    parser.add_argument("--dataset", choices=["cwq", "webqsp"], default=None,
                        help="Dataset preset: overrides decomp/topk/skip-ner/allow-1step with tuned defaults")
    args = parser.parse_args()

    # ── Dataset auto-detection ──
    if args.dataset is None:
        # Auto-detect from pkl: sample first 20 cases, check if IDs have hash suffix
        import pickle as _pkl
        _samples = _pkl.loads(Path(args.cwq_pkl).read_bytes())
        _has_hash = sum(1 for s in _samples[:50] if '_' in s.get('id', '') and len(s['id'].split('_')[-1]) > 10)
        if _has_hash > 30:  # >60% have hash suffix → CWQ
            args.dataset = "cwq"
        else:
            args.dataset = "webqsp"
        print(f"  Auto-detected dataset: {args.dataset}")

    # ── Dataset presets ──
    if args.dataset == "webqsp":
        # WebQSP: mostly 1-hop, cascade now accepts 1-step naturally
        args.skip_ner = True
        args.allow_1step = True
        print(f"  Preset [webqsp]: decomp={args.decomp} skip-ner={args.skip_ner} allow-1step={args.allow_1step} topk={args.topk}")
    elif args.dataset == "cwq":
        # CWQ: mostly 2-hop, cascade shines here
        args.decomp = "cascade"
        args.skip_ner = True
        print(f"  Preset [cwq]: decomp={args.decomp} skip-ner={args.skip_ner} topk={args.topk}")

    # Update global config
    import kgqa.core.config as _cfg
    _cfg.REASON_STYLE = args.reason_style
    _cfg.SKIP_NER = args.skip_ner
    _cfg.ALLOW_1STEP = args.allow_1step
    _cfg.PRUNE_TOPK = args.topk

    pilot_rows = json.loads(Path(args.pilot_results).read_text())
    samples = pickle.loads(Path(args.cwq_pkl).read_bytes())
    sample_map = {}
    for s in samples:
        if "id" in s:
            sample_map[s["id"]] = s
        elif "question_id" in s:
            sample_map[s["question_id"]] = s

    # Load mask
    masked_ids = set()
    if MASK_WRONG_TYPE.exists():
        masked_ids = set(json.loads(MASK_WRONG_TYPE.read_text()))
        print(f"  Masked {len(masked_ids)} wrong-type cases")

    # Prepare cases
    cases_to_run = []
    for idx, pilot_row in enumerate(pilot_rows[:args.limit], 1):
        sample = sample_map.get(pilot_row["case_id"])
        if not sample:
            for s in samples:
                if s.get("question", "") == pilot_row["question"]:
                    sample = s; break
        if not sample:
            print(f"SKIP: {pilot_row['case_id']}")
            continue
        if pilot_row["case_id"] in masked_ids:
            continue
        cases_to_run.append((sample, pilot_row, idx))

    total_cases = len(cases_to_run)

    if args.mode == "stage":
        await run_stage_mode(cases_to_run, args)
        return

    # Case mode: delegate to runner for now (full case mode implementation)
    print(f"\nNote: case mode delegates to stage mode for batch efficiency.")
    await run_stage_mode(cases_to_run, args)


if __name__ == "__main__":
    asyncio.run(amain())
