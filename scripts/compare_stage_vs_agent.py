#!/usr/bin/env python3
"""Compare STAGE pipeline vs 4-tool AGENT on the SAME 342 CWQ cases.

Both were multi-sampled on the same 342 cases:
  - stage: reports/cwq_full_test/chunk*/results.json  (3397 records, ~10/case)
  - agent: data/offline_grpo/full_sample_3k.jsonl     (13588 records, ~40/case)

Goal: the agent baseline is F1=0.703 but the stage pipeline scored ~0.74-0.81.
Before RL training, find WHERE the agent loses vs stage (so we don't RL-polish a
worse baseline without understanding the gap).

Confound handled: agent records include `agent_failed` HTTP-error samples
(vLLM overloaded during sampling) counted as F1=0. We report both
"all-samples" (honest, includes failures) and "valid-only" (real capability).

Aggregation: per-CASE mean + best F1 (each case weighted equally), so
over-sampled cases don't dominate. Re-scores llm_answer with current eval
(fuzzy 0.95) for metric consistency.

Outputs:
  - aggregate table (stage vs agent, mean/best, all vs valid)
  - per-case diff (stage_mean - agent_mean), sorted
  - top loss / top win cases with both answers + agent trajectory path
"""
import json, glob, sys, os, statistics, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kgqa.core.utils import compute_match_stats

STAGE_GLOB = "reports/cwq_full_test/chunk*/results.json"
AGENT_PATH = "data/offline_grpo/full_sample_3k.jsonl"


def base(cid):
    return cid.split("_")[0]


def load_json_or_jsonl(path):
    raw = open(path).read()
    s = raw.lstrip()
    if s.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


def parse_answer(a):
    if not a:
        return []
    return [x.strip() for x in str(a).split("|") if x.strip()]


def rescore(rec):
    preds = parse_answer(rec.get("llm_answer"))
    gt = rec.get("gt_answers") or []
    return compute_match_stats(preds, gt)["f1"]


def per_case(records):
    """Group by base case_id, compute per-case stats."""
    by = collections.defaultdict(list)
    for r in records:
        by[base(r["case_id"])].append(r)
    out = {}
    for cid, recs in by.items():
        f1s = [rescore(r) for r in recs]
        out[cid] = dict(
            n=len(recs),
            mean_f1=statistics.mean(f1s) if f1s else 0.0,
            best_f1=max(f1s) if f1s else 0.0,
            gt_hit=any(r.get("gt_hit") for r in recs),
            recs=recs,
            f1s=f1s,
        )
    return out


def agg(case_stats, key="mean_f1"):
    """Mean over cases (equal weight)."""
    vals = [c[key] for c in case_stats.values()]
    return statistics.mean(vals) if vals else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", default="reports/stage_vs_agent_diff.json")
    args = ap.parse_args()

    stage = []
    for p in sorted(glob.glob(STAGE_GLOB)):
        stage += load_json_or_jsonl(p)
    agent_all = load_json_or_jsonl(AGENT_PATH)
    # split agent: valid vs http-failed
    agent_valid = [r for r in agent_all if not r.get("agent_failed")]
    agent_failed = [r for r in agent_all if r.get("agent_failed")]

    sp = per_case(stage)
    ap_all = per_case(agent_all)
    ap_val = per_case(agent_valid)

    n_cases = len(sp)

    def gt_hit_rate(cs):
        return sum(1 for c in cs.values() if c["gt_hit"]) / len(cs)

    print("=" * 72)
    print(f"STAGE vs AGENT on SAME {n_cases} CWQ cases (current eval, fuzzy 0.95)")
    print("=" * 72)
    print(f"{'':30} {'stage':>10} {'agent(all)':>12} {'agent(valid)':>14}")
    print("-" * 72)
    print(f"{'records':30} {len(stage):>10} {len(agent_all):>12} {len(agent_valid):>14}")
    print(f"{'mean-F1 (per-case mean)':30} {agg(sp):>10.4f} {agg(ap_all):>12.4f} {agg(ap_val):>14.4f}")
    print(f"{'best-F1 (per-case best)':30} {agg(sp,'best_f1'):>10.4f} {agg(ap_all,'best_f1'):>12.4f} {agg(ap_val,'best_f1'):>14.4f}")
    print(f"{'gt-hit rate (any sample)':30} {gt_hit_rate(sp):>10.4f} {gt_hit_rate(ap_all):>12.4f} {gt_hit_rate(ap_val):>14.4f}")
    print(f"\nagent http-failed records: {len(agent_failed)} ({100*len(agent_failed)/len(agent_all):.1f}%)")
    print(f"  failed cases (>=1 failure): {len(set(base(r['case_id']) for r in agent_failed))}")

    # per-case diff: stage_mean - agent_valid_mean (real capability gap)
    shared = sorted(set(sp) & set(ap_val))
    diffs = []
    for cid in shared:
        sf = sp[cid]["mean_f1"]
        af = ap_val[cid]["mean_f1"]
        diffs.append(dict(
            cid=cid,
            q=ap_val[cid]["recs"][0].get("question", "")[:90],
            gt=ap_val[cid]["recs"][0].get("gt_answers"),
            stage_mean=sf, agent_mean=af,
            stage_best=sp[cid]["best_f1"], agent_best=ap_val[cid]["best_f1"],
            stage_n=sp[cid]["n"], agent_n_valid=ap_val[cid]["n"],
            stage_gt=sp[cid]["gt_hit"], agent_gt=ap_val[cid]["gt_hit"],
            diff=sf - af,
        ))

    losses = sorted(diffs, key=lambda d: -d["diff"])
    wins = sorted(diffs, key=lambda d: d["diff"])

    print(f"\n{'='*72}\nTOP {args.top} CASES WHERE AGENT LOSES (stage_mean - agent_mean)\n{'='*72}")
    for d in losses[:args.top]:
        print(f"  {d['cid']:<16} diff={d['diff']:+.3f}  stage={d['stage_mean']:.2f}(best{d['stage_best']:.2f}) "
              f"agent={d['agent_mean']:.2f}(best{d['agent_best']:.2f}) "
              f"gt_stage={int(d['stage_gt'])} gt_agent={int(d['agent_gt'])}")
        print(f"     Q: {d['q']}")
        print(f"     GT: {d['gt']}")

    print(f"\n{'='*72}\nTOP {args.top} CASES WHERE AGENT WINS\n{'='*72}")
    for d in wins[:args.top]:
        print(f"  {d['cid']:<16} diff={d['diff']:+.3f}  stage={d['stage_mean']:.2f} agent={d['agent_mean']:.2f} "
              f"gt_stage={int(d['stage_gt'])} gt_agent={int(d['agent_gt'])}  Q: {d['q']}")

    # bucket the gap
    both_gt = [d for d in diffs if d["stage_gt"] and d["agent_gt"]]
    stage_only_gt = [d for d in diffs if d["stage_gt"] and not d["agent_gt"]]
    agent_only_gt = [d for d in diffs if not d["stage_gt"] and d["agent_gt"]]
    neither_gt = [d for d in diffs if not d["stage_gt"] and not d["agent_gt"]]
    print(f"\n{'='*72}\nGT-REACH BUCKETS (where did gold land in candidate pool)\n{'='*72}")
    print(f"  both reach GT      : {len(both_gt):4d}  (answer-quality gap lives here)")
    print(f"  stage-only reaches : {len(stage_only_gt):4d}  (agent LOST retrieval/plan)")
    print(f"  agent-only reaches : {len(agent_only_gt):4d}  (agent GAINED retrieval)")
    print(f"  neither reaches    : {len(neither_gt):4d}  (unreachable for both)")

    # among both-reach: answer-quality F1 gap
    if both_gt:
        s_mean = statistics.mean(d["stage_mean"] for d in both_gt)
        a_mean = statistics.mean(d["agent_mean"] for d in both_gt)
        print(f"\n  among both-reach ({len(both_gt)} cases): stage F1={s_mean:.4f} agent F1={a_mean:.4f} gap={s_mean-a_mean:+.4f}")

    out = dict(
        n_cases=n_cases,
        stage=dict(n=len(stage), mean_f1=agg(sp), best_f1=agg(sp, "best_f1"), gt_hit=gt_hit_rate(sp)),
        agent_all=dict(n=len(agent_all), mean_f1=agg(ap_all), best_f1=agg(ap_all, "best_f1"), gt_hit=gt_hit_rate(ap_all)),
        agent_valid=dict(n=len(agent_valid), mean_f1=agg(ap_val), best_f1=agg(ap_val, "best_f1"), gt_hit=gt_hit_rate(ap_val)),
        agent_failed_n=len(agent_failed),
        buckets=dict(both_gt=len(both_gt), stage_only_gt=len(stage_only_gt),
                     agent_only_gt=len(agent_only_gt), neither_gt=len(neither_gt)),
        losses=losses[:args.top],
        wins=wins[:args.top],
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=2)
    print(f"\nwrote -> {args.out}")


if __name__ == "__main__":
    main()
