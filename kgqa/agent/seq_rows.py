"""ROW LAYER — entity-block layout with inline CVT brackets (user ruling
2026-09-15): patterns render as an index line; evidence groups by entity
blocks. Within each block:
  * direct edges: tail-merged (one head, many tails per row)
  * incoming edges: head-merged (many heads, one tail per row)
  * CVT connections: INLINE brackets — m.xxx [key: value | key: value]
  * deduplicated: same edge with short/full relation name shows once
  * hub entities whose edges are all shown in other blocks: skipped
"""
from collections import defaultdict

_NOTE = ("note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' "
         "merges tails; 'h1 | h2 --rel--> t' merges heads. m.xxx [key: value] "
         "shows a CVT's attributes inline — the owning entity connects to it. "
         "Compare blocks to discriminate candidates (dates, values, symbols).")

_TAIL_CAP = 40
_HEAD_CAP = 12
_VAL_CAP = 8
_GROUP_CAP = 10
_MULTI_MIN = 3


def _cvt(n):
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _is_value(n):
    s = str(n)
    if _cvt(s):
        return False
    return (len(s) <= 14 and any(c.isdigit() for c in s)
            and not any(c.isalpha() for c in s.replace("-", "").replace(":", "")))


def _short_rel(r):
    return str(r).rsplit(".", 1)[-1].lower()


def render_rows(store):
    if store.get("frontier"):
        L = [f"entities: {' | '.join(store['centers'])}  "
             f"(sequence root; this layer applies to the frontier: "
             f"{' | '.join(store['frontier'])})"]
    else:
        L = [f"entities: {' | '.join(store['centers'])}"]

    all_edges = []
    cvt_attrs = []
    pattern_labels = []
    for pat in store["patterns"]:
        pattern_labels.append(pat["label"])
        for sh, hop in pat["hops"]:
            for h, ts in hop.items():
                for t in ts:
                    all_edges.append((h, sh, t))
        for _hi, (mid, k, v) in pat.get("attrs", ()):
            cvt_attrs.append((mid, k, v))
    for h, r, t in store.get("env_triples", ()):
        all_edges.append((h, r, t))

    if pattern_labels:
        L.append(f"▸ patterns: {' | '.join(pattern_labels)}")

    # dedup edges by (h, short_rel, t)
    _seen = set()
    deduped = []
    for h, r, t in all_edges:
        k = (str(h), _short_rel(r), str(t))
        if k not in _seen:
            _seen.add(k)
            deduped.append((h, r, t))
    all_edges = deduped
    _seen_a = set()
    cvt_d = []
    for mid, k, v in cvt_attrs:
        k2 = (mid, _short_rel(k), v)
        if k2 not in _seen_a:
            _seen_a.add(k2)
            cvt_d.append((mid, k, v))
    cvt_attrs = cvt_d

    # CVT owner map
    cvt_owner = {}
    for h, r, t in all_edges:
        if _cvt(t) and not _cvt(h) and not _is_value(h):
            cvt_owner.setdefault(t, h)
        elif _cvt(h) and not _cvt(t) and not _is_value(t):
            cvt_owner.setdefault(h, t)

    centers = set(store.get("centers", []))
    ent_out = defaultdict(list)
    ent_in = defaultdict(list)
    for h, r, t in all_edges:
        if not _cvt(h) and not _is_value(h):
            ent_out[h].append((h, r, t))
        if not _cvt(t) and not _is_value(t):
            ent_in[t].append((h, r, t))

    cvt_connected = set(cvt_owner.values())
    all_ents = set(ent_out) | set(ent_in)
    block_ents = sorted(
        all_ents,
        key=lambda e: (
            0 if e in centers else 1,
            0 if e in cvt_connected else 1,
            -(len(ent_out.get(e, ())) + len(ent_in.get(e, ()))),
            e))[:_GROUP_CAP]

    shown_edges = set()
    for ent in block_ents:
        out_e = ent_out.get(ent, [])
        in_e = ent_in.get(ent, [])
        if not out_e and not in_e:
            continue
        L.append(f"── {ent} ──")
        # outgoing: tail-merge
        by_hr = defaultdict(lambda: [None, []])
        for h, r, t in out_e:
            k = (h, _short_rel(r))
            by_hr[k][0] = r
            by_hr[k][1].append(t)
            shown_edges.add((str(h), _short_rel(r), str(t)))
        for (h, _), (r, ts) in sorted(by_hr.items()):
            ts_u = sorted(set(ts))
            shown = " | ".join(ts_u[:_TAIL_CAP])
            more = (f" …(+{len(ts_u) - _TAIL_CAP})" if len(ts_u) > _TAIL_CAP else "")
            L.append(f"    --{r}--> {shown}{more}")
        # incoming: skip already-shown, head-merge when many
        by_rt = defaultdict(list)
        for h, r, t in in_e:
            k = (str(h), _short_rel(r), str(t))
            if k in shown_edges:
                continue
            by_rt[(_short_rel(r), t)].append((h, r))
            shown_edges.add(k)
        for (_, t), hrs in sorted(by_rt.items()):
            if len(hrs) >= _MULTI_MIN:
                hs_u = sorted(set(h for h, _ in hrs))
                shown_h = " | ".join(hs_u[:_HEAD_CAP])
                more = (f" …(+{len(hs_u) - _HEAD_CAP})" if len(hs_u) > _HEAD_CAP else "")
                L.append(f"    {shown_h}{more} --{hrs[0][1]}--> {t}")
            else:
                for h, r in sorted(hrs):
                    L.append(f"    {h} --{r}--> {t}")
        # CVT inline brackets
        my_cvts = defaultdict(lambda: defaultdict(set))
        for mid, owner in cvt_owner.items():
            if owner == ent:
                for m2, k, v in cvt_attrs:
                    if m2 == mid:
                        my_cvts[mid][_short_rel(k)].add(v)
        for mid in sorted(my_cvts):
            pairs = []
            for k in sorted(my_cvts[mid]):
                vs = sorted(my_cvts[mid][k])
                shown_v = " | ".join(vs[:_VAL_CAP])
                pairs.append(f"{k}: {shown_v}")
            if pairs:
                L.append(f"    {mid} [{' | '.join(pairs)}]")
            else:
                L.append(f"    {mid}")

    # context tail
    ctx = []
    for h, r, t in all_edges:
        k = (str(h), _short_rel(r), str(t))
        if k not in shown_edges and not _cvt(h) and not _cvt(t):
            ctx.append((h, r, t))
    if ctx:
        _ctx_by = defaultdict(list)
        for h, r, t in ctx[:_GROUP_CAP * 3]:
            _ctx_by[(h, _short_rel(r))].append((r, t))
        _n = 0
        for (h, _), rts in sorted(_ctx_by.items()):
            if _n >= 8:
                break
            r0 = rts[0][0]
            ts_u = sorted(set(t for _, t in rts))
            shown = " | ".join(ts_u[:_TAIL_CAP])
            L.append(f"    {h} --{r0}--> {shown}")
            _n += 1

    L.append(_NOTE)
    return "\n".join(L)
