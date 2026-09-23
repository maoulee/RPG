#!/usr/bin/env python3
"""Regression compare dump (one-off, 2026-09-23): for the top-loss cases of
the aligned v24b vs v23 run, emit BOTH trajectories (full chain: call + tool
result) plus an auto-diff of EVIDENCE LINES present in v23 but absent in
v24b — aimed at the three regression suspects (through-chain mid-hop tail
loss / edge-level dedup overkill / frontier direct-hop disappearance).
Usage: python scripts/regress_compare.py
Writes specs/regress_compare_2026-09-23.md
"""
import json, re
from collections import defaultdict

V23 = "reports/v23_final_48x3.json"
V24 = "reports/v24b_lenfirst_48x3.json"
CASES = ["WebQTrn-2152", "WebQTest-1171", "WebQTest-576",
         "WebQTrn-21_", "WebQTrn-25_", "WebQTrn-2540"]

def load(path):
    out = defaultdict(list)
    for r in json.loads(open(path).read()):
        out[r["case_id"]].append(r)
    return out

def call_of(traj, j):
    for k in range(j - 1, -1, -1):
        if traj[k].get("role") == "assistant":
            c = str(traj[k].get("content", ""))
            m = re.search(r"tool:\s*(\S+).*?((?:\n(?:center|relations|sg|entities|answer|fact):[^\n]*)+)",
                          c, re.S)
            if m:
                return m.group(1), [l for l in m.group(0).split("\n") if l.strip()]
            return "?", [l for l in c.split("\n") if l.startswith(("tool:", "center:", "relations:", "sg:"))][:4]
    return "?", []

def ev_lines(content):
    """Evidence rows of a tool result (── sections and edge rows)."""
    out = []
    for ln in content.split("\n"):
        s = ln.strip()
        if s.startswith("──") or re.search(r"--[\w.]+-->", s) or s.startswith("▸ patterns"):
            out.append(re.sub(r"\s+", " ", s))
    return out

def canon(line):
    """Direction/order-insensitive signature for row-level compare."""
    s = re.sub(r"\s*\[.*?\]\s*", " ", line)
    parts = re.split(r"\s*\|\s*", s)
    return " ".join(sorted(p.strip() for p in parts if p.strip()))

def pick_pair(v23rs, v24rs):
    """v23 best-f1 sample vs v24 worst-f1 sample of the case."""
    a = max(v23rs, key=lambda r: r.get("f1") or 0)
    b = min(v24rs, key=lambda r: r.get("f1") or 0)
    return a, b

def dump_traj(L, tag, r):
    traj = r.get("trajectory") or []
    L.append(f"\n{'='*72}\n[{tag}] sample={r.get('sample_idx')} f1={r.get('f1')} "
             f"hit={r.get('hit')} answer={str(r.get('answer'))[:60]!r} "
             f"gold={str(r.get('gold'))[:60]}")
    for j, m in enumerate(traj):
        role = m.get("role")
        c = str(m.get("content", ""))
        if role == "tool":
            tool, cl = call_of(traj, j)
            L.append(f"\n--- msg{j} [tool:{tool}] {' / '.join(cl[1:4])}")
            L.append(c)
        elif role == "assistant":
            L.append(f"\n--- msg{j} [assistant: 思考+命令,完整] ---")
            L.append(c)
        elif role in ("user", "system"):
            L.append(f"\n--- msg{j} [{role}: 环境消息,完整] ---")
            L.append(c)

def main():
    v23, v24 = load(V23), load(V24)
    L = ["# 回退 case 对比轨迹 dump（v23_final vs v24b_lenfirst）— 2026-09-23",
         "",
         "每 case:v23 最优采样 vs v24 最差采样,全链路(调用+完整工具结果)。",
         "尾部附自动 diff:v23 渲染过而 v24 全轨迹未再出现的证据行(丢失证据,",
         "对准三嫌疑:through-chain 中间层丢弃/边级去重误杀/frontier 直连消失)。",]
    for pfx in CASES:
        k23 = [k for k in v23 if k.startswith(pfx)]
        k24 = [k for k in v24 if k.startswith(pfx)]
        if not k23 or not k24:
            continue
        a, b = pick_pair(v23[k23[0]], v24[k24[0]])
        L.append(f"\n\n########## CASE {pfx} ##########")
        L.append(f"Q: {a.get('question','')}")
        L.append(f"v23 mean-f1={sum(r.get('f1') or 0 for r in v23[k23[0]])/3:.2f}  "
                 f"v24 mean-f1={sum(r.get('f1') or 0 for r in v24[k24[0]])/3:.2f}")
        dump_traj(L, "v23", a)
        dump_traj(L, "v24", b)
        # lost-evidence diff
        ev23, ev24 = set(), set()
        for r in (a, b):
            tgt, sink = (ev23, ev24) if r is a else (ev24, ev23)
            for m in (r.get("trajectory") or []):
                if m.get("role") == "tool":
                    for ln in ev_lines(str(m.get("content", ""))):
                        sink.add(canon(ln))
        lost = sorted(x for x in ev23 - ev24 if "--" in x and "patterns" not in x)
        L.append(f"\n〔丢失证据行〕v23 有 / v24 无 (canonical, {len(lost)} 行):")
        for ln in lost[:40]:
            L.append(f"    - {ln[:150]}")
    open("specs/regress_compare_2026-09-23.md", "w").write("\n".join(L) + "\n")
    print("wrote specs/regress_compare_2026-09-23.md")

if __name__ == "__main__":
    main()
