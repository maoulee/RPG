#!/usr/bin/env python3
"""Stage-level fine-grained scoring labels for the tool-calling agent.

Decomposes the single `llm_f1` into TWO independent, separately-optimizable
stage scores, written to `score_labels.json` for downstream SFT/RL consumption
(GRPO weighting, or per-trajectory-stage optimization as a rollout tree).

This scorer does NOT combine the two stages — the combination policy is left to
the downstream trainer. It only emits each stage's score + its sub-metrics.

Stages
------
S_select (Stage 7 — path selection) = f1_path × ans_recall:
    Two combined requirements for a good selection stage:
        f1_path   = precision of expanded branches = |valid| / |expanded|
                    (the chosen branches hit GT, not junk. Recall denominator
                     is the expanded set itself — the select overview truncates
                     candidate lists to cands[:4], so the true count of ALL
                     GT-bearing branches in the graph is unrecoverable, making
                     recall collapse to 1 and F1 = precision.)
        ans_recall = |U_sel ∩ GT| / |GT|
                    (the union of chosen branches covers the GT well.
                     "选了5跳到Stage8，这5条总共含多少答案".)
    S_select = f1_path × ans_recall
    Both must hold: a pile of junk branches with high recall still scores low
    (low f1_path); a precise but partial selection also scores low (low
    ans_recall). ans_recall additionally bounds S_reason's ceiling.

S_reason (Stage 8 — branch reasoning, V11 formula):
    Did the model dig out everything reachable in the expanded subgraph?
        U        = U_sel  (expanded subgraph candidate pool)
        Y        = answer entities
        U_correct = U ∩ GT   ;   Y_correct = Y ∩ GT
        retention = |Y_correct| / |U_correct|  if U_correct else 0
        final_F1  = F1(Y, GT)
        S_reason  = retention × final_F1
    retention gates the score: a high final_F1 built on answers the model could
    NOT have reached (low U_correct) still scores low.

Matching uses kgqa.core.utils (normalize + substring + fuzzy), identical to the
existing llm_f1, so scores are directly comparable.

Usage:
    python scripts/agent_stage_scorer.py \
        --results reports/agent_tree_100/results.json \
        [--compare reports/agent_100_stage5/results.json] \
        [--out score_labels.json] [--no-save]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root importable when run as a script.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from kgqa.core.utils import normalize, candidate_hit, compute_match_stats


# ---------------------------------------------------------------------------
# Trajectory parsing
# ---------------------------------------------------------------------------

def _parse_tool_content(content: str) -> Dict[str, Any]:
    """Parse a tool-role message's JSON content; return {} on failure."""
    if not content:
        return {}
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_plan_reachable(overview: str, select_pool: List[str]) -> List[str]:
    """Recover ALL entities on plan-stage paths from the overview text.

    The overview is a rendered trie. Two kinds of answer-bearing strings live
    in it that the flat `candidates`/`select_pool` list omits:

    1. Named nodes on the path: lines like ``- node1: Brad Paisley`` — these
       are intermediate entities the traversal passed through.
    2. CVT attribute values: bracket groups like
       ``[degree=Bachelor's degree, institution=Belmont University, ...]`` —
       these are attributes of a CVT node on the path. The answer entity may
       live here (e.g. ``institution=Belmont University``) even when the
       terminal `select_pool` only captured the CVT's parent.

    Returns the union of select_pool + named nodes + CVT attribute values,
    deduped (normalized). Freebase machine IDs (``m.``/``g.`` prefixes) and
    bracket keys (``degree``/``institution``) are kept out — only values.
    """
    if not overview:
        return list(select_pool)
    reachable = list(select_pool)
    seen = {normalize(c) for c in reachable}

    # 1. Named nodes: "- nodeN: <name>" or "nodeN: <name>"
    for m in re.finditer(r"node\d+\s*:\s*([^\[\]\n]+?)(?:\s{2,}|\s*$|\s+#\d)", overview):
        name = m.group(1).strip()
        # skip bare IDs / shared markers / empty
        if name and not name.startswith(("m.", "g.", "shared:")):
            n = normalize(name)
            if n and n not in seen:
                seen.add(n)
                reachable.append(name)

    # 2. CVT attribute values inside [key=value, key=value, ...]
    for m in re.finditer(r"\[([^\[\]]+)\]", overview):
        group = m.group(1)
        # split "key=value, key=value" into values
        for pair in group.split(","):
            if "=" not in pair:
                continue
            val = pair.split("=", 1)[1].strip()
            if val and not val.startswith(("m.", "g.")):
                n = normalize(val)
                if n and n not in seen:
                    seen.add(n)
                    reachable.append(val)
    return reachable


def parse_trajectory(case: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the stage signals from one case's agent_trajectory.

    Returns:
        branch_cand : {branch_id -> [candidate names]} from expand_branch calls
        expanded_ids: [branch_id, ...] in call order (deduped)
        Y           : final answer entity list (from the answer tool)
        select_pool : candidate pool from the `select` tool = the full traversal
                       over all select_relations-chosen relations. This is the
                       data source for S_plan (plan-stage GT recall).
        answer_candidates: select-stage global pool (result-level fallback for U)
        has_select_relations: whether select_relations was called
        has_select  : whether select was called
        has_answer  : whether answer was called
    """
    traj = case.get("agent_trajectory") or []
    branch_cand: Dict[str, List[str]] = {}
    expanded_ids: List[str] = []
    Y: List[str] = []
    select_pool: List[str] = []
    plan_reachable: List[str] = []   # ALL entities on plan-stage paths + CVT attr values
    expand_triples: List[str] = []   # all entities appearing in expand's (h,r,t) triples
    expand_candidates: List[str] = []   # flat `candidates` list from expand (terminal entities)
    expand_attr_values: List[str] = []  # raw CVT `candidate_attrs` lines (key=value) from expand
    selected_relations: Dict[str, List[str]] = {}
    has_select_relations = False
    has_select = False
    has_answer = False

    for step in traj:
        if step.get("role") != "tool":
            continue
        name = step.get("name", "")
        data = _parse_tool_content(step.get("content", ""))
        if not data:
            continue

        if name == "select_relations":
            has_select_relations = True
            sel = data.get("selected") or {}
            if isinstance(sel, dict):
                for fid, rels in sel.items():
                    selected_relations[str(fid)] = list(rels) if isinstance(rels, list) else []
            # 4-tool merge: select_relations runs traversal inline and returns
            # the plan-stage candidate pool in `candidates` (a flat list, same
            # shape the legacy `select` tool produced). Capture it here so
            # S_plan can be measured even when no standalone select call exists.
            srels_cands = data.get("candidates") or []
            if isinstance(srels_cands, list) and srels_cands:
                select_pool = [str(c) for c in srels_cands if c]
            # S_plan measures whether the plan REACHED the answer — i.e. whether
            # any entity or CVT attribute value on the traversed paths equals GT.
            # The flat `candidates` list is only the last-step terminal entities
            # and omits CVT attribute values that appear in the overview text
            # (e.g. "institution=Belmont University" sits in a CVT node rendered
            # as "[degree=..., institution=Belmont University, ...]"). Parse the
            # overview to recover ALL entities on plan-stage paths: named nodes
            # AND CVT attribute values. This is what "plan reached it" means.
            overview = data.get("overview") or ""
            plan_reachable = _extract_plan_reachable(overview, select_pool)
        elif name == "select":
            has_select = True
            # Legacy 6-tool flow: select's `candidates` = full traversal pool
            # over chosen relations. In the 4-tool flow this data comes from
            # select_relations instead (handled above).
            cands = data.get("candidates") or []
            if isinstance(cands, list):
                select_pool = [str(c) for c in cands if c]
            overview = data.get("overview") or ""
            if overview:
                plan_reachable = _extract_plan_reachable(overview, select_pool)
        elif name in ("expand_branch", "expand_branches"):
            # S_select measures whether the EXPANDED paths carry the answer.
            # The expand result includes a `triples` list of (h, r, t) — every
            # entity appearing in those triples (both endpoints, plus any CVT
            # attribute value surfaced as a tail) is "on the selected path".
            # This is broader than per-branch candidate lists, which only keep
            # terminal/leaf entities.
            trips = data.get("triples") or []
            for tr in trips:
                # triples are rendered as "(h, r, t)" strings or [h, r, t] lists
                if isinstance(tr, str):
                    parts = [p.strip().strip("()") for p in tr.split(",")]
                elif isinstance(tr, (list, tuple)):
                    parts = [str(p).strip() for p in tr]
                else:
                    continue
                for p in parts:
                    if p and not p.startswith("m.") and not p.startswith("g."):
                        expand_triples.append(p)
            # CVT-transparent capture: the expand result also carries a flat
            # `candidates` list and `candidate_attrs` (CVT key=value lines). The
            # answer frequently lives ONLY here — as a CVT attribute value (e.g.
            # "institution=Belmont University"), never in the (h,r,t) triples.
            # Score against all three or the answer is scored unreachable (=0).
            for c in (data.get("candidates") or []):
                if c:
                    expand_candidates.append(str(c))
            ca = data.get("candidate_attrs")
            if isinstance(ca, list):
                expand_attr_values.extend(str(x) for x in ca if x)
            elif isinstance(ca, str) and ca:
                expand_attr_values.append(ca)
            # Current agent format: `expand_branches` returns branches_expanded
            # (ordered id list) + per_branch [{branch_id, candidates}]. Older
            # single-branch format used one branch_id + flat candidates.
            per_branch = data.get("per_branch")
            if per_branch and isinstance(per_branch, list):
                # New format: per-branch candidate split.
                ids_this = data.get("branches_expanded") or [
                    str(pb.get("branch_id", "")) for pb in per_branch]
                for bid_raw in ids_this:
                    bid = str(bid_raw)
                    if bid and bid not in branch_cand:
                        expanded_ids.append(bid)
                for pb in per_branch:
                    bid = str(pb.get("branch_id", ""))
                    if not bid:
                        continue
                    cands = pb.get("candidates") or []
                    merged = list(branch_cand.get(bid, []))
                    seen = {normalize(c) for c in merged}
                    for c in cands:
                        if c and normalize(c) not in seen:
                            merged.append(c)
                            seen.add(normalize(c))
                    branch_cand[bid] = merged
            else:
                # Legacy single-branch format.
                bid = str(data.get("branch_id", ""))
                cands = data.get("candidates") or []
                if bid:
                    if bid not in branch_cand:
                        expanded_ids.append(bid)
                    # Merge in case a branch is expanded twice.
                    merged = list(branch_cand.get(bid, []))
                    seen = {normalize(c) for c in merged}
                    for c in cands:
                        if c and normalize(c) not in seen:
                            merged.append(c)
                            seen.add(normalize(c))
                    branch_cand[bid] = merged
        elif name == "answer":
            ents = data.get("entities") or []
            if isinstance(ents, list):
                Y = [str(e).strip() for e in ents if str(e).strip()]
            has_answer = True

    return {
        "branch_cand": branch_cand,
        "expanded_ids": expanded_ids,
        "Y": Y,
        "select_pool": select_pool,           # last-step terminal entities (legacy)
        "plan_reachable": plan_reachable,      # ALL entities + CVT attrs on plan paths
        "expand_triples": expand_triples,      # entities on expanded (h,r,t) triples
        "expand_candidates": expand_candidates,    # flat candidates list from expand
        "expand_attr_values": expand_attr_values,  # CVT candidate_attrs lines from expand
        "selected_relations": selected_relations,  # {fact_id: [rels]} from select_relations
        "has_select_relations": has_select_relations,
        "has_select": has_select,
        "has_answer": has_answer,
        "answer_candidates": list(case.get("answer_candidates") or []),
    }


# ---------------------------------------------------------------------------
# Stage scores
# ---------------------------------------------------------------------------

def _norm_set(items: List[str]) -> List[str]:
    """Normalize + dedup a string list, dropping empties."""
    seen = set()
    out = []
    for it in items:
        nc = normalize(it)
        if nc and nc not in seen:
            seen.add(nc)
            out.append(it)
    return out


def score_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Compute three stage scores per the canonical definition:

    S_plan   (select_relations → traverse): GT recall in the full traversal
             pool produced by the `select` tool (= every relation path the
             plan unlocked). Did the plan unlock paths that reach GT?

    S_select (expand_branch): precision of expanded branches — what fraction
             of the branches the model chose to expand actually carry GT?
             Capped by S_plan: you can't precisely expand what the plan never
             reached.  S_select = branch_precision × S_plan.

    S_reason (answer): F1 of the model's final answer vs the GT that was
             actually reachable in the expanded pool U. Capped by S_select:
             you can't reason out answers the selection never surfaced.
             S_reason = answer_F1_in_U × S_select.

    Each score is the upper bound (ceiling) of the next — plan gates select,
    select gates reason. This mirrors the user's definition where each stage's
    recall serves as the cap on the downstream stage.
    """
    cid = case.get("case_id", "?")
    question = case.get("question", "")
    gt = list(case.get("gt_answers") or [])
    p = parse_trajectory(case)

    branch_cand = p["branch_cand"]
    expanded_ids = p["expanded_ids"]
    Y = p["Y"]
    select_pool = p["select_pool"]
    plan_reachable = p.get("plan_reachable") or []
    notes: List[str] = []

    # Stage-pipeline baseline compatibility (no agent_trajectory → Y from llm_answer)
    is_baseline = (not p["has_select"]) and (not p["has_answer"])
    if is_baseline:
        notes.append("stage_pipeline_baseline")
        raw_ans = case.get("llm_answer", "") or ""
        Y = [e.strip() for e in raw_ans.split("|") if e.strip()] if raw_ans else []

    if not gt:
        return {
            "case_id": cid, "question": question, "gt_answers": gt,
            "S_plan": None, "S_select": None, "S_reason": None,
            "detail": {}, "notes": ["no_gt"],
        }

    if not p["has_select_relations"]:
        notes.append("no_select_relations_call")
    if not p["has_select"]:
        notes.append("no_select_call")
    if not expanded_ids:
        notes.append("no_expand_call")

    gt_norm = [normalize(g) for g in gt]

    def _recall_in(pool: List[str]) -> float:
        """Fraction of GT present in a candidate pool.

        Uses STRICT matching (_matches_strict): a pool entry counts as
        reaching GT only if it is at least as long as GT and contains it, or
        is exact. This prevents a short entity (e.g. "Spain") from counting
        as reaching a longer GT ("Spain national football team") — the path
        must actually arrive at the team entity, not just the country."""
        if not gt_norm:
            return 0.0
        pool_norm = [normalize(c) for c in pool] if pool else []
        hit = sum(1 for g in gt_norm if any(_matches_strict(g, u) for u in pool_norm))
        return hit / len(gt_norm)

    # ---- FULL structured reachable pools (CVT-transparent) ----
    # The agent surfaces graph entities in SEVERAL structured fields per stage.
    # The old code scored each stage against ONE field (S_plan: answer_candidates
    # only; S_select: expand triples only) → missed answers living in the others,
    # chiefly CVT attribute values (candidate_attrs) and the flat `candidates`
    # list. That produced the ~57% false-zero artifact (S_select=0 / S_plan=0
    # even though the answer was reachable). Score against the per-stage UNION.
    expand_cands = list(p.get("expand_candidates") or [])
    expand_attrs = list(p.get("expand_attr_values") or [])
    bc_flat = [c for bid in expanded_ids for c in branch_cand.get(bid, [])]
    expand_full = (list(p.get("expand_triples") or []) + expand_cands
                   + expand_attrs + bc_flat)
    plan_full = (list(p["answer_candidates"] or [])
                 + list(p.get("select_pool") or [])
                 + list(plan_reachable or []))

    # ---- U: the pool the model could actually reason over at answer time ----
    # Union of the expanded subgraph (incl CVT attribute values) + everything on
    # plan-stage paths. The model SAW the overview/tree and could reason over all
    # of it, so CVT attribute values count as reachable for S_reason too — this
    # stops S_reason being forced to 0 by a CVT-only answer (the S_reason artifact).
    U_list = expand_full + list(plan_reachable or [])
    U_source = "expand_full+plan_reachable"
    if not U_list:
        U_list = list(p["answer_candidates"] or [])
        U_source = "answer_candidates_fallback"

    # =====================================================================
    # S_plan: did the plan REACH the answer? (structured pool UNION)
    # answer_candidates (captured at sample time) + select_relations `candidates`
    # + plan_reachable (named nodes + CVT attr values parsed from the overview).
    # =====================================================================
    plan_pool = plan_full
    S_plan = _recall_in(plan_pool)
    if not plan_pool:
        notes.append("no_structured_pool")

    # =====================================================================
    # S_select: did the EXPANDED paths carry the answer? (structured UNION)
    # expand triples endpoints + flat candidates + CVT candidate_attrs + branch
    # candidates, capped by S_plan. No expand → pass-through (S_select = S_plan).
    # =====================================================================
    n_expanded = len(expanded_ids)
    if n_expanded and expand_full:
        S_select_raw = _recall_in(expand_full)
    elif n_expanded:
        S_select_raw = 0.0
        notes.append("select_empty_pool")
    else:
        # No expand call → selection is pass-through; the model reasoned over
        # whatever the plan exposed (the overview). S_select = S_plan.
        S_select_raw = S_plan
        notes.append("select_passthrough")
    S_select = min(S_select_raw, S_plan) if S_plan else 0.0

    # =====================================================================
    # S_reason: answer F1 within the reachable pool U, capped by S_select.
    #   answer_F1_in_U = F1 of (Y ∩ U) vs (GT ∩ U)  — only count answers the
    #                    model could have reached in the expanded pool.
    #   S_reason = answer_F1_in_U × S_select        (select is the ceiling)
    # =====================================================================
    U_correct = [g for g in gt if candidate_hit([g], U_list)]      # GT in U
    Y_in_U = [y for y in Y if candidate_hit([y], U_list) or True]  # keep all Y for F1
    # Compute F1 restricted to what's reachable: gold = GT∩U, pred = Y∩(GT∩U) hits
    reachable_gold = U_correct
    reachable_pred_hit = [y for y in Y if candidate_hit([y], reachable_gold)] if reachable_gold else []
    if reachable_gold:
        reason_precision = len(reachable_pred_hit) / max(len(Y), 1)
        reason_recall = len(set(normalize(y) for y in reachable_pred_hit)) / len(reachable_gold)
        # simpler: just use compute_match_stats on Y vs reachable_gold
        rstats = compute_match_stats(Y, reachable_gold)
        answer_f1_in_U = rstats.get("f1", 0.0)
    else:
        answer_f1_in_U = 0.0
        notes.append("gt_unreachable_in_U")
    S_reason = answer_f1_in_U * S_select

    # diagnostics
    if U_correct and len(reachable_pred_hit) < len(U_correct):
        notes.append("reason_leak")
    if (S_plan or 0) == 0:
        notes.append("plan_fail")

    detail = {
        "plan": {
            "S_plan": round(S_plan, 4) if S_plan is not None else None,
            "select_pool_size": len(select_pool),
            "plan_recall": round(S_plan, 4) if S_plan is not None else None,
            "selected_relations": p["selected_relations"],
        },
        "select": {
            "S_select": round(S_select, 4),
            "select_recall": round(S_select_raw, 4) if n_expanded else None,
            "n_expanded": n_expanded,
            "expand_ents_size": len(expand_full) if n_expanded else 0,
            "expanded_ids": expanded_ids,
            "U_size": len(U_list),
            "U_source": U_source,
        },
        "reason": {
            "S_reason": round(S_reason, 4),
            "answer_f1_in_U": round(answer_f1_in_U, 4),
            "U_correct_n": len(U_correct),
            "reachable_pred_hit_n": len(reachable_pred_hit) if reachable_gold else 0,
            "GT_n": len(gt),
            "U_correct": U_correct,
        },
    }

    return {
        "case_id": cid, "question": question, "gt_answers": gt,
        "S_plan": round(S_plan, 4) if S_plan is not None else None,
        "S_select": round(S_select, 4),
        "S_reason": round(S_reason, 4),
        "detail": detail,
        "notes": notes,
    }


def _matches(a: str, b: str) -> bool:
    """Substring / equality match on already-normalized strings (no fuzzy here
    — fuzzy GT-matching is handled inside candidate_hit / compute_match_stats)."""
    return a == b or a in b or b in a


def _matches_strict(gt_norm: str, cand_norm: str) -> bool:
    """Stricter match for path-reachability scoring (S_plan / S_select).

    The loose `_matches` (bidirectional substring) is right for answer
    matching, where "Brad Pitt" should match "Brad Pitts". But for
    path-reachability it over-counts: a path that contains "Spain" must NOT
    count as reaching GT "Spain national football team" — one is a country,
    the other a team, and the path never actually arrived at the team.

    Rule: exact equality, OR the candidate is at least as long as the GT and
    contains it (cand ⊇ gt). This lets "Spain national football team" match
    "the spain national football team" but blocks "spain" from matching
    "spain national football team". When the candidate is SHORTER than the
    GT, a substring match is not enough — it must be exact.
    """
    if gt_norm == cand_norm:
        return True
    # candidate longer or equal → allow cand containing gt (extra qualifier ok)
    if len(cand_norm) >= len(gt_norm) and gt_norm in cand_norm:
        return True
    return False


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------

def aggregate(labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mean of each score + sub-metric over scored (non-None) cases."""
    scored = [l for l in labels if l.get("S_select") is not None]
    n = len(scored)
    if n == 0:
        return {"n": 0}

    def _mean(key_path: str) -> float:
        vals = []
        for l in scored:
            node = l
            for k in key_path.split("."):
                node = node.get(k, {}) if isinstance(node, dict) else {}
                if not isinstance(node, dict):
                    break
            if isinstance(node, (int, float)):
                vals.append(node)
        return sum(vals) / len(vals) if vals else 0.0

    s_select = sum(l["S_select"] for l in scored) / n
    s_reason = sum(l["S_reason"] for l in scored) / n
    s_plan = sum((l["S_plan"] or 0) for l in scored) / n

    return {
        "n": n,
        "S_plan_avg": round(s_plan, 4),
        "S_select_avg": round(s_select, 4),
        "S_reason_avg": round(s_reason, 4),
        "select_recall_avg": round(_mean("detail.select.select_recall"), 4),
        "answer_f1_in_U_avg": round(_mean("detail.reason.answer_f1_in_U"), 4),
        "select_fail_n": sum(1 for l in scored if "select_fail" in l.get("notes", [])),
        "reason_leak_n": sum(1 for l in scored if "reason_leak" in l.get("notes", [])),
        "gt_unreachable_n": sum(1 for l in scored if "gt_unreachable_in_U" in l.get("notes", [])),
        "plan_fail_n": sum(1 for l in scored if "plan_fail" in l.get("notes", [])),
        "select_passthrough_n": sum(1 for l in scored if "select_passthrough" in l.get("notes", [])),
        "no_expand_n": sum(1 for l in scored if "no_expand_call" in l.get("notes", [])),
    }


def print_per_case(labels: List[Dict[str, Any]], sort_by: str = "S_reason",
                   limit: int = 0) -> None:
    """Print per-case one-liners, worst-first, for failure inspection."""
    scored = [l for l in labels if l.get("S_reason") is not None]
    rev = False if sort_by in ("S_select",) else True
    scored.sort(key=lambda l: l.get(sort_by, 0.0), reverse=rev)
    if limit:
        scored = scored[:limit]
    print(f"\n--- per-case (sorted by {sort_by}, {'worst' if rev else 'best'} first) ---")
    for l in scored:
        d = l["detail"]
        sel = d["select"]; rea = d["reason"]
        print(f"  [{l['case_id'][:22]:22s}] "
              f"S_plan={l['S_plan'] if l['S_plan'] is not None else 0:.2f} "
              f"S_sel={l['S_select']:.2f} S_rea={l['S_reason']:.2f} "
              f"[srec={sel['select_recall']:.2f} "
              f"exp={sel['n_expanded']}/{sel['expand_ents_size']}/{sel['U_size']} | "
              f"f1U={rea['answer_f1_in_U']:.2f} "
              f"Uc={rea['U_correct_n']} hit={rea['reachable_pred_hit_n']}/{rea['GT_n']}] "
              f"{','.join(l.get('notes', []))} | {l['question'][:34]}")


def print_summary(agg: Dict[str, Any], label: str) -> None:
    print(f"\n=== {label} ({agg['n']} scored cases) ===")
    print(f"  S_plan_avg   = {agg['S_plan_avg']:.4f}   (GT recall over plan-path entities + CVT attrs)")
    print(f"  S_select_avg = {agg['S_select_avg']:.4f}   "
          f"(select_recall={agg['select_recall_avg']:.3f}, capped by S_plan)")
    print(f"  S_reason_avg = {agg['S_reason_avg']:.4f}   "
          f"(answer_f1_in_U={agg['answer_f1_in_U_avg']:.3f} × S_select)")
    print(f"  diagnostics: plan_fail={agg['plan_fail_n']} "
          f"select_fail={agg['select_fail_n']} "
          f"reason_leak={agg['reason_leak_n']} "
          f"gt_unreachable={agg['gt_unreachable_n']} "
          f"select_passthrough={agg['select_passthrough_n']} "
          f"no_expand={agg['no_expand_n']}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def print_comparison(labels_a: List[Dict], labels_b: List[Dict],
                     la: str, lb: str, top_n: int = 15) -> None:
    map_a = {l["case_id"]: l for l in labels_a}
    map_b = {l["case_id"]: l for l in labels_b}
    common = sorted(set(map_a) & set(map_b))

    rows = []
    for cid in common:
        a, b = map_a[cid], map_b[cid]
        if a.get("S_select") is None or b.get("S_select") is None:
            continue
        rows.append({
            "cid": cid, "q": a["question"],
            "sel_a": a["S_select"], "sel_b": b["S_select"],
            "rea_a": a["S_reason"], "rea_b": b["S_reason"],
            "dsel": b["S_select"] - a["S_select"],
            "drea": b["S_reason"] - a["S_reason"],
        })

    sel_up = sum(1 for r in rows if r["dsel"] > 1e-6)
    sel_dn = sum(1 for r in rows if r["dsel"] < -1e-6)
    rea_up = sum(1 for r in rows if r["drea"] > 1e-6)
    rea_dn = sum(1 for r in rows if r["drea"] < -1e-6)
    mean_dsel = sum(r["dsel"] for r in rows) / len(rows) if rows else 0.0
    mean_drea = sum(r["drea"] for r in rows) / len(rows) if rows else 0.0

    print(f"\n=== {lb} vs {la} ({len(rows)} common scored cases) ===")
    print(f"  S_select: up={sel_up} down={sel_dn} same={len(rows)-sel_up-sel_dn} "
          f"| mean Δ = {mean_dsel:+.4f}")
    print(f"  S_reason: up={rea_up} down={rea_dn} same={len(rows)-rea_up-rea_dn} "
          f"| mean Δ = {mean_drea:+.4f}")

    # Top movement by |ΔS_reason|
    rows.sort(key=lambda r: -abs(r["drea"]))
    print(f"\n  top {top_n} by |ΔS_reason|:")
    print(f"    {'case':22s} {'sel_a':>6} {'sel_b':>6} {'Δsel':>7} "
          f"{'rea_a':>6} {'rea_b':>6} {'Δrea':>7}  q")
    for r in rows[:top_n]:
        print(f"    {r['cid'][:22]:22s} {r['sel_a']:6.2f} {r['sel_b']:6.2f} "
              f"{r['dsel']:+7.2f} {r['rea_a']:6.2f} {r['rea_b']:6.2f} "
              f"{r['drea']:+7.2f}  {r['q'][:30]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_results(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text())


def main():
    ap = argparse.ArgumentParser(description="Stage-level scoring labels for the agent")
    ap.add_argument("--results", type=Path, required=True,
                    help="results.json from run_agent.py")
    ap.add_argument("--compare", type=Path, default=None,
                    help="second results.json for A/B delta")
    ap.add_argument("--out", type=Path, default=None,
                    help="output score_labels.json path (default: beside results)")
    ap.add_argument("--no-save", action="store_true",
                    help="do not write score_labels.json")
    ap.add_argument("--per-case", action="store_true",
                    help="print per-case one-liners (worst S_reason first)")
    ap.add_argument("--per-case-limit", type=int, default=0,
                    help="limit per-case rows (0 = all)")
    ap.add_argument("--compare-top", type=int, default=15,
                    help="top-N delta rows in compare mode")
    args = ap.parse_args()

    primary = load_results(args.results)
    labels = [score_case(c) for c in primary]
    agg = aggregate(labels)

    print_summary(agg, args.results.name)
    if args.per_case:
        print_per_case(labels, limit=args.per_case_limit)

    if not args.no_save:
        out_path = args.out or (args.results.parent / "score_labels.json")
        payload = {"results_path": str(args.results), "aggregate": agg,
                   "labels": labels}
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\n> wrote {out_path}")

    if args.compare and args.compare.exists():
        comp = load_results(args.compare)
        comp_labels = [score_case(c) for c in comp]
        comp_agg = aggregate(comp_labels)
        print_summary(comp_agg, args.compare.name)
        print_comparison(labels, comp_labels,
                         la=args.results.stem, lb=args.compare.stem,
                         top_n=args.compare_top)


if __name__ == "__main__":
    main()
