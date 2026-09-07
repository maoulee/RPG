#!/usr/bin/env python3
"""Dump the 31 truly-untrainable modules for HUMAN review (user request).

Truly-untrainable = competition-corrupted (informative ∧ dI<−θ ∧ vetoed)
∧ NOT joint_eff (pair-LOO didn't crash) ∧ NOT carrier (checkpoint didn't
declare a gold in a mostly-correct run). Each entry: question/gold/answer,
plan facts, module table with classes, target module's call + ack head +
declared checkpoint, every axis's reading, and the failed-resolution note.
Output: tmp/unresolvable_dump.md
"""
import json
import re
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tooltrace_calib import gold_forms
from informat_tf_calib import plan_var, module_fact

TH = 0.005
CK = re.compile(r"=\s*\[([^\]]*)\]")

out = json.load(open("tmp/abstain_resolved.json"))
pair = {(r["case_id"], r["sample"], r["ack"]): r
        for r in json.load(open("tmp/pair_loo.json"))}
unified = json.load(open("tmp/unified_class.json"))
recs = json.load(open("reports/walkfix_r267g3.json"))
by_key = {}
for r in recs:
    by_key.setdefault((r["case_id"], r["sample_idx"]), r)

corrupted = [o for o in out if o["cls2"] == "abstain" and o["dI"] is not None
             and o["dI"] < -TH and "loo_neg" not in o["votes2"]]

entries = []
for o in corrupted:
    rec = by_key[(o["case_id"], o["sample"])]
    pr = pair.get((o["case_id"], o["sample"], o["ack"]))
    if pr and pr["verdict"] == "joint_eff":
        continue
    golds = [g.lower() for g in gold_forms(rec)]
    ck_vals = ""
    for j in range(o["ack"] + 1, len(rec["trajectory"])):
        st = rec["trajectory"][j]
        if st.get("role") == "assistant":
            m = CK.search(st.get("content") or "")
            ck_vals = (m.group(1).lower() if m else "")
            break
    if any(g in ck_vals for g in golds) and rec["f1"] > 0.5:
        continue                                       # carrier → resolved
    entries.append((o, rec, pr))

lines = [f"# 真不可裁决模块人工审核包({len(entries)} 条)\n",
         "判定态:有信息(alone⁺)∧ 移除后概率反升(dI<0)∧ 有害被否决 "
         "∧ 成对移除不塌 ∧ checkpoint 未承载金标(或轨迹答错)。\n",
         "请逐条人审:该模块的行为该算什么?(有效/冗余/有害/不训)\n"]
for n, (o, rec, pr) in enumerate(entries, 1):
    traj = rec["trajectory"]
    fact, fvar = module_fact(traj, o["ack"])
    lines.append("\n" + "═" * 96)
    lines.append(f"## #{n}  {o['case_id']}  样本 s{o['sample']}  f1={rec['f1']:.2f}")
    lines.append(f"问题: {rec['question']}")
    lines.append(f"金标: {rec['gold'][:5]}")
    lines.append(f"实际答案: {str(rec['answer'])[:80]}")
    lines.append(f"plan 答案变量: {plan_var(traj)}")
    # module table
    mods = [r for r in unified
            if r["case_id"] == o["case_id"] and r["sample"] == o["sample"]]
    lines.append("模块表:")
    for r in mods:
        mark = "  ← 目标" if r["ack"] == o["ack"] else ""
        cls = r["cls"]
        if r["ack"] == o["ack"]:
            cls = "corrupted"
        lines.append(f"  mod@{r['ack']:3d} [{cls:8s}] 票={','.join(r['votes'])} "
                     f"center={r['center'][:32]}{mark}")
    # target module detail
    i = o["ack"]
    call = ""
    for k in range(i - 1, -1, -1):
        if traj[k].get("role") == "assistant":
            call = (traj[k].get("content") or "").strip()[:300]
            break
    ack = (traj[i].get("content") or "").strip().split("\n")
    lines.append(f"目标模块调用:\n```\n{call}\n```")
    lines.append(f"目标模块返回(前 12 行):\n```\n" +
                 "\n".join(ack[:12]) + "\n```")
    lines.append(f"事实归属: {fact}  绑定变量: {fvar}")
    lines.append(f"checkpoint 声明值: {ck_vals[:120] or '(空/未找到)'}")
    # axis readings
    pl = f"成对搭档 @{pr['partner_ack']}(行重叠 {pr['overlap']}), dI_pair={pr['dI_pair']:.3f}" \
         if pr and pr.get("dI_pair") is not None else "无行重叠搭档/未测成对"
    lines.append(
        f"各轴读数: dI={o['dI']:.3f}(移除反升)  alone_gain={o['alone_gain']:.3f}  {pl}")
    lines.append(f"原结构票: {','.join(o['votes'])} → {pl}")
    # what the model did right after
    nxt = ""
    for k in range(i + 1, min(i + 3, len(traj))):
        if traj[k].get("role") == "assistant":
            nxt = (traj[k].get("content") or "").strip()[:200]
            break
    lines.append(f"下一动作:\n```\n{nxt}\n```")

open("tmp/unresolvable_dump.md", "w").write("\n".join(lines))
print(f"dumped {len(entries)} entries → tmp/unresolvable_dump.md")
# compact index
for n, (o, rec, pr) in enumerate(entries, 1):
    print(f"#{n:2d} f1={rec['f1']:.2f} dI={o['dI']:+.3f} "
          f"alone={o['alone_gain']:+.2f} "
          f"pair={pr['dI_pair'] if pr and pr.get('dI_pair') is not None else '—'} "
          f"Q: {rec['question'][:60]}")
