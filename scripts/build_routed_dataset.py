#!/usr/bin/env python3
"""Build the ROUTED training dataset (offline preprocessing).

Consumes route labels (route_cases.py) + train_msgs (messages + S_* + llm_f1),
emits ONE training example per (case, sample) with the routing baked into two
fields the trainer reads:

  train_stages : which assistant-turn stages go into the completion_mask
                   a_sft / c_grpo → ["plan","select","reason"]  (all turns)
                   b_origin_X     → ["X"]                        (bottleneck segment only)
  advantage    : SCALAR (group-baselined within the case) — never per-token
                   a_sft   → 1.0                          (imitation; CiSPO λ applies)
                   b_origin_X → S_X(sample) − mean_case(S_X)
                   c_grpo  → llm_f1(sample) − mean_case(llm_f1)   (terminal reward)

All advantages are scalar → the trainer routes every example through
LigerFusedLinearGRPOLoss (no logits materialized → no OOM → batch=2 feasible).

d_discard / b_stuck are dropped here (b_stuck → Phase-2 directed rollout).

Output schema (one line per training example):
  {case_id, sample_id, messages, train_stages, advantage, role, route, llm_f1, S_*}
"""
import json, argparse, collections, statistics
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_advantage_dataset import _turn_stage  # stage of a message turn

ALL_STAGES = ["plan", "select", "reason"]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def _truncate_at_stage(messages, stage):
    """Truncate messages to end at (include) the LAST assistant turn of `stage`.

    For b_origin segment training, only the bottleneck-stage turn(s) are labeled
    (train_stages=[stage]); every turn AFTER the last bottleneck turn is fully
    masked (-100) AND causally irrelevant (a token can't depend on later tokens).
    So those trailing turns are pure dead weight — dropping them shortens the
    sequence (often dramatically, e.g. plan-bottleneck drops select+reason)
    with ZERO loss of training signal. No-op if the stage isn't found."""
    last_idx = -1
    for i in range(len(messages)):
        if _turn_stage(messages, i) == stage:
            last_idx = i
    return messages[: last_idx + 1] if last_idx >= 0 else messages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msgs", required=True, help="train_msgs.jsonl (messages + S_* + llm_f1)")
    ap.add_argument("--routes", required=True, help="route_cases.py output (routes.jsonl)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.msgs) if l.strip()]
    by_case = collections.defaultdict(list)
    for r in recs:
        by_case[r["case_id"]].append(r)
    route_of = {r["case_id"]: r["route"] for r in (json.loads(l) for l in open(args.routes) if l.strip())}

    out, stats = [], collections.Counter()
    for cid, rs in by_case.items():
        route = route_of.get(cid, "d_discard")
        if route.startswith("a_sft"):
            # one best sample, all turns, adv=1.0
            best = max(rs, key=lambda r: r.get("llm_f1") or 0)
            out.append(_ex(best, cid, ALL_STAGES, 1.0, "sft", route))
            stats["a_sft"] += 1
        elif route.startswith("b_origin"):
            stage = route.split("_")[-1]  # plan | select | reason
            scores = [r.get(f"S_{stage}") for r in rs]
            mu = mean(scores)
            for r in rs:
                s = r.get(f"S_{stage}")
                if s is None:
                    continue
                # truncate the trailing (post-bottleneck) turns — dead weight for
                # segment training. Build a per-sample record with shortened msgs.
                rec = dict(r)
                rec["messages"] = _truncate_at_stage(r["messages"], stage)
                out.append(_ex(rec, cid, [stage], round(s - mu, 6), "grpo", route))
            stats["b_origin"] += len(rs)
        elif route == "c_grpo":
            f1s = [r.get("llm_f1") or 0 for r in rs]
            mu = mean(f1s)
            for r in rs:
                out.append(_ex(r, cid, ALL_STAGES, round((r.get("llm_f1") or 0) - mu, 6), "grpo", route))
            stats["c_grpo"] += len(rs)
        else:  # d_discard, b_stuck → drop here
            stats[route] += 0

    print(f"=== routed dataset ===")
    for k in ["a_sft", "b_origin", "c_grpo"]:
        print(f"  {k:10s}: {stats[k]:5d} examples")
    print(f"  total     : {len(out):5d} examples")
    advs = [r["advantage"] for r in out if r["role"] == "grpo"]
    if advs:
        print(f"  grpo advantage: min={min(advs):.3f} max={max(advs):.3f} mean={statistics.mean(advs):.4f} (should ~0)")
    print(f"  sft examples (adv=1.0): {sum(1 for r in out if r['role']=='sft')}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote -> {args.output}")


def _ex(rec, cid, train_stages, advantage, role, route):
    return {
        "case_id": cid,
        "sample_id": rec.get("sample_id", 0),
        "messages": rec["messages"],
        "train_stages": train_stages,
        "advantage": advantage,
        "role": role,
        "route": route,
        "llm_f1": rec.get("llm_f1", 0.0),
        "S_plan": rec.get("S_plan"),
        "S_select": rec.get("S_select"),
        "S_reason": rec.get("S_reason"),
    }


if __name__ == "__main__":
    main()
