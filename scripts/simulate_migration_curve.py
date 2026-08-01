#!/usr/bin/env python3
"""
General FORWARD MIGRATION F1 curve (PPT) — polarization-from-the-middle.
Works for any dataset (CWQ / WebQSP). You set the INITIAL distribution
(middle-heavy) + target F1 + the polarization split p_high.

Dynamics:
  * the MIDDLE bucket separates (front-loaded, fast rounds 1-2): its partially-
    correct cases polarize — fraction p_high resolve -> HIGH, the rest -> LOW.
  * p_high is the "resolve correctly" rate; keep it HIGH (>=0.85) so the split
    is NOT balanced (most middle cases get solved, few fall to low) — matches
    "左右跌入不要占比太平均".
  * later rounds: HIGH mean -> ceiling, LOW mean rises (stuck cases slowly
    improve), MIDDLE count keeps shrinking to a small residual.

Initial means: low~0.06, high~0.96 (fixed, structural); mid mean solved from
--init-f1. End means: high~0.98, mid~0.70; low mean solved from --target-f1.

Usage:
  # WebQSP: 0.711 -> 0.842, init low 11.4/mid 39.6/high 49.0
  python scripts/simulate_migration_curve.py --dataset WebQSP --init-low 0.114 --init-mid 0.396 --init-high 0.490 --init-f1 0.711 --target-f1 0.842 --p-high 0.88
  # CWQ: 0.664 -> 0.786
  python scripts/simulate_migration_curve.py --dataset CWQ --init-low 0.16 --init-mid 0.44 --init-high 0.40 --init-f1 0.664 --target-f1 0.786 --p-high 0.85
"""
import argparse, math

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="CWQ")
    ap.add_argument("--init-low", type=float, required=True)
    ap.add_argument("--init-mid", type=float, required=True)
    ap.add_argument("--init-high", type=float, required=True)
    # all means are now EXPLICIT (no forced solve) — fully transparent, adjustable
    ap.add_argument("--init-low-m", type=float, default=0.10, help="low group START mean F1")
    ap.add_argument("--init-mid-m", type=float, default=0.50, help="mid group START mean F1")
    ap.add_argument("--init-high-m", type=float, default=0.82, help="high group START mean F1 (multi-answer => <0.96)")
    ap.add_argument("--target-f1", type=float, required=True)
    ap.add_argument("--end-high-m", type=float, default=0.90, help="high group END (max) mean — capped by multi-answer")
    ap.add_argument("--end-mid-m", type=float, default=0.70)
    ap.add_argument("--p-high", type=float, default=0.88, help="fraction of separating mid -> HIGH (>=0.85 = not balanced)")
    ap.add_argument("--end-mid", type=float, default=0.05, help="residual mid fraction at round R")
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    R = args.rounds
    L0, M0, H0 = args.init_low, args.init_mid, args.init_high
    lm0, mm0, hm0 = args.init_low_m, args.init_mid_m, args.init_high_m
    ov0 = L0*lm0 + M0*mm0 + H0*hm0          # actual init F1 (computed, not forced)

    # END counts: mid separates to end_mid; leavers split p_high -> high
    leavers = M0 - args.end_mid
    end_low = L0 + (1 - args.p_high) * leavers
    end_high = H0 + args.p_high * leavers
    end_mid = args.end_mid
    # END low mean solved from target_f1 (high/mid means given)
    end_low_m = (args.target_f1 - end_mid*args.end_mid_m - end_high*args.end_high_m) / end_low
    feasible = 0.0 <= end_low_m <= args.init_mid_m   # low mean should stay < mid range

    print("=" * 96)
    print(f"FORWARD MIGRATION CURVE — {args.dataset}  (high-start={hm0}, high-max={args.end_high_m}; multi-answer aware)")
    print(f"round 0 = base (no train), F1={ov0:.3f} (computed)  ->  round {R} target F1={args.target_f1}  |  p_high={args.p_high}")
    print("=" * 96)
    print(f"\n[round-0 base] low={L0:.1%}@{lm0:.2f}  mid={M0:.1%}@{mm0:.2f}  high={H0:.1%}@{hm0:.2f}  => F1 {ov0:.3f}")
    print(f"[round-{R} end]  low={end_low:.1%}@{end_low_m:.3f}  mid={end_mid:.1%}@{args.end_mid_m:.2f}  high={end_high:.1%}@{args.end_high_m:.2f}  => F1 {args.target_f1}")
    if not feasible:
        print(f"  ⚠ NOTE: end low mean {end_low_m:.3f} {'偏高(>mid区间)' if end_low_m>args.init_mid_m else '<0'} — target可能需调高/低位组占比需更大")
    print(f"  (mid 极化:leavers {leavers:.1%}, {args.p_high:.0%}->high, {1-args.p_high:.0%}->low)\n")

    k = 0.95
    rows = []
    for r in range(R + 1):
        frac = r / R
        cm = end_mid if r == R else end_mid + (M0 - end_mid) * math.exp(-k * r)
        cl = L0 + (end_low - L0) * frac
        ch = 1.0 - cl - cm
        ml = lm0 + (end_low_m - lm0) * frac
        mm = mm0 + (args.end_mid_m - mm0) * frac
        mh = hm0 + (args.end_high_m - hm0) * frac
        ov = cl*ml + cm*mm + ch*mh
        rows.append((r, cl, cm, ch, ml, mm, mh, ov))

    print("-" * 96)
    print(f"{'round':>5} | {'overall':>7} | {'low':>20s} | {'mid':>20s} | {'high':>20s}")
    print("-" * 96)
    for (r, cl, cm, ch, ml, mm, mh, ov) in rows:
        tag = " <- base" if r == 0 else (" <- end" if r == R else "")
        print(f" R{r:<3}|  {ov:.3f} | {cl:4.1%}@{ml:.3f} | {cm:4.1%}@{mm:.3f} | {ch:4.1%}@{mh:.3f}{tag}")

    print("\n" + "=" * 96)
    print("ANALYSIS")
    print("=" * 96)
    to_high = args.p_high * leavers; to_low = (1 - args.p_high) * leavers
    print(f"  high mean: {hm0:.2f} -> {args.end_high_m:.2f}  (起始{hm0},最高{args.end_high_m};多答案→答不全→<1.0)")
    print(f"  low mean : {lm0:.2f} -> {end_low_m:.3f}  (拉高)")
    print(f"  mid 极化 : {M0:.1%} -> {end_mid:.1%}; ->high {to_high:.1%}, ->low {to_low:.1%}; 比 {to_high/max(to_low,1e-6):.1f}:1 {'✓不平均' if to_high/max(to_low,1e-6)>=4 else '偏平均'}")
    print(f"  整体 F1 : {ov0:.3f} -> {args.target_f1}")
    if ov0 < args.target_f1 - 0.15:
        print(f"  ⚠ init F1 {ov0:.3f} 偏低(high-start {hm0} 拉低了整体);若要 init≈0.711,需 high-start≥0.90 或调高 init-high 占比")


if __name__ == "__main__":
    main()
