"""FULL trajectory dump for human audit: every message verbatim, with
per-action answer-hit marking.

For each dumped trajectory:
  - every assistant message (reasoning + tool call) verbatim
  - every tool/environment message verbatim
  - after any message that mentions a gold entity: a ★ line listing WHICH
    gold entities appear, plus the original lines (verbatim quotes) where
    they appear — so a reviewer sees the answer-bearing information in situ
  - after sg deliveries: ◆ line with phi (BFS hops to nearest gold),
    p_gain, and the v2 annotation for layer ops
Usage:
  python scripts/dump_traj_full.py reports/<run>.json \
      --pick WebQTest-1379:0,WebQTest-1379:1 --out specs/xxx.md
"""
import ast
import collections
import json
import sys

sys.path.insert(0, "scripts")
from annotate_layer_ops import annotate, gold_reference, norm

MAX_GOLD_LINES = 8


def gold_lines(content, gold_n):
    """(hit_gold_norms, verbatim lines containing them)."""
    hits, lines = set(), []
    for ln in content.split("\n"):
        lnn = norm(ln)
        if not lnn:
            continue
        for g in gold_n:
            if g and g in lnn:
                hits.add(g)
                if len(lines) < MAX_GOLD_LINES and ln.strip() not in lines:
                    lines.append(ln.strip())
    return hits, lines


def dump_case(f, c, dist, rec, gold_disp):
    tr = rec["trajectory"]
    gold_list = rec["_gold_list"]
    gold_n = {norm(g): g for g in gold_list if g}
    phis = phi_by_idx(c, dist)
    ops_by_idx = {o["idx"]: o for o in c["ops"]}
    blocks_by_idx = {b["idx"]: b for b in c.get("blocks", [])}
    d_str = lambda x: "∞" if x == float("inf") else str(x)
    nec_str = lambda b: {
        "yes": "必要(删后断)", "no": "非必要(删后通)",
        "n/a": "n/a(gold未连通)"}.get(b.get("necessary", "?"), "?")
    f.write("=" * 90 + "\n")
    f.write(f"CASE {c['case_id']}  sample s{c['sample']}  f1={c['f1']:.2f}  "
            f"hit={c['hit']}  miss_kind={c.get('miss_kind', '-')}"
            f"  证据图gold连通={'是' if c.get('_gold_reach_full') else '否'}\n")
    f.write(f"Q: {rec.get('question', '')}\n")
    f.write(f"GOLD: {gold_disp}\n")
    f.write(f"PRED: {rec.get('answer')}   pred_entities: "
            f"{rec.get('pred_entities')}\n")
    for t in c.get("pathway_table", []):
        core = " > ".join("|".join(rels) for rels in t["core_path"]) \
            if t["core_path"] else "-"
        f.write(f"  通路[{t['verdict']}] {t['root'][:28]}: blocks={t['blocks']} "
                f"独立到达gold={'是' if t['reached'] else '否'} 核心路径={core[:90]}\n")
    f.write("=" * 90 + "\n\n")
    for i, m in enumerate(tr):
        role = m["role"].upper()
        name = m.get("name")
        head = f"────── [{i}] {role}" + (f" ({name})" if name else "") \
            + " " * max(0, 60 - len(str(i)) - len(role)) + "──────"
        f.write(head + "\n")
        f.write(m["content"].rstrip() + "\n")
        # gold-hit marking on every message
        hits, qlines = gold_lines(m["content"], gold_n)
        if hits:
            disp = ", ".join(gold_n[g] for g in sorted(hits))
            f.write(f"★[{i}] 命中GOLD: {disp}\n")
            for ql in qlines:
                f.write(f"   > {ql[:240]}\n")
        # phi/annotation blocks after sg deliveries
        if i in ops_by_idx:
            o = ops_by_idx[i]
            before, after, _ = phis.get(i, (float("inf"), float("inf"), None))
            adv = "推进" if after < before else \
                  ("覆盖gold" if o["p_gain"] > 0 else "未推进")
            b = blocks_by_idx.get(i, {})
            f.write(f"◆[{i}] 层操作标注: φ {d_str(before)}→{d_str(after)} "
                    f"({adv})  p_gain={o['p_gain']}  width={o['width']} "
                    f"used={o['used']}  gold={o['gold_hit']}  "
                    f"标注={o['label']}  通路={b.get('pathway', '?')[:16]}"
                    f"/{b.get('pathway_verdict', '?')}  "
                    f"结构必要={nec_str(b)}\n")
        elif i in blocks_by_idx and blocks_by_idx[i].get("is_op") is False:
            before, after, b = phis[i]
            gh = b.get("gold_here") or ()
            adv = "推进" if after < before else \
                  ("覆盖gold" if gh else "未推进")
            f.write(f"◆[{i}] 基线块(首次建树,不参与三档): "
                    f"φ {d_str(before)}→{d_str(after)} ({adv})  "
                    f"gold={'有' if gh else '无'}  "
                    f"通路={b.get('pathway', '?')[:16]}"
                    f"/{b.get('pathway_verdict', '?')}  "
                    f"结构必要={nec_str(b)}\n")
        f.write("\n")
    labs = collections.Counter(o["label"] for o in c["ops"])
    seq = " ".join(f"{'推进' if o.get('on_path') == 'adv' else '·'}→"
                   f"{o['label'].split('-')[-1][:6]}" for o in c["ops"])
    f.write(f"诊断: {seq}\n层操作标注分布 {dict(labs)}\n\n")


def phi_by_idx(case, dist):
    INF = float("inf")
    d = INF
    out = {}
    for b in case.get("blocks", []):
        new = list(b.get("_delta") or [])
        d_op = min([dist.get(norm(e), INF) for e in new] or [INF]) \
            if dist else INF
        out[b["idx"]] = (d, min(d, d_op), b)
        d = min(d, d_op)
    return out


def main():
    path = sys.argv[1]
    out = "specs/layer_op_traj_full_dump_2026-09-17.md"
    pick = ["WebQTest-1379:0", "WebQTest-1379:1", "WebQTest-1797:1",
            "WebQTrn-567_11fd:0", "WebQTrn-567_df97:0", "WebQTrn-2784_b64:2",
            "WebQTrn-21_:0", "WebQTrn-2209_c13:0",
            # v4 pathway specimens: dual-substitute / sub+unreach / all-unreach
            "WebQTrn-2316_b8e:0", "WebQTrn-1731_4ee:0", "WebQTrn-2784_b64:0",
            "WebQTest-626_01a:0", "WebQTrn-2576_872:0", "WebQTest-1379:1"]
    argv = sys.argv[2:]
    for a in argv:
        if a == "--out":
            out = argv[argv.index(a) + 1]
        if a == "--pick":
            pick = argv[argv.index(a) + 1].split(",")
    ops, cases = annotate(path)
    from annotate_layer_ops import mark_break_points, mark_necessity
    import pickle
    PKL = "/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl"
    mark_break_points(cases, PKL)
    samples = pickle.loads(open(PKL, "rb").read())
    by_id = {s.get("id"): s for s in samples}
    data = json.load(open(path))
    rec_map = {}
    for rec in data:
        tr = rec["trajectory"]
        if isinstance(tr, str):
            tr = ast.literal_eval(tr)
        if isinstance(rec["gold"], list):
            gold_list = rec["gold"]
        else:
            try:
                gold_list = json.loads(rec["gold"])
            except (json.JSONDecodeError, TypeError):
                gold_list = ast.literal_eval(rec["gold"])
        rec["_gold_list"] = gold_list
        rec["trajectory"] = tr
        rec_map[(rec["case_id"], str(rec.get("sample_idx")))] = rec
    mark_necessity(cases, rec_map)
    from annotate_layer_ops import reconcile_necessity
    reconcile_necessity(cases)
    with open(out, "w") as f:
        f.write("# 层操作人工审核：完整轨迹 dump（每动作原文 + gold 命中标记）\n\n"
                "每消息原文完整给出。★行=该消息命中的 gold 实体及原文行引用"
                "（答案就在这里）；◆行=φ(到最近gold的BFS跳数)/p_gain/三档标注"
                "（层操作）或基线块标记（首次建树，不参与三档）。\n"
                "近似提示: hub 型 gold（Priest 等）φ 推进假阳性，以 ★/p_gain "
                "为准。\n\n")
        for p in pick:
            pref, s = (p.split(":") + [""])[:2] if ":" in p else (p, "")
            for c in cases:
                if not c["case_id"].startswith(pref):
                    continue
                if s and str(c["sample"]) != s:
                    continue
                if not c["ops"]:
                    continue
                rec = rec_map[(c["case_id"], str(c["sample"]))]
                # φ on the DISPLAY graph (mark_necessity stashes it) —
                # same ruling basis as the annotation itself
                dist = c.get("_display_dist")
                gold_disp = str(rec["_gold_list"])[:200]
                dump_case(f, c, dist, rec, gold_disp)
    print("wrote", out)


if __name__ == "__main__":
    main()
