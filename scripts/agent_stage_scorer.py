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


def parse_trajectory(case: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the stage signals from one case's agent_trajectory.

    Returns:
        branch_cand : {branch_id -> [candidate names]} from expand_branch calls
        expanded_ids: [branch_id, ...] in call order (deduped)
        Y           : final answer entity list (from the answer tool)
        answer_candidates: select-stage global pool (result-level fallback for U)
        has_select  : whether select was called
    """
    traj = case.get("agent_trajectory") or []
    branch_cand: Dict[str, List[str]] = {}
    expanded_ids: List[str] = []
    Y: List[str] = []
    has_select = False
    has_answer = False

    for step in traj:
        if step.get("role") != "tool":
            continue
        name = step.get("name", "")
        data = _parse_tool_content(step.get("content", ""))
        if not data:
            continue

        if name == "select":
            has_select = True
        elif name == "expand_branch":
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
    """Compute S_select + S_reason + sub-metrics for one case."""
    cid = case.get("case_id", "?")
    question = case.get("question", "")
    gt = list(case.get("gt_answers") or [])
    p = parse_trajectory(case)

    branch_cand = p["branch_cand"]
    expanded_ids = p["expanded_ids"]
    Y = p["Y"]
    notes: List[str] = []

    # Stage-pipeline baseline compatibility: it has no agent_trajectory, so
    # parse_trajectory yields Y=[]. Fall back to its own llm_answer / global
    # candidate pool so S_reason is still computable for A/B reasoning compare.
    is_baseline = (not p["has_select"]) and (not p["has_answer"])
    if is_baseline:
        notes.append("stage_pipeline_baseline")
        raw_ans = case.get("llm_answer", "") or ""
        Y = [e.strip() for e in raw_ans.split("|") if e.strip()] if raw_ans else []

    # Edge: no GT
    if not gt:
        return {
            "case_id": cid, "question": question, "gt_answers": gt,
            "S_select": None, "S_reason": None,
            "detail": {}, "notes": ["no_gt"],
        }

    if not p["has_select"]:
        notes.append("no_select_call")
    if not expanded_ids:
        notes.append("no_expand_call")

    # ---- U: expanded-subgraph candidate pool (fallback to global pool) ----
    U_list: List[str] = []
    for bid in expanded_ids:
        U_list.extend(branch_cand.get(bid, []))
    U_source = "expanded"
    if not U_list:
        # Fallback: no expand calls — use select's global candidate pool so the
        # reason score (retention) is still meaningful, not forced to 0.
        U_list = p["answer_candidates"]
        U_source = "answer_candidates_fallback"

    # ---- valid branches: expanded branches whose candidates hit GT ----
    valid_ids = [bid for bid in expanded_ids
                 if candidate_hit(branch_cand.get(bid, []), gt)]

    # ---- S_select = f1_path × ans_recall ----
    # Two combined requirements for a good selection stage:
    #   1. f1_path   — the chosen branches are valid (hit GT), not junk.
    #                  (= precision of expanded branches; recall denominator is
    #                   the expanded set itself, since the select overview
    #                   truncates candidate lists to cands[:4] so the true count
    #                   of ALL GT-bearing branches in the graph is unrecoverable.)
    #   2. ans_recall — the union of chosen branches covers the GT well.
    # "路径选得好" AND "这些路径把答案高召回" — both must hold. Multiplying
    # encodes: great recall from a pile of junk branches (low f1_path) still
    # scores low; a precise but partial selection (low ans_recall) also scores
    # low. ans_recall also bounds S_reason's ceiling.
    n_expanded = len(expanded_ids)
    n_valid = len(valid_ids)

    select_precision = (n_valid / n_expanded) if n_expanded else 0.0
    f1_path = select_precision   # recall=1 → F1 = precision

    # ans_recall: GT items covered by the union of expanded branches (= U).
    U_norm = _norm_set(U_list)
    gt_norm = [normalize(g) for g in gt]
    gt_hit_in_U = sum(1 for g in gt_norm
                      if any(_matches(g, u) for u in (normalize(u) for u in U_list)))
    ans_recall = gt_hit_in_U / len(gt_norm) if gt_norm else 0.0

    # No expand calls → no selection happened; the sub-metrics via the
    # global-pool fallback are still informative as diagnostics but the stage
    # score is 0 (the model did not perform a selection action).
    if n_expanded == 0:
        S_select = 0.0
    else:
        S_select = f1_path * ans_recall

    # ---- S_reason (V11: retention × final_F1) ----
    # U_correct : GT items reachable in the expanded pool U
    # Y_correct : GT items reachable in U AND actually answered by the model.
    #   NB: Y_correct is INTERSECTED with U_correct (not |Y ∩ GT|) so that
    #   retention = |Y_correct| / |U_correct| stays ≤ 1, matching V11's premise
    #   that the model can only "retain" what was reachable in U. Answers the
    #   model gave that were NOT in U (lucky guesses / from the global pool)
    #   don't raise retention — they're already credited in final_F1.
    U_correct = [g for g in gt if candidate_hit([g], U_list)]
    Y_correct = [g for g in U_correct if candidate_hit([g], Y)]

    retention = (len(Y_correct) / len(U_correct)) if U_correct else 0.0
    final_stats = compute_match_stats(Y, gt)
    final_f1 = final_stats.get("f1", 0.0)
    S_reason = retention * final_f1

    if not U_correct:
        notes.append("gt_unreachable_in_U")
    if U_correct and len(Y_correct) < len(U_correct):
        notes.append("reason_leak")        # model could have reached more than it answered
    if ans_recall == 0:
        notes.append("select_fail")        # expanded pool missed GT entirely

    detail = {
        "select": {
            "S_select": round(S_select, 4),
            "ans_recall": round(ans_recall, 4),
            "f1_path": round(f1_path, 4),
            "select_precision": round(select_precision, 4),
            "n_expanded": n_expanded,
            "n_valid": n_valid,
            "expanded_ids": expanded_ids,
            "valid_ids": valid_ids,
            "U_sel_size": len(U_norm),
            "U_source": U_source,
        },
        "reason": {
            "final_F1": round(final_f1, 4),
            "final_precision": round(final_stats.get("precision", 0.0), 4),
            "final_recall": round(final_stats.get("recall", 0.0), 4),
            "retention": round(retention, 4),
            "U_correct_n": len(U_correct),
            "Y_correct_n": len(Y_correct),
            "GT_n": len(gt),
            "U_correct": U_correct,
            "Y_correct": Y_correct,
            "missed_in_U": [g for g in gt if g not in U_correct],   # GT not reachable in expanded pool
            "missed_in_Y": [g for g in U_correct if g not in Y_correct],  # reachable but not answered
        },
    }

    return {
        "case_id": cid, "question": question, "gt_answers": gt,
        "S_select": round(S_select, 4),
        "S_reason": round(S_reason, 4),
        "detail": detail,
        "notes": notes,
    }


def _matches(a: str, b: str) -> bool:
    """Substring / equality match on already-normalized strings (no fuzzy here
    — fuzzy GT-matching is handled inside candidate_hit / compute_match_stats)."""
    return a == b or a in b or b in a


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

    return {
        "n": n,
        "S_select_avg": round(s_select, 4),
        "S_reason_avg": round(s_reason, 4),
        "ans_recall_avg": round(_mean("detail.select.ans_recall"), 4),
        "f1_path_avg": round(_mean("detail.select.f1_path"), 4),
        "select_precision_avg": round(_mean("detail.select.select_precision"), 4),
        "final_F1_avg": round(_mean("detail.reason.final_F1"), 4),
        "retention_avg": round(_mean("detail.reason.retention"), 4),
        "select_fail_n": sum(1 for l in scored if "select_fail" in l.get("notes", [])),
        "reason_leak_n": sum(1 for l in scored if "reason_leak" in l.get("notes", [])),
        "gt_unreachable_n": sum(1 for l in scored if "gt_unreachable_in_U" in l.get("notes", [])),
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
              f"S_sel={l['S_select']:.2f} S_rea={l['S_reason']:.2f} "
              f"[ansR={sel['ans_recall']:.2f} f1path={sel['f1_path']:.2f} "
              f"exp={sel['n_expanded']}/{sel['n_valid']} | "
              f"ret={rea['retention']:.2f} f1={rea['final_F1']:.2f} "
              f"Uc={rea['U_correct_n']} Yc={rea['Y_correct_n']}/{rea['GT_n']}] "
              f"{','.join(l.get('notes', []))} | {l['question'][:34]}")


def print_summary(agg: Dict[str, Any], label: str) -> None:
    print(f"\n=== {label} ({agg['n']} scored cases) ===")
    print(f"  S_select_avg = {agg['S_select_avg']:.4f}   (= f1_path × ans_recall)")
    print(f"    f1_path={agg['f1_path_avg']:.3f} (expanded branches hit GT), "
          f"ans_recall={agg['ans_recall_avg']:.3f} (union covers GT; reason ceiling)")
    print(f"  S_reason_avg = {agg['S_reason_avg']:.4f}   "
          f"(final_F1={agg['final_F1_avg']:.3f}, retention={agg['retention_avg']:.3f})")
    print(f"  diagnostics: select_fail={agg['select_fail_n']} "
          f"reason_leak={agg['reason_leak_n']} "
          f"gt_unreachable={agg['gt_unreachable_n']} "
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
