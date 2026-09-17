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


def dump_case(f, c, dist, rec, gold_disp, probs=None):
    tr = rec["trajectory"]
    gold_list = rec["_gold_list"]
    gold_n = {norm(g): g for g in gold_list if g}
    phis = phi_by_idx(c, dist)
    ops_by_idx = {o["idx"]: o for o in c["ops"]}
    blocks_by_idx = {b["idx"]: b for b in c.get("blocks", [])}
    block_list = c.get("blocks", [])
    pm = {}
    if probs:
        pm = {block_list[int(i)]["idx"]: m for i, m in
              (probs.get("modules") or {}).items()
              if int(i) < len(block_list)}
    d_str = lambda x: "∞" if x == float("inf") else str(x)
    nec_str = lambda b: {
        "yes": "必要(删后断)", "no": "非必要(删后通)",
        "n/a": "n/a(gold未连通)"}.get(b.get("necessary", "?"), "?")
    f.write("=" * 90 + "\n")
    _head = (f"CASE {c['case_id']}  sample s{c['sample']}  f1={c['f1']:.2f}  "
             f"hit={c['hit']}  miss_kind={c.get('miss_kind', '-')}"
             f"  证据图gold连通="
             f"{'是' if c.get('_gold_reach_full') else '否'}")
    if probs and probs.get("p0") is not None:
        _head += (f"  概率 p0={probs['p0']:.4f} pF={probs['pF']:.4f}"
                  f" Δ={(probs['pF'] or 0)-(probs['p0'] or 0):+.4f}")
    f.write(_head + "\n")
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
        pstr = ""
        if i in pm:
            m = pm[i]
            def _r(x):
                return f"{x:+.4f}" if isinstance(x, (int, float)) else "?"
            pstr = (f"  概率 d={_r(m.get('d'))} l(移除伤害)={_r(m.get('l'))}"
                    f" f(独立)={_r(m.get('f'))} N={m.get('N')}"
                    f" g={'首达' if m.get('g') else '-'}"
                    f" 台阶={'是' if m.get('lineage') else 'no'}"
                    f" ⇒ 概率档={m.get('cls')}")
        if i in ops_by_idx:
            o = ops_by_idx[i]
            before, after, _ = phis.get(i, (float("inf"), float("inf"), None))
            adv = "推进" if after < before else \
                  ("覆盖gold" if o["p_gain"] > 0 else "未推进")
            b = blocks_by_idx.get(i, {})
            f.write(f"◆[{i}] 层操作: φ {d_str(before)}→{d_str(after)} "
                    f"({adv})  cov_gain={o['p_gain']}  width={o['width']} "
                    f"used={o['used']}  gold={o['gold_hit']}  "
                    f"通路={b.get('pathway', '?')[:16]}"
                    f"/{b.get('pathway_verdict', '?')}  "
                    f"结构必要={nec_str(b)}{pstr}\n")
        elif i in blocks_by_idx and blocks_by_idx[i].get("is_op") is False:
            before, after, b = phis[i]
            gh = b.get("gold_here") or ()
            adv = "推进" if after < before else \
                  ("覆盖gold" if gh else "未推进")
            f.write(f"◆[{i}] 基线块(首次建树): "
                    f"φ {d_str(before)}→{d_str(after)} ({adv})  "
                    f"gold={'有' if gh else '无'}  "
                    f"通路={b.get('pathway', '?')[:16]}"
                    f"/{b.get('pathway_verdict', '?')}  "
                    f"结构必要={nec_str(b)}{pstr}\n")
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
    # order matters: necessity stashes the display-graph phi that
    # break-point marking consumes
    mark_necessity(cases, rec_map)
    mark_break_points(cases, PKL)
    from annotate_layer_ops import reconcile_necessity
    reconcile_necessity(cases)
    # probability family (teacher-forcing p0/pF/p⁻/p_alone per module) when
    # available — produced by scripts/score_layer_op_probs.py
    probs_all = {}
    import os
    _pj = os.environ.get("PROBS_JSON",
                         "specs/layer_op_probs_2026-09-17.json")
    if os.path.exists(_pj):
        probs_all = json.load(open(_pj))
    with open(out, "w") as f:
        f.write("# 层操作人工审核：完整轨迹 dump（每动作原文 + gold 命中标记）\n\n"
                "每消息原文完整给出。★行=该消息命中的 gold 实体及原文行引用"
                "（答案就在这里）；◆行=φ(展示图上到最近gold的跳数)/cov_gain"
                "(gold覆盖率增量,非概率)/三档标注/通路判定/结构必要 + 概率族"
                "（p⁻=移除本模块后的gold概率, p_alone=仅本模块, l_i=pF−p⁻"
                "移除伤害;case头有 p0=模型直答/pF=全证据）。\n\n")
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
                probs = probs_all.get(f"{c['case_id']}|s{c['sample']}")
                dump_case(f, c, dist, rec, gold_disp, probs)
    print("wrote", out)


if __name__ == "__main__":
    main()
