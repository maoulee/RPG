"""TRIPLE LAYER (user core-principle ruling 2026-09-12): the RECONSTRUCTED
TRIPLE SET is each subgraph's core content. The full case graph is the base;
the logical paths obtained from the pattern walk are rebuilt into the
subgraph's triples; dedup / merge evaluation / CVT admission all operate on
those triples. Everything except plan parsing works on the walk's ACTUAL
outputs. This module owns that reconstruction — it knows treq/bres/ctx but
knows NOTHING about rows or display.

Output (the "store") is consumed exclusively by the row layer (seq_rows.py).
"""
from collections import defaultdict


def _cvt(n):
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _short_r(rname):
    return ".".join(str(rname).rsplit(".", 2)[-2:])


def collect_pattern_triples(treq, bres, ctx, kept, edges, hop_dir,
                            mid_attr_pairs):
    """Rebuild the pattern-walk's logical paths into the subgraph's triples.

    kept/edges/hop_dir/mid_attr_pairs are render_v38_ack's collection-phase
    products (the walk's actual outputs — the only source of truth)."""
    groups = defaultdict(list)          # rels tuple -> [nodes tuple]
    for (key, _dirs), v in kept.items():
        for relsn in v["rels"]:
            groups[tuple(str(r) for r in relsn)].append(key)

    # submitted-terminal priority: the model's own submission order
    # (attr_expansion keys; rel_names fallback for echo-less full names)
    _sub_sh = {_short_r(k): i for i, k in
               enumerate((treq.get("attr_expansion") or {}).keys())}
    for _i, _rn in enumerate(treq.get("rel_names") or []):
        _sub_sh.setdefault(_short_r(str(_rn)), 50 + _i)
    _cn = {str(c) for c, _i in (treq["centers"] or [])}

    # the SUBMITTED relation's direct edges (CVT penetration edges ride
    # p.triples, not kept paths) join their 1-hop pattern
    _full_of_short = {}
    for _rn in (treq.get("rel_names") or []):
        _full_of_short.setdefault(_short_r(_rn), str(_rn))
    for _h, _r, _t in list(edges):
        _fr = _full_of_short.get(_r)
        if _fr is not None:
            groups.setdefault((_fr,), []).append((_h, _t))

    def _pkey(rt):
        insts = {k for k in groups[rt]}
        anchored = any(k[0] in _cn or k[-1] in _cn for k in insts)
        return (0 if _short_r(rt[-1]) in _sub_sh else 1,
                0 if anchored else 1,
                len(rt), rt)

    # ORDER walked patterns, never cut (semantic choice happened in B phase)
    _env_cap = 2
    _shown = []
    for rt in sorted(groups, key=_pkey):
        if _short_r(rt[-1]) not in _sub_sh:
            if _env_cap <= 0:
                continue
            _env_cap -= 1
        _shown.append(rt)

    patterns = []
    shown_edges = set()
    ms_emitted = set()
    for rt in _shown[:6]:
        insts = sorted({k for k in groups[rt]})
        hops = []                       # [(rel_short, {h: [t...]})]
        attrs = []                      # [(hop_idx, (mid, key, value))]
        for i, r in enumerate(rt):
            sh = _short_r(r)
            tails_of_h = {}
            mids_here = []
            for key in insts:
                a, b = key[i], key[i + 1]
                d = hop_dir(r, a, b)
                h, t = (b, a) if d == "r" else (a, b)
                if (h, sh, t) not in shown_edges:
                    shown_edges.add((h, sh, t))
                    tails_of_h.setdefault(h, set()).add(t)
                for x in (h, t):
                    if _cvt(x) and x not in ms_emitted:
                        ms_emitted.add(x)
                        mids_here.append((x, {a.lower(), b.lower()}))
            hops.append((sh, {h: sorted(ts) for h, ts in tails_of_h.items()}))
            for mid, red in mids_here:
                for k, vs in mid_attr_pairs(mid, red):
                    for v in vs:
                        attrs.append((i, (mid, k, v)))
        patterns.append({"label": " ⭢ ".join(_short_r(r) for r in rt),
                         "hops": hops, "attrs": attrs, "n_inst": len(insts)})

    # environment: walked edges not on any rendered pattern
    _edges = set()
    for (key, _dirs), v in kept.items():
        for relsn in v["rels"]:
            for i in range(len(key) - 1):
                d = hop_dir(relsn[i], key[i], key[i + 1])
                _edges.add((key[i + 1], _short_r(relsn[i]), key[i]) if d == "r"
                           else (key[i], _short_r(relsn[i]), key[i + 1]))
    for e in edges:
        _edges.add(e)
    env_triples = sorted(e for e in _edges if e not in shown_edges)

    return {"centers": [str(c) for c, _i in treq["centers"]],
            "patterns": patterns, "env_triples": env_triples}
