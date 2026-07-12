#!/usr/bin/env python3
"""Offline ROUTING classifier — assign each case to one training strategy.

The user's framework (NOT per-token): route each case to a STAGE-LEVEL strategy,
all using SCALAR advantage (→ LigerFusedLinearGRPOLoss, no logits, no OOM):

  a  all-correct      every sample llm_f1 >= F1_OK     → SFT one best sample
                                                      (train_stages=all, adv=1.0)
  b  localized        variance dominated by ONE stage  → origin-stage GRPO on that
         origin         (var(bottleneck) >= LOC_FRAC×total, bottleneck has a       (train_stages=[bottleneck],
                        positive sample S>0.5)                          adv=S_bottleneck-group_mean)
  b-stuck             localized bottleneck but ALL samples fail at it  → directed-rollout
                        (no sample S_bottleneck>0.5)                     target (Phase 2; skip here)
  c  diffuse          variance spread across >=2 stages               → whole-traj scalar GRPO
                                                                     (train_stages=all,
                                                                      adv=traj_composite-group_mean)
  d  discard          no usable variance (flat) or flat-wrong/GT-suspect → drop

Input: train_msgs.jsonl (messages + S_plan/S_select/S_reason + llm_f1, base case_id).
Output: per-case route label + diagnostics JSONL + a summary.
"""
import json, math, argparse, collections, statistics
from pathlib import Path

STAGES = ["plan", "select", "reason"]


def var(xs):
    xs = [x or 0 for x in xs if x is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="train_msgs.jsonl (messages + S_* + llm_f1)")
    ap.add_argument("--out-diagnostics", required=True)
    ap.add_argument("--f1-ok", type=float, default=0.95, help="all-correct threshold")
    ap.add_argument("--f1-bad", type=float, default=0.5, help="below this = no good sample")
    ap.add_argument("--var-thresh", type=float, default=0.01, help="min total stage variance to count as 'has variance'")
    ap.add_argument("--loc-frac", type=float, default=0.6, help="bottleneck var >= this fraction of total → localized")
    ap.add_argument("--s-ok", type=float, default=0.5, help="sample counts as reaching a stage if S_stage > this")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.input) if l.strip()]
    by_case = collections.defaultdict(list)
    for r in recs:
        by_case[r["case_id"]].append(r)

    rows = []
    counts = collections.Counter()
    for cid, rs in by_case.items():
        f1s = [r.get("llm_f1") or 0 for r in rs]
        sp = [r.get("S_plan") for r in rs]
        ss = [r.get("S_select") for r in rs]
        sr = [r.get("S_reason") for r in rs]
        vp, vs, vr = var(sp), var(ss), var(sr)
        total = vp + vs + vr
        max_f1 = max(f1s)
        all_correct = all(f >= args.f1_ok for f in f1s) and len(f1s) >= 2

        route = "d_discard"
        bottleneck = None
        reason = ""
        if all_correct:
            route = "a_sft"
            reason = "all samples correct"
        elif total < args.var_thresh:
            # low variance — if never good → discard (GT suspect); if decent → still discard (no GRPO signal)
            route = "d_discard"
            reason = "flat (no stage variance)"
        else:
            stage_vars = {"plan": vp, "select": vs, "reason": vr}
            bottleneck = max(stage_vars, key=stage_vars.get)
            if stage_vars[bottleneck] >= args.loc_frac * total:
                # localized — does the bottleneck ever succeed?
                bottleneck_vals = {"plan": sp, "select": ss, "reason": sr}[bottleneck]
                reached = [v for v in bottleneck_vals if v is not None and v > args.s_ok]
                if reached:
                    route = "b_origin_" + bottleneck
                    reason = f"localized at {bottleneck} (var {stage_vars[bottleneck]:.3f} >= {args.loc_frac}×{total:.3f}); has positive sample"
                else:
                    route = "b_stuck_" + bottleneck
                    reason = f"localized at {bottleneck} but ALL samples fail it → directed-rollout target"
            else:
                route = "c_grpo"
                reason = f"diffuse (plan {vp:.3f}/select {vs:.3f}/reason {vr:.3f})"
        counts[route.split("_")[0] if route.startswith("b") else route] += 1
        rows.append(dict(case_id=cid, route=route, bottleneck=bottleneck, reason=reason,
                         n=len(rs), max_f1=round(max_f1, 3), all_correct=all_correct,
                         vp=round(vp, 4), vs=round(vs, 4), vr=round(vr, 4), total=round(total, 4)))

    # pretty route counts (collapse b_origin_* / b_stuck_*)
    pretty = collections.Counter()
    for r in rows:
        key = r["route"].split("_")[0] + ("_" + r["route"].split("_")[1] if r["route"].startswith("b") else "")
        pretty[key] += 1
    print(f"=== route distribution over {len(rows)} cases ===")
    for k in ["a_sft", "b_origin", "b_stuck", "c_grpo", "d_discard"]:
        print(f"  {k:12s}: {pretty.get(k,0):4d}")
    bk = collections.Counter(r["bottleneck"] for r in rows if r["bottleneck"])
    print(f"  b-bottleneck stage: {dict(bk)}")

    Path(args.out_diagnostics).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_diagnostics, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows)} case routes -> {args.out_diagnostics}")


if __name__ == "__main__":
    main()
