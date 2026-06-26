#!/usr/bin/env python3
"""A/B comparison: agent run vs baseline, with hop split + stage scores.

Usage:
    python scripts/ab_compare.py \
        --agent reports/agent_tree_400/results.json \
        --baseline reports/baselineA_400/results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Reuse the stage scorer's logic (same dir).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_stage_scorer import score_case, aggregate  # noqa: E402


def _hop_stats(rows, label):
    n = len(rows)
    if n == 0:
        return f"{label}: (empty)"
    gt = sum(1 for r in rows if r.get("gt_hit"))
    llm = sum(1 for r in rows if r.get("llm_hit"))
    f1 = sum(r.get("llm_f1", 0) for r in rows) / n
    return f"{label}: n={n:3d} GT={gt}/{n}({100*gt/n:3.0f}%) LLM_hit={llm}/{n}({100*llm/n:3.0f}%) F1={f1:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, required=True)
    args = ap.parse_args()

    agent = json.loads(args.agent.read_text())
    base = json.loads(args.baseline.read_text())

    # Align by case_id so the comparison is on the SAME cases.
    agent_map = {r["case_id"]: r for r in agent}
    base_map = {r["case_id"]: r for r in base}
    common = sorted(set(agent_map) & set(base_map))
    a = [agent_map[c] for c in common]
    b = [base_map[c] for c in common]

    print("=" * 78)
    print(f"A/B over {len(common)} common cases")
    print(f"  AGENT    : {args.agent}")
    print(f"  BASELINE : {args.baseline}")
    print("=" * 78)

    # ---- overall + hop split ----
    def hop_split(rows, tag):
        one = [r for r in rows if len(r.get("gt_answers", [])) <= 1]
        mul = [r for r in rows if len(r.get("gt_answers", [])) >= 2]
        print(f"\n--- {tag} ---")
        print(" ", _hop_stats(rows, "all   "))
        print(" ", _hop_stats(one, "1-hop "))
        print(" ", _hop_stats(mul, "2+-hop"))

    hop_split(a, "AGENT (agent_tree)")
    hop_split(b, "BASELINE (v2 stage)")

    # ---- stage scores (agent only; baseline has no expand_branch) ----
    print("\n" + "=" * 78)
    print("STAGE SCORES (agent_stage_scorer)")
    print("=" * 78)
    a_labels = [score_case(r) for r in a]
    a_agg = aggregate(a_labels)
    print(f"\nAGENT stage scores ({a_agg['n']} scored):")
    print(f"  S_select_avg = {a_agg['S_select_avg']:.4f}  "
          f"(f1_path={a_agg['f1_path_avg']:.3f} × ans_recall={a_agg['ans_recall_avg']:.3f})")
    print(f"  S_reason_avg = {a_agg['S_reason_avg']:.4f}  "
          f"(final_F1={a_agg['final_F1_avg']:.3f}, retention={a_agg['retention_avg']:.3f})")
    print(f"  diagnostics: select_fail={a_agg['select_fail_n']} "
          f"reason_leak={a_agg['reason_leak_n']} "
          f"gt_unreachable={a_agg['gt_unreachable_n']} "
          f"no_expand={a_agg['no_expand_n']}")

    # baseline stage scores (no agent_trajectory: S_select=0 by design since it
    # has no expand_branch action; S_reason is computed from its llm_answer
    # against its global candidate pool — a fair reasoning-quality compare).
    b_labels = [score_case(r) for r in b]
    b_agg = aggregate(b_labels)
    print(f"\nBASELINE stage scores ({b_agg['n']} scored) — stage pipeline, no expand_branch:")
    print(f"  S_select_avg = {b_agg['S_select_avg']:.4f}  "
          f"(0 by design; its global pool ans_recall={b_agg['ans_recall_avg']:.3f})")
    print(f"  S_reason_avg = {b_agg['S_reason_avg']:.4f}  "
          f"(final_F1={b_agg['final_F1_avg']:.3f}, retention={b_agg['retention_avg']:.3f})")

    # ---- per-case win/loss on llm_hit ----
    a_hit = {r["case_id"]: r.get("llm_hit") for r in a}
    b_hit = {r["case_id"]: r.get("llm_hit") for r in b}
    gained = [c for c in common if a_hit[c] and not b_hit[c]]
    lost = [c for c in common if b_hit[c] and not a_hit[c]]
    print(f"\n--- per-case LLM_hit movement ---")
    print(f"  agent gained: {len(gained)}   agent lost: {len(lost)}   "
          f"net = {len(gained) - len(lost):+d}")

    if lost:
        print(f"\n  sample LOST cases (agent wrong, baseline right) — first 10:")
        am = {r["case_id"]: r for r in a}
        for c in lost[:10]:
            r = am[c]
            print(f"    {c[:24]:24s} | {r.get('question','')[:40]:40s} "
                  f"| agent_ans={r.get('llm_answer','')[:30]}")

    if gained:
        print(f"\n  sample GAINED cases (agent right, baseline wrong) — first 10:")
        am = {r["case_id"]: r for r in a}
        for c in gained[:10]:
            r = am[c]
            print(f"    {c[:24]:24s} | {r.get('question','')[:40]:40s}")


if __name__ == "__main__":
    main()
