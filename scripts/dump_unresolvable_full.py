#!/usr/bin/env python3
"""FULL-trajectory dump of the 31 unresolvable modules (user request: every
module's content, not just the target). Every trajectory step verbatim —
assistant reasoning + content, every tool/harness ack in full; the target
module wrapped in ◀◀ markers. Output: tmp/unresolvable_full.md
"""
import json
import re
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tooltrace_calib import gold_forms
from informat_tf_calib import plan_var

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
        continue
    entries.append((o, rec, pr))

def indent(text, prefix):
    return "\n".join(prefix + ln for ln in text.split("\n"))


L = [f"# 真不可裁决模块 — 完整轨迹人工审核包({len(entries)} 条)",
     "",
     "每条含该样本的完整轨迹全文(assistant 的 reasoning 与调用、全部工具/"
     "harness 返回)。◀◀ 标记目标模块。请判定:有效/冗余/有害/不训。",
     ""]
for n, (o, rec, pr) in enumerate(entries, 1):
    traj = rec["trajectory"]
    L.append("")
    L.append("█" * 100)
    pl_txt = (f"搭档@{pr['partner_ack']}(行重叠{pr['overlap']}) dI_pair={pr['dI_pair']:+.3f}"
              if pr and pr.get("dI_pair") is not None else "无行重叠搭档(成对未测)")
    L.append(f"## #{n}  {o['case_id']}  样本 s{o['sample']}  f1={rec['f1']:.2f}"
             f"   【目标 mod@{o['ack']}】")
    L.append(f"问题: {rec['question']}")
    L.append(f"金标: {rec['gold'][:6]}")
    L.append(f"实际答案: {str(rec['answer'])[:100]}")
    L.append(f"读数: dI={o['dI']:+.3f}(移除反升) alone={o['alone_gain']:+.2f} "
             f"结构票={','.join(o['votes'])} | {pl_txt}")
    L.append("")
    L.append("模块判定表:")
    for r in unified:
        if r["case_id"] == o["case_id"] and r["sample"] == o["sample"]:
            cls = "★corrupted" if r["ack"] == o["ack"] else r["cls"]
            L.append(f"  mod@{r['ack']:3d} [{cls:10s}] 票={','.join(r['votes']):40s} "
                     f"center={r['center'][:34]}")
    L.append("")
    L.append("──── 轨迹全文 ────")
    for k, st in enumerate(traj):
        role = st.get("role")
        content = (st.get("content") or "").rstrip()
        name = st.get("name") or ""
        is_target = (role == "tool" and k == o["ack"])
        if is_target:
            L.append(f"◀◀◀ 目标模块开始 [{k}] TOOL({name}) ◀◀◀")
        if role == "assistant":
            reasoning = (st.get("reasoning") or "").strip()
            if reasoning:
                L.append(f"[{k}] ASSISTANT 推理:")
                L.append(indent(reasoning, "    | "))
            L.append(f"[{k}] ASSISTANT 动作:")
            L.append(indent(content, "    "))
        elif role == "tool":
            L.append(f"[{k}] TOOL({name}):")
            L.append(indent(content, "    "))
        else:
            L.append(f"[{k}] {role}:")
            L.append(indent(content, "    "))
        if is_target:
            L.append(f"◀◀◀ 目标模块结束 [{k}] ◀◀◀")
open("tmp/unresolvable_full.md", "w").write("\n".join(L))
print(f"dumped {len(entries)} FULL trajectories → tmp/unresolvable_full.md "
      f"({os.path.getsize('tmp/unresolvable_full.md')//1024} KB)")

