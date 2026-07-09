#!/usr/bin/env python3
"""Trace WHERE the gold answer gets dropped in TRAVERSAL-class plan failures.

TRAVERSAL = the model selected a gold relation (gold in L2 AND L3) yet S_plan==0
(answer not in the plan-reachable pool). plan_reachable is PARSED FROM THE
OVERVIEW TEXT, which is truncated (top-30 branches, <=3 candidates/branch,
selected_candidates[:60]). So "not in plan_reachable" has distinct causes:

  ENGINE_MISS   — the traversal engine never reached the answer (absent even
                  from ctx.all_candidates / cs.answer_candidates).
  TRUNCATION    — the engine reached it, but display/S_plan scoring truncated
                  it out of the overview the model sees.
  SCORER_MISS   — the answer IS in the overview text, but the scorer's
                  _extract_plan_reachable regex failed to recover it (so S_plan
                  is an artifact, not a traversal failure).

This replays `_do_select` with the model's REAL selection per TRAVERSAL case and
reports answer presence at each stage, pinpointing the drop.

Usage:
  python scripts/trace_traversal_drop.py --max 60
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import importlib.util
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from kgqa.agent.loop import build_context, _resolve_anchor
from kgqa.agent import tools as T
from kgqa.core.utils import normalize
from diagnose_plan_failures import (
    extract_signals, resolve_anchor_idx, answer_idxs, gold_relations,
    classify_one, anchor_is_generic, is_generic_relation,
)

PKL_DEFAULT = _PROJECT_ROOT / "data/cwq_processed/val.pkl"
BATCHES_DEFAULT = str(_PROJECT_ROOT / "reports/samp_val_pool/batch_*.jsonl")


def _hit(answer, pool) -> bool:
    """Is `answer` present in a pool of entity-name strings (or in overview text)?"""
    if not answer or not pool:
        return False
    a = normalize(answer)
    if not a:
        return False
    for e in pool:
        en = normalize(str(e))
        if not en:
            continue
        if en == a or (len(a) >= 3 and a in en):
            return True
    return False


def parse_selection(record: dict):
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
    facts_order = [str(f.get("id")) for f in (dec or {}).get("facts", []) if f.get("id")]
    selected = {}
    if sel and isinstance(sel.get("selected"), dict):
        for fid, rels in sel["selected"].items():
            selected[str(fid)] = [str(r) for r in rels] if isinstance(rels, list) else []
    return (dec or {}).get("anchor"), facts_order, selected


async def trace_one(sample, record):
    cid = record["case_id"]
    gt = record.get("gt_answers") or []
    model_anchor, facts_order, selected = parse_selection(record)
    ctx = build_context(sample, {"case_id": cid, "question": record.get("question", ""),
                                 "gt_answers": gt}, 0)
    ctx._model_anchor = model_anchor
    _resolve_anchor(ctx)
    rel_idx = {r: i for i, r in enumerate(ctx.rels)}
    ctx.fact_ids = list(facts_order) or list(selected.keys())
    ctx.fact_relations = {fid: {rel_idx[r] for r in rels if r in rel_idx}
                          for fid, rels in selected.items()}
    ctx.fact_relations = {fid: v for fid, v in ctx.fact_relations.items() if v}
    if not ctx.fact_relations or ctx.anchor_idx is None:
        return {"case_id": cid, "verdict": "REPLAY_SETUP_FAILED",
                "anchor": ctx.anchor_name, "n_sel_facts": len(ctx.fact_relations)}

    # Use the SAME answer resolver as the classifier (substring+ratio) so
    # answer_in_graph is consistent with the TRAVERSAL classification.
    a_idxs = answer_idxs(ctx, gt)
    try:
        result = json.loads(await T._do_select(ctx))
    except Exception as e:
        return {"case_id": cid, "verdict": "REPLAY_ERROR", "err": repr(e)}

    overview = result.get("overview", "")
    select_pool = [str(c) for c in result.get("candidates", [])]          # [:20] shown
    full_pool = list(getattr(ctx, "all_candidates", []) or [])            # engine full
    sel_cands = list(getattr(ctx, "selected_candidates", []) or [])       # [:60]
    spec = importlib.util.spec_from_file_location("scorer", str(_PROJECT_ROOT / "scripts/agent_stage_scorer.py"))
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    plan_reachable = scorer._extract_plan_reachable(overview, select_pool)

    g = gt[0] if gt else ""
    in_ovr = bool(g) and normalize(g) in normalize(overview)
    return {
        "case_id": cid, "question": record.get("question", "")[:80], "gt": gt,
        "anchor": ctx.anchor_name, "answer_in_graph": bool(a_idxs),
        "n_full_pool": len(full_pool), "n_selected_cands": len(sel_cands),
        "in_full_pool": _hit(g, full_pool),
        "in_selected_cands60": _hit(g, sel_cands),
        "in_select_pool20": _hit(g, select_pool),
        "in_overview": in_ovr,
        "in_plan_reachable": _hit(g, plan_reachable),
        "n_paths": len(getattr(ctx, "all_paths", []) or []),
        "n_logical_paths": len(getattr(ctx, "logical_paths", []) or []),
        "hop_to_answer": _bfs_depth(ctx, ctx.anchor_idx, a_idxs),
    }


def _bfs_depth(ctx, src, targets, cap=4):
    if src is None or not targets:
        return None
    from collections import deque
    adj = {}
    for h, t in zip(ctx.h_ids, ctx.t_ids):
        adj.setdefault(h, []).append(t)
        adj.setdefault(t, []).append(h)
    dist = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        if dist[u] >= cap:
            break
        for v in adj.get(u, []):
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    ds = [dist[t] for t in targets if t in dist]
    return min(ds) if ds else None


def classify_drop(r: dict) -> str:
    if r.get("verdict"):
        return r["verdict"]
    if not r.get("answer_in_graph"):
        return "ANSWER_NOT_IN_GRAPH"
    if not r.get("in_full_pool"):
        return "ENGINE_MISS"
    if r.get("in_overview") and not r.get("in_plan_reachable"):
        return "SCORER_MISS (answer in overview, scorer dropped)"
    if r.get("in_plan_reachable"):
        return "REACHED_AND_SCORED (not a real drop)"
    return "TRUNCATION (engine reached, display dropped)"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60, help="max TRAVERSAL cases to trace")
    ap.add_argument("--batches", default=BATCHES_DEFAULT, help="glob/path to sampling jsonl")
    ap.add_argument("--pkl", default=str(PKL_DEFAULT), help="case pkl (must match the sampling source)")
    args = ap.parse_args()

    samples = pickle.loads(Path(args.pkl).read_bytes())
    sample_by_id = {s.get("id"): s for s in samples if s.get("id")}
    rec_by_case = {}
    for bf in sorted(glob.glob(args.batches)):
        for line in open(bf):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            rec_by_case.setdefault(rec.get("case_id"), []).append(rec)

    ctx_cache = {}

    def get_ctx(cid, rec):
        if cid not in ctx_cache:
            s = sample_by_id.get(cid)
            if not s:
                ctx_cache[cid] = None
                return None, None, None
            ctx = build_context(s, {"case_id": cid, "question": rec.get("question", ""),
                                    "gt_answers": rec.get("gt_answers") or []}, 0)
            scope = {ctx.rels[r] for r in T._anchor_outgoing_rel_ids(ctx) if 0 <= r < len(ctx.rels)}
            ctx_cache[cid] = (ctx, scope, set(ctx.rels))
        return ctx_cache[cid]

    def classify(rec, ctx, scope, rels_set):
        sig = extract_signals(rec)
        anchor_idx, _ = resolve_anchor_idx(ctx, sig["model_anchor"])
        generic, _ = anchor_is_generic(ctx, anchor_idx)
        a_ids = answer_idxs(ctx, rec.get("gt_answers") or [])
        gold_all, gold_note = gold_relations(ctx, anchor_idx, a_ids)
        gold_real = {r for r in gold_all if not is_generic_relation(r)}
        reachable = gold_note not in ("answer_unreachable", "no_anchor") and bool(gold_all)
        if generic and reachable and not gold_real:
            return "ANCHOR_MISS"
        g = gold_real if gold_real else gold_all
        cat, _ = classify_one(g, sig, scope, rels_set, gold_note)
        return cat

    targets = []
    for cid, recs in rec_by_case.items():
        if max((r.get("S_plan") or 0) for r in recs) > 0:
            continue
        rec = next((r for r in recs if (r.get("S_plan") or 0) == 0 and not r.get("agent_failed")), None)
        if not rec:
            continue
        ctx, scope, rels_set = get_ctx(cid, rec)
        if ctx is None:
            continue
        try:
            if classify(rec, ctx, scope, rels_set) == "TRAVERSAL":
                targets.append((cid, rec))
        except Exception:
            pass
    print(f"Found {len(targets)} TRAVERSAL cases; tracing up to {args.max}...\n", flush=True)
    targets = targets[:args.max]

    results = []
    for cid, rec in targets:
        s = sample_by_id.get(cid)
        try:
            r = await trace_one(s, rec)
        except Exception as e:
            r = {"case_id": cid, "verdict": "REPLAY_ERROR", "err": repr(e)}
        r["drop"] = classify_drop(r)
        results.append(r)

    drops = Counter(r["drop"] for r in results)
    print("=" * 72)
    print(f"TRAVERSAL drop-location breakdown ({len(results)} cases traced)")
    print("=" * 72)
    for d, n in drops.most_common():
        print(f"  {d:48s} {n:4d}  ({n/len(results)*100:5.1f}%)")
    # engine-miss hop analysis
    misses = [r for r in results if r["drop"].startswith("ENGINE_MISS")]
    hops = Counter(r.get("hop_to_answer") for r in misses if r.get("hop_to_answer") is not None)
    none_reach = sum(1 for r in misses if r.get("hop_to_answer") is None)
    print("-" * 72)
    print(f"ENGINE_MISS hop-to-answer (BFS, undirected): {dict(sorted(hops.items())) if hops else '{}'}; "
          f"unreachable<{4}=hop>: {none_reach}/{len(misses)}")
    print("\nDetail (first 15):")
    for r in results[:15]:
        if r.get("verdict"):
            print(f"  [{r['drop']}] {r['case_id'][:20]} {r.get('err','')}")
            continue
        print(f"  [{r['drop']:42s}] hop={r.get('hop_to_answer')} full={r['in_full_pool']}/{r['n_full_pool']} "
              f"ovr={r['in_overview']} plan={r['in_plan_reachable']} | {r['question'][:46]}")


if __name__ == "__main__":
    asyncio.run(main())
