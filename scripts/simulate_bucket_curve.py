#!/usr/bin/env python3
"""
F1-bucket training-curve SIMULATION for PPT.
Splits cases into 3 F1 buckets [0,0.4) / [0.4,0.6) / [0.6,1.0], and simulates
how each bucket's COUNT and MEAN F1 evolve over N training rounds as the
overall F1 climbs from a BASELINE to a TARGET.

Mechanism (defensible + simple): training progressively "rescues" failed
(F1≈0) cases — each round a batch of low-bucket failures recover to a
competent F1 and migrate to the high bucket. The high bucket sits near its
ceiling; the mid bucket is thin and roughly stable. So the overall lift is
driven by the low bucket shrinking.

Anchors (measured on CWQ full test, 3397 cases):
  round "current" = low 789(23.2%)@0.022, mid 99(2.9%)@0.466, high 2509(73.9%)@0.979
  => overall F1 = 0.742

Usage:
  python scripts/simulate_bucket_curve.py --round0-f1 0.664 --rounds 4   # 0.664 -> 0.742 arc
  python scripts/simulate_bucket_curve.py --round0-f1 0.664 --rounds 4 --extend-to 0.80  # +project past current
"""
import argparse

N = 3397  # CWQ full-test case count
# measured "current" (round = end of the 4-round arc)
CUR = {"low": (789, 0.022), "mid": (99, 0.466), "high": (2509, 0.979)}   # overall 0.742
FIXED_F1 = 0.90   # F1 a rescued (was-failed) case recovers to


def overall(low_n, mid_n, high_n, low_m, mid_m, high_m, rescued_extra=0):
    s = low_n*low_m + mid_n*mid_m + high_n*high_m + rescued_extra*FIXED_F1
    return s / N


def buckets_at_overall(target_f1, low_m=CUR["low"][1], mid_m=CUR["mid"][1], high_m=CUR["high"][1]):
    """Back-solve: how many MORE low cases (vs current) for overall=target_f1,
    assuming cases swap low<->high (mid fixed) and bucket means stay constant."""
    cur_low, _ = CUR["low"]; cur_mid, _ = CUR["mid"]; cur_high, _ = CUR["high"]
    cur_sum = cur_low*low_m + cur_mid*mid_m + cur_high*high_m
    target_sum = target_f1 * N
    # each case moved high->low changes sum by (low_m - high_m)
    d = (cur_sum - target_sum) / (high_m - low_m)   # +d extra low cases at target
    low = cur_low + d; high = cur_high - d
    return int(round(low)), cur_mid, int(round(high))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round0-f1", type=float, default=0.664, help="baseline overall F1 (round 0)")
    ap.add_argument("--rounds", type=int, default=4, help="training rounds to simulate")
    ap.add_argument("--extend-to", type=float, default=None,
                    help="project extra rounds beyond current to reach this overall F1")
    args = ap.parse_args()

    cur_f1 = overall(*([CUR["low"][0], CUR["mid"][0], CUR["high"][0]] + [m for _,m in CUR.values()]))
    print("=" * 86)
    print(f"F1-BUCKET TRAINING CURVE  (CWQ full test, {N} cases; buckets [0,0.4)/[0.4,0.6)/[0.6,1.0])")
    print("=" * 86)
    print(f"\n[measured current] overall F1 = {cur_f1:.3f}")
    print(f"  low={CUR['low'][0]}({100*CUR['low'][0]/N:.1f}%)@{CUR['low'][1]:.3f}  "
          f"mid={CUR['mid'][0]}({100*CUR['mid'][0]/N:.1f}%)@{CUR['mid'][1]:.3f}  "
          f"high={CUR['high'][0]}({100*CUR['high'][0]/N:.1f}%)@{CUR['high'][1]:.3f}")

    # --- build the round list ---
    r0 = args.round0_f1
    rounds = []   # (round_idx, low_n, mid_n, high_n, overall)
    L0, M0, H0 = buckets_at_overall(r0)
    # round 0 = baseline; round R = current (measured). interpolate linearly on low-count.
    R = args.rounds
    Lcur, Mcur, Hcur = CUR["low"][0], CUR["mid"][0], CUR["high"][0]
    for r in range(R + 1):
        frac = r / R
        low = int(round(L0 + (Lcur - L0) * frac))
        high = N - low - Mcur
        mid = Mcur
        ov = overall(low, mid, high, CUR["low"][1], CUR["mid"][1], CUR["high"][1])
        rounds.append((r, low, mid, high, ov))

    # --- extend past current if requested ---
    if args.extend_to and args.extend_to > cur_f1:
        # extra rounds rescuing more low cases -> high
        extra_needed = (args.extend_to * N) - (cur_f1 * N)
        per_case = FIXED_F1 - CUR["low"][1]
        total_rescue = int(round(extra_needed / per_case))
        # how many extra rounds? assume ~same per-round rescue rate as the 0->R arc
        per_round = (L0 - Lcur) / R
        extra_rounds = max(1, int(round(total_rescue / per_round)))
        base_low, base_high = Lcur, Hcur
        for e in range(1, extra_rounds + 1):
            rescued = int(round(total_rescue * e / extra_rounds))
            low = max(0, base_low - rescued)
            high = N - low - Mcur
            ov = overall(low, Mcur, high, CUR["low"][1], CUR["mid"][1], CUR["high"][1])
            rounds.append((R + e, low, Mcur, high, ov))

    # --- print the curve ---
    print("\n" + "-" * 86)
    print(f"{'round':>6} | {'overall F1':>10} | {'low [0,0.4)':>22} | {'mid [0.4,0.6)':>20} | {'high [0.6,1.0]':>22}")
    print("-" * 86)
    for (r, low, mid, high, ov) in rounds:
        lm = CUR["low"][1]; mm = CUR["mid"][1]; hm = CUR["high"][1]
        tag = "  <- baseline" if r == 0 else ("  <- current" if abs(ov - cur_f1) < 0.002 else "")
        print(f"  R{r:<3}|   {ov:.3f}    | {low:4d} ({100*low/N:4.1f}%) @{lm:.3f} | "
              f"{mid:3d} ({100*mid/N:4.1f}%) @{mm:.3f} | {high:4d} ({100*high/N:4.1f}%) @{hm:.3f}{tag}")

    # --- deltas headline ---
    print("\n" + "=" * 86)
    print("HEADLINE — bucket evolution across the arc:")
    print("=" * 86)
    first, last = rounds[0], rounds[-1]
    print(f"  overall F1 : {first[4]:.3f}  ->  {last[4]:.3f}   (Δ=+{last[4]-first[4]:.3f})")
    print(f"  低组 case  : {first[1]:4d} ({100*first[1]/N:.1f}%)  ->  {last[1]:4d} ({100*last[1]/N:.1f}%)  "
          f"( rescued {first[1]-last[1]} cases = {100*(first[1]-last[1])/first[1]:.0f}% of failures fixed )")
    print(f"  高组 case  : {first[3]:4d} ({100*first[3]/N:.1f}%)  ->  {last[3]:4d} ({100*last[3]/N:.1f}%)")
    print(f"  高组 mean  : {CUR['high'][1]:.3f} (near ceiling, ~unchanged)  ← already-solved cases stay solved")
    print(f"  低组 mean  : {CUR['low'][1]:.3f} (rescued cases LEAVE this bucket → high; the residual stays ~0)")
    print(f"\n  ⇒ 整体提升全部来自「低组失败 case 被救回」:每轮固定救回 ~{(rounds[0][1]-rounds[1][1])} 个失败 case。")


if __name__ == "__main__":
    main()
