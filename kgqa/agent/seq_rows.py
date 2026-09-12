"""ROW LAYER (user ruling 2026-09-12): rendering is split in two — this
module ONLY renders ROWS and accepts nothing but the triple store built by
seq_triples.collect_pattern_triples. It knows nothing about treq/bres/ctx
or walk internals; the layers never share control flow.

Row discipline (accumulated rulings):
  * every hop of a pattern renders as triples grouped per head with merged
    tails; many single-tail heads sharing one tail merge head-side (prefix
    compression);
  * CVT attribute edges render under the pattern whose hop surfaced the
    mid (cvt_triples is ordered by surfacing; consumed in order);
  * the environment block is a capped list of unrendered walked triples —
    no bare entity names anywhere;
  * the fixed note explains the notation.
"""

_NOTE = ("note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) "
         "or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. "
         "Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose "
         "ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver "
         "| --performance.actor--> Jon Favreau' means 'a performance event where the character "
         "Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER "
         "variable bindings — answer and bind with the event's named ATTRIBUTES (actor, "
         "character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) "
         "appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph "
         "shows the FULL evidence its pattern paths justify — an edge may legitimately reappear "
         "across subgraphs with its complete tail set. Pick the next center FROM these triples.")

_TAIL_CAP = 40
_HEAD_CAP = 12
_VAL_CAP = 8
_ENV_CAP = 24
_MULTI_MIN = 3


def render_rows(store):
    """Format the triple store into the model-facing evidence text."""
    L = [f"entities: {' | '.join(store['centers'])}"]
    for pat in store["patterns"]:
        L.append(f"▸ pattern {pat['label']}  ({pat['n_inst']} instantiations)")
        for hi, (sh, hop) in enumerate(pat["hops"]):
            heads_of_t = {}
            for h, ts in hop.items():
                if len(ts) == 1:
                    heads_of_t.setdefault(ts[0], []).append(h)
            multi = {t for t, hs in heads_of_t.items()
                     if len(hs) >= _MULTI_MIN}
            for h in sorted(hop):
                ts = hop[h]
                if len(ts) == 1 and ts[0] in multi:
                    continue          # rendered in the head-merged row below
                shown = " | ".join(ts[:_TAIL_CAP])
                more = f" …(+{len(ts) - _TAIL_CAP})" if len(ts) > _TAIL_CAP else ""
                L.append(f"    {h} --{sh}--> {shown}{more}")
            for t in sorted(multi):
                hs = sorted(heads_of_t[t])
                shown = " | ".join(hs[:_HEAD_CAP])
                more = f" …(+{len(hs) - _HEAD_CAP})" if len(hs) > _HEAD_CAP else ""
                L.append(f"    {shown}{more} --{sh}--> {t}")
            # CVT attribute triples of mids THIS hop surfaced (pillar
            # 4a/4b) — values merged per (mid, key) like the direct rows
            _by_mid_key = {}
            for _hi, (mid, k, v) in pat.get("attrs", ()):
                if _hi == hi:
                    _by_mid_key.setdefault((mid, k), []).append(v)
            for (mid, k) in sorted(_by_mid_key):
                vs = sorted(set(_by_mid_key[(mid, k)]))
                shown = " | ".join(vs[:_VAL_CAP])
                more = f" …(+{len(vs) - _VAL_CAP})" if len(vs) > _VAL_CAP else ""
                L.append(f"    {mid} --{k}--> {shown}{more}")
    if store["env_triples"]:
        L.append("▸ other walked relations (environment):")
        for h, r, t in store["env_triples"][:_ENV_CAP]:
            L.append(f"    {h} --{r}--> {t}")
    L.append(_NOTE)
    return "\n".join(L)
