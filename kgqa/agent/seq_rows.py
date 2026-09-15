"""ROW LAYER (user ruling 2026-09-12; entity-block layout 2026-09-15):
rendering is split in two — this module ONLY renders ROWS and accepts
nothing but the triple store built by seq_triples.collect_pattern_triples.

ENTITY-BLOCK LAYOUT (user ruling 2026-09-15): patterns render as an INDEX
line at the top; the evidence body groups triples by ENTITY — each
non-CVT entity gets a block with all its edges (both directions, tail-
merged) plus the CVT attribute expansions of edges that connect to it.
No candidate marking: structurally related entities appear together and
the model reads/compares blocks naturally. Blocks are ordered by
information density (discriminator-carrying entities first, then
by degree); the anchor's block serves as the roster/context view.
"""
from collections import defaultdict

_NOTE = ("note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) "
         "or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. "
         "Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose "
         "ATTRIBUTES are the event's content. Event nodes are NEVER answer candidates and NEVER "
         "variable bindings — answer and bind with the event's named ATTRIBUTES. "
         "Discriminator attributes (dates, values, symbols) appear within the owning entity's "
         "block — compare blocks to pick latest/largest/incumbent. Pick the next center FROM "
         "these blocks.")

_TAIL_CAP = 40
_HEAD_CAP = 12
_VAL_CAP = 8
_ENV_CAP = 24
_MULTI_MIN = 3
_BLOCK_CAP = 16


def _cvt(n):
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _has_discriminator(edges):
    """Whether any edge targets a value/date/number/symbol key."""
    _DISC = ("date", "number", "symbol", "id", "value", "rate", "amount",
             "year", "time", "kind", "type_of", "name")
    return any(any(d in str(r).lower() for d in _DISC)
               for _, r, _ in edges)


def render_rows(store):
    """Format the triple store into the model-facing evidence text:
    pattern index → entity blocks → note."""
    # ── header ──
    if store.get("frontier"):
        L = [f"entities: {' | '.join(store['centers'])}  "
             f"(sequence root; this layer applies to the frontier: "
             f"{' | '.join(store['frontier'])})"]
    else:
        L = [f"entities: {' | '.join(store['centers'])}"]

    # ── collect ALL edges from patterns + env into a flat edge list ──
    all_edges = []          # (h, r, t)
    cvt_attrs = []          # (mid, key, value) — attributes of CVT nodes
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

    # ── pattern index ──
    if pattern_labels:
        L.append(f"▸ patterns: {' | '.join(pattern_labels)}")

    # ── build entity blocks ──
    # entity → list of (h, r, t) edges where it participates
    # VALUE entities (dates, numbers, bare values) are NOT block owners —
    # they are discriminating VALUES that belong inside the block of the
    # entity that carries them via a CVT (user ruling 2026-09-15: no
    # ── 1997-08:00 ── blocks)
    _VALUE_HINTS = ("08:00", "utc", "19", "20")
    def _is_value_entity(n):
        s = str(n)
        if _cvt(s):
            return False
        return (len(s) <= 12 and any(c.isdigit() for c in s)
                and not any(c.isalpha() for c in s.replace("-","").replace(":","")))

    ent_edges = defaultdict(list)
    for h, r, t in all_edges:
        if not _cvt(h) and not _is_value_entity(h):
            ent_edges[h].append((h, r, t))
        if not _cvt(t) and not _is_value_entity(t):
            ent_edges[t].append((h, r, t))
    # CVT attributes: assign to the entity that connects to this CVT
    cvt_owner = {}
    for h, r, t in all_edges:
        if _cvt(t):
            cvt_owner.setdefault(t, h)     # first non-CVT connector
        elif _cvt(h):
            cvt_owner.setdefault(h, t)
    cvt_block = defaultdict(list)
    for mid, k, v in cvt_attrs:
        owner = cvt_owner.get(mid)
        if owner:
            cvt_block[owner].append((mid, k, v))
    # value-carrying edges (date/number → value): assign to the CVT's owner
    # instead of creating a value-entity block
    for h, r, t in all_edges:
        if _cvt(h) and _is_value_entity(t):
            owner = cvt_owner.get(h)
            if owner and owner in ent_edges:
                cvt_block[owner].append((h, r, t))

    # ── order blocks: discriminator-carrying first, then by edge count ──
    centers = set(store.get("centers", []))
    ordered = sorted(
        ent_edges,
        key=lambda e: (
            0 if e in centers else 1,              # anchor/context first
            0 if _has_discriminator(ent_edges[e]) else 1,
            -len(ent_edges[e]),
            e))
    # ── render blocks ──
    _n = 0
    for ent in ordered:
        if _n >= _BLOCK_CAP:
            break
        edges = ent_edges[ent]
        if not edges:
            continue
        L.append(f"── {ent} ──")
        # tail-merge: same (h, r) → one row with merged tails
        by_hr = defaultdict(list)
        for h, r, t in edges:
            by_hr[(h, r)].append(t)
        for (h, r), ts in sorted(by_hr.items()):
            ts_u = sorted(set(ts))
            shown = " | ".join(ts_u[:_TAIL_CAP])
            more = (f" …(+{len(ts_u) - _TAIL_CAP})"
                    if len(ts_u) > _TAIL_CAP else "")
            prefix = "" if h == ent else f"{h} "
            L.append(f"    {prefix}--{r}--> {shown}{more}")
        # CVT attribute expansions for CVTs this entity connects to
        _by_mid_key = defaultdict(list)
        for mid, k, v in cvt_block.get(ent, ()):
            _by_mid_key[(mid, k)].append(v)
        for (mid, k) in sorted(_by_mid_key):
            vs = sorted(set(_by_mid_key[(mid, k)]))
            shown = " | ".join(vs[:_VAL_CAP])
            more = (f" …(+{len(vs) - _VAL_CAP})"
                    if len(vs) > _VAL_CAP else "")
            L.append(f"    {mid} --{k}--> {shown}{more}")
        _n += 1

    L.append(_NOTE)
    return "\n".join(L)
