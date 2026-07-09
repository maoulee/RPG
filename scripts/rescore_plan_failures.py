#!/usr/bin/env python3
"""Re-score saved sampling records with the FIXED S_plan (structured-pool-based).

Existing batch/samples jsonl records were scored with the buggy S_plan (regex on
the rendered overview) AND did not save the structured candidate pool. This
script replays `_do_select` per record to recover ctx.all_candidates (the
structured pool the traversal actually produced), then computes the corrected
S_plan = recall(gt, pool) with the scorer's strict matcher.

It writes <out> (a corrected jsonl: same records with corrected S_plan +
answer_candidates populated) and prints old-vs-new plan-failure tallies so the
impact of the scorer fix is visible.

Usage:
  python scripts/rescore_plan_failures.py \
      --records reports/samp_cwq_full/samples.jsonl \
      --pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \
      --out reports/samp_cwq_full/rescored.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import pickle
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from kgqa.agent.loop import build_context, _resolve_anchor
from kgqa.agent import tools as T
from kgqa.core.utils import normalize
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "scorer", _PROJECT_ROOT / "scripts/agent_stage_scorer.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)
_matches_strict = scorer._matches_strict


def _recall(gt, pool):
    gt_norm = [normalize(g) for g in gt if g]
    if not gt_norm:
        return 0.0
    pool_norm = [normalize(c) for c in pool] if pool else []
    hit = sum(1 for g in gt_norm if any(_matches_strict(g, u) for u in pool_norm))
    return hit / len(gt_norm)


def _parse_selection(record):
    """model anchor, endpoints, {fact_id: [selected_rel_names]} from messages."""
    dec = sel = None
    for m in record.get("messages", []):
        c = m.get("content", "")
        if not isinstance(c, str):
            continue
        if c.startswith("Tool result (decompose):"):
            try:
                dec = json.loads(c[len("Tool result (decompose):"):].strip())
            except Exception:
                dec = None
        elif c.startswith("Tool result (select_relations):"):
            try:
                sel = json.loads(c[len("Tool result (select_relations):"):].strip())
            except Exception:
                sel = None
    sd = {}
    if sel and isinstance(sel.get("selected"), dict):
        for fid, rels in sel["selected"].items():
            sd[str(fid)] = [str(r) for r in rels] if isinstance(rels, list) else []
    return (dec or {}).get("anchor"), (dec or {}).get("endpoints") or [], sd


async def _corrected_splan(sample, record):
    """Replay _do_select with the model's real selection -> structured pool -> S_plan."""
    cid = record.get("case_id", "")
    gt = record.get("gt_answers") or []
    anc, eps, sd = _parse_selection(record)
    ctx = build_context(sample, {"case_id": cid, "question": record.get("question", ""),
                                 "gt_answers": gt}, 0)
    ctx._model_anchor = anc
    ctx._model_endpoints = list(eps)
    _resolve_anchor(ctx)
    ridx = {r: i for i, r in enumerate(ctx.rels)}
    ctx.fact_ids = list(sd.keys())
    ctx.fact_relations = {fid: {ridx[x] for x in v if x in ridx} for fid, v in sd.items()}
    ctx.fact_relations = {fid: v for fid, v in ctx.fact_relations.items() if v}
    if not ctx.fact_relations or ctx.anchor_idx is None:
        return None, []  # cannot replay (no selection / no anchor)
    try:
        await T._do_select(ctx)
    except Exception:
        return None, []
    pool = list(getattr(ctx, "all_candidates", []) or [])
    return _recall(gt, pool), pool


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, help="glob/path to sampling jsonl")
    ap.add_argument("--pkl", required=True, help="case pkl matching the sampling source")
    ap.add_argument("--out", required=True, help="corrected jsonl output path")
    args = ap.parse_args()

    samples = pickle.loads(Path(args.pkl).read_bytes())
    sample_by_id = {s.get("id"): s for s in samples if s.get("id")}
    records = []
    for bf in sorted(glob.glob(args.records)):
        for line in open(bf):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    print(f"Loaded {len(records)} records", flush=True)

    old_fail = new_fail = flipped_up = flipped_down = no_replay = 0
    out_f = open(args.out, "w")
    for i, rec in enumerate(records):
        sample = sample_by_id.get(rec.get("case_id"))
        old = rec.get("S_plan")
        if sample is None or rec.get("agent_failed"):
            new, pool = None, rec.get("answer_candidates", [])
            no_replay += 1
        else:
            new, pool = await _corrected_splan(sample, rec)
            if new is None:
                no_replay += 1
        old_zero = (old in (0.0, 0, None))
        new_zero = (new in (0.0, 0, None))
        if old_zero:
            old_fail += 1
        if new_zero:
            new_fail += 1
        if old_zero and not new_zero:
            flipped_up += 1
        if not old_zero and new_zero:
            flipped_down += 1
        rec2 = dict(rec)
        rec2["S_plan_old"] = old
        if new is not None:
            rec2["S_plan"] = round(new, 4)
        rec2["answer_candidates"] = pool
        out_f.write(json.dumps(rec2, ensure_ascii=False) + "\n")
        if (i + 1) % 500 == 0:
            print(f"  ...{i+1}/{len(records)}  old_fail={old_fail} new_fail={new_fail} "
                  f"0->>0:{flipped_up} >0->0:{flipped_down} no_replay={no_replay}", flush=True)
    out_f.close()

    print("\n" + "=" * 64)
    print(f"RE-SCORE (fixed S_plan)  ({len(records)} records)")
    print("=" * 64)
    print(f"  old S_plan==0 (buggy)          : {old_fail}")
    print(f"  new S_plan==0 (corrected)      : {new_fail}")
    print(f"  flipped 0  -> >0 (scorer fixed): {flipped_up}")
    print(f"  flipped >0 -> 0                : {flipped_down}")
    print(f"  no-replay (agent_failed/etc)   : {no_replay}")
    print(f"  plan-failure rate: old {old_fail/len(records)*100:.1f}% -> "
          f"new {new_fail/len(records)*100:.1f}%")
    print(f"\n> wrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
