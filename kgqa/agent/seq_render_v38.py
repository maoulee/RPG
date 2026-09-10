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
import os
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
    # EDGE DISPLAY SHORT NAME (user audit 2026-09-09): last TWO components
    # (type.attribute). The bare attribute collapsed semantically different
    # relations in one subgraph (division/facility/league/location all
    # rendered '--teams-->') — the model could not tell which relation a row
    # came from. Typed shorts disambiguate rows AND match the rr display's
    # group keys.
    def _short(rname: str) -> str:
        return ".".join(rname.rsplit(".", 2)[-2:])

    # PATH-CONSISTENT EVIDENCE (user ruling 2026-09-10, Belgium specimen):
    # tier-1 admits only hops on CENTER-ANCHORED chains — the abstract
    # pattern instantiated with the center (Belgium --containedby--> Europe).
    # Terminal edges of RPE bridge segments (Belgium →adjoin-CVT→ Luxembourg
    # --containedby→ …) and sibling expansions are still WALKED evidence but
    # are environment rows: they demote to "other walked relations" instead
    # of posing as the asked relation's answers.
    _center_names = {str(c) for c in center_names}

    def _anchored_hops(key):
        if key and key[0] in _center_names:
            return {(key[i], key[i + 1]) for i in range(len(key) - 1)}
        return set()

    anchored = set()                  # (h_name, t_name) on center-anchored paths

    def _anch_pair(a, b):
        return (a, b) in anchored or (b, a) in anchored

    edges = set()                       # (h_name, rel_short, t_name)
    for (key, _dirs), v in kept.items():
        anchored |= _anchored_hops(key)
        for relsn in v["rels"]:
            for i in range(len(key) - 1):
                rname = relsn[i] if i < len(relsn) else None
                if rname is None:
                    continue
                sh = _short(rname)
                d = hop_dir(rname, key[i], key[i + 1])
                if d == "r":
                    edges.add((key[i + 1], sh, key[i]))
                    anchored.add((key[i + 1], key[i]))
                else:
                    edges.add((key[i], sh, key[i + 1]))
                    anchored.add((key[i], key[i + 1]))
    # CVT PENETRATION + CENTER-PARENTED SIBLINGS are part of the center's
    # pattern instantiation (pathcons rollout: demoting them cost -4.4pp —
    # film names behind performance CVTs left tier-1). A penetration pair
    # (cvt, named) is anchored when the CVT sits on ANY walked path or is
    # reached directly from a center; a sibling row is anchored when its
    # head/parent is a center or a path node.
    _path_nodes = {n for (key, _d), _v in kept.items() for n in key}
    for (cname, cidx), pe in zip(treq["centers"], bres["pe_list"]):
        for pid, p in (pe.items() if isinstance(pe, dict) else []):
            for tr in (getattr(p, "triples", None) or []):
                if len(tr) != 3:
                    continue
                h, _r, t = str(tr[0]), str(tr[1]), str(tr[2])
                # tier-1 is gated by the SELECTED relations anyway, so
                # anchoring every CVT-headed walk triple cannot re-admit
                # unselected environment sections — it only keeps the
                # selected relations' CVT-mediated instantiations visible
                if _cvt(h) or h in _center_names:
                    anchored.add((h, t))
    # CVT PENETRATION EDGES from p.triples (user audit 2026-09-08: the walk
    # ENUMERATES CVT→named edges — 54 in the 25 specimen — but tree_data
    # paths are step-relation-constrained and only record anchor→CVT→anchor
    # round-trips; the named endpoints (film names, rosters) never join the
    # render. Add them from the walk's actual enumeration.)
    for (cname, cidx), pe in zip(treq["centers"], bres["pe_list"]):
        for pid, p in (pe.items() if isinstance(pe, dict) else []):
            for tr in (getattr(p, "triples", None) or []):
                if len(tr) != 3:
                    continue
                h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
                if _cvt(h) and not _cvt(t):
                    sh = _short(r)
                    d = hop_dir(r, h, t)
                    if d == "r":
                        edges.add((t, sh, h))
                    else:
                        edges.add((h, sh, t))
                elif not _cvt(h) and _cvt(t):
                    sh = _short(r)
                    d = hop_dir(r, h, t)
                    if d == "r":
                        edges.add((t, sh, h))
                    else:
                        edges.add((h, sh, t))

    # ── CVT attrs (graph-reconstructed, decoration-independent) ──
    # SELECTED-relation CVT edges are EXCLUDED from attrs: they render as
    # rows instead (1171 specimen: film.dubbing_performance.character folded
    # into attrs made the selected relation invisible while bridge edges
    # showed — "relations and walk results misaligned")
    sel_shorts = {_short(r) for r in sel_rels}
    sel_bare = {r.rsplit(".", 1)[-1] for r in sel_rels}
    cvt_graph = defaultdict(list)
    cvt_graph_all = defaultdict(list)   # same WITHOUT the sel_bare exclusion
    for h, rl, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        hn = str(ents[h]) if 0 <= h < len(ents) else ""
        if not _cvt(hn):
            continue
        k = (str(rels[rl]).rsplit(".", 1)[-1]
             if 0 <= rl < len(rels) else "?")
        tv = str(ents[t]) if 0 <= t < len(ents) else str(t)
        if not _cvt(tv) and len(tv) < 60 and k not in _NOISY_ATTR:
            # COMPRESSION summary source: the SELECTED key (film=, for a
            # film-family row) is exactly the content the compressed row
            # must show — excluding it (the bracket rule) left the summary
            # with secondary keys (character:) that mislead at that position
            # (cvtinline3: 0.6570 with character-first summaries vs 0.6836
            # with the summary hidden entirely)
            cvt_graph_all[hn].append(f"{k}={tv}")
            if k not in sel_bare:
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

    # CVT ATTR-KEY TOP-K (user design 2026-09-08): the question→key GTE
    # ranking pre-computed in _sg_execute selects which attributes each CVT
    # bracket shows — top-K keys only, the rest suppressed (avg 96 keys/
    # case would flood every bracket; GTE top-3 covers 50% of gold keys vs
    # random 5%). Fallback when no ranking: show all (cap 6, old behavior).
    _krank = getattr(ctx, "_cvt_key_rank", None)
    _kranked_keys = _krank[1] if _krank and _krank[1] else None
    _K = int(os.environ.get("SEQ_CVT_ATTR_TOPK", "3") or 0)  # 0 = off
    _submitted_components = set()
    for _sr in (treq.get("rel_names") or []):
        for _seg in str(_sr).split("."):
            if _seg:
                _submitted_components.add(_seg)

    def cvt_disp(mid, red):
        pairs = [a for a in cvt_graph.get(mid, ())
                 if "=" in a and a.split("=", 1)[1].strip().lower() not in red]
        if _kranked_keys and _K > 0:
            _topk = set(_kranked_keys[:_K])
            # submitted-relation components always join the top-K — the model
            # may submit the INVERSE direction (film.actor.dubbing_performances
            # vs film.performance.actor: same CVT family, different key names),
            # so exempt EVERY dotted component of every submitted relation
            _topk |= _submitted_components
            pairs = [a for a in pairs if a.split("=", 1)[0].strip() in _topk]
        at = "; ".join(pairs[:6])
        return f"{mid} [{at}]" if at else mid

    lines = []

    # ── CVT-TAIL COMPRESSION (user approval 2026-09-09) ─────────────────────
    # A row with MANY CVT tails (Miley --actor.film--> 18 bare mids) is noise:
    # mids are never answers, and per-mid brackets repeat the overlapping
    # values 18× (actor=Miley Cyrus in every record). For (h,r) rows with ≥4
    # CVT tails, collapse the tail set to its GTE-ranked attribute content —
    # per KEY: the DISTINCT values (question-ranked keys first, submitted
    # components next); a key with ONE distinct value folds to `k=v (×n)`.
    # A/B (user design 2026-09-09): SEQ_CVT_STYLE=inline puts the collapsed
    # form IN the row; =block leaves a pointer in the row and appends an
    # `event attributes` section after the relation sections.
    _CVT_COMPRESS_MIN = 4

    def _cvt_tail_keys(mids, red):
        # per-key distinct values across the tail set (top-K filtered, same
        # discipline as cvt_disp), keys ordered: GTE rank, then the rest.
        # Reads cvt_graph_all — the compression summary needs the SELECTED
        # family's own key first (see cvt_graph_all build note).
        kv = defaultdict(set)
        for mid in mids:
            for a in cvt_graph_all.get(mid, ()):
                if "=" not in a:
                    continue
                k, v = a.split("=", 1)
                k, v = k.strip(), v.strip()
                if not v or v.lower() in red or k in _NOISY_ATTR:
                    continue
                if len(v) >= 60:
                    continue
                kv[k].add(v)
        if not kv:
            return []
        if _kranked_keys and _K > 0:
            _topk = set(_kranked_keys[:_K]) | _submitted_components
            kv = {k: vs for k, vs in kv.items() if k in _topk} or kv
        order = {k: i for i, k in enumerate(_kranked_keys or [])}

        def _kord(k):
            # submitted components rank right after the GTE top keys
            return (0, order.get(k, 99)) if k in order else (1, k)
        return sorted(kv.items(), key=lambda kv_: _kord(kv_[0]))

    def _cvt_tail_summary(h, r, mids):
        red = {h.lower()}
        kv = _cvt_tail_keys(mids, red)
        if not kv:
            return ""
        parts = []
        for k, vs in kv[:3]:
            vs = sorted(vs)
            if len(vs) == 1:
                # one distinct value across the whole tail set (overlap) —
                # fold to k=v (×n) instead of echoing it per event
                parts.append(f"{k}={next(iter(vs))} (×{len(mids)})")
            else:
                shown = " | ".join(vs[:8])
                more = f" …(+{len(vs) - 8})" if len(vs) > 8 else ""
                parts.append(f"{k}: {shown}{more}")
        return f"{len(mids)} event records · " + " · ".join(parts)

    _cvt_block = []               # block-mode deferred summaries
    _style = os.environ.get("SEQ_CVT_STYLE", "inline").strip().lower()
    n = 0                         # synthetic-entry counter for compressed rows

    # shape 1: same h + r → many tails (direct + records share the row space)
    tails_of = defaultdict(dict)        # (h, r) -> {t: display}
    for h, r, t in direct:
        tails_of[(h, r)][t] = t
    for (h, r), mids in rec_out.items():
        _mset = sorted(m for m in mids if _cvt(m))
        if len(_mset) >= _CVT_COMPRESS_MIN:
            _sum = _cvt_tail_summary(h, r, _mset)
            if _sum:
                # the whole mid tail set becomes ONE entry (repeating the
                # summary per mid would echo it 18×) — named direct tails
                # in the same (h, r) row are untouched
                for mid in mids:
                    tails_of[(h, r)].pop(mid, None)
                if _style == "block":
                    _cvt_block.append((r, h, _sum))
                    tails_of[(h, r)][f"__evt{n}"] = f"(↓ {len(mids)} event records)"
                else:
                    tails_of[(h, r)][f"__evt{n}"] = f"({_sum})"
                n += 1
                continue
        for mid in mids:
            tails_of[(h, r)][mid] = cvt_disp(mid, {h.lower()})
    # shape 2: singletons regroup many heads → same r + t. Synthetic
    # compressed entries (__evt*) must NOT enter the regroup — it keys by
    # the TAIL NAME, which would print the raw key instead of the summary;
    # they render directly as one row.
    rows = []
    single = [(h, r, t) for (h, r), ts in tails_of.items() for t in ts
              if len(ts) == 1 and not t.startswith("__evt")]
    for (h, r), ts in tails_of.items():
        if len(ts) == 1:
            t = next(iter(ts))
            if t.startswith("__evt"):
                rows.append((r, f"{h} --{r}--> {ts[t]}", _anch_pair(h, t)))
    multi = {(h, r): ts for (h, r), ts in tails_of.items() if len(ts) >= 2}
    heads_of = defaultdict(set)         # (r, t) -> {h}
    for h, r, t in single:
        heads_of[(r, t)].add(h)

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
        rows.append((r, f"{h} --{r}--> {joined}",
                     any(_anch_pair(h, _t) for _t in multi[(h, r)])))
    for (r, t) in sorted(heads_of, key=lambda k: (k[0], -len(heads_of[k]), k[1])):
        hs = sorted(heads_of[(r, t)])
        disp = cvt_disp(t, {x.lower() for x in hs}) if _cvt(t) else t
        rows.append((r, f"{' | '.join(hs)} --{r}--> {disp}",
                     any(_anch_pair(h, t) for h in hs)))
    # SELECTED CVT→entity rows: `m.xxx [attrs] --selected_rel--> entity` —
    # every relation the model asked for stays visible as a triple
    for (r, t) in sorted(sel_cvt):
        disps = [cvt_disp(m, {t.lower()}) for m in sorted(sel_cvt[(r, t)])]
        rows.append((r, f"{' | '.join(disps)} --{r}--> {t}",
                     any(_anch_pair(m, t) for m in sel_cvt[(r, t)])))
    # record reverse-shape rows (CVT→entity edges that stayed as records)
    seen_recs = {mid for mids in rec_out.values() for mid in mids}
    seen_recs |= {mid for mids in sel_cvt.values() for mid in mids}
    for (r, t), mids in rec_in.items():
        extra = {m for m in mids if m not in seen_recs}
        if not extra:
            continue
        for m in sorted(extra):
            rows.append((r, f"{cvt_disp(m, {t.lower()})} --{r}--> {t}",
                         _anch_pair(m, t)))

    # RELATION-SECTIONED DISPLAY (user design 2026-09-02) + PATH
    # CONSISTENCY (user ruling 2026-09-10): tier-1 admits only rows on
    # CENTER-ANCHORED chains (the abstract pattern instantiated with the
    # center); environment rows — RPE bridge-segment terminals, sibling
    # expansions — all demote to "other walked relations", never posing as
    # the asked relation's answers.
    by_rel = defaultdict(list)
    for r, row, anch in rows:
        by_rel[r].append((row, anch))

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
    sel_shorts = {_short(r) for r in sel_rels}
    for r in sorted(r for r in by_rel if r in sel_shorts):
        tier_rows = [row for row, anch in by_rel[r] if anch]
        if not tier_rows:
            continue         # selected but NO center-anchored instantiation
        ros = roster(r)
        L.append(f"▸ --{r}-->  (retrieved"
                 + (f" · candidates: {ros}" if ros else "") + ")")
        L.extend(f"    {row}" for row in tier_rows)
    L.append("▸ other walked relations (environment — not center-anchored paths):")
    for r in sorted(by_rel):
        env_rows = [row for row, anch in by_rel[r] if not anch]
        L.extend(f"    {row}" for row in env_rows)
    if _cvt_block:
        # BLOCK MODE (SEQ_CVT_STYLE=block): the compressed attribute content
        # of large CVT-tail rows lives here, one line per (relation, head)
        L.append("▸ event attributes (compressed from the ↓-marked rows):")
        for r, h, s in _cvt_block:
            L.append(f"    {h} --{r}--> {s}")
    return "\n".join(L)
