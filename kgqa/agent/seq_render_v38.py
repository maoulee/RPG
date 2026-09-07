"""V3.8 triple-form renderer (user + Codex design ①, 2026-09-02).

RETURN TO TRIPLE-FORM evidence. Rows are compressed triples and ONLY two
compression shapes are legal (user ruling):

    same h + r → many tails    `h --r--> t1 | t2 | t3`
    many heads + same r + t    `h1 | h2 | h3 --r--> t`

CVT expansion unchanged (attrs inline in brackets, graph-reconstructed).
The pattern-paths overview and the forced candidates line are DROPPED —
in triple form every entity in a row IS a usable candidate (the ack's
env-computed `candidates` field still carries the walk's roster).

Input discipline inherited from V37h (walk-faithful): tree_data paths with
base-name + per-hop-direction dedup, same-relation out-and-back loop
suppression, suffix continuation drop. Edges derive from the kept paths'
hops with TRUE storage orientation (h→t as the graph stores it), so each
relation's own triples stay distinct (member vs member_of are different
rows by construction).

Gate: SEQ_RENDER_V38=1"""
import re
from collections import defaultdict

_VAL_RE = re.compile(
    r"^\d{4}-\d{2}|^\d{2}:\d{2}|^[+-]?[\d.,]+$|^\d{4}s?$")
_NOISY_ATTR = {"type", "types", "instance", "instances", "notable_types",
               "topic_equivalent_webpage", "webpage", "mid", "guid",
               "key", "keys", "permission", "is_reviewed", "article",
               "description", "alias", "name"}


def _cvt(n):
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _parse_node(s):
    s = str(s)
    if s.endswith("]") and ": [" in s:
        base, _, attr_txt = s.partition(": [")
        base = base.strip()
        if _cvt(base):
            return base, [a.strip() for a in attr_txt[:-1].split(",")
                          if a.strip()]
    return s, []


def render_v38_ack(treq, bres, ctx):
    ents, rels = ctx.ents, ctx.rels
    rel_adj = defaultdict(set)
    for h, rl, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        rel_adj[rl].add((h, t))
    ent_idx = {}
    for j, e in enumerate(ents):
        ent_idx.setdefault(str(e), j)
    center_names = [e for e, _i in (treq.get("centers") or [])]
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

    # ── collect walked paths (V37h discipline: base names + per-hop
    # direction key; same-relation out-and-back paths dropped) ──
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
                if len(relsn) >= 2:
                    rd = {i: hop_dir(relsn[i], key[i], key[i + 1])
                          for i in range(len(relsn))}
                    if any(relsn[a] == relsn[b] and rd[a] != rd[b]
                           for a in range(len(relsn))
                           for b in range(a + 1, len(relsn))):
                        continue
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

    node_seqs = {k[0] for k in raw}
    kept = {k: v for k, v in raw.items()
            if not any(k[0][i:] in node_seqs for i in range(1, len(k[0])))}

    # ── derive EDGES with true storage orientation ──
    edges = set()                       # (h_name, rel_short, t_name)
    for (key, _dirs), v in kept.items():
        for relsn in v["rels"]:
            for i in range(len(key) - 1):
                rname = relsn[i] if i < len(relsn) else None
                if rname is None:
                    continue
                sh = rname.rsplit(".", 1)[-1]
                d = hop_dir(rname, key[i], key[i + 1])
                if d == "r":
                    edges.add((key[i + 1], sh, key[i]))
                else:
                    edges.add((key[i], sh, key[i + 1]))

    # ── CVT attrs (graph-reconstructed, decoration-independent) ──
    # SELECTED-relation CVT edges are EXCLUDED from attrs: they render as
    # rows instead (1171 specimen: film.dubbing_performance.character folded
    # into attrs made the selected relation invisible while bridge edges
    # showed — "relations and walk results misaligned")
    sel_shorts = {r.rsplit(".", 1)[-1] for r in sel_rels}
    cvt_graph = defaultdict(list)
    for h, rl, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        hn = str(ents[h]) if 0 <= h < len(ents) else ""
        if not _cvt(hn):
            continue
        k = (str(rels[rl]).rsplit(".", 1)[-1]
             if 0 <= rl < len(rels) else "?")
        tv = str(ents[t]) if 0 <= t < len(ents) else str(t)
        if (not _cvt(tv) and len(tv) < 60 and k not in _NOISY_ATTR
                and k not in sel_shorts):
            cvt_graph[hn].append(f"{k}={tv}")

    # ── row building: the two legal compression shapes ──
    # direct entity↔entity rows
    direct = sorted(e for e in edges
                    if not _cvt(e[0]) and not _cvt(e[2]))
    # entity—CVT edges → record rows; CVT→entity edges whose relation was
    # SELECTED also become rows (see above) — only non-selected ones fold
    rec_out = defaultdict(set)          # (h, r) -> {cvt}
    rec_in = defaultdict(set)           # (r, t) -> {cvt}   (reverse shape)
    sel_cvt = defaultdict(set)          # (r, t) -> {cvt}   selected CVT edges
    for h, r, t in edges:
        if _cvt(t) and not _cvt(h):
            rec_out[(h, r)].add(t)
        elif _cvt(h) and not _cvt(t):
            if r in sel_shorts:
                sel_cvt[(r, t)].add(h)
            else:
                rec_in[(r, t)].add(h)

    def cvt_disp(mid, red):
        pairs = [a for a in cvt_graph.get(mid, ())
                 if "=" in a and a.split("=", 1)[1].strip().lower() not in red]
        at = "; ".join(pairs[:6])
        return f"{mid} [{at}]" if at else mid

    lines = []
    # shape 1: same h + r → many tails (direct + records share the row space)
    tails_of = defaultdict(dict)        # (h, r) -> {t: display}
    for h, r, t in direct:
        tails_of[(h, r)][t] = t
    for (h, r), mids in rec_out.items():
        for mid in mids:
            tails_of[(h, r)][mid] = cvt_disp(mid, {h.lower()})
    # shape 2: singletons regroup many heads → same r + t
    single = [(h, r, t) for (h, r), ts in tails_of.items() for t in ts
              if len(ts) == 1]
    multi = {(h, r): ts for (h, r), ts in tails_of.items() if len(ts) >= 2}
    heads_of = defaultdict(set)         # (r, t) -> {h}
    for h, r, t in single:
        heads_of[(r, t)].add(h)

    rows = []
    for (h, r) in sorted(multi, key=lambda k: (k[1], -len(multi[k]), k[0])):
        # join the DISPLAY values (CVT tails carry inline attrs) — joining
        # the dict keys printed bare mids and hid every measurement value
        # (co2/population specimens: 100+ bare mids, values unreachable).
        # STRUCTURE-PRESERVING fold (user ruling 2026-09-03 + measurement):
        # entities are core and NEVER dropped; only row STRUCTURE compresses
        # — long tails keep the first records verbatim, the remainder fold
        # to their full attr pairs grouped per record (`;` within, `|`
        # between). No caps on names.
        disp_list = [d for _t, d in sorted(multi[(h, r)].items())]
        joined = " | ".join(disp_list)
        if len(joined) > 1200:
            head_ds, used = [], 0
            for dd in disp_list:
                if used + len(dd) > 600 and head_ds:
                    break
                head_ds.append(dd)
                used += len(dd) + 3
            rest = disp_list[len(head_ds):]
            recs = ["; ".join(re.findall(r"[a-zA-Z_]+=[^;\]]+", dd))
                    for dd in rest]
            recs = [x for x in recs if x] or rest
            joined = (" | ".join(head_ds)
                      + f" (+{len(rest)}: {' | '.join(recs)}"
                      + ")")
        rows.append((r, f"{h} --{r}--> {joined}"))
    for (r, t) in sorted(heads_of, key=lambda k: (k[0], -len(heads_of[k]), k[1])):
        hs = sorted(heads_of[(r, t)])
        disp = cvt_disp(t, {x.lower() for x in hs}) if _cvt(t) else t
        rows.append((r, f"{' | '.join(hs)} --{r}--> {disp}"))
    # SELECTED CVT→entity rows: `m.xxx [attrs] --selected_rel--> entity` —
    # every relation the model asked for stays visible as a triple
    for (r, t) in sorted(sel_cvt):
        disps = [cvt_disp(m, {t.lower()}) for m in sorted(sel_cvt[(r, t)])]
        rows.append((r, f"{' | '.join(disps)} --{r}--> {t}"))
    # record reverse-shape rows (CVT→entity edges that stayed as records)
    seen_recs = {mid for mids in rec_out.values() for mid in mids}
    seen_recs |= {mid for mids in sel_cvt.values() for mid in mids}
    for (r, t), mids in rec_in.items():
        extra = {m for m in mids if m not in seen_recs}
        if not extra:
            continue
        for m in sorted(extra):
            rows.append((r, f"{cvt_disp(m, {t.lower()})} --{r}--> {t}"))

    # RELATION-SECTIONED DISPLAY (user design 2026-09-02): triples of the
    # SELECTED relations centralize first — each section headed by the
    # relation with its candidate-side roster (the fan-out side of its
    # edges) — then other walked relations follow. Pure reorganization of
    # the same rows; zero-loss unchanged.
    by_rel = defaultdict(list)
    for r, row in rows:
        by_rel[r].append(row)

    def roster(r):
        tails, heads = set(), set()
        for h, rr, t in edges:
            if rr == r and not _cvt(t) and not _cvt(h):
                tails.add(t)
                heads.add(h)
        side = tails if len(tails) >= len(heads) else heads
        ns = sorted(side)
        if not ns:
            return ""
        txt = " | ".join(ns[:40])
        return txt + (f" …(+{len(ns) - 40})" if len(ns) > 40 else "")

    L = [f"entities: {' | '.join(center_names)}"]
    sel_shorts = {r.rsplit(".", 1)[-1] for r in sel_rels}
    for r in sorted(r for r in by_rel if r in sel_shorts):
        ros = roster(r)
        L.append(f"▸ --{r}-->  (retrieved"
                 + (f" · candidates: {ros}" if ros else "") + ")")
        L.extend(f"    {row}" for row in by_rel[r])
    other = sorted(r for r in by_rel if r not in sel_shorts)
    if other:
        L.append("▸ other walked relations:")
        for r in other:
            L.extend(f"    {row}" for row in by_rel[r])
    return "\n".join(L)
