#!/usr/bin/env python3
"""Rendering-mechanism demo (2026-08-21): the three S4 forms on REAL case data.

Prototype of specs/rendering_mechanism_design.md — not the integrated pipeline.
Forms: list / record-table / join-table; separator hierarchy | > · > ; > =;
L1 uniform-attr hoist; L2 single-print. Input = real case graphs from the pkl.
"""
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/zhaoshu/subgraph")
from kgqa.traversal.cvt import is_cvt_like

PKL = Path("/zhaoshu/subgraph/data/cwq_processed/train_v4_repaired.pkl")


def case_by_prefix(prefix):
    s = next(x for x in pickle.loads(PKL.read_bytes())
             if x["id"].startswith(prefix))
    return s


def edges_of(s):
    ents = list(s["text_entity_list"]) + list(s.get("non_text_entity_list") or [])
    rels = s["relation_list"]
    out = []
    for k in range(len(s["r_id_list"])):
        r = rels[s["r_id_list"][k]] if s["r_id_list"][k] < len(rels) else None
        h = ents[s["h_id_list"][k]] if s["h_id_list"][k] < len(ents) else None
        t = ents[s["t_id_list"][k]] if s["t_id_list"][k] < len(ents) else None
        if r and h and t:
            out.append((h, r.rsplit(".", 1)[-1], t, r))
    return out


def short(r):
    return r.rsplit(".", 1)[-1].replace("_", " ")


# ── S1 事件化: CVT → 记录对象 ────────────────────────────────────────────────
def eventify(edges):
    records = {}          # cvt_id -> {role: value}
    named = []            # 命名↔命名边
    for h, rs, t, r in edges:
        if is_cvt_like(h) and not is_cvt_like(t):
            records.setdefault(h, {})[rs] = t
        elif is_cvt_like(t) and not is_cvt_like(h):
            records.setdefault(t, {})[rs] = h
            named.append((h, rs, t, r))     # 挂接头边(进入记录的辐条)
        else:
            named.append((h, rs, t, r))
    return records, named


# ── 形态一: 列表行(1跳纯边) ──────────────────────────────────────────────────
def render_list(named_edges, anchor):
    by_r = defaultdict(list)
    for h, rs, t, r in named_edges:
        if h == anchor and not is_cvt_like(t):
            by_r[rs].append(t)
        elif t == anchor and not is_cvt_like(h):
            by_r[rs].append(h)
    for rs, ts in by_r.items():
        ts = list(dict.fromkeys(ts))
        print(f"  {anchor} --{rs}--> {' | '.join(ts[:8])}"
              + (f"  (+{len(ts)-8} more)" if len(ts) > 8 else ""))


# ── 形态二: 记录表(CVT 簇) ───────────────────────────────────────────────────
def render_record_table(records, spoke_heads, title):
    """spoke_heads: 该簇的挂接关系(表头语境). 列=属性键并集, L1 一致列上提."""
    if not records:
        return
    keys = []
    for rec in records.values():
        for k in rec:
            if k not in keys:
                keys.append(k)
    uniform = [k for k in keys
               if all(k in rec and rec[k] == next(iter(records.values()))[k]
                      for rec in records.values())]
    cols = [k for k in keys if k not in uniform]
    hdr = f"  {title}"
    if uniform:
        u = next(iter(records.values()))
        hdr += f"   (all: " + "; ".join(f"{k}={u[k]}" for k in uniform) + ")"
    print(hdr)
    if cols:
        print("    " + " | ".join(f"{c:>26s}" for c in cols))
    for rid, rec in list(records.items())[:12]:
        cells = [ " · ".join([rec[c]]) if c in rec else ""
                  for c in cols ]
        print("    " + " | ".join(f"{c[:26]:>26s}" for c in cells))
    if len(records) > 12:
        print(f"    … +{len(records)-12} more rows (see navigation index)")


# ── 形态三: 连接表(2命名跳) ─────────────────────────────────────────────────
def render_join_table(edges, anchor, rel1, rel2):
    mids = defaultdict(set)
    for h, rs, t, r in edges:
        if h == anchor and rs == rel1:
            mids[t]
        if t == anchor and rs == rel1:
            mids[h]
    for h, rs, t, r in edges:
        for mid in list(mids):
            if h == mid and rs == rel2 and not is_cvt_like(t):
                mids[mid].add(t)
            elif t == mid and rs == rel2 and not is_cvt_like(h):
                mids[mid].add(h)
    print(f"  {anchor} — {rel1} → {rel2}")
    print(f"    {'mid':>26s} | {rel2}")
    for mid, leaves in mids.items():
        cell = " · ".join(sorted(leaves)[:6]) + (" · …" if len(leaves) > 6 else "")
        print(f"    {mid[:26]:>26s} | {cell}")


def find_case(pred, desc):
    for x in pickle.loads(PKL.read_bytes()):
        try:
            if pred(edges_of(x)):
                print(f"  [案例 {x['id'][:24]}]")
                return x
        except Exception:
            continue
    print(f"  (未找到含 {desc} 的案例)")
    return None


print("=" * 90)
print("【形态二：记录表】Sandler 表演事件簇（原 8k-token 单行）")
s = find_case(lambda es: any(e[0] == "Adam Sandler" for e in es)
              and sum(1 for e in es if is_cvt_like(e[2]) and e[0] == "Adam Sandler") >= 15,
              "Adam Sandler 表演簇")
if s:
    edges = edges_of(s)
    recs, named = eventify(edges)
    perf = {k: v for k, v in recs.items() if ("film" in v or "character" in v)}
    render_record_table(perf, [], "Adam Sandler — film performances")

print()
print("=" * 90)
print("【形态三：连接表】北欧语言（原跨行重复+方向混乱）")
s3 = find_case(lambda es: any(e[0] == "Denmark" and e[1] == "contains" for e in es)
               and any(e[1] == "languages_spoken" for e in es),
               "Denmark contains + languages_spoken")
if s3:
    render_join_table(edges_of(s3), "Denmark", "contains", "languages_spoken")

print()
print("=" * 90)
print("【形态一：列表行】1 跳纯边")
if s3:
    render_list([e for e in edges_of(s3) if not is_cvt_like(e[0]) and not is_cvt_like(e[2])], "Faroe Islands")
