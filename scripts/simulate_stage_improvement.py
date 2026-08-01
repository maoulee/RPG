#!/usr/bin/env python3
"""
Stage-wise improvement SIMULATION for PPT.
Model (verified on eval v27): the three process scores form a MULTIPLICATIVE
CASCADE, so the final answer F1 factorizes:

    final_F1  =  S_plan  *  select_retention  *  answer_accuracy
                 ^^^^^^     ^^^^^^^^^^^^^^^^^     ^^^^^^^^^^^^^^^^
                 plan        S_select/S_plan       S_reason/S_select
                 recall      (gold-bearing          (answer F1 among
                 (GT in      branches expanded)     reachable gold)
                  plan-path)

Eval v27 measured: 0.922 * 0.957 * 0.866 = 0.764  (llm_f1 = 0.774).

This script, given a BASELINE F1 and a TARGET F1, simulates how much each
stage must improve to close the gap — under several distribution strategies
(answer-only / data+traversal-only / balanced) — and prints a PPT-ready table.

Usage:
  python scripts/simulate_stage_improvement.py --baseline-f1 0.664 --target-f1 0.742
  python scripts/simulate_stage_improvement.py --target-f1 0.80  # aspirational
"""
import argparse

# Measured per-stage on eval v27 (99-case). final = P * Rsel * A.
EVAL = {"plan": 0.922, "select_retention": 0.957, "answer_accuracy": 0.866}


def final_f1(P, Rsel, A):
    return P * Rsel * A


def show(label, P, Rsel, A):
    f = final_f1(P, Rsel, A)
    print(f"  {label:34s} plan={P:.3f}  select={Rsel:.3f}  answer={A:.3f}  ->  final F1={f:.4f}  hit@1~{f*0.90:.3f}")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-f1", type=float, default=0.664, help="starting F1 (e.g. 0.664)")
    ap.add_argument("--baseline-hit", type=float, default=0.701, help="starting hit@1 (e.g. 0.701)")
    ap.add_argument("--target-f1", type=float, default=0.742, help="target F1 (CWQ full effect)")
    # current (eval) per-stage — the "where we are" reference
    ap.add_argument("--cur-plan", type=float, default=EVAL["plan"])
    ap.add_argument("--cur-select", type=float, default=EVAL["select_retention"])
    ap.add_argument("--cur-answer", type=float, default=EVAL["answer_accuracy"])
    args = ap.parse_args()

    P0, R0, A0 = args.cur_plan, args.cur_select, args.cur_answer
    cur_f1 = final_f1(P0, R0, A0)
    b, t = args.baseline_f1, args.target_f1
    ratio = t / b  # overall relative lift needed (if starting from baseline)

    print("=" * 78)
    print(f"STAGE IMPROVEMENT SIMULATION  (cascade model: final = plan × select × answer)")
    print("=" * 78)
    print(f"\n[reference] current eval per-stage (v27, 99-case):")
    show("current eval", P0, R0, A0)
    print(f"\n[goal] baseline F1={b:.3f} (hit@1={args.baseline_hit:.3f})  ->  target F1={t:.3f}")
    print(f"       overall lift needed: ΔF1=+{t-b:.3f}  ({(t/b-1)*100:.1f}% relative)\n")

    # --- Decompose the BASELINE into per-stage. Reading: plan & select
    #     (data/traversal) were already strong at baseline; the ANSWER stage
    #     carries the gap. Back-solve answer_accuracy at baseline. ---
    A_base = b / (P0 * R0)            # answer accuracy at baseline (plan/select at eval lvl)
    Pb0, Rb0, Ab0 = P0, R0, A_base    # BASELINE per-stage
    print(f"[baseline per-stage] (plan & select held at eval strength; answer back-solved)")
    show(f"  BASELINE (F1={b:.3f})", Pb0, Rb0, Ab0)
    print(f"  => the gap to current is carried by ANSWER: {Ab0:.3f} -> {A0:.3f} (current eval)\n")

    # --- Strategies to reach TARGET from BASELINE per-stage (positive deltas) ---
    print("-" * 78)
    print(f"To reach target F1={t:.3f} FROM BASELINE, each stage-improvement strategy:")
    print("-" * 78)
    # 1) answer-only (the main lever)
    A_need = min(1.0, t / (Pb0 * Rb0))
    show(f"① answer-only (plan/select fixed)", Pb0, Rb0, A_need)
    print(f"     answer: {Ab0:.3f} -> {A_need:.3f}  (Δ=+{A_need-Ab0:.3f}, {(A_need/Ab0-1)*100:.1f}%)\n")
    # 2) data-repair (plan) + answer  — the Virtuoso subgraph-repair lever
    #    plan rises by the data-repair gain (assume plan can reach ~0.96), answer fills the rest
    P_rep = min(0.99, Pb0 + 0.04)     # data repair lifts plan recall ~+0.04
    A_rep = min(1.0, t / (P_rep * Rb0))
    show(f"② data-repair(plan)+answer", P_rep, Rb0, A_rep)
    print(f"     plan: {Pb0:.3f} -> {P_rep:.3f} (Δ=+{P_rep-Pb0:.3f});  answer: {Ab0:.3f} -> {A_rep:.3f} (Δ=+{A_rep-Ab0:.3f})\n")
    # 3) balanced: equal relative lift g on all three (from baseline)
    g = (t / b) ** (1 / 3) - 1
    show(f"③ balanced (+{g*100:.1f}% on each stage)", Pb0*(1+g), Rb0*(1+g), Ab0*(1+g))
    print(f"     each stage +{g*100:.1f}% relative\n")

    # --- Headline: per-stage BASELINE -> TARGET (balanced reading) ---
    print("=" * 78)
    print(f"HEADLINE — per-stage lift to reach target F1={t:.3f} (balanced reading):")
    print("=" * 78)
    Pb, Rb, Ab = Pb0*(1+g), Rb0*(1+g), Ab0*(1+g)
    print(f"  {'stage':20s} {'baseline':>10s} {'target':>10s} {'Δ':>8s} {'rel':>8s}")
    for name, v0, v1 in [("plan_recall", Pb0, Pb), ("select_retention", Rb0, Rb), ("answer_accuracy", Ab0, Ab)]:
        print(f"  {name:20s} {v0:>10.3f} {v1:>10.3f} {v1-v0:>+8.3f} {(v1/v0-1)*100:>+7.1f}%")
    print(f"  {'FINAL F1':20s} {b:>10.3f} {final_f1(Pb,Rb,Ab):>10.3f} {final_f1(Pb,Rb,Ab)-b:>+8.3f}")
    print(f"\n  Leverage (baseline headroom to 1.0 — bigger = more addressable):")
    for name, val in [("answer_accuracy", Ab0), ("plan_recall", Pb0), ("select_retention", Rb0)]:
        print(f"    {name:20s}: {val:.3f}  (headroom {1-val:.3f})  {'<-- biggest lever' if name=='answer_accuracy' else ''}")


if __name__ == "__main__":
    main()
