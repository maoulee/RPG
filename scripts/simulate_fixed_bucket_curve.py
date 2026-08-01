#!/usr/bin/env python3
"""
FIXED-bucket F1 training curve (PPT).
The cases are PINNED to their round-0 (base model, no training) F1 bucket:
  low [0,0.4), mid [0.4,0.6), high [0.6,1.0].
Buckets do NOT exchange cases — we track each FIXED group's MEAN F1 as
training proceeds round 0 -> round R.

Model (geometric headroom capture): each round, every group captures a fixed
fraction α of its REMAINING headroom to 1.0:
    mean_r(group) = 1 - (1 - mean_0) * (1 - α)^r
Low group has the most headroom => rises fastest; high group is near ceiling
=> barely moves. α is solved so that the overall F1 hits the target at round R.

Round 0 = base model (NO training). Anchors (CWQ full test, 3397 cases):
  base overall 0.664 -> low 1065(31.4%)@0.022, mid 99(2.9%)@0.466, high 2233(65.7%)@0.979

Usage:
  python scripts/simulate_fixed_bucket_curve.py --round0-f1 0.664 --target-f1 0.786 --rounds 4
"""
import argparse

N = 3397
# round-0 (base) buckets — back-solved so overall = 0.664, means held at measured CWQ values
BASE = {"low": (1065, 0.022), "mid": (99, 0.466), "high": (2233, 0.979)}


def overall(low_m, mid_m, high_m):
    s = BASE["low"][0]*low_m + BASE["mid"][0]*mid_m + BASE["high"][0]*high_m
    return s / N


def solve_alpha(target_f1, R):
    """overall_r = 1 - K*(1-α)^r ; solve α for overall_R = target."""
    # K = sum(n_g * headroom_g) / N ; overall_0 = 1-K
    K = 1 - overall(BASE["low"][1], BASE["mid"][1], BASE["high"][1])
    import math
    # 1 - K*(1-α)^R = target  =>  (1-α)^R = (1-target)/K
    ratio = (1 - target_f1) / K
    q = ratio ** (1.0 / R)      # q = 1-α
    return 1 - q, K


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round0-f1", type=float, default=0.664)
    ap.add_argument("--target-f1", type=float, default=0.786)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    R = args.rounds
    alpha, K = solve_alpha(args.target_f1, R)
    q = 1 - alpha
    m0 = {"low": BASE["low"][1], "mid": BASE["mid"][1], "high": BASE["high"][1]}
    head = {g: 1 - m0[g] for g in m0}

    print("=" * 90)
    print(f"FIXED-BUCKET F1 TRAINING CURVE  (cases pinned to round-0 base buckets; CWQ {N} cases)")
    print(f"round 0 = base (NO training), F1={args.round0_f1}  ->  round {R} target F1={args.target_f1}")
    print(f"model: mean_r = 1 - headroom*(1-α)^r ; α={alpha:.4f} (each round captures {alpha*100:.1f}% of remaining headroom)")
    print("=" * 90)
    print(f"\n[round-0 base buckets, FIXED] overall={args.round0_f1:.3f}")
    print(f"  low  = {BASE['low'][0]:4d} ({100*BASE['low'][0]/N:.1f}%) @ mean {m0['low']:.3f}  (headroom {head['low']:.3f})")
    print(f"  mid  = {BASE['mid'][0]:4d} ({100*BASE['mid'][0]/N:.1f}%) @ mean {m0['mid']:.3f}  (headroom {head['mid']:.3f})")
    print(f"  high = {BASE['high'][0]:4d} ({100*BASE['high'][0]/N:.1f}%) @ mean {m0['high']:.3f}  (headroom {head['high']:.3f})\n")

    print("-" * 90)
    print(f"{'round':>6} | {'overall F1':>10} | {'low mean':>9s} {'(Δ)':>8s} | {'mid mean':>9s} {'(Δ)':>8s} | {'high mean':>9s} {'(Δ)':>8s}")
    print("-" * 90)
    rows = []
    for r in range(R + 1):
        qr = q ** r
        ml = 1 - head["low"] * qr
        mm = 1 - head["mid"] * qr
        mh = 1 - head["high"] * qr
        ov = overall(ml, mm, mh)
        rows.append((r, ov, ml, mm, mh))
    for i, (r, ov, ml, mm, mh) in enumerate(rows):
        dl = f"+{ml - m0['low']:.3f}" if r else "  —"
        dm = f"+{mm - m0['mid']:.3f}" if r else "  —"
        dh = f"+{mh - m0['high']:.3f}" if r else "  —"
        tag = "  <- base, no train" if r == 0 else ("  <- target" if r == R else "")
        print(f"  R{r:<3}|   {ov:.3f}    | {ml:.3f}  {dl:>7s} | {mm:.3f}  {dm:>7s} | {mh:.3f}  {dh:>7s}{tag}")

    print("\n" + "=" * 90)
    print("HEADLINE — each FIXED group's mean F1 lift over the arc:")
    print("=" * 90)
    for g, m_init, label in [("low", m0["low"], "低组 (base F1<0.4)"),
                              ("mid", m0["mid"], "中组 (0.4-0.6)"),
                              ("high", m0["high"], "高组 (0.6-1.0)")]:
        m_end = 1 - head[g] * (q ** R)
        print(f"  {label:18s}: {m_init:.3f}  ->  {m_end:.3f}   (Δ=+{m_end-m_init:.3f}, 涨 {(m_end/m_init-1)*100:.0f}% rel)")
    ov0, ovR = rows[0][1], rows[-1][1]
    print(f"  {'整体 F1':18s}: {ov0:.3f}  ->  {ovR:.3f}   (Δ=+{ovR-ov0:.3f})")
    print(f"\n  ⇒ 低组涨最多(+{1-head['low']*q**R - m0['low']:.3f},余量最大);高组几乎不动(贴天花板);")
    print(f"     提升按余量分配,每轮捕获剩余余量的 {alpha*100:.1f}%。")


if __name__ == "__main__":
    main()
