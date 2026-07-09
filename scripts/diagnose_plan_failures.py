#!/usr/bin/env python3
"""Diagnose S_plan=0 (plan-failed) cases: is the failure MODEL DECISION or
SYSTEM RETRIEVAL, or TRAVERSAL/COMPOSITION, or DATA?

WHY
---
S_plan (agent_stage_scorer) measures, at the ENTITY level, whether the plan
unlocked paths reaching the gold answer — AFTER the model selected relations
and the system traversed them. So S_plan==0 conflates several failure modes.
This script splits them by checking, per plan-failed sample, whether the GOLD
RELATION (the relation on the anchor->answer path in the case's own subgraph)
was ever:

  - in the candidate pool the model SAW (L2 = decompose's candidate_relations)
  - SELECTED by the model (L3 = select_relations' `selected`)
  - in the anchor's structural scope (`_anchor_outgoing_rel_ids`, fact_1 scope)
  - in the case subgraph at all (BFS anchor->answer reachability)

TAXONOMY (priority order), per S_plan==0 sample
-----------------------------------------------
  GTE_MISS         gold_rel ∉ L2, gold_rel ∈ anchor scope
                   -> GTE retrieved other relations; improve GTE accuracy.
  SCOPE_MISS       gold_rel ∉ L2, ∉ scope, ∈ rels
                   -> structural prune/scope dropped it; system logic.
  DECISION         gold_rel ∈ L2, ∉ L3
                   -> model saw it but didn't pick it; prompt/selection + display.
  TRAVERSAL        gold_rel ∈ L2 AND ∈ L3, answer still not reached
                   -> relation right, but graph walk/composition missed answer.
  SUBGRAPH_MISS    no anchor->answer path in the case subgraph (BFS unreachable)
                   -> data/subgraph extraction problem (answer not in graph).

Gold relations are derived intrinsically from each val.pkl case (the per-case
subgraph + gold answer `a_entity`), NOT from SPARQL — cwq_sparql/test.json
aligns to the TEST pkl, not the val.pkl that was sampled.

USAGE
-----
  python scripts/diagnose_plan_failures.py
  python scripts/diagnose_plan_failures.py --batches 'reports/samp_val_pool/batch_*.jsonl' \
         --pkl data/cwq_processed/val.pkl --out reports/samp_val_pool/plan_failure_diagnosis.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import sys
import traceback
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from kgqa.agent.loop import build_context, CaseContext
from kgqa.agent import tools as T
from kgqa.core.utils import normalize

# Generic / meta / typing namespaces. Relations (and entities whose incident
# relations are dominated by these) are NOT answer-discriminative — they're the
# Freebase schema/topic layer (common.topic.notable_types, ontologies, etc.).
# A path that reaches the answer only through these is spurious for retrieval
# analysis; an anchor whose neighborhood is mostly these is a TYPE node, not a
# concrete entity the plan can root on.
GENERIC_NS = (
    "common.topic.", "common.webpage.", "base.ontologies.",
    "base.schemastaging.", "base.descriptive_names.", "freebase.",
    "fictional_universe.", "type.", "/type/",
)


def is_generic_relation(r: str) -> bool:
    return any(r.startswith(p) or p in r for p in GENERIC_NS)


def anchor_is_generic(ctx: CaseContext, anchor_idx: Optional[int]) -> Tuple[bool, dict]:
    """True if the anchor is a type/meta hub rather than a concrete entity.

    Signal: the fraction of the anchor's incident relations that live in generic
    namespaces. Concrete entities (Turkey, a song, a person) have mostly domain
    relations (location.*, music.*, people.*); type nodes (Country, President)
    are dominated by common.topic.*/ontologies/freebase.*. Also flags an
    unresolved anchor (idx None) — the plan has no concrete root either way.
    """
    if anchor_idx is None or anchor_idx >= len(ctx.ents):
        return True, {"reason": "unresolved", "anchor": None}
    inc = []
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if h == anchor_idx or t == anchor_idx:
            inc.append(ctx.rels[r])
    if not inc:
        return True, {"reason": "no_neighbors", "anchor": ctx.ents[anchor_idx]}
    frac = sum(1 for r in inc if is_generic_relation(r)) / len(inc)
    # A type/meta hub is BOTH mostly-generic AND high-degree (Country, President
    # have 30+ generic relations). A sparse concrete entity (a minor character
    # whose only relations are notable_types) has low degree — it's a fine
    # anchor, just a small subgraph; don't mis-flag it. Threshold separates the
    # two.
    is_hub = frac >= 0.5 and len(inc) >= 12
    return is_hub, {"reason": "type_hub" if is_hub else "concrete",
                    "anchor": ctx.ents[anchor_idx], "generic_frac": round(frac, 2),
                    "degree": len(inc)}


# ---------------------------------------------------------------------------
# Trajectory parsing  (batch_*.jsonl stores chat `messages`, not agent_trajectory)
# ---------------------------------------------------------------------------
def _parse_tool_msg(prefix: str, messages: List[dict]) -> Optional[dict]:
    """Return the parsed JSON payload of the LAST user message beginning with
    `Tool result (<prefix>):`, or None."""
    payload = None
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str) and c.startswith(f"Tool result ({prefix}):"):
            raw = c[len(f"Tool result ({prefix}):"):].strip()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = None
    return payload


def extract_signals(record: dict) -> Dict[str, Any]:
    """From one sampling record, pull L2 (candidate pool per fact + union),
    L3 (selected per fact + union), relation_hints, and the model anchor."""
    msgs = record.get("messages", []) or []
    dec = _parse_tool_msg("decompose", msgs) or {}
    sel = _parse_tool_msg("select_relations", msgs) or {}

    l2_by_fact: Dict[str, List[str]] = {}
    hints_by_fact: Dict[str, str] = {}
    for f in dec.get("facts", []) or []:
        fid = str(f.get("id") or f.get("fact_id") or "")
        if not fid:
            continue
        l2_by_fact[fid] = [str(r) for r in (f.get("candidate_relations") or [])]
        hints_by_fact[fid] = str(f.get("relation_hint") or f.get("text") or "")
    l2_union: Set[str] = set()
    for v in l2_by_fact.values():
        l2_union |= set(v)

    l3_by_fact: Dict[str, List[str]] = {}
    sd = sel.get("selected") or {}
    if isinstance(sd, dict):
        for fid, rels in sd.items():
            l3_by_fact[str(fid)] = [str(r) for r in rels] if isinstance(rels, list) else []
    l3_union: Set[str] = set()
    for v in l3_by_fact.values():
        l3_union |= set(v)

    return {
        "l2_by_fact": l2_by_fact, "l2_union": l2_union,
        "l3_by_fact": l3_by_fact, "l3_union": l3_union,
        "hints_by_fact": hints_by_fact,
        "model_anchor": dec.get("anchor"),
        "n_decompose_facts": len(dec.get("facts") or []),
    }


# ---------------------------------------------------------------------------
# Gold-path relation extraction (BFS anchor -> answer in the case subgraph)
# ---------------------------------------------------------------------------
def _adj(ctx: CaseContext) -> Dict[int, List[Tuple[int, int]]]:
    """Undirected adjacency: node -> [(neighbor, r_id), ...]. Uses the same
    expanded graph the agent traverses (ctx.h/r/t_ids post expand_cvt_leaves)."""
    adj: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        adj[h].append((t, r))
        adj[t].append((h, r))
    return adj


def gold_relations(ctx: CaseContext, anchor_idx: int,
                   answer_idxs: List[int], max_len: int = 3) -> Tuple[Set[str], str]:
    """Relations on shortest anchor->answer path(s). Returns (rel_name_set, note)."""
    if anchor_idx is None:
        return set(), "no_anchor"
    adj = _adj(ctx)
    # BFS distances + parent edges from anchor
    dist = {anchor_idx: 0}
    parent: Dict[int, List[Tuple[int, int]]] = defaultdict(list)  # node -> [(prev, r_id)]
    q = deque([anchor_idx])
    while q:
        u = q.popleft()
        if dist[u] >= max_len:
            continue
        for v, r in adj[u]:
            if v == anchor_idx:
                continue
            nd = dist[u] + 1
            if v not in dist:
                dist[v] = nd
                parent[v].append((u, r))
                q.append(v)
            elif dist[v] == nd:
                parent[v].append((u, r))
    reachable_answers = [a for a in answer_idxs if a in dist]
    if not reachable_answers:
        return set(), "answer_unreachable"
    best = min(dist[a] for a in reachable_answers)
    nearest = [a for a in reachable_answers if dist[a] == best]
    # Backtrack: collect ALL r_ids on any shortest path anchor->nearest answers
    gold_rids: Set[int] = set()
    target_set = set(nearest)
    visited_nodes: Set[int] = set()
    stack = list(nearest)
    while stack:
        node = stack.pop()
        if node in visited_nodes or node == anchor_idx:
            continue
        visited_nodes.add(node)
        for prev, r in parent.get(node, []):
            gold_rids.add(r)
            if prev != anchor_idx and prev not in visited_nodes:
                stack.append(prev)
    rels = {ctx.rels[r] for r in gold_rids if 0 <= r < len(ctx.rels)}
    return rels, f"len{best}"


def _degree_map(ctx: CaseContext) -> Dict[int, int]:
    """Cached entity-degree map (neighbors via any triple). Type/meta hubs and
    real entities have high degree; ':'/m./g.-prefixed stub nodes have low."""
    dm = getattr(ctx, "_deg_cache", None)
    if dm is None:
        dm = defaultdict(int)
        for h, t in zip(ctx.h_ids, ctx.t_ids):
            dm[h] += 1
            dm[t] += 1
        ctx._deg_cache = dm
    return dm


def _stub(name: str) -> bool:
    """Image/topic stub or Freebase machine-id node — never a good anchor."""
    return bool(name) and (name.startswith(":") or name.startswith("m.")
                           or name.startswith("g.") or name.startswith("shared:"))


def _pick_anchor(ctx: CaseContext, cands: List[Tuple[int, bool]]) -> Optional[int]:
    """Pick the best anchor candidate: exact-match preferred, then non-stub,
    then higher degree (resolves ':Sydney' stub vs 'Sydney' city collisions)."""
    if not cands:
        return None
    dm = _degree_map(ctx)

    def key(ic):
        idx, exact = ic
        name = ctx.ents[idx] if 0 <= idx < len(ctx.ents) else ""
        return (exact, not _stub(name), dm.get(idx, 0), -len(name))
    cands.sort(key=key, reverse=True)
    return cands[0][0]


def resolve_anchor_idx(ctx: CaseContext, model_anchor: Optional[str]) -> Tuple[Optional[int], str]:
    """Resolve anchor to graph idx: prefer the model's decompose anchor, then
    q_entity heuristic. Among normalize-collisions, prefer exact, non-stub,
    high-degree nodes (audit: ':Sydney' stub was winning over 'Sydney' city)."""
    if model_anchor:
        mn = normalize(str(model_anchor))
        if mn:
            exact, sub = [], []
            for i, e in enumerate(ctx.ents):
                en = normalize(e)
                if not en:
                    continue
                if en == mn:
                    exact.append((i, True))
                elif len(mn) >= 3 and len(en) >= 3 and (mn in en or en in mn):
                    sub.append((i, False))
            pick = _pick_anchor(ctx, exact) or _pick_anchor(ctx, sub)
            if pick is not None:
                return pick, "model_exact" if (pick in {i for i, _ in exact}) else "model_substr"
    for qe in (ctx.sample.get("q_entity") or []):
        qn = normalize(str(qe))
        if not qn:
            continue
        exact, sub = [], []
        for i, e in enumerate(ctx.ents):
            en = normalize(e)
            if not en:
                continue
            if en == qn:
                exact.append((i, True))
            elif len(qn) >= 3 and len(en) >= 3 and (qn in en or en in qn):
                sub.append((i, False))
        pick = _pick_anchor(ctx, exact) or _pick_anchor(ctx, sub)
        if pick is not None:
            return pick, "qent_exact" if (pick in {i for i, _ in exact}) else "qent_substr"
    return None, "anchor_unresolved"


def answer_idxs(ctx: CaseContext, gt_answers: List[str]) -> List[int]:
    """Map gold answer entity names to graph node indices (exact then substring).

    Guards against two false-match bugs found by adversarial audit:
      - normalize() can yield '' for non-Latin (CJK/Korean) names; '' substring-
        matches anything. Skip empty-normalized answers AND entities.
      - short literal/value nodes ('.fr' -> 'fr') substring-match long answers.
        Require BOTH sides length>=3 AND a length ratio >= 0.4 (mirrors the
        scorer's _matches_strict: 'spain' must NOT match 'spain national team').
    """
    out: List[int] = []
    for raw in (gt_answers or []):
        if not raw:
            continue
        g = normalize(raw)
        if not g or len(g) < 2:
            continue
        hit = None
        for i, e in enumerate(ctx.ents):
            en = normalize(e)
            if not en:
                continue
            if en == g:
                hit = i
                break
        if hit is None:
            for i, e in enumerate(ctx.ents):
                en = normalize(e)
                if not en or len(en) < 3:
                    continue
                if (len(g) >= 3 and (g in en or en in g)
                        and min(len(g), len(en)) / max(len(g), len(en)) >= 0.4):
                    hit = i
                    break
        if hit is not None:
            out.append(hit)
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def classify_one(gold: Set[str], sig: dict, scope_names: Set[str],
                 rels_set: Set[str], gold_note: str) -> Tuple[str, dict]:
    """Return (category, detail)."""
    l2 = sig["l2_union"]
    l3 = sig["l3_union"]
    detail = {
        "n_gold": len(gold),
        "gold": sorted(gold),
        "gold_in_L2": sorted(gold & l2),
        "gold_in_L3": sorted(gold & l3),
        "gold_in_scope": sorted(gold & scope_names),
        "gold_in_rels_only": sorted((gold & rels_set) - scope_names),
        "l2_union_size": len(l2),
        "l3_union_size": len(l3),
        "scope_size": len(scope_names),
        "gold_note": gold_note,
    }
    if gold_note == "answer_unreachable":
        return "SUBGRAPH_MISS", detail
    if not gold:
        return "SUBGRAPH_MISS", detail  # BFS found no path -> answer not in subgraph
    # 1) Did the model ever SEE a gold relation?
    if gold & l2:
        # 2) Did it SELECT it?
        if gold & l3:
            return "TRAVERSAL", detail
        return "DECISION", detail
    # gold never in L2 -> retrieval/system side
    if gold & scope_names:
        return "GTE_MISS", detail
    if gold & rels_set:
        return "SCOPE_MISS", detail
    return "SUBGRAPH_MISS", detail


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="reports/samp_val_pool/batch_*.jsonl")
    ap.add_argument("--pkl", default="data/cwq_processed/val.pkl")
    ap.add_argument("--out", default="reports/samp_val_pool/plan_failure_diagnosis.json")
    ap.add_argument("--max-cases", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    # 1. Load all sampling records
    batch_files = sorted(glob.glob(args.batches))
    records: List[dict] = []
    for bf in batch_files:
        for line in open(bf):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    print(f"Loaded {len(records)} records from {len(batch_files)} batches", flush=True)

    # 2. Load val.pkl
    samples = pickle.loads(Path(args.pkl).read_bytes())
    sample_by_id = {}
    for s in samples:
        sid = s.get("id") or s.get("question_id")
        if sid:
            sample_by_id[sid] = s
    print(f"Loaded {len(samples)} cases from {args.pkl}", flush=True)

    # 3. Iterate S_plan==0 samples, classify
    CATS = ["ANCHOR_MISS", "GTE_MISS", "SCOPE_MISS", "DECISION", "TRAVERSAL",
            "SUBGRAPH_MISS", "ERROR"]
    counts = {c: 0 for c in CATS}
    exemplars: Dict[str, List[dict]] = {c: [] for c in CATS}
    _ex_seen: Dict[str, set] = {c: set() for c in CATS}  # dedup exemplars by case_id
    n_plan_fail_samples = 0
    n_total_samples = 0
    n_agent_failed = 0
    ctx_cache: Dict[str, Tuple[Any, Set[str], Set[str]]] = {}  # case_id -> (ctx, scope, rels)
    errors = 0

    for rec in records:
        n_total_samples += 1
        s_plan = rec.get("S_plan")
        if s_plan is None:
            continue
        if rec.get("agent_failed"):
            n_agent_failed += 1
            continue
        if s_plan > 0:
            continue
        n_plan_fail_samples += 1
        cid = rec.get("case_id", "")
        sample = sample_by_id.get(cid)
        if sample is None:
            counts["ERROR"] += 1
            errors += 1
            continue

        # Build ctx + scope once per case (cache)
        if cid not in ctx_cache:
            try:
                pilot_row = {"case_id": cid, "question": rec.get("question", sample.get("question", "")),
                             "gt_answers": rec.get("gt_answers") or sample.get("a_entity") or []}
                ctx = build_context(sample, pilot_row, 0)
                scope_idx = T._anchor_outgoing_rel_ids(ctx)
                scope_names = {ctx.rels[r] for r in scope_idx if 0 <= r < len(ctx.rels)}
                rels_set = set(ctx.rels)
                ctx_cache[cid] = (ctx, scope_names, rels_set)
            except Exception as e:
                ctx_cache[cid] = (None, set(), set())
                errors += 1
        ctx, scope_names, rels_set = ctx_cache[cid]
        if ctx is None:
            counts["ERROR"] += 1
            continue

        anchor_note = None
        anchor_meta = {}
        try:
            sig = extract_signals(rec)
            anchor_idx, anchor_note = resolve_anchor_idx(ctx, sig["model_anchor"])
            # ANCHOR_MISS: plan rooted on a type/meta node (or unresolved) — gold
            # derivation is unreliable and this is itself the root cause.
            generic, anchor_meta = anchor_is_generic(ctx, anchor_idx)
            # answer entity location + incident relations (for audit; anchor-independent)
            a_ids = answer_idxs(ctx, rec.get("gt_answers") or [])
            ans_inc = set()
            for ai in a_ids:
                for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
                    if h == ai or t == ai:
                        ans_inc.add(ctx.rels[r])
            gold_all, gold_note = gold_relations(ctx, anchor_idx, a_ids)
            # Discriminative gold = non-generic relations on the anchor->answer path.
            gold_real = {r for r in gold_all if not is_generic_relation(r)}
            reachable = (gold_note not in ("answer_unreachable", "no_anchor")
                         and bool(gold_all))
            # ANCHOR_MISS ONLY when the anchor is a type-hub AND the only path to the
            # answer runs through generic typing edges (no discriminative relation).
            # If a non-generic path exists, the anchor is concrete enough -> fall
            # through to normal retrieval/decision classification (audit: Kirk case).
            if generic and reachable and not gold_real:
                cat = "ANCHOR_MISS"
                detail = {"anchor_note": anchor_note, **anchor_meta,
                          "q_entity": ctx.sample.get("q_entity"),
                          "n_decompose_facts": sig.get("n_decompose_facts")}
            else:
                g = gold_real if gold_real else gold_all
                if not gold_real and gold_all:
                    gold_note += "/weak_gold"
                cat, detail = classify_one(g, sig, scope_names, rels_set, gold_note)
            # Audit enrichment (uniform across categories)
            detail["anchor"] = detail.get("anchor") or anchor_meta.get("anchor")
            detail["anchor_degree"] = anchor_meta.get("degree")
            detail["anchor_generic_frac"] = anchor_meta.get("generic_frac")
            detail["answer_incident_rels"] = sorted(ans_inc)[:12]
            detail["answer_found_in_subgraph"] = len(a_ids) > 0
            detail["l2_sample"] = sorted(sig["l2_union"])[:14]
            detail["scope_sample"] = sorted(scope_names)[:14]
        except Exception:
            cat = "ERROR"
            detail = {"err": traceback.format_exc(limit=1)}
            errors += 1

        counts[cat] += 1
        if cid not in _ex_seen[cat] and len(exemplars[cat]) < 8:
            _ex_seen[cat].add(cid)
            exemplars[cat].append({
                "case_id": cid, "sample_id": rec.get("sample_id"),
                "question": rec.get("question", ""),
                "gt_answers": rec.get("gt_answers"),
                "S_plan": rec.get("S_plan"), "S_select": rec.get("S_select"),
                "S_reason": rec.get("S_reason"),
                "n_decompose_facts": sig.get("n_decompose_facts") if cat != "ERROR" else None,
                "relation_hints": sig.get("hints_by_fact") if cat != "ERROR" else None,
                **detail,
            })

        if args.max_cases and n_plan_fail_samples >= args.max_cases:
            break

    # ---- Report ----
    total_classified = sum(counts[c] for c in CATS if c != "ERROR")
    print("\n" + "=" * 66)
    print(f"PLAN-FAILURE DIAGNOSIS  (S_plan==0, agent_completed samples)")
    print("=" * 66)
    print(f"Total samples scanned          : {n_total_samples}")
    print(f"  agent_failed (excluded)      : {n_agent_failed}")
    print(f"  plan-failed (S_plan==0)      : {n_plan_fail_samples}")
    print(f"  classified                   : {total_classified}  (errors: {counts['ERROR']})")
    print("-" * 66)
    recall = counts["GTE_MISS"] + counts["SCOPE_MISS"]
    decision = counts["DECISION"]
    traversal = counts["TRAVERSAL"]
    data = counts["SUBGRAPH_MISS"]
    anchor = counts["ANCHOR_MISS"]
    def pct(x): return f"{x/total_classified*100:5.1f}% ({x})" if total_classified else "  -  "
    print(f"MODEL-DECISION SIDE (model-controlled):")
    print(f"  ANCHOR_MISS  (anchored on a type/meta node)     : {pct(anchor)}")
    print(f"  DECISION     (gold in L2, not selected)         : {pct(decision)}")
    print(f"  TRAVERSAL    (gold in L2 & L3, answer not hit)  : {pct(traversal)}")
    print(f"  -> model-decision subtotal                      : {pct(anchor+decision+traversal)}")
    print(f"SYSTEM-RETRIEVAL SIDE (gold never reached model):")
    print(f"  GTE_MISS     (gold in scope, GTE didn't surface): {pct(counts['GTE_MISS'])}")
    print(f"  SCOPE_MISS   (gold pruned by structural scope)  : {pct(counts['SCOPE_MISS'])}")
    print(f"  -> retrieval subtotal                           : {pct(recall)}")
    print(f"DATA SIDE (answer absent from case subgraph)      : {pct(data)}")
    print("-" * 66)
    print(f"MODEL-DECISION  (anchor+decision+traversal) : {pct(anchor+decision+traversal)}")
    print(f"SYSTEM-RETRIEVAL (GTE+scope)                : {pct(recall)}")
    print(f"DATA/SUBGRAPH                               : {pct(data)}")
    print("=" * 66)

    out = {
        "totals": {
            "scanned": n_total_samples, "agent_failed": n_agent_failed,
            "plan_failed": n_plan_fail_samples, "classified": total_classified,
            "errors": counts["ERROR"],
        },
        "category_counts": {c: counts[c] for c in CATS},
        "category_pct": {c: round(counts[c] / total_classified, 4) for c in CATS} if total_classified else {},
        "rollup": {
            "model_decision_side": anchor + decision + traversal,
            "retrieval_side": recall,
            "data_side": data,
        },
        "exemplars": exemplars,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n> wrote {args.out}")
    print("\n--- exemplars (first 2 per category) ---")
    for c in CATS:
        if not exemplars[c]:
            continue
        print(f"\n[{c}]  ({counts[c]} total)")
        for ex in exemplars[c][:2]:
            print(f"  Q: {ex.get('question','')[:90]}")
            print(f"     GT={ex.get('gt_answers')}  gold={ex.get('gold')}  "
                  f"inL2={ex.get('gold_in_L2')}  inL3={ex.get('gold_in_L3')}  "
                  f"inScope={ex.get('gold_in_scope')}  [{ex.get('gold_note')}/{ex.get('anchor_note')}]")


if __name__ == "__main__":
    main()
