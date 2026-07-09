#!/usr/bin/env python3
"""Offline regression for the CVT-passthrough fix (no LLM/GTE needed).

Replays `_do_select` (pure graph traversal) on saved trajectories WITH the fix,
and compares against the pools recorded in rescored.jsonl (which were produced
by the SAME replay BEFORE the fix). Reports:
  - exceptions (must be 0)
  - gold-in-pool rate: old vs new (should not regress; should improve on CVT cases)
  - pool-size distribution: old vs new (must stay bounded -> no CVT-fan-out explosion)
  - flips: 0->>0 (fixed), >0->0 (regression)

This validates the engine change is safe + beneficial. It does NOT measure the
model's end-to-end F1 reaction (that needs the live vLLM+GTE eval).

Usage:
  python scripts/regress_cvt_passthrough.py --records reports/samp_val_pool/rescored.jsonl \
      --pkl data/cwq_processed/val.pkl --sample 800
"""
from __future__ import annotations
import argparse, asyncio, glob, json, pickle, sys
from pathlib import Path
from statistics import median

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
from kgqa.agent.loop import build_context, _resolve_anchor
from kgqa.agent import tools as T
from kgqa.core.utils import normalize
import importlib.util
_spec = importlib.util.spec_from_file_location("scorer", _ROOT / "scripts/agent_stage_scorer.py")
scorer = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(scorer)
_strict = scorer._matches_strict


def _gold_in(gt, pool):
    gn = [normalize(g) for g in gt if g]
    if not gn:
        return False
    pn = [normalize(c) for c in pool] if pool else []
    return any(any(_strict(g, u) for u in pn) for g in gn)


def _parse_sel(rec):
    dec = sel = None
    for m in rec.get("messages", []):
        c = m.get("content", "")
        if not isinstance(c, str):
            continue
        if c.startswith("Tool result (decompose):"):
            try: dec = json.loads(c[len("Tool result (decompose):"):])
            except Exception: dec = None
        elif c.startswith("Tool result (select_relations):"):
            try: sel = json.loads(c[len("Tool result (select_relations):"):])
            except Exception: sel = None
    sd = {}
    if sel and isinstance(sel.get("selected"), dict):
        for fid, rels in sel["selected"].items():
            sd[str(fid)] = [str(r) for r in rels] if isinstance(rels, list) else []
    return (dec or {}).get("anchor"), (dec or {}).get("endpoints") or [], sd


async def _new_pool(sample, rec):
    cid = rec.get("case_id", "")
    anc, eps, sd = _parse_sel(rec)
    ctx = build_context(sample, {"case_id": cid, "question": rec.get("question", ""),
                                 "gt_answers": rec.get("gt_answers") or []}, 0)
    ctx._model_anchor = anc; ctx._model_endpoints = list(eps); _resolve_anchor(ctx)
    ridx = {r: i for i, r in enumerate(ctx.rels)}
    ctx.fact_ids = list(sd.keys())
    ctx.fact_relations = {fid: {ridx[x] for x in v if x in ridx} for fid, v in sd.items()}
    ctx.fact_relations = {fid: v for fid, v in ctx.fact_relations.items() if v}
    if not ctx.fact_relations or ctx.anchor_idx is None:
        return None
    try:
        await T._do_select(ctx)
    except Exception as e:
        return ("ERR", repr(e))
    return list(getattr(ctx, "all_candidates", []) or [])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--pkl", required=True)
    ap.add_argument("--sample", type=int, default=800)
    ap.add_argument("--plan-failed-only", action="store_true",
                    help="only sample S_plan==0 records (where the fix can help)")
    args = ap.parse_args()

    samples = pickle.loads(Path(args.pkl).read_bytes())
    by_id = {s.get("id"): s for s in samples if s.get("id")}
    recs = []
    for bf in sorted(glob.glob(args.records)):
        for line in open(bf):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    pool = [r for r in recs if (r.get("S_plan") or 0) == 0 and not r.get("agent_failed")] if args.plan_failed_only else recs
    # prioritize plan-failed, fill with others up to --sample
    pf = [r for r in pool if (r.get("S_plan") or 0) == 0]
    ok = [r for r in pool if (r.get("S_plan") or 0) > 0]
    sample = (pf + ok)[:args.sample] if args.sample else pool
    print(f"Loaded {len(recs)} records; sampling {len(sample)} "
          f"({len(pf)} plan-failed prioritized)...", flush=True)

    old_in = new_in = 0
    fixed = regressed = 0
    old_sizes = []; new_sizes = []
    errs = 0; skipped = 0
    for i, r in enumerate(sample):
        s = by_id.get(r.get("case_id"))
        if not s:
            skipped += 1; continue
        gt = r.get("gt_answers") or []
        old_pool = r.get("answer_candidates") or []
        new = await _new_pool(s, r)
        if new is None:
            skipped += 1; continue
        if isinstance(new, tuple) and new[0] == "ERR":
            errs += 1
            if errs <= 5:
                print(f"  EXCEPTION {r.get('case_id','')[:20]}: {new[1]}", flush=True)
            continue
        o = _gold_in(gt, old_pool); n = _gold_in(gt, new)
        old_in += o; new_in += n
        if not o and n: fixed += 1
        if o and not n: regressed += 1
        old_sizes.append(len(old_pool)); new_sizes.append(len(new))
        if (i + 1) % 200 == 0:
            print(f"  ...{i+1}/{len(sample)}  errs={errs} gold-in old={old_in} new={new_in} "
                  f"fixed={fixed} regressed={regressed}", flush=True)

    def stats(xs):
        if not xs: return "n/a"
        xs = sorted(xs)
        return f"median={median(xs):.0f} p90={xs[int(len(xs)*0.9)]:d} max={max(xs)}"
    n = len(old_sizes)
    print("\n" + "=" * 64)
    print(f"CVT-PASSTHROUGH OFFLINE REGRESSION  ({n} replayed, {errs} exceptions, {skipped} skipped)")
    print("=" * 64)
    print(f"  exceptions (engine errors)   : {errs}  {'OK' if errs==0 else 'FAIL'}")
    print(f"  gold-in-pool rate: old {old_in}/{n} ({old_in/n*100:.1f}%) -> "
          f"new {new_in}/{n} ({new_in/n*100:.1f}%)")
    print(f"  flipped 0 -> >0 (fixed)      : {fixed}")
    print(f"  flipped >0 -> 0 (REGRESSED)  : {regressed}  {'OK' if regressed==0 else 'CHECK'}")
    print(f"  pool size old: {stats(old_sizes)}")
    print(f"  pool size new: {stats(new_sizes)}  <- explosion check (max should stay bounded)")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
