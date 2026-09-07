#!/usr/bin/env python3
"""Trajectory-signal consistency audit (user methodology: 必须人读轨迹).

Samples modules per class from tmp/unified_class.json, joins the rollout
records, prints a compact human-readable specimen: question/gold/f1, module
table, the target module's call + key ack lines, the next action, final
answer. For manual verdict-against-story review.
"""
import json
import random
import re
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from informat_tf_calib import plan_var, module_fact

rows = json.load(open("tmp/unified_class.json"))
recs = json.load(open("reports/walkfix_r267g3.json"))
by_key = {}
for r in recs:
    by_key.setdefault((r["case_id"], r["sample_idx"]), r)

rng = random.Random(20260829)
def pick(cls, n, votes=None, anti=None):
    cand = [r for r in rows if r["cls"] == cls
            and (votes is None or votes in r["votes"])
            and (anti is None or anti not in r["votes"])
            and (r["case_id"], r["sample"]) in by_key]
    return rng.sample(cand, min(n, len(cand)))

SPECS = ([("eff", 3, None), ("red", 2, "repeat"), ("red", 2, "unused"),
          ("harm", 2, "div"), ("abstain", 2, None)] +
         [(r, 1, "constraint") for r in rng.sample(
             [r for r in rows if "constraint" in r["votes"]], 2)])
seen = set()
for cls, n, vote in SPECS:
    for row in pick(cls, n, vote):
        key = (row["case_id"], row["sample"])
        if key in seen:
            continue
        seen.add(key)
        r = by_key[key]
        traj = r["trajectory"]
        print("═" * 100)
        print(f"[{row['cls']}/{','.join(row['votes'])}] {row['case_id']} "
              f"s{row['sample']}  f1={r['f1']:.2f}  conf={row['conf']}")
        print(f"Q: {r['question']}")
        print(f"GOLD: {r['gold'][:3]}  ANSWER: {str(r['answer'])[:60]}  "
              f"plan_var={plan_var(traj)}")
        # module table
        for rr in rows:
            if rr["case_id"] == row["case_id"] and rr["sample"] == row["sample"]:
                mark = " ←TARGET" if rr["ack"] == row["ack"] else ""
                print(f"  mod@{rr['ack']:3d} [{rr['cls']:7s}] "
                      f"center={rr['center'][:30]}{mark}")
        # target detail
        i = row["ack"]
        for k in range(max(0, i - 1), min(len(traj), i + 3)):
            st = traj[k]
            c = (st.get("content") or "").strip()
            if st.get("role") == "assistant":
                print(f"  [{k}] ASST: {c[:220]}")
            else:
                head = "\n".join(c.split("\n")[:6])[:400]
                print(f"  [{k}] TOOL({st.get('name','')}): {head}")
        fact, fvar = module_fact(traj, i)
        print(f"  fact={fact} binds={fvar}")
