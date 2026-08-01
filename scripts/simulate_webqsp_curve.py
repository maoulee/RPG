#!/usr/bin/env python3
"""
WebQSP-specific F1 curve (PPT) — HIGH-GROUP STRIVING model.
WebQSP is simpler => few total failures (low bucket small, and those are hard
cases); but it has MANY multi-answer questions => even "high" cases can't get
ALL answers, so the high group sits at partial F1 (~0.84). The MAIN training
lever is therefore the HIGH group's mean F1 RISING (answer more of the
multi-answers -> 0.84 -> 0.94), NOT low-rescue (as in CWQ) or middle-polarize.

Dynamics:
  * high group (dominant): mean F1 rises 0.84 -> 0.94 (multi-answer completion).
    This is the main driver (large count x rising mean).
  * mid group: shrinks (improves into high).
  * low group: small (simple questions), slight mean rise (the few are hard).

Usage:
  python scripts/simulate_webqsp_curve.py                      # defaults 0.714 -> 0.842
  python scripts/simulate_webqsp_curve.py --target-f1 0.82
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init-f1", type=float, default=0.714)
    ap.add_argument("--target-f1", type=float, default=0.842)
    ap.add_argument("--rounds", type=int, default=4)
    # init distribution (WebQSP: low few, high dominant at partial F1)
    ap.add_argument("--init-low", type=float, default=0.08)
    ap.add_argument("--init-mid", type=float, default=0.22)
    ap.add_argument("--init-high", type=float, default=0.70)
    ap.add_argument("--init-low-m", type=float, default=0.10)
    ap.add_argument("--init-mid-m", type=float, default=0.52)
    ap.add_argument("--init-high-m", type=float, default=0.84, help="high START (multi-answer partial)")
    # end
    ap.add_argument("--end-high-m", type=float, default=0.94, help="high END (answer more multi-answer)")
    ap.add_argument("--end-mid", type=float, default=0.08)
    ap.add_argument("--end-mid-m", type=float, default=0.66)
    ap.add_argument("--end-low-m", type=float, default=0.16)
    args = ap.parse_args()

    R = args.rounds
    L0, M0, H0 = args.init_low, args.init_mid, args.init_high
    lm0, mm0, hm0 = args.init_low_m, args.init_mid_m, args.init_high_m
    ov0 = L0*lm0 + M0*mm0 + H0*hm0

    # end counts: mid shrinks to end_mid (-> high mostly); low grows slightly
    mid_leavers = M0 - args.end_mid
    end_low = L0 + 0.25 * mid_leavers     # few mid fall to low
    end_high = 1.0 - end_low - args.end_mid
    em_l, em_m, em_h = args.end_low_m, args.end_mid_m, args.end_high_m
    ovR = end_low*em_l + args.end_mid*em_m + end_high*em_h

    print("=" * 94)
    print(f"WebQSP CURVE — HIGH-GROUP STRIVING (multi-answer completion)")
    print(f"round 0 = base (no train), F1={ov0:.3f}  ->  round {R} F1={ovR:.3f}")
    print(f"main lever: high group mean {hm0:.2f} -> {em_h:.2f} (answer more multi-answer)")
    print("=" * 94)
    print(f"\n[round-0 base] low={L0:.0%}@{lm0:.2f}  mid={M0:.0%}@{mm0:.2f}  high={H0:.0%}@{hm0:.2f}  => {ov0:.3f}")
    print(f"[round-{R} end]  low={end_low:.0%}@{em_l:.2f}  mid={args.end_mid:.0%}@{em_m:.2f}  high={end_high:.0%}@{em_h:.2f}  => {ovR:.3f}\n")

    rows = []
    for r in range(R + 1):
        f = r / R
        cl = L0 + (end_low - L0) * f
        cm = M0 + (args.end_mid - M0) * f
        ch = 1.0 - cl - cm
        ml = lm0 + (em_l - lm0) * f
        mm = mm0 + (em_m - mm0) * f
        mh = hm0 + (em_h - hm0) * f
        ov = cl*ml + cm*mm + ch*mh
        rows.append((r, cl, cm, ch, ml, mm, mh, ov))

    print("-" * 94)
    print(f"{'round':>5} | {'overall':>7} | {'low (few, hard)':>20s} | {'mid':>18s} | {'high (striving)':>20s}")
    print("-" * 94)
    for (r, cl, cm, ch, ml, mm, mh, ov) in rows:
        tag = " <- base" if r == 0 else (" <- end" if r == R else "")
        print(f" R{r:<3}|  {ov:.3f} | {cl:4.1%}@{ml:.3f} | {cm:4.1%}@{mm:.3f} | {ch:4.1%}@{mh:.3f}{tag}")

    # lift decomposition
    print("\n" + "=" * 94)
    print("LIFT DECOMPOSITION (where the +%.3f comes from):" % (ovR - ov0))
    print("=" * 94)
    # contribution = end_count*end_mean - init_count*init_mean (per group)
    c_low = end_low*em_l - L0*lm0
    c_mid = args.end_mid*em_m - M0*mm0
    c_high = end_high*em_h - H0*hm0
    tot = c_low + c_mid + c_high
    for name, c in [("high (mean 0.84->0.94 + count up)", c_high),
                    ("mid (shrink + mean up)", c_mid),
                    ("low (few, slight)", c_low)]:
        print(f"  {name:36s}: {c:+.3f}  ({100*c/tot:.0f}% of lift)")
    print(f"\n  ⇒ WebQSP 提升主力 = 高位组({100*c_high/tot:.0f}%):多答案逐步答全,F1 0.84->0.94。")
    print(f"     低组很少(题简单),中组缩量;和 CWQ(救低组失败)的机制完全不同。")


if __name__ == "__main__":
    main()
