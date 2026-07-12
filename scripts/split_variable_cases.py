#!/usr/bin/env python3
"""From multi-sample results, pick VARIABLE (discriminative, GRPO-has-signal)
cases, filter clean (gold-reachable), split into train / held-out by CASE.

GRPO needs per-case reward VARIANCE (all-same reward → zero gradient). Flat cases
(62% on test) are useless for GRPO. This keeps only variable cases, splits by case
(no sample leakage), writes train + held-out trajectory sets.
"""
import json, sys, argparse, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_stage_scorer import score_case


def var(xs):
    xs = [x or 0 for x in xs]
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="multi-sample results.json")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--var-threshold", type=float, default=0.01,
                    help="min total stage-variance to keep (GRPO signal)")
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.input.endswith('.jsonl'):
        d = [json.loads(line) for line in open(args.input) if line.strip()]
    else:
        d = json.load(open(args.input))
    by_case = collections.defaultdict(list)
    for r in d:
        by_case[r["case_id"].split("_")[0]].append(r)

    rows = []
    for cid, rs in by_case.items():
        if len(rs) < 2:
            continue
        scored = []
        for r in rs:
            try:
                s = score_case(r)
                scored.append((s.get("S_plan") or 0, s.get("S_select") or 0, s.get("S_reason") or 0, r))
            except Exception:
                pass
        if len(scored) < 2:
            continue
        vp = var([x[0] for x in scored]); vs = var([x[1] for x in scored]); vr = var([x[2] for x in scored])
        tot = vp + vs + vr
        reachable = any((x[0] or 0) > 0.5 for x in scored)  # S_plan>0.5 → gold reached
        bottleneck = max([('plan', vp), ('select', vs), ('reason', vr)], key=lambda x: x[1])[0] if tot > 1e-9 else 'flat'
        rows.append(dict(cid=cid, tot=tot, vp=vp, vs=vs, vr=vr, reachable=reachable,
                         bottleneck=bottleneck, n=len(scored), recs=[x[3] for x in scored]))

    n_total = len(rows)
    variable = [r for r in rows if r["tot"] >= args.var_threshold and r["reachable"]]
    flat = [r for r in rows if r["bottleneck"] == "flat"]
    print(f"total cases: {n_total} | variable+clean: {len(variable)} | flat: {len(flat)} | unreachable: {n_total - len(variable) - sum(1 for r in flat if r['reachable'])}")
    bk = collections.Counter(r["bottleneck"] for r in variable)
    print(f"variable bottleneck: {dict(bk)}")

    # deterministic split by case (sorted), test_frac held out
    variable.sort(key=lambda r: r["cid"])
    n_test = max(1, int(len(variable) * args.test_frac))
    heldout_cids = set(r["cid"] for r in variable[:n_test])
    train, held = [], []
    for r in variable:
        (held if r["cid"] in heldout_cids else train).append(r)

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    def write(split, cases):
        recs = []
        for c in cases:
            for r in c["recs"]:
                rec = dict(r)
                recs.append(rec)
        Path(out / f"{split}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
        return len(recs), len(cases)

    ntr, ctr = write("train", train)
    nhe, che = write("heldout", held)
    print(f"\ntrain: {ctr} cases / {ntr} trajectories")
    print(f"heldout: {che} cases / {nhe} trajectories")
    print(f"(var-threshold={args.var_threshold}, test-frac={args.test_frac})")
    # also dump case-level diagnostics
    Path(out / "case_diagnostics.jsonl").write_text("\n".join(json.dumps({k: v for k, v in r.items() if k != "recs"}, ensure_ascii=False) for r in rows))
    print(f"wrote train.jsonl / heldout.jsonl / case_diagnostics.jsonl -> {out}")


if __name__ == "__main__":
    main()
