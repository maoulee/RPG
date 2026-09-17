"""Annotate every layer operation in a run's trajectories with effectiveness
signals (human-review ground truth for the walk-result-based idempotence /
gold-reach redesign).

Per layer-op (retrieve_subgraph result carrying layer_action / anchor_sequence):
  gold_hit   first vs re-hit of a gold entity in this op's evidence blocks
  width      # new entity names vs the union of all earlier tool messages
  used       # of those new names cited by a LATER checkpoint/answer line
  comps      per-layer completion counts (vs previous op on the same root)
Preliminary label (heuristic, for human review):
  effective   gold first-hit, or (width>=3 and used>=1)
  ineffective layer_action=repeat / counts-unchanged with width==0 and no gold
  harmful     update after which previously-seen gold never reappears (f1<0.5),
              or width>=10 & used==0 & >=2 rejections after the op
  mixed       everything else

Usage: python scripts/annotate_layer_ops.py reports/<run>.json \
           [--families WebQTrn-2209,WebQTest-626 --out specs/xxx.md]
"""
import ast
import collections
import json
import pickle
import re
import sys

ROOT_SPLIT = "⭢"
BLOCK_RE = re.compile(r"^── (.+) ──$")
EDGE_RE = re.compile(r"--([\w.]+)--> (.+)")
ANCHOR_RE = re.compile(r"^anchor_sequence: (.+)$", re.M)
ACTION_RE = re.compile(r"^layer_action: (.+)$", re.M)
CHECKPOINT_RE = re.compile(r"(✓\]|✗\])|tool: answer|entities:")
REJECT_RE = re.compile(r"STAGE GATE|REJECTED|Second refusal|NONE → ladder|"
                       r"MECHANICAL MISMATCH")


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def entities_of(content):
    """Entity names from evidence blocks: block headers, edge tails/heads.
    Only lines between `triples:` and the first note/anchor/candidates line
    (the note section contains format EXAMPLES that would pollute the set).
    CVT ids (m./g.) excluded; numeric values kept (gold may be numeric)."""
    out, in_blocks = set(), False
    for line in content.split("\n"):
        if line.startswith("triples:"):
            in_blocks = True
            continue
        if not in_blocks:
            continue
        if line.startswith(("note:", "anchor_sequence:", "layer_action:",
                            "candidates:", "entities: not")):
            break
        b = BLOCK_RE.match(line)
        if b:
            _add(out, b.group(1))
            continue
        m = EDGE_RE.search(line)
        if m:
            _add(out, m.group(2))
            head = line.split("--", 1)[0].strip()
            _add(out, head)
    return out


def _add(out, chunk):
    for name in chunk.split(" | "):
        name = name.strip()
        if not name or name.startswith(("m.", "g.", "CVT:")):
            continue
        if "[" in name:                       # CVT inline-attr display
            name = name.split("[", 1)[0].strip()
        if name and not name.startswith("--"):
            out.add(name)


def parse_anchor(content):
    m = ANCHOR_RE.search(content)
    if not m:
        return None, []
    parts = [p.strip() for p in m.group(1).split(ROOT_SPLIT)]
    root, layers = parts[0], []
    for p in parts[1:]:
        cm = re.search(r"\((\d+)\)\s*$", p)
        layers.append((p, int(cm.group(1)) if cm else -1))
    return root, layers


def cite_lines(msgs):
    """Assistant lines that cite evidence: checkpoints, answer calls."""
    lines = []
    for m in msgs:
        if m["role"] != "assistant":
            continue
        for ln in m["content"].split("\n"):
            if CHECKPOINT_RE.search(ln):
                lines.append(norm(ln))
    return lines


def annotate(path):
    data = json.load(open(path))
    ops, cases = [], []
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
        gold_n = {norm(g): g for g in gold_list if g}
        seen = set()
        prev_comps = {}                        # root -> [(rels,count),...]
        gold_seen_before = set()
        case_ops, blocks = [], []
        for i, m in enumerate(tr):
            if m["role"] != "tool":
                continue
            c = m["content"]
            is_sg = c.startswith(("triples:", "fact_id:"))
            is_op = "layer_action" in c
            if not (is_sg or is_op):
                continue
            # ALL sg deliveries (with or without layer ops) update the
            # information baseline — non-layer first-tree calls deliver
            # entities too and must count toward width/phi/gold coverage.
            action_m = ACTION_RE.search(c)
            action = action_m.group(1) if action_m else ("sg" if is_sg else "?")
            root, layers = parse_anchor(c)
            ents = entities_of(c)
            gold_here = {g for g in gold_n if g in {norm(e) for e in ents}}
            delta = {e for e in ents if norm(e) not in seen}
            blocks.append({"idx": i, "is_op": is_op, "action": action,
                           "_ents": ents, "_delta": delta,
                           "gold_here": gold_here})
            if not is_op:
                # baseline-only delivery: no annotation row, but the
                # sequence has already covered this gold/information
                gold_seen_before |= gold_here
                seen |= {norm(e) for e in ents}
                continue
            later = cite_lines(tr[i + 1:])
            used = sum(1 for e in delta
                       if any(norm(e) in ln for ln in later))
            counts = [n for _, n in layers]
            prev = prev_comps.get(root)
            prev_comps[root] = counts
            # v2 label (user ruling 2026-09-16): judge the INFORMATION MODULE's
            # help to answering, not the action form. helpful = advances gold
            # coverage or is cited by the final (hit) answer; nohelp-repeat =
            # zero new information regardless of action form; nohelp-irrelevant
            # = new entities, zero coverage gain, zero hit-citation.
            first_hit = bool(gold_here) and not (gold_seen_before & gold_here)
            new_gold = gold_here - gold_seen_before
            p_gain = len(new_gold) / max(1, len(gold_n))
            pred_n = {norm(p) for p in (rec.get("pred_entities") or [])}
            cited_hit = (float(rec.get("f1") or 0) > 0
                         and any(norm(e) in pred_n for e in delta))
            if p_gain > 0 or cited_hit:
                label = "helpful"
            elif len(delta) == 0:
                label = "nohelp-repeat"
            else:
                label = "nohelp-irrelevant"
            gold_seen_before |= gold_here
            seen |= {norm(e) for e in ents}
            op = {
                "case": rec["case_id"], "sample": rec.get("sample_idx"),
                "idx": i, "root": root, "action": action,
                "counts": counts, "width": len(delta), "used": used,
                "gold_hit": ("first" if first_hit else
                             "re" if gold_here else "-"),
                "p_gain": round(p_gain, 3), "label": label,
                "_ents": ents, "_delta": delta,
            }
            ops.append(op)
            case_ops.append(op)
            blocks[-1]["op"] = op
        cases.append({
            "case_id": rec["case_id"], "sample": rec.get("sample_idx"),
            "f1": float(rec.get("f1") or 0), "hit": str(rec.get("hit")),
            "question": rec.get("question", ""), "ops": case_ops,
            "blocks": blocks,
        })
    return ops, cases


def edges_of(content):
    """(h, rel, t) edges from the evidence-block region, normalized names.
    Handles merged-tail (--rel--> t1 | t2), merged-head (h1 | h2 --rel--> t)
    and CVT inline-attr node display (name [k: v])."""
    out, head, in_blocks = [], None, False
    for line in content.split("\n"):
        if line.startswith("triples:"):
            in_blocks = True
            continue
        if not in_blocks:
            continue
        if line.startswith(("note:", "anchor_sequence:", "layer_action:",
                            "candidates:")):
            break
        b = BLOCK_RE.match(line)
        if b:
            head = _clean_name(b.group(1))
            continue
        if not line.startswith("    "):
            continue
        m = EDGE_RE.search(line)
        if not m:
            continue
        rel = m.group(1)
        tails = [_clean_name(t) for t in m.group(2).split(" | ")]
        lhs = line.split("--", 1)[0].strip()
        heads = [_clean_name(h) for h in lhs.split(" | ")] \
            if lhs and not line.lstrip().startswith("--") else [head]
        for h in heads:
            for t in tails:
                if h and t and h != t:
                    out.append((norm(h), rel, norm(t)))
    return [e for e in out if e[0] and e[2]]


def _clean_name(name):
    name = name.strip()
    if not name or name.startswith("…") or name.startswith("..."):
        return ""
    if "[" in name:                       # CVT inline-attr display
        name = name.split("[", 1)[0].strip()
    return name


def _bfs_reach(adj, starts, goals):
    if not starts or not goals:
        return False
    seen = set(s for s in starts if s in adj)
    q = collections.deque(seen)
    while q:
        u = q.popleft()
        if u in goals:
            return True
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return any(s in goals for s in seen)


def reconcile_necessity(cases):
    """Meta-audit fix (2026-09-17): a nohelp-irrelevant op whose removal
    BREAKS anchor→gold connectivity is NOT irrelevant — it delivered the
    mid-chain hops the gold's own edges hang on (8 specimens, 7/8 in
    f1=1.0 trajectories). The Tier-1 conditions (zero coverage, zero
    citation) miss bridge value; necessity outranks them."""
    for c in cases:
        for b in c.get("blocks", []):
            o = b.get("op")
            if o and o["label"] == "nohelp-irrelevant" \
                    and b.get("necessary") == "yes":
                o["label"] = "helpful-midchain"


def mark_necessity(cases, recs_by_key):
    """STRUCTURAL NECESSITY (user ruling 2026-09-17): step i is necessary
    iff removing the edges FIRST DELIVERED by step i from the accumulated
    evidence graph breaks anchor→gold connectivity — a pure evidence-state
    check, NO re-walking. Duplicate re-renders of an edge are the same
    information and belong to its first deliverer."""
    for c in cases:
        if not c.get("blocks"):
            continue
        rec = recs_by_key[(c["case_id"], str(c["sample"]))]
        anchors = set()
        golds = {norm(g) for g in rec["_gold_list"] if g}
        for m in rec["trajectory"]:
            if m["role"] == "assistant" and "tool: plan" in m["content"]:
                em = re.search(r"^entities:\s*(.+)$", m["content"], re.M)
                if em:
                    anchors = {norm(x) for x in em.group(1).split(" | ") if x}
                break
        edges_owner = {}                        # (step_idx) -> set(edges)
        seen_edges = set()
        full_adj = collections.defaultdict(set)
        for b in c["blocks"]:
            es = set()
            for e in edges_of(rec["trajectory"][b["idx"]]["content"]):
                if e not in seen_edges:
                    seen_edges.add(e)
                    es.add(e)
                full_adj[e[0]].add(e[2])
                full_adj[e[2]].add(e[0])
            edges_owner[b["idx"]] = es
        c["_gold_reach_full"] = _bfs_reach(full_adj, anchors, golds)
        for b in c["blocks"]:
            drop = edges_owner[b["idx"]]
            if not drop:
                b["necessary"] = "no"           # no first-delivered information
                b["reach_wo"] = c["_gold_reach_full"]
                continue
            adj2 = collections.defaultdict(set)
            for u in full_adj:
                adj2[u] = set(full_adj[u])
            for (h, _r, t) in drop:
                adj2[h].discard(t)
                adj2[t].discard(h)
                if not adj2[h]:
                    del adj2[h]
                if not adj2[t] and t in adj2:
                    del adj2[t]
            reach_wo = _bfs_reach(adj2, anchors, golds)
            b["reach_wo"] = reach_wo
            if not c["_gold_reach_full"]:
                b["necessary"] = "n/a"          # gold never reachable at all
            else:
                b["necessary"] = "yes" if not reach_wo else "no"


def gold_reference(sample, gold_list):
    """Effective-path reference: BFS from the GOLD set backwards over raw
    undirected edges (CVTs pass as ordinary nodes). Returns a dist map
    {node_norm: hops_to_nearest_gold} — the potential function for advance
    detection. None when gold is unreachable from the graph at all."""
    ents = list(sample.get("text_entity_list", [])) + \
        list(sample.get("non_text_entity_list", []))
    adj = collections.defaultdict(list)
    for h, t in zip(sample.get("h_id_list", []), sample.get("t_id_list", [])):
        if h < len(ents) and t < len(ents):
            hn, tn = norm(ents[h]), norm(ents[t])
            if hn and tn:
                adj[hn].append(tn)
                adj[tn].append(hn)
    golds = {norm(g) for g in gold_list if g}
    golds = {g for g in golds if g in adj or True}
    golds_in_graph = {g for g in golds if g in adj}
    starts = {norm(q) for q in sample.get("q_entity", []) if q}
    if not golds_in_graph or not (starts & set(adj)):
        return None
    dist = {g: 0 for g in golds_in_graph}
    q = collections.deque(golds_in_graph)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    if not (starts & set(dist)):
        return None                      # anchors cannot reach gold
    return dist


def mark_break_points(cases, pkl_path):
    """Tier 2 (user ruling 2026-09-16): with the gold-side BFS potential
    φ = hops-to-gold, an op ADVANCES the sequence when its new entities
    lower min-φ (covering gold is φ=0). In MISS cases the structural break
    point is the FIRST non-advancing op after which the trajectory never
    advances again — the departure from the effective path that cost the
    case. Miss cases that never advance get their first op marked; miss
    cases that keep advancing to the end failed in the answer stage, not
    the walk (no break)."""
    samples = pickle.loads(open(pkl_path, "rb").read())
    by_id = {s.get("id"): s for s in samples}
    n_ref = n_unreach = n_answer_stage = 0
    for c in cases:
        if not c["ops"]:
            continue
        sample = by_id.get(c["case_id"])
        if sample is None:
            continue
        # gold already delivered anywhere in the sequence (baseline sg
        # calls included) → a remaining miss is an ANSWER-STAGE failure,
        # not a walk break: no break marking, ops keep their Tier-1 labels
        gold_covered = bool(set().union(*(b.get("gold_here") or set()
                                          for b in c.get("blocks", [])
                                          if b.get("gold_here")))) \
            if c.get("blocks") else bool(c["ops"])
        dist = gold_reference(sample, sample.get("a_entity", []))
        INF = float("inf")
        if dist is not None:
            d = INF
            for b in c.get("blocks", c["ops"]):
                o = b.get("op")
                if o is None and "idx" in b:
                    # non-layer delivery: advances the baseline, no annotation
                    new_ents = list(b.get("_delta") or [])
                    d_op = min([dist.get(norm(e), INF) for e in new_ents]
                               or [INF])
                    if d_op < d:
                        d = d_op
                    continue
                if o is None:
                    continue
                new_ents = list(o.get("_delta") or [])
                d_op = min([dist.get(norm(e), INF) for e in new_ents]
                           or [INF])
                advance = d_op < d
                o["on_path"] = "adv" if advance else "-"
                o["phi"] = d_op if d_op < INF else -1
                if advance:
                    d = d_op
                    if o["label"] == "nohelp-irrelevant":
                        o["label"] = "helpful"      # mid-chain advance counts
        if c["hit"] == "True":
            continue
        if gold_covered:
            n_answer_stage += 1
            c["miss_kind"] = "answer-stage"
            continue
        if dist is None:
            n_unreach += 1
            c["miss_kind"] = "unreach"
            for o in c["ops"]:
                o["on_path"] = "?"
            continue
        # walk-break miss: mark the break point
        n_ref += 1
        c["miss_kind"] = "walk-break"
        adv_idx = [i for i, o in enumerate(c["ops"]) if o["on_path"] == "adv"]
        if adv_idx and adv_idx[-1] < len(c["ops"]) - 1:
            c["ops"][adv_idx[-1] + 1]["label"] = "harmful-break"
        elif not adv_idx:
            c["ops"][0]["label"] = "harmful-break"   # never advanced
    return n_ref, n_unreach, n_answer_stage


def main():
    path = sys.argv[1]
    fams = []
    out_md = None
    pkl = "/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl"
    for a in sys.argv[2:]:
        if a == "--families":
            fams = sys.argv[sys.argv.index(a) + 1].split(",")
        if a == "--out":
            out_md = sys.argv[sys.argv.index(a) + 1]
        if a == "--pkl":
            pkl = sys.argv[sys.argv.index(a) + 1]
    ops, cases = annotate(path)
    import os
    # structural necessity (user ruling 2026-09-17): counterfactual edge
    # removal on the accumulated evidence graph — needs raw records
    recs_by_key = {}
    for rec in json.load(open(path)):
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
        recs_by_key[(rec["case_id"], str(rec.get("sample_idx")))] = rec
    mark_necessity(cases, recs_by_key)
    n_ref = n_unreach = n_ans = 0
    if os.path.exists(pkl):
        n_ref, n_unreach, n_ans = mark_break_points(cases, pkl)
    reconcile_necessity(cases)
    lab = collections.Counter(o["label"] for o in ops)
    act = collections.Counter(o["action"].split()[0] for o in ops)
    cover = sum(o["p_gain"] for o in ops)
    miss_kinds = collections.Counter(c.get("miss_kind")
                                     for c in cases if c.get("miss_kind"))
    # necessity cross-tab (layer ops only)
    cross = collections.Counter()
    nec_cnt = collections.Counter()
    for c in cases:
        for b in c.get("blocks", []):
            if b.get("is_op"):
                o = b.get("op")
                if o is not None:
                    cross[(o["label"], b.get("necessary", "?"))] += 1
                    nec_cnt[b.get("necessary", "?")] += 1
    n_steps = sum(len(c.get("blocks", [])) for c in cases)
    print(f"== {path}: {len(ops)} layer-ops / {n_steps} sg-steps ==")
    print("labels:", dict(lab))
    print("actions:", dict(act))
    print(f"sum p_gain (gold coverage advanced by layer ops): {cover:.2f}")
    print("necessity (all sg steps):", dict(nec_cnt))
    print("cross label x necessity:", dict(cross))
    if n_ref or n_unreach or n_ans:
        print(f"tier2 miss kinds: {dict(miss_kinds)} "
              f"(walk-break {n_ref} / answer-stage {n_ans} / "
              f"unreach {n_unreach})")
    if out_md:
        with open(out_md, "w") as f:
            f.write("# 层操作标注评估集 v2（信息模块对答案的帮助，待人审）\n\n"
                    f"来源: `{path}`；脚本: `scripts/annotate_layer_ops.py`；"
                    f"图参照: `{pkl}`。\n\n"
                    "**v2 语义（用户裁定 2026-09-16）**: 评估对象是每次操作交付的"
                    "信息模块对回答问题的帮助，不是操作形式（extend/update/repeat"
                    "只是设计侧分类）。\n\n"
                    "- **helpful（有效）**: 该信息模块在当前序列下推进答案——"
                    "gold 覆盖增量 p_gain>0（p_gain=本op新增gold覆盖/|gold|），"
                    "或其新实体被最终命中的 answer 引用（中间链贡献）\n"
                    "- **nohelp-repeat（无效·重复）**: 零新信息（width=0，信息已在"
                    "序列中）——与操作是否标记 repeat 无关\n"
                    "- **nohelp-irrelevant（无效·无关）**: 有新实体但零 gold 推进、"
                    "零命中引用\n"
                    "- **harmful-break（有害·断链点）**: 仅未命中 case——Tier2 图"
                    "参照（锚→gold 最短链并集=有效路径），实际探索第一个偏离有效"
                    "路径的 op；其后的偏离记 nohelp-irrelevant，在路径上的 op 仍"
                    "helpful（败在答案层不在游走）\n\n"
                    f"汇总: {dict(lab)}；Σp_gain={cover:.2f}。"
                    f"Tier2: {n_ref} 个未命中 case 有图参照，{n_unreach} 个 "
                    "gold 图上不可达（无法定断链）。\n\n"
                    "## 全量层操作表\n\n"
                    "| case | s | idx | root | action | width | gold | p_gain "
                    "| on_path | necessary | label |\n"
                    "|---|---|---|---|---|---|---|---|---|---|---|\n")
            blocks_by = {}
            for c in cases:
                for b in c.get("blocks", []):
                    blocks_by[(c["case_id"], str(c["sample"]), b["idx"])] = b
            for o in ops:
                b = blocks_by.get((o["case"], str(o["sample"]), o["idx"]), {})
                f.write(f"| {o['case'][:16]} | {o['sample']} | {o['idx']} | "
                        f"{(o['root'] or '?')[:24]} | {o['action'][:24]} | "
                        f"{o['width']} | {o['gold_hit']} | {o['p_gain']} | "
                        f"{o.get('on_path', '-')} | {b.get('necessary', '?')} "
                        f"| {o['label']} |\n")
            f.write("\n## 按家族汇总\n\n| family | s | f1 | hit | #ops | labels |\n"
                    "|---|---|---|---|---|---|\n")
            for c in cases:
                if not c["ops"]:
                    continue
                if fams and not any(c["case_id"].startswith(x)
                                    for x in fams):
                    continue
                ls = collections.Counter(o["label"] for o in c["ops"])
                f.write(f"| {c['case_id'][:20]} | {c['sample']} | {c['f1']:.2f} "
                        f"| {c['hit']} | {len(c['ops'])} | {dict(ls)} |\n")
        print("wrote", out_md)


if __name__ == "__main__":
    main()
