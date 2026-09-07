# 渲染设计交接文档 — V37h 候选中心渲染 + SAPS 走查层
**用途**:交 Codex 做渲染设计审计与讨论(只优化渲染,不改任何现有逻辑)。
Codex 无代码库访问权,本文档自包含:代码全文 + 走查层 + 集成点 + 裁决账本 + 真实标本 + 度量。
日期:2026-09-02。当前生产版本:SEQ_RENDER_V37=1,48×3 meanF1 = 0.7078。

---

## 0. 核心矛盾(本次审计要解决的问题)

以候选为核心的渲染在**超大候选集**(几十个中心 × 每中心大量记录)上
**反而不如路径式**。同一调用(24 个电影中心 × 提名记录)两种风格实测:

| 风格 | 字符数 | 形态 |
|---|---|---|
| V37h 候选中心(当前) | 34,563 | 每候选一块,块内记录带全属性 |
| v3.3 dense 路径式(基线) | 19,152 | 模式路径头 + 中心合并行 |

小/中候选集上候选中心全面胜出(见 §6 度量);超大候选集上重复爆炸。
**设计问题:如何在保持候选中心语义的前提下,让超大候选集的 token 成本
与可读性回到路径式水平?** 约束见 §5(折叠规则/零丢失/实体优先裁决)。

## 1. 数据流(渲染层在管线中的位置)

```
模型调用 retrieve_subgraph(center(s), relations)
  → dispatch_prepare: 实体解析(?var 展开)、关系校验、中心起点记录
  → SAPS walk(logical_paths.py):从每个中心按选定关系走查
      · 2-hop 枚举:末跳必须踩选定关系,首跳任意(桥 hop)
      · CASE C: CVT 透明的 3 边路径
      → PatternEvidence 每模式:triples + candidates + tree_data["paths"]
         (tree_data 由 formatting.py 构建:节点显示名 + CVT 装饰属性)
  → render_v37_ack(seq_render_v37.py):本文档主角,组织走径为候选中心行
  → ack 组装(seq_tools._sg_finalize):triples 渲染 + candidates 字段
      + note(格式说明)+ 200 行预算 + provenance
```

关键事实:**渲染器只消费 tree_data["paths"]**(走查的真实路径:
`nodes: ['Missouri River', 'm.0wg906w: [partially_contains=…]', 'Iowa']`
+ `relations: [全名,...]`)。它不改图、不重走、不丢信息。

## 2. 当前渲染器全文(kgqa/agent/seq_render_v37.py,367 行)

```python
"""V3.7 candidate-centric renderer (user design 2026-08-31: 候选为主键).

WALK-FAITHFUL: v3.6 discarded the walked node sequences (kept only each
pattern's first path's RELATIONS, then re-enumerated directions by max
instance count). That reconstruction inverted CVT-mediated patterns — the
fan-out direction won ([center→state→cvt ×88], candidates buried mid-tree,
CVT records carrying ◂) while the walk itself had the semantic witnesses
([center ←cvt─ state ×7]). V3.7 organizes the walked paths directly:

One line per candidate, self-contained — the candidate(s) lead the line,
their shared instantiated path follows, the final arrow points back at them:

    Iowa ◂  Missouri River ←partially_contains─ m.0wg906w ─partially_contained_by→
    Iowa ◂  Missouri River ─partially_containedby→ ─adjoin_s→ m.02tbl_w [adjoins=North Dakota; …]

Mechanics (folding is structure-only; entity names are never folded):
- every walked tree path renders as one candidate line (all patterns, ALL
  centers — v3.6 broke after the first center);
- a path that is a node-suffix of a longer walked path drops (the longer
  form carries it) — kills the walk's mid-rooted continuation duplicates;
- trailing CVT/value hops strip into a records suffix on the candidate's
  line; len-2 paths keep the CVT as the candidate with attrs inline;
- candidates whose chains differ only by the final node fold onto one line
  (fan-out compression: `A | B | C ◂ <shared chain>`);
- attr pairs present on EVERY record of a group fold to one header line
  (L1 uniform compression); attrs restating an instantiated path node drop;
  per-record attrs cap at 6;
- group order = (hops asc, entity-last-hop first, instances desc) — the
  last hop defines the candidate (user ruling), so patterns whose last hop
  LANDS on a named entity outrank record-fanout patterns of equal length.

Gate: SEQ_RENDER_V37=1"""
import re
from collections import defaultdict

_VAL_RE = re.compile(
    r"^\d{4}-\d{2}|^\d{2}:\d{2}|^[+-]?[\d.,]+$|^\d{4}s?$")


def _cvt(n):
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _val(n):
    return bool(_VAL_RE.match(str(n).strip()))


def _parse_node(s):
    """'m.xxx: [k=v, k2=v2]' → (name, [k=v, ...]); bare name → (name, [])."""
    s = str(s)
    if s.endswith("]") and ": [" in s:
        base, _, attr_txt = s.partition(": [")
        base = base.strip()
        if _cvt(base):
            attrs = [a.strip() for a in attr_txt[:-1].split(",") if a.strip()]
            return base, attrs
    return s, []


_NOISY_ATTR = {"type", "types", "instance", "instances", "notable_types",
               "topic_equivalent_webpage", "webpage", "mid", "guid",
               "key", "keys", "permission", "is_reviewed", "article",
               "description", "alias", "name"}


def render_v37_ack(treq, bres, ctx):
    ents, rels = ctx.ents, ctx.rels
    rel_adj = defaultdict(set)
    for h, rl, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        rel_adj[rl].add((h, t))
    ent_idx = {}
    for j, e in enumerate(ents):
        ent_idx.setdefault(str(e), j)

    # graph-reconstructed CVT attrs (decoration-independent — the walk's
    # decoration is sometimes empty for CVTs whose content the graph HAS:
    # 31 bare mids with film= edges, 2784 specimen)
    cvt_graph = defaultdict(list)      # mid -> [k=v, ...]
    for h, rl, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        hn = str(ents[h]) if 0 <= h < len(ents) else ""
        if not _cvt(hn):
            continue
        k = (str(rels[rl]).rsplit(".", 1)[-1]
             if 0 <= rl < len(rels) else "?")
        tv = str(ents[t]) if 0 <= t < len(ents) else str(t)
        if not _cvt(tv) and len(tv) < 60 and k not in _NOISY_ATTR:
            cvt_graph[hn].append(f"{k}={tv}")

    def merged_pairs(mid, deco_pairs):
        seen = set(deco_pairs)
        return deco_pairs + [a for a in cvt_graph.get(mid, ())
                             if a not in seen]

    center_names = [e for e, _i in (treq.get("centers") or [])]
    # BRIDGE-HOP ANNOTATION (user flag 2026-09-01, Liszt specimen): the walk
    # deliberately enumerates 2-hop completions whose LAST hop rides a
    # selected relation from ANY first hop (Bernie Brewer semantics) — hops
    # the model did NOT select render parenthesized so "gave relations but
    # walked something else" is visible instead of silent. Exact full-name
    # match: parallel encodings of a selected relation also read as bridges.
    sel_rels = {str(r) for r in (treq.get("rel_names") or [])}

    def hop_dir(rname, a_name, b_name):
        if rname in rels:
            rid = rels.index(rname)
            ai = ent_idx.get(a_name)
            bi = ent_idx.get(b_name)
            if ai is not None and bi is not None:
                if (ai, bi) in rel_adj.get(rid, ()):
                    return "f"
                if (bi, ai) in rel_adj.get(rid, ()):
                    return "r"
        return "?"

    # ── collect walked paths (all patterns, all centers), dedup ──
    # DEDUP RULE (user ruling 2026-09-01, corrected): each relation keeps its
    # OWN path and its OWN candidate — member and member_of designate
    # different candidates (their edge DIRECTIONS differ), so member's path
    # must NEVER fold into member_of's display. Lines merge only when node
    # sequence AND per-hop direction both coincide (parallel same-direction
    # spellings union their labels; opposite-direction relations split into
    # separate lines, each with its own arrows).
    raw = {}
    for (cname, cidx), pe in zip(treq["centers"], bres["pe_list"]):
        for pid, p in (pe.items() if isinstance(pe, dict) else []):
            td = (getattr(p, "tree_data", None) or {})
            for tp in (td.get("paths") or []):
                nodes = tp.get("nodes") or []
                if len(nodes) < 2:
                    continue
                key = tuple(_parse_node(n)[0] for n in nodes)
                relsn = tuple(str(r) for r in
                              (tp.get("relations") or [])[:len(nodes) - 1])
                # SAME-RELATION LOOP RULE (user ruling 2026-09-02, Freemasonry
                # specimen): cycles through DIFFERENT relations are legitimate
                # evidence, but a path that goes out and comes back on the
                # SAME relation (`A ─members→ m.x ←members─ …`) is a
                # degenerate out-and-back — drop it. Same-direction repeats
                # (nested contains→ contains→) stay.
                if len(relsn) >= 2:
                    raw_d = {i: hop_dir(relsn[i], key[i], key[i + 1])
                             for i in range(len(relsn))}
                    _degen = False
                    for a in range(len(relsn)):
                        for b in range(a + 1, len(relsn)):
                            if (relsn[a] == relsn[b]
                                    and raw_d[a] != raw_d[b]):
                                _degen = True
                                break
                        if _degen:
                            break
                    if _degen:
                        continue
                # direction is CANDIDATE-DEFINING only on selected hops —
                # bridge hops (unselected parallel edges) fold their two
                # storage directions into one neutral line; selected
                # relations keep per-direction lines (member vs member_of)
                dirs = tuple(
                    hop_dir(relsn[i], key[i], key[i + 1])
                    if relsn[i] in sel_rels else "?"
                    for i in range(len(relsn)))
                v = raw.setdefault((key, dirs), {"rels": [], "attrs": None})
                if relsn not in v["rels"]:
                    v["rels"].append(relsn)
                if v["attrs"] is None:
                    v["attrs"] = [_parse_node(n)[1] for n in nodes]
    if not raw:
        return "(empty)"

    # ── drop continuations: any proper node-suffix of a longer walked path ──
    node_seqs = {k[0] for k in raw}
    items = [(k[0], raw[k]["rels"], raw[k]["attrs"], k[1]) for k in raw
             if not any(k[0][i:] in node_seqs for i in range(1, len(k[0])))]

    def seg_for(relsns, dirs, names, ent_idx, hi, a_i, b_i):
        # per-hop relation label: union of the parallel SAME-DIRECTION
        # spellings that walked this node pair (the raw key guarantees every
        # variant shares this hop's direction)
        shorts = []
        for rv in relsns:
            rn = rv[hi] if hi < len(rv) else None
            if rn is None:
                continue
            sh = rn.rsplit(".", 1)[-1]
            if sh not in shorts:
                shorts.append(sh)
        if not shorts:
            sh = "?"
        elif len(shorts) == 1:
            sh = shorts[0]
        else:
            sh = "/".join(shorts[:2]) + ("+" if len(shorts) > 2 else "")
        if not any((rv[hi] if hi < len(rv) else None) in sel_rels
                   for rv in relsns):
            sh = f"({sh})"          # bridge hop — no variant was selected
        d = dirs[hi] if hi < len(dirs) else "?"
        if d == "f":
            return f"─{sh}→"
        if d == "r":
            return f"←{sh}─"
        return f"─{sh}─"

    # ── pass 1: decompose paths; collect attr stats for uniform folding ──
    # TERMINAL-TYPE LINE FORM (user ruling 2026-09-01, Mandela specimen): the
    # walked terminal IS the line's terminal — a named entity leads the line
    # as candidate (◂); a CVT/value terminal is a RECORD the chain completes
    # INTO, attrs inline (the model picks among its attrs at answer time).
    # No trailing-CVT stripping: it pulled mid-chain entities to the head and
    # left adjacent arrows where the entity used to sit.
    groups = {}          # gsig → {"n", "ent_last", "paths": [entry...]}
    for key, relsns, attrs, dirs in items:
        names = list(key)
        q = list(range(len(names)))
        ci = q[-1]
        cand = names[ci]
        red = {names[j].lower() for j in q}

        def clean_pairs(attr_list):
            out = []
            for a in attr_list:
                if "=" in a:
                    _k, v = a.split("=", 1)
                    if v.strip().lower() in red:
                        continue        # restates an instantiated path node
                out.append(a)
            return out

        chain = [names[q[0]]]
        sig = []
        for hi in range(len(q) - 1):
            ar = seg_for(relsns, dirs, names, ent_idx, hi, q[hi], q[hi + 1])
            sig.append(ar)
            chain.append(ar)
            if hi + 1 < len(q) - 1:
                nd = names[q[hi + 1]]
                if _cvt(nd):
                    # body CVT: inline its graph attrs (decoration-independent)
                    at = "; ".join(clean_pairs(merged_pairs(
                        nd, attrs[q[hi + 1]]))[:3])
                    chain.append(f"{nd} [{at}]" if at else nd)
                else:
                    chain.append(nd)
        cand_pairs = (clean_pairs(merged_pairs(cand, attrs[ci]))
                      if _cvt(cand) else [])
        # record paths (CVT/value terminal) hang under their OWNER — the
        # last named entity on the chain before the terminal
        owner = cand
        if _cvt(cand) or _val(cand):
            for j in range(len(q) - 2, -1, -1):
                nm_ = names[q[j]]
                if not _cvt(nm_) and not _val(nm_):
                    owner = nm_
                    break
        entry = {
            "sig": tuple(sig),
            "chain": " ".join(chain),          # ends with arrow INTO cand
            "cand": cand,
            "owner": owner,
            "cand_pairs": cand_pairs,
            "ent_last": not (_cvt(cand) or _val(cand)),
            "mark": "" if (_cvt(cand) or _val(cand)) else " ◂",
        }
        g = groups.setdefault(entry["sig"],
                              {"n": 0, "ent_last": 0, "paths": []})
        g["n"] += 1
        g["ent_last"] += 1 if entry["ent_last"] else 0
        g["paths"].append(entry)

    if not groups:
        return "(empty)"

    # ── pass 2: uniform attr folding, then ENTITY-FIRST blocks ──
    # (user ruling 2026-09-01: group by candidate FIRST — each entity's
    # pattern paths and relations list UNDER it, `Reiner Schöne：路径…` —
    # not entities re-listed per pattern. Record paths hang under their
    # owner entity; candidates with IDENTICAL path sets fold onto one
    # block head.)
    L = [f"entities: {' | '.join(center_names)}"]
    all_cands = set()
    stats = {}
    for gsig, g in groups.items():
        pair_cnt, hosts = defaultdict(int), 0
        for e in g["paths"]:
            if e["cand_pairs"]:
                hosts += 1
            for a in set(e["cand_pairs"]):
                pair_cnt[a] += 1
        stats[gsig] = {a for a, c in pair_cnt.items()
                       if hosts > 2 and c == hosts}

    blocks = {}
    for gsig, g in groups.items():
        uniform = stats[gsig]
        for e in g["paths"]:
            lead = str(e["cand"])
            if e["cand_pairs"]:
                at = "; ".join([a for a in e["cand_pairs"]
                                if a not in uniform][:6])
                if at:
                    lead = f"{e['cand']} [{at}]"
            if e["mark"]:
                all_cands.add(e["cand"])
                bkey = e["cand"]
            else:
                bkey = e["owner"]
            b = blocks.setdefault(bkey, {"entity": False, "fold": {}, "n": 0})
            if e["mark"]:
                b["entity"] = True
            b["fold"].setdefault(e["chain"], []).append(
                (e["cand"], lead, bool(e["mark"])))
            b["n"] += 1

    rendered = {}                      # line-tuple -> block info (merge twins)
    for bkey, b in blocks.items():
        lines = []
        for chain, items in sorted(b["fold"].items()):
            recs = [lead for _c, lead, mk in sorted(items) if not mk]
            ents = [c for c, _l, mk in sorted(items) if mk]
            if ents:
                # entity-candidate path: the chain's final arrow points at
                # the block head itself
                lines.append(chain)
            if recs:
                shown, used = [], 0
                for lead in recs:
                    if used + len(lead) > 480 and shown:
                        break
                    shown.append(lead)
                    used += len(lead) + 3
                line = f"{chain} {' | '.join(shown)}"
                more = recs[len(shown):]
                if more:
                    nm, used_n = [], 0
                    for x in more:
                        if used_n + len(x) > 360:
                            break
                        nm.append(x)
                        used_n += len(x) + 3
                    dot = " …" if len(nm) < len(more) else ""
                    line += f" (+{len(more)}: {' | '.join(nm)}{dot})"
                lines.append(line)
        lines = sorted(set(lines))
        key = tuple(lines)
        if key in rendered:
            rendered[key]["heads"].append(bkey)
            rendered[key]["entity"] = rendered[key]["entity"] or b["entity"]
            rendered[key]["n"] += b["n"]
        else:
            rendered[key] = {"heads": [bkey], "entity": b["entity"],
                             "n": b["n"], "lines": lines}

    for blk in sorted(rendered.values(),
                      key=lambda x: (not x["entity"], -x["n"],
                                     sorted(x["heads"])[0])):
        heads = " | ".join(sorted(set(blk["heads"])))
        mark = " ◂" if blk["entity"] else ""
        L.append(f"{heads}{mark}  ({blk['n']} paths)")
        for ln in blk["lines"][:88]:
            L.append(f"    {ln}")
        if len(blk["lines"]) > 88:
            L.append(f"    ... +{len(blk['lines']) - 88} paths "
                     f"(see candidates)")

    named = sorted(all_cands)
    L.append(f"candidates ({len(named)}): {' | '.join(named)}")
    return "\n".join(L)

```

## 3. SAPS 走查层(渲染的输入从哪来)

### 3a. 走查核心 _hit_paths(logical_paths.py:99-190)
每步从当前端点枚举:1-hop 命中 / 2-hop(末跳=选定关系,首跳任意=桥) /
CASE C(CVT 透明 3 边)。方向无约束(无向邻接),去重靠 used_edges。

```python
    adj = _build_adj(h_ids, r_ids, t_ids, with_edge_idx=True, skip_rel_ids=noisy_rel_ids)

    def _hit_paths(state, target_rels, step_idx):
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        hits = []

        def _make_hit(extra_nodes, extra_rels, extra_edges, hit_rel):
            return {
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),
                "covered_steps": state["covered_steps"] | frozenset({step_idx}),
                "terminal_rels": state["terminal_rels"] + (hit_rel,),
                "skipped_steps": state["skipped_steps"],
                "endpoint_steps": state.get("endpoint_steps", frozenset()),
                "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
                "depth": state["depth"] + len(extra_rels),
            }

        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if rel1 in target_rels:
                hits.append(_make_hit((nb1,), (rel1,), (e1,), rel1))
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            # ORIGINAL DESIGN (per-relation last-hop walk, restored 2026-08-19):
            # enumerate ALL 2-hop completions whose LAST hop rides a selected
            # relation — from EVERY first hop, target-hit or not. The old
            # "hit-and-stop" (CASE A continue / CASE B non-target-only) made a
            # bridge+payload selection walkable only when the graph happened
            # to store a reverse-direction UNSELECTED edge for the bridge
            # (Greeley contains/containedby luck); single-direction data
            # silently lost the payload relation (Bernie Brewer specimen).
            # Detour pruning (same-relation back-edge chains, Nordics) lives
            # in the evidence adjudication layer (_hop_ok), NOT here — the
            # walk only enumerates, direction constraints live downstream.
            # The 1-hop-target CVT extension below is subsumed by this loop
            # (CVT mids are traversed like any other).
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if rel2 in target_rels:
                    hits.append(_make_hit((nb1, nb2), (rel1, rel2),
                                           (e1, e2), rel2))
            # CASE C: CVT-transparent 3-edge path — end -> nb1 -> nb2 -> nb3 (rel3 in target).
            # A CVT mediator collapses its in/out edges into ONE logical hop, so a 3-graph-hop
            # path with EXACTLY ONE CVT mediator (at nb1 or nb2) is within the 2-logical-hop
            # budget. This is what makes the WALK match the relation POOL's reachability:
            # _seq_pool_relids surfaces a relation behind a CVT bridge + one named hop (e.g.
            # museum --org_rel--> CVT --child--> university, then university's `colors`) via its
            # CVT-transparent hop, the model selects it, and CASE C lets the walk actually
            # traverse it — without it, retrieve_relations returns a relation the walk can't
            # reach ("reached nothing"). Gated: FINAL edge must be a target relation (emitted
            # endpoints are target answers, few) and exactly one CVT mediator (no CVT->CVT) —
            # so no beam explosion.
            nb1_is_cvt = 0 <= nb1 < len(ents) and is_cvt_like(ents[nb1])
            if not nb1_is_cvt:
                continue   # the common CVT-bridge case has the mediator at the front (nb1);
            # nb1-is-CVT covers museum->CVT->university->target. (nb2-CVT symmetric case is
            # rarer and would fire here too if the `continue` above were removed; kept narrow
            # to bound fan-out.)
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1 or nb2 == end or nb2 == nb1:
                    continue
                if 0 <= nb2 < len(ents) and is_cvt_like(ents[nb2]):
                    continue   # CVT->CVT: skip (ambiguous, rare)
                used2 = used1 | frozenset({e2})
                for nb3, rel3, e3 in adj.get(nb2, ()):
                    if e3 in used2 or rel3 not in target_rels:
                        continue
                    if nb3 == end or nb3 == nb1 or nb3 == nb2:
                        continue
                    hits.append(_make_hit((nb1, nb2, nb3), (rel1, rel2, rel3),
                                           (e1, e2, e3), rel3))
        return hits

    endpoint_targets = set(breakpoint_indices or ()) - {anchor_idx, None}
    nonempty_step_indices = [i for i, rels_for_step in enumerate(step_relations) if rels_for_step]
    endpoint_bridge_step = nonempty_step_indices[-1] if nonempty_step_indices else None

    def _endpoint_bridge_paths(state, step_idx):
        if not endpoint_targets or step_idx != endpoint_bridge_step:
            return []
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
```

### 3b. 主扩展循环(logical_paths.py:185-262)

```python
        if not endpoint_targets or step_idx != endpoint_bridge_step:
            return []
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        if end in endpoint_targets:
            return []

        hits = []
        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if nb1 in endpoint_targets:
                hits.append((1, (nb1,), (rel1,), (e1,)))
                continue
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if nb2 in endpoint_targets:
                    hits.append((2, (nb1, nb2), (rel1, rel2), (e1, e2)))

        if not hits:
            return []
        min_depth = min(depth for depth, _, _, _ in hits)
        bridged = []
        endpoint_marker = -100000 - step_idx
        for _, extra_nodes, extra_rels, extra_edges in hits:
            if len(extra_nodes) != min_depth:
                continue
            bridged.append({
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),
                "covered_steps": state["covered_steps"] | frozenset({step_idx}),
                "terminal_rels": state["terminal_rels"] + (endpoint_marker,),
                "skipped_steps": state["skipped_steps"],
                "endpoint_steps": state.get("endpoint_steps", frozenset()) | frozenset({step_idx}),
                "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
                "depth": state["depth"] + len(extra_rels),
            })
        return bridged

    def _state_rank(state):
        return (
            -len(state["covered_steps"]),
            len(state["skipped_steps"]),
            state["depth"],
            state["terminal_rels"],
            state["nodes"][-1],
        )

    def _prune_states(states):
        grouped = {}
        for state in states:
            sig = (state["terminal_rels"], state["nodes"][-1], state["covered_steps"], state["skipped_steps"])
            prev = grouped.get(sig)
            if prev is None or _state_rank(state) < _state_rank(prev):
                grouped[sig] = state
        return sorted(grouped.values(), key=_state_rank)[:max_states]

    active = [{
        "nodes": (anchor_idx,),
        "relations": (),
        "used_edges": frozenset(),
        "covered_steps": frozenset(),
        "terminal_rels": (),
        "skipped_steps": frozenset(),
        "endpoint_steps": frozenset(),
        "domain_fallback_steps": frozenset(),
        "depth": 0,
    }]
    summary_states = []

    for step_idx, rels_for_step in enumerate(step_relations):
```

### 3c. 选中模式的精确实例化 materialize(355-426)

```python

def materialize_selected_logical_patterns(selected_patterns, ents, rels_list,
                                          h_ids, r_ids, t_ids, anchor_idx,
                                          breakpoint_indices,
                                          max_paths_per_pattern=200,
                                          max_count_per_pattern=10000):
    """After mode selection, enumerate raw paths for each selected exact witness mode."""
    if not selected_patterns or anchor_idx is None:
        return selected_patterns

    adj = _build_adj(h_ids, r_ids, t_ids, with_edge_idx=True)

    materialized = []
    for lp in selected_patterns:
        witness = lp.get("best_raw_path") or {}
        rel_seq = tuple(witness.get("relations", []))
        if not rel_seq:
            materialized.append(lp)
            continue

        found_paths = []
        path_count = 0
        stack = [(anchor_idx, (anchor_idx,), (), frozenset(), 0)]
        while stack:
            node, nodes, rels, used_edges, pos = stack.pop()
            if pos == len(rel_seq):
                path_count += 1
                if len(found_paths) < max_paths_per_pattern:
                    found_paths.append({
                        "nodes": list(nodes),
                        "relations": list(rels),
                        "depth": len(rels),
                        "covered_steps": witness.get("covered_steps", frozenset()),
                        "matched_relations": frozenset(rels),
                    })
                if path_count >= max_count_per_pattern:
                    break
                continue

            target_rel = rel_seq[pos]
            for nb, rel, edge_idx in adj.get(node, ()):
                if edge_idx in used_edges or rel != target_rel:
                    continue
                stack.append((
                    nb,
                    nodes + (nb,),
                    rels + (rel,),
                    used_edges | frozenset({edge_idx}),
                    pos + 1,
                ))

        if not found_paths:
            materialized.append(lp)
            continue

        found_paths.sort(key=lambda p: (p["depth"], p["nodes"]))
        new_lp = dict(lp)
        new_lp["raw_paths"] = found_paths
        new_lp["best_raw_path"] = found_paths[0]
        new_lp["path_count"] = path_count
        new_lp["path_count_capped"] = path_count >= max_count_per_pattern
        new_lp["materialized"] = True
        count_suffix = f"{path_count}{'+' if new_lp['path_count_capped'] else ''}"
        readable = new_lp.get("readable", "")
        if readable and "materialized paths=" not in readable:
            new_lp["readable"] = f"{readable}  [materialized paths={count_suffix}]"
        candidate_counts = _candidate_name_counts_from_paths(
            found_paths, ents, anchor_idx, breakpoint_indices)
        new_lp["candidate_counts"] = dict(candidate_counts)
        new_lp["candidates"] = [name for name, _ in candidate_counts[:20]]
        materialized.append(new_lp)
    return materialized
```

### 3d. tree_data 构建(formatting.py:692-782)
`_node_display`:CVT 节点内联属性(≤20,噪声过滤);tree paths = 走径
节点序列 + 关系名,含 sibling-CVT 补充路径与 mid-rooted 续路径。

```python
        def _node_display(node_idx, expand_full=False):
            name = ents[node_idx] if 0 <= node_idx < len(ents) else "?"
            if is_cvt_like(name):
                # CVT event node: show its attrs INLINE on the node — use the
                # FULL graph attrs (not just the narrow witness-path ones) so
                # every CVT node carries its attrs (e.g. adjoins=Montana).
                path_attrs = [a for a in cvt_attrs.get(name, [])
                              if not _is_noisy_cvt_attr_short(a)]
                graph_attrs = [a for a in _cvt_attr_display(node_idx)
                               if not _is_noisy_cvt_attr_short(a)]
                seen_a = set(path_attrs)
                merged = list(path_attrs)
                for a in graph_attrs:
                    if a not in seen_a:
                        merged.append(a)
                        seen_a.add(a)
                if merged:
                    return f"{name}: [" + ", ".join(merged[:20]) + "]"
                return f"{name}: []"
            return name

        tree_paths = []
        tree_seen = set()
        for sp in support_paths:
            sp_nodes = sp.get("nodes", [])
            sp_rels = sp.get("relations", [])
            if not sp_nodes or not sp_rels:
                continue
            n = len(sp_nodes)
            display_nodes = [_node_display(idx, expand_full=(pos >= n - 2)) for pos, idx in enumerate(sp_nodes)]
            display_rels = [
                rel_to_text(rels_list[rel_idx]) if 0 <= rel_idx < len(rels_list) else "?"
                for rel_idx in sp_rels[: max(0, len(display_nodes) - 1)]
            ]
            sig = (tuple(display_nodes), tuple(display_rels))
            if sig not in tree_seen:
                tree_seen.add(sig)
                tree_paths.append({"nodes": display_nodes, "relations": display_rels})
            # Mirror _expand_sibling_cvts: emit sibling-CVT display paths so the
            # tree shows disambiguating CVTs (e.g. a performance CVT and its
            # character_note) that the graph-side enrichment adds to triples but
            # which are absent from the raw witness-path nodes. Without this the
            # rendered tree shows only the shallow witness CVT and hides the
            # branch carrying the answer. Uses display_nodes[i-1] as the parent
            # so _render_path_tree nests the sibling under the same parent edge.
            sib_pair_seen = set()
            for i in range(1, len(sp_nodes)):
                cvt_idx = sp_nodes[i]
                cvt_name = ents[cvt_idx] if 0 <= cvt_idx < len(ents) else ""
                if not is_cvt_like(cvt_name):
                    continue
                prev_idx = sp_nodes[i - 1]
                rel_idx = sp_rels[i - 1] if i - 1 < len(sp_rels) else None
                if rel_idx is None:
                    continue
                pair = (prev_idx, rel_idx)
                if pair in sib_pair_seen:
                    continue
                sib_pair_seen.add(pair)
                rel_disp = rel_to_text(rels_list[rel_idx]) if 0 <= rel_idx < len(rels_list) else "?"
                prev_disp = display_nodes[i - 1]
                for edge_h, edge_r, edge_t in node_edges.get(prev_idx, []):
                    if edge_h != prev_idx or edge_r != rel_idx or edge_t == cvt_idx:
                        continue
                    t_name = ents[edge_t] if 0 <= edge_t < len(ents) else ""
                    if not is_cvt_like(t_name):
                        continue
                    sib_disp = _node_display(edge_t, expand_full=True)
                    s_nodes = [prev_disp, sib_disp]
                    s_rels = [rel_disp]
                    s_sig = (tuple(s_nodes), tuple(s_rels))
                    if s_sig in tree_seen:
                        continue
                    tree_seen.add(s_sig)
                    tree_paths.append({"nodes": s_nodes, "relations": s_rels})

        result[label] = PatternEvidence(
            label=label,
            readable=lp.get("readable", ""),
            candidates=cand_list,
            triples=pat_triples,
            tree_data={"paths": tree_paths},
        )

    return result


# ---------------------------------------------------------------------------
# Path tree renderer
# ---------------------------------------------------------------------------

```

## 4. 集成点(seq_tools._sg_finalize 渲染分支摘录)
V37 分支 → 空回退修复 → 200 行预算(_TREE_LINE_BUDGET)→ provenance →
candidates 字段(env 真值,walk 计算)→ note(旧 dense 格式说明,未同步)。

```python
# _sg_finalize 摘录(实际行号见文件)
if os.environ.get("SEQ_RENDER_V37", "") == "1":
    from kgqa.agent.seq_render_v37 import render_v37_ack
    v37 = render_v37_ack(treq, bres, ctx)
    if v37 and v37 != "(empty)":
        tree_lines = v37.split("\n")
        _ov, _blocks, _covered = [], [], set()
    else:
        # v3.3 dense 回退(空渲染兜底)
        _ov, _blocks, _covered = render_evidence_sections(...)
        _uncovered = _select_uncovered(...)
        tree_lines, n_overlap = _render_records(_uncovered, shown)
        tree_lines = _group_facts_by_rel(tree_lines)
_TREE_LINE_BUDGET = 200   # 超出截断 "(see candidates)"
# ack JSON: triples=渲染文本 / candidates=walk 真值候选(≤60) / note=格式说明
```

## 5. 设计裁决账本(全部为用户裁决,审计不可违反)

| # | 裁决 | 标本 | 现实现 |
|---|---|---|---|
| 1 | **候选为主键**:实体块头 + 其路径在下,非按模式列实体 | 1171 | 块 = `Reiner Schöne ◂ (N paths)` |
| 2 | **每关系自己的候选**:方向是候选定义性;member≠member_of | Liszt | 键=节点序列+每跳方向;反向分行 |
| 3 | 未选桥 hop 括号标注,方向折叠中性 | Liszt | `─(based_on/image+)─` |
| 4 | **CVT/值终端 = 记录**:链完整收入,attrs 内联 | Mandela | `… South Africa ←jurisdiction_of_office─ m.040vj88 [attrs]` |
| 5 | 记录路径挂 owner(链上最后命名实体) | 1171 | Vader 块含其记录 |
| 6 | **零实体丢失**:折叠只折结构,永不折实体名 | 全量 | 重放 27 ack 0 缺失 |
| 7 | L1 一致压缩:组内严格一致 attr → 头(≤2 host 除外) | Brad Stevens | `all records: (…)` |
| 8 | 重言 attr 丢(值=路径节点) | 626 states | administrative_division=Iowa 丢 |
| 9 | 同体重复候选折叠共块;行内 480 字符预算,溢出带键 | Missouri | `(+N: partially_contains=X \| …)` |
| 10 | **同关系回环抑制**(一去一回);异关系回环保留 | Freemasonry | members→←members 丢 |
| 11 | 走径忠实:不重选方向、后缀续路径去重 | Missouri 88→7 | walk 的路径直接组织 |
| 12 | 多中心全渲染(v36 曾只渲染第一中心) | 2570 | 全部 center |

已知微妙点(用户确认不改):多候选块链尾箭头不点名具体候选(结构无损失,
合并块=路径集全同)。

## 6. 度量演化(48-cohort × 3 seeds,TEMP=0.3)

| 版本 | meanF1 | 说明 |
|---|---|---|
| v3.3 dense 基线 | 0.6877 | 模式+dense 行,200 行预算 |
| V36c | 0.5904 | 模式分组树(多中心 bug + 空-回退崩溃) |
| V37 | 0.6515 | 走径忠实重写 |
| V37b | 0.6690 | +键值溢出 +图重建 CVT attrs |
| V37c | 0.6730 | +记录行形态 +multi_anchor 提醒 |
| V37d | 0.6990 | +拼写并集(member/member_of 同行) |
| V37e | 0.6348 | 方向分拆(并集被否) |
| V37f | 0.6939 | **实体优先块**(收回分拆代价) |
| V37g | 0.6919 | +消费门(答案前单次拦截未消费实体) |
| **V37h** | **0.7078** | +同关系回环抑制(当前生产) |

已知失败家族(渲染外):判别属性检索空手(tvrage_id)、多答案完备性
(配音只绑单候)、实体解析碎('75th Ranger'→'7')。

## 7. 真实标本(同一 walk,两种渲染)

### 7a. 小候选(Brad Stevens, 1 中心)— V37h 胜
```
triples:
entities: Brad Stevens
Brad Stevens ◂  (6 paths)
    Brad Stevens ─(coach)─ m.0w3_qv3 [position=Head coach; team=Boston Celtics; has_no_value=To] ←teams_coached─
    Brad Stevens ─(coach)─ m.0w48285 [position=Assistant Coach; team=Butler Bulldogs men's basketball] ←teams_coached─
    Brad Stevens ─(coach)─ m.0w4828t [position=Head coach; team=Butler Bulldogs men's basketball] ←teams_coached─
    Brad Stevens ─teams_coached→ m.0w3_qv3 [position=Head coach; team=Boston Celtics; has_no_value=To] | m.0w48285 [position=Assistant Coach; team=Butler Bulldogs men's basketball] | m.0w4828t [position=Head coach; team=Butler Bulldogs men's basketball]
Boston Celtics ◂  (2 paths)
    Brad Stevens ←head_coach─
    Brad Stevens ─team→
candidates (2): Boston Celtics | Brad Stevens
  candidates not shown above: Brandon Miller (walk candidates — no visible edge this case) — these ARE connected evidence from earlier retrievals; absence from THIS render is not a disconnection.
candidates: Boston Celtics | Brad Stevens | Head coach | Assistant Coach | Butler Bulldogs men's basketball | Brandon Miller
n_candidates: 6
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --character--> Denver | --actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
```

### 7b. 中候选(Taylor Lautner films, 1 中心)— 相当
```
triples:
entities: Taylor Lautner
Taylor Lautner ◂  (56 paths)
    Taylor Lautner ←person─ m.0h0z90x [film=Ulalume: Howling at New Moon; type_of_appearance=Him/Herself]
    Taylor Lautner ─(actor)─ m.012zk7ct [film=Run the Tide] ←film─
    Taylor Lautner ─(actor)─ m.0131gszv [film=The Ridiculous Six] ←film─
    Taylor Lautner ─(actor)─ m.04tz40k [character=Jack Spivey; seasons=My Own Worst Enemy - Season 1; series=My Own Worst Enemy] ←starring_roles─
    Taylor Lautner ─(actor)─ m.04z4zmg [character=Jacob Black; film=Twilight] ←film─
    Taylor Lautner ─(actor)─ m.05tflhw [character=Jacob Black; film=The Twilight Saga: New Moon] ←film─
    Taylor Lautner ─(actor)─ m.06z_2jg [character=Kismet (Child); film=Shadow Fury] ←film─
    Taylor Lautner ─(actor)─ m.075wxc2 [character=Jacob Black; film=Eclipse] ←film─
    Taylor Lautner ─(actor)─ m.0772zp4 [character=Willy; film=Valentine's Day] ←film─
    Taylor Lautner ─(actor)─ m.0b68zn5 [character=Jacob Black; film=The Twilight Saga: Breaking Dawn - Part 1] ←film─
    Taylor Lautner ─(actor)─ m.0djz10s [character=Jacob Black; film=The Twilight Saga: Breaking Dawn - Part 2] ←film─
    Taylor Lautner ─(actor)─ m.0gvd5lx [character=Nathan Harper; film=Abduction] ←film─
    Taylor Lautner ─(actor)─ m.0gwrkz0 [character=Mouseketeer; film=The Nick and Jessica Variety Hour] ←film─
    Taylor Lautner ─(actor)─ m.0gwrkzm [character=Joe Agate; film=He's a Bully; Charlie Brown] ←film─
    Taylor Lautner ─(actor)─ m.0gwrl_1 [character=Boy on Beach; series=Summerland] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlx_ [character=Aaron; series=The Bernie Mac Show] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlyc [character=Reggie Wasserstein; series=Duck Dodgers] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlyk [character=Tyrone; series=My Wife and Kids] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlyy [character=Dennis; series=What's New; Scooby-Doo?] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlz9 [character=Young Blood] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gwrlzp [character=Oliver; series=Love; Inc.] ←starring_roles─
    Taylor Lautner ─(actor)─ m.0gx8qdk [character=Finn; film=Incarceron] ←film─
    Taylor Lautner ─(actor)─ m.0h7fzt3 [character=Iowa Farmer; film=Field of Dreams 2: Lockout] ←film─
    Taylor Lautner ─(actor)─ m.0jw95q [character=Eliott Murtaugh; film=Cheaper by the Dozen 2] ←film─
    Taylor Lautner ─(actor)─ m.0k490j [character=Sharkboy; film=The Adventures of Sharkboy and Lavagirl] ←film─
    Taylor Lautner ─(actor)─ m.0ngj__g [character=Cam; film=Tracers] ←film─
    Taylor Lautner ─(actor)─ m.0ngk01h [character=Frat Boy Andy; film=Grown Ups 2] ←film─
    Taylor Lautner ─(actor)─ m.0wc86jj [film=Northern Lights] ←film─
    Taylor Lautner ─(films)─ m.0h0z90x [film=Ulalume: Howling at New Moon; type_of_appearance=Him/Herself] ─person→
    Taylor Lautner ─film→ m.012zk7ct [film=Run the Tide] | m.0131gszv [film=The Ridiculous Six] | m.04z4zmg [character=Jacob Black; film=Twilight] | m.05tflhw [character=Jacob Black; film=The Twilight Saga: New Moon] | m.06z_2jg [character=Kismet (Child); film=Shadow Fury] | m.075wxc2 [character=Jacob Black; film=Eclipse] | m.0772zp4 [character=Willy; film=Valentine's Day] | m.0b68zn5 [character=Jacob Black; film=The Twilight Saga: Breaking Dawn - Part 1] (+11: m.0djz10s [character=Jacob Black; film=The Twilight Saga: Breaking Dawn - Part 2] | m.0gvd5lx [character=Nathan Harper; film=Abduction] | m.0gwrkz0 [character=Mouseketeer; film=The Nick and Jessica Variety Hour] | m.0gwrkzm [character=Joe Agate; film=He's a Bully; Charlie Brown; film=He's a Bully, Charlie Brown] | m.0gx8qdk [character=Finn; film=Incarceron] …)
    Taylor Lautner ─starring_roles→ m.04tz40k [character=Jack Spivey; seasons=My Own Worst Enemy - Season 1; series=My Own Worst Enemy] | m.0gwrl_1 [character=Boy on Beach; series=Summerland] | m.0gwrlx_ [character=Aaron; series=The Bernie Mac Show] | m.0gwrlyc [character=Reggie Wasserstein; series=Duck Dodgers] | m.0gwrlyk [character=Tyrone; series=My Wife and Kids] | m.0gwrlyy [character=Dennis; series=What's New; Scooby-Doo?; series=What's New, Scooby-Doo?] | m.0gwrlz9 [character=Young Blood] (+1: m.0gwrlzp [character=Oliver; series=Love; Inc.; series=Love, Inc.])
candidates (1): Taylor Lautner
candidates: Taylor Lautner | Run the Tide | Willy | Valentine's Day | Twilight | Jacob Black | Tracers | Cam | The Nick and Jessica Variety Hour | Mouseketeer | The Twilight Saga: New Moon | Eclipse | Abduction | Nathan Harper | The Adventures of Sharkboy and Lavagirl | Sharkboy | Cheaper by the Dozen 2 | Eliott Murtaugh | Shadow Fury | Kismet (Child) | Northern Lights | He's a Bully, Charlie Brown | Joe Agate | The Twilight Saga: Breaking Dawn - Part 1 | Incarceron | Finn | Grown Ups 2 | Frat Boy Andy | The Twilight Saga: Breaking Dawn - Part 2 | Field of Dreams 2: Lockout | Iowa Farmer | The Ridiculous Six | Aaron | The Bernie Mac Show | Young Blood | Oliver | Love, Inc. | Boy on Beach | Summerland | Jack Spivey | My Own Worst Enemy - Season 1 | My Own Worst Enemy | Tyrone | My Wife and Kids | Reggie Wasserstein | Duck Dodgers | Dennis | What's New, Scooby-Doo? | Ulalume: Howling at New Moon | Him/Herself
n_candidates: 50
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --character--> Denver | --actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evide
```

### 7c. 超大候选(24 中心 × 提名记录)— **dense 反超,本次审计焦点**
V37h(34563 字符):
```
triples:
entities: Run the Tide | The Ridiculous Six | Twilight | The Twilight Saga: New Moon | Shadow Fury | Eclipse | Valentine's Day | The Twilight Saga: Breaking Dawn - Part 1 | The Twilight Saga: Breaking Dawn - Part 2 | Abduction | The Nick and Jessica Variety Hour | He's a Bully, Charlie Brown | Incarceron | Field of Dreams 2: Lockout | Cheaper by the Dozen 2 | The Adventures of Sharkboy and Lavagirl | Tracers | Grown Ups 2 | Northern Lights | My Own Worst Enemy | Summerland | The Bernie Mac Show | Duck Dodgers | What's New, Scooby-Doo? | Love, Inc.
Eclipse ◂  (31 paths)
    Eclipse ←nominated_for─ m.0dlsjrg [award=People's Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] | m.0dlsl0_ [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] (+7: m.0g8l2p6 [award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=31st Golden Raspberry Awards; nominated_for=Valentine's Day] | m.0pc68dv [award=MTV Movie Award for Best Kiss; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner; ceremony=2011 MTV Movie Awards] …)
    Eclipse ─(award_nominations)─ m.0dlsjrg [award=People's Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] | m.0dlsl0_ [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] (+7: m.0g8l2p6 [award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=31st Golden Raspberry Awards; nominated_for=Valentine's Day] | m.0pc68dv [award=MTV Movie Award for Best Kiss; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner; ceremony=2011 MTV Movie Awards] …)
    Eclipse ─(award_nominations)─ m.0dlsjrg [award=People's Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0dlsl0_ [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0g8l2p6 [award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=31st Golden Raspberry Awards] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0pc68dv [award=MTV Movie Award for Best Kiss; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0pc6mm8 [award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2011 MTV Movie Awards] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0z87_06 [award=Teen Choice Award for Choice Movie: Liplock; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0z87vxq [award=Teen Choice Award for Choice Movie Actor - Sci-Fi/Fantasy; award_nominee=Taylor Lautner; ceremony=2011 Teen Choice Awards] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0z8vmjl [award=Teen Choice Award for Choice Summer Movie Star: Male; award_nominee=Taylor Lautner; ceremony=2010 Teen Choice Awards] ─nominated_for→
    Eclipse ─(award_nominations)─ m.0zc41z3 [award=Teen Choice Award for Choice Most Fanatic Fans; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] ─nominated_for→
    Eclipse ─(awards_won)─ m.0g4t6qq [award=People's Choice Award for Favorite On-Screen Chemistry; award_winner=Kristen Stewart; award_winner=Robert Pattinson; ceremony=37th People's Choice Awards] | m.0z87vt9 [award=Teen Choice Award for Choice Movie Actor - Sci-Fi/Fantasy; ceremony=2011 Teen Choice Awards] | m.0zc41vm [award=Teen Choice Award for Choice Most Fanatic Fans; award_winner=Kristen Stewart; award_winner=Robert Pattinson; ceremony=2010 Teen Choice Awards]
    Valentine's Day ─(award_nominations)─ m.0g8l2p6 [award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=31st Golden Raspberry Awards] ─nominated_for→
The Twilight Saga: New Moon ◂  (26 paths)
    The Twilight Saga: New Moon ←nominated_for─ m.09sftk2 [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=36th People's Choice Awards] | m.09tz5_t [award=Golden Raspberry Award for Worst Screenplay; award_nominee=Melissa Rosenberg; ceremony=30th Golden Raspberry Awards; notes_description=Based on the Novel by Stephenie Meyer; notes_description=Based on the Novel by Stephenie Meyer"@en; year=2009-08:00] (+5: m.09tz609 [award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=30th Golden Raspberry Awards] | m.0c02330 [award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2010 MTV Movie Awards] …)
    The Twilight Saga: New Moon ─(award_nominations)─ m.09sftk2 [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=36th People's Choice Awards] | m.09tz5_t [award=Golden Raspberry Award for Worst Screenplay; award_nominee=Melissa Rosenberg; ceremony=30th Golden Raspberry Awards; notes_description=Based on the Novel by Stephenie Meyer; notes_description=Based on the Novel by Stephenie Meyer"@en; year=2009-08:00] (+7: m.09tz601 | m.09tz609 [award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson; award_nominee=Taylor Lautner; ceremony=30th Golden Raspberry Awards] | m.09tz60m | m.0c02330 [award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2010 MTV Movie Awards] …)
    The Twilight Saga: New Moon ─(award_nominations)─ m.09sftk2 [award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.09tz5_t [award=Golden Raspberry Award for Worst Screenplay; award_nominee=Melissa Rosenberg; ceremony=30th Golden Raspberry Awards] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.09tz609 [award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.0c02330 [award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2010 MTV Movie Awards] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.0sgl6rq [award=Kids' Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=2010 Kids' Choice Awards] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.0sgl9q8 [award=Blimp Award for Cutest Couple; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] ─nominated_for→
    The Twilight Saga: New Moon ─(award_nominations)─ m.0z8jj9c [award=Teen Choice Award for Choice Movie Actor: Fantasy; award_nominee=Taylor Lautner; ceremony=2010 Teen Choice Awards] ─nominated_for→
    The Twilight Saga: New Moon ─(awards_won)─ m.0sgl4jf [award=Kids' Choice Award for Favorite Movie Actor; ceremony=2010 Kids' Choice Awards] | m.0sglcdq [award=Blimp Award for Cutest Couple; award_winner=Kristen Stewart; ceremony=2010 Kids' Choice Awards] | m.0z8jh9r [award=Teen Choice Award for Choice Movie Actor: Fantasy; ceremony=2010 Teen Choice Awards]
The Twilight Saga: Breaking Dawn - Part 2 ◂  (16 paths)
    The Twilight Saga: Breaking Dawn - Part 2 ←nominated_for─ m.0pdgl_y [award=Razzie Award for Worst Supporting Actor; award_nominee=Taylor Lautner; ceremony=33rd Golden Raspberry Awards] | m.0pdglz9 [award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Mackenzie Foy; award_nominee=Taylor Lautner; ceremony=33rd Golden Raspberry Awards] | m.0r9hvx9 [award=MTV Movie Award for Best Shirtless Performance; award_nominee=Taylor Lautner; ceremony=2013 MTV Movie Awards] (+1: m.0wjc4x6 [award=Teen Choice Award for Choice Movie Actor - Sci-Fi/Fantasy; award_nominee=Taylor Lautner; ceremony=2013 Teen Choice Awards])
    The Twilight Saga: Breaking Dawn - Part 2 ─(award_nominations)─ m.0pdgl_y [award=Razzie Award for Worst Supporting Actor; award_nominee=Taylor Lautner; ceremony=33rd Golden Raspberry Awards] | m.0pdglz9 [award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Mackenzie Foy; award_nominee=Taylor Lautner; ceremony=33rd Golden Raspberry Awards] | m.0r9hvx9 [award=MTV Movie Award for Best Shirtless Performance; award_nominee=Taylor Lautner; ceremony=2013 MTV Movie Awards] (+1: m.0wjc4x6 [award=Teen Choice Award for Choice Movie Actor - Sci-Fi/Fantasy; award_nominee=Taylor Lautner; ceremony=2013 Teen Choice Awards])
    The 
```
dense v3.3(19152 字符):
```
entities: Run the Tide | The Ridiculous Six | Twilight | The Twilight Saga: New Moon | Shadow Fury | Eclipse | Valentine's Day | The Twilight Saga: Breaking Dawn - Part 1 | The Twilight Saga: Breaking Dawn - Part 2 | Abduction | The Nick and Jessica Variety Hour | He's a Bully, Charlie Brown | Incarceron | Field of Dreams 2: Lockout | Cheaper by the Dozen 2 | The Adventures of Sharkboy and Lavagirl | Tracers | Grown Ups 2 | Northern Lights | My Own Worst Enemy | Summerland | The Bernie Mac Show | Duck Dodgers | What's New, Scooby-Doo? | Love, Inc.
triples:
pattern paths:
  Twilight | Eclipse | Valentine's Day | Abduction | …(+4 centers) <--nominated_for-- [34 records]
  Twilight | Eclipse | Valentine's Day | Abduction | …(+1 centers) <--nominated_for-- ?x --nominated_for--> ?y  (23 instances)
  Twilight | Eclipse | Abduction <--nominated_for-- ?x <--nominees-- ?y  (8 instances)
  Twilight | Eclipse | Valentine's Day | Abduction | …(+1 centers) --award_nominations--> ?x --nominated_for--> ?y  (23 instances)
  Twilight | Eclipse | Abduction --award_nominations--> ?x <--nominees-- ?y  (8 instances)
  The Nick and Jessica Variety Hour | He's a Bully, Charlie Brown | My Own Worst Enemy | Summerland | …(+4 centers) --country_of_origin--> ?x <--country-- ?y <--nominated_for-- [224 records]
  He's a Bully, Charlie Brown | My Own Worst Enemy | Summerland | The Bernie Mac Show | …(+3 centers) --languages--> ?x <--language-- ?y <--nominated_for-- [196 records]
  Valentine's Day --award_nominations--> ?x --award--> ?y --nominees--> [3 records]
  Twilight <--honored_for-- ?x --award--> ?y --nominees--> [1 records]
  Grown Ups 2 --awards_won--> ?x --award--> ?y --nominees--> [1 records]
    --award_nominations--> ∅ (no instances from these centers)
    Twilight <--nominated_for-- m.0b3tz45 [nominated_for=Twilight; award=MTV Movie Award for Best Breakthrough Performance - Male; award_nominee=Taylor Lautner; ceremony=2009 MTV Movie Awards] | m.0z8zbq7 [nominated_for=Twilight; award=Teen Choice Award for Choice Movie Breakout Star - Male; award_nominee=Taylor Lautner; ceremony=2009 Teen Choice Awards]
    Eclipse <--nominated_for-- m.0dlsjrg [nominated_for=Eclipse; award=People's Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=37th People's Choice Awards] | m.0dlsl0_ [nominated_for=Eclipse; award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] | m.0g8l2p6 [nominated_for=Eclipse; award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=31st Golden Raspberry Awards] | m.0pc68dv [nominated_for=Eclipse; award=MTV Movie Award for Best Kiss; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] | m.0pc6mm8 [nominated_for=Eclipse; award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2011 MTV Movie Awards] | m.0z87_06 [nominated_for=Eclipse; award=Teen Choice Award for Choice Movie: Liplock; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] | m.0z87vxq [nominated_for=Eclipse; award=Teen Choice Award for Choice Movie Actor - Sci-Fi/Fantasy; award_nominee=Taylor Lautner; ceremony=2011 Teen Choice Awards] | m.0z8vmjl [nominated_for=Eclipse; award=Teen Choice Award for Choice Summer Movie Star: Male; award_nominee=Taylor Lautner; ceremony=2010 Teen Choice Awards] | m.0zc41z3 [nominated_for=Eclipse; award=Teen Choice Award for Choice Most Fanatic Fans; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson]
    Valentine's Day <--nominated_for-- m.0g8l2p6 | m.0c032jc [nominated_for=Valentine's Day; award=MTV Movie Award for Best Kiss; award_nominee=Taylor Lautner; award_nominee=Taylor Swift] | m.0ngmz7j [nominated_for=Valentine's Day; award=Teen Choice Award for Choice Movie: Chemistry; award_nominee=Taylor Lautner; award_nominee=Taylor Swift] | m.0ngmzll [nominated_for=Valentine's Day; award=Teen Choice Award for Choice Movie: Liplock; award_nominee=Taylor Lautner; award_nominee=Taylor Swift]
    Abduction <--nominated_for-- m.0j2vjzw [nominated_for=The Twilight Saga: Breaking Dawn - Part 1; award=Razzie Award for Worst Actor; award_nominee=Taylor Lautner; ceremony=32nd Golden Raspberry Awards] | m.0hj8l0h [nominated_for=Abduction; award=People's Choice Award for Favorite Action Movie Star; award_nominee=Taylor Lautner; ceremony=38th People's Choice Awards] | m.0z837pz [nominated_for=Abduction; award=Teen Choice Award for Choice Movie Actor: Drama/Action Adventure; award_nominee=Taylor Lautner; ceremony=2012 Teen Choice Awards]
    Grown Ups 2 <--nominated_for-- m.0_80vng [nominated_for=Grown Ups 2; award=Razzie Award for Worst Supporting Actor; award_nominee=Taylor Lautner; ceremony=34th Golden Raspberry Awards] | m.0wjg9ly [nominated_for=Grown Ups 2; award=Teen Choice Award for Choice Hissy Fit: Film; award_nominee=Taylor Lautner; ceremony=2013 Teen Choice Awards]
    The Twilight Saga: New Moon <--nominated_for-- m.09sftk2 [nominated_for=The Twilight Saga: New Moon; award=People's Choice Award for Favorite On-Screen Chemistry; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] | m.09tz609 [nominated_for=The Twilight Saga: New Moon; award=Razzie Award for Worst Screen Couple/Ensemble; award_nominee=Kristen Stewart; award_nominee=Robert Pattinson] | m.0c02330 [nominated_for=The Twilight Saga: New Moon; award=MTV Movie Award for Best Male Performance; award_nominee=Taylor Lautner; ceremony=2010 MTV Movie Awards] | m.0sgl6rq [nominated_for=The Twilight Saga: New Moon; award=Kids' Choice Award for Favorite Movie Actor; award_nominee=Taylor Lautner; ceremony=2010 Kids' Choice Awards] | m.0sgl9q8 [nominated_for=The Twilight Saga: New Moon; award=Blimp Award for Cutest Couple; award_nominee=Kristen Stewart; award_nominee=Taylor Lautner] | m.0z8jj9c [nominated_for=The Twilight Saga: New Moon; award=Teen Choice Award for Choice Movie Actor: Fantasy; award_nominee=Taylor Lautner; ceremony=2010 Teen Choice Awards] | m.09tz5_t [nominated_
```

## 8. 给 Codex 的讨论问题

1. 超大候选集下,候选中心渲染的哪部分成本是可折叠的?(候选块头重复?
   块内 attrs 重复?链前缀重复?)
2. dense 的"中心合并行"(Twilight | Eclipse | … ←nominated_for--)与
   候选中心的"每候选一块"能否统一?混合策略的切换判据(候选数?块内
   路径同构度?)应该是什么?
3. 在裁决账本(§5)约束下,有哪些不违反零丢失/实体优先的压缩空间?
4. 记录 attrs 的显示预算(当前每记录 6 对/块内 480 字符)在超大候选下
   是否应该退化为纯键值透视(award=… | ceremony=… 每键一列)?
