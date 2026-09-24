"""ROW LAYER — entity-block primary with inline CVT brackets (user ruling
2026-09-16): entities are the primary grouping unit; pattern paths render
as an index line only. Within each entity block:
  * outgoing edges: tail-merged
  * incoming edges: head-merged (many→one)
  * CVT connections: INLINE brackets — m.xxx [key: value; key: value]
  * cross-block dedup: each (h, rel, t) edge appears exactly once
Two rules (user): ① related attributes together, ② no duplicate rendering.
"""
from collections import defaultdict

# NOTE CONSOLIDATED (user request 2026-09-20): the two per-message notes
# (block-formatting + triple-grammar) merged into ONE compact note emitted
# by seq_tools' result assembly; this renderer no longer appends its own.
_NOTE = ""

_TAIL_CAP = 40
_HEAD_CAP = 12
_VAL_CAP = 6
_GROUP_CAP = 10
_MULTI_MIN = 3



def _is_value(n):
    s = str(n)
    if _cvt(s):
        return False
    return (len(s) <= 14 and any(c.isdigit() for c in s)
            and not any(c.isalpha() for c in s.replace("-", "").replace(":", "")))


def _short_rel(r):
    return str(r).rsplit(".", 1)[-1].lower()


def render_rows(store):
    # NO CENTER ECHO (user ruling 2026-09-23, correction): the call command
    # already carries the centers — repeating them (or the frontier) in the
    # result is duplication, not a budget/truncation matter. Root/layer
    # context is carried by anchor_sequence + the SEQUENCE EXTENSION note.
    L = []

    # ── flatten + dedup all edges ──
    _seen_e = set()
    all_edges = []
    pattern_labels = []
    for pat in store["patterns"]:
        pattern_labels.append(pat["label"])
        for sh, hop in pat["hops"]:
            for h, ts in hop.items():
                for t in ts:
                    k = (str(h), _short_rel(sh), str(t))
                    if k not in _seen_e:
                        _seen_e.add(k)
                        all_edges.append((h, sh, t))
    for h, r, t in store.get("env_triples", ()):
        k = (str(h), _short_rel(r), str(t))
        if k not in _seen_e:
            _seen_e.add(k)
            all_edges.append((h, r, t))

    # CVT attrs (deduped)
    cvt_kv = defaultdict(lambda: defaultdict(set))
    _seen_a = set()
    for pat in store["patterns"]:
        for _hi, (mid, kk, v) in pat.get("attrs", ()):
            k2 = (mid, _short_rel(kk), v)
            if k2 not in _seen_a:
                _seen_a.add(k2)
                cvt_kv[mid][_short_rel(kk)].add(v)

    # pattern index (one line)
    if pattern_labels:
        L.append(f"▸ patterns: {' | '.join(pattern_labels)}")

    def _tail_str(t):
        if _cvt(t) and t in cvt_kv and cvt_kv[t]:
            pairs = []
            for k in sorted(cvt_kv[t]):
                vs = sorted(cvt_kv[t][k])
                pairs.append(f"{k}: {' | '.join(vs[:_VAL_CAP])}")
            return f"{t} [{'; '.join(pairs)}]"
        return str(t)

    # ── CVT owner: which entity connects to each CVT ──
    cvt_owner = {}
    for h, r, t in all_edges:
        if _cvt(t) and not _cvt(h) and not _is_value(h):
            cvt_owner.setdefault(t, h)
        elif _cvt(h) and not _cvt(t) and not _is_value(t):
            cvt_owner.setdefault(h, t)

    # DISCRIMINATOR VALUE LANE (audit ③ specimen 626, 2026-09-21): a
    # CVT --date/number--> value edge had NO render lane — ent_out/ent_in
    # require a non-CVT non-value endpoint on that side, and the context
    # tail dropped CVT heads, so walked dates/runtimes never reached the
    # screen (the model abstained "no date evidence" with the values in
    # the walk). Detected purely by VALUE SHAPE (_is_value) — never by the
    # model-declared answer type (user design). Rendered under the CVT's
    # owning entity block, merged per (cvt, relation).
    val_by_mid = defaultdict(lambda: defaultdict(list))
    for h, r, t in all_edges:
        if _cvt(h) and _is_value(t):
            val_by_mid[h][_short_rel(r)].append(t)

    # ── entity classification ──
    centers = set(store.get("centers", []))
    ent_out = defaultdict(list)
    ent_in = defaultdict(list)
    for h, r, t in all_edges:
        if not _cvt(h) and not _is_value(h):
            ent_out[h].append((h, r, t))
        if not _cvt(t) and not _is_value(t):
            ent_in[t].append((h, r, t))

    # block candidates: anchor + entities with CVT connections or high degree
    # CVT PARTNERS COUNT TOO (audit ③ specimen 241): the named ENDPOINT of
    # a CVT edge carries CVT-mediated evidence — without it, degree-1
    # environment entities (French arrondissement…) alphabetically starved
    # Monaco/Germany out of the 10-block budget while their edges existed.
    cvt_connected = set(cvt_owner.values())
    cvt_connected |= {t for h, r, t in all_edges
                      if _cvt(h) and not _cvt(t) and not _is_value(t)}
    all_ents = set(ent_out) | set(ent_in)
    scored = sorted(
        all_ents,
        key=lambda e: (
            0 if e in centers else 1,
            0 if e in cvt_connected else 1,
            -(len(ent_out.get(e, ())) + len(ent_in.get(e, ()))),
            e))
    block_ents = scored[:_GROUP_CAP]

    # ── render blocks with cross-block dedup ──
    rendered_edges = set()
    for ent in block_ents:
        out_e = ent_out.get(ent, [])
        in_e = ent_in.get(ent, [])
        has_new = any((str(h), _short_rel(r), str(t)) not in rendered_edges
                      for h, r, t in out_e + in_e)
        if not has_new:
            continue    # all edges already shown in earlier blocks — skip
        L.append(f"── {ent} ──")
        # outgoing: tail-merge
        by_hr = defaultdict(lambda: [None, []])
        for h, r, t in out_e:
            k = (str(h), _short_rel(r), str(t))
            if k in rendered_edges:
                continue
            rendered_edges.add(k)
            sk = (h, _short_rel(r))
            by_hr[sk][0] = r
            by_hr[sk][1].append(t)
        for (h, _), (r, ts) in sorted(by_hr.items()):
            rendered = [_tail_str(t) for t in ts[:_TAIL_CAP]]
            shown_s = " | ".join(rendered)
            more = (f" …(+{len(ts) - _TAIL_CAP})" if len(ts) > _TAIL_CAP else "")
            if more:
                more += (f" (to answer with ALL of them, include "
                         f"\"#{h}::{_short_rel(r)}\" as one answer entity)")
            L.append(f"    --{r}--> {shown_s}{more}")
        # incoming: skip shown, head-merge many→one
        by_rt = defaultdict(list)
        for h, r, t in in_e:
            k = (str(h), _short_rel(r), str(t))
            if k in rendered_edges:
                continue
            rendered_edges.add(k)
            by_rt[(_short_rel(r), t)].append((h, r))
        for (_, t), hrs in sorted(by_rt.items()):
            if len(hrs) >= _MULTI_MIN:
                # CVT heads carry their attrs bracket too (audit 2026-09-24,
                # Eleanor-1392 specimen): the incoming lane rendered bare
                # mids while the outgoing lane (_tail_str) bracketed them —
                # a CVT at a chain's SOURCE side (m.xxx --student--> person)
                # lost its institution/degree attributes entirely.
                hs_u = sorted(set(h for h, _ in hrs))
                shown_h = " | ".join(_tail_str(h) for h in hs_u[:_HEAD_CAP])
                more = (f" …(+{len(hs_u) - _HEAD_CAP})" if len(hs_u) > _HEAD_CAP else "")
                # ANSWER-EXPANSION ESCAPE (user audit 2026-09-19): the legacy
                # +N-more lines advertise the "#name::rel" completion; this
                # rows-renderer cap did not — a capped list with no pointer
                # to the mechanism that answers with ALL of them.
                if more:
                    more += (f" (to answer with ALL of them, include "
                             f"\"#{hs_u[0]}::{_short_rel(hrs[0][1])}\" "
                             f"as one answer entity)")
                L.append(f"    {shown_h}{more} --{hrs[0][1]}--> {t}")
            else:
                for h, r in sorted(hrs):
                    L.append(f"    {_tail_str(h)} --{r}--> {t}")
        # discriminator value rows for this block's owned CVTs
        for mid, ent2 in sorted(cvt_owner.items(), key=lambda kv: str(kv[0])):
            if ent2 != ent or mid not in val_by_mid:
                continue
            for sr, vs in sorted(val_by_mid[mid].items()):
                fresh = [v for v in vs
                         if (str(mid), sr, str(v)) not in rendered_edges]
                if not fresh:
                    continue
                for v in fresh:
                    rendered_edges.add((str(mid), sr, str(v)))
                shown_v = " | ".join(str(v) for v in sorted(set(fresh))[:_VAL_CAP])
                L.append(f"    {mid} --{sr}--> {shown_v}")

    # context tail: remaining unshown edges. CVT-HEADED edges with a named
    # endpoint are ADMITTED (audit ③ specimen 241): Monaco's only edge was
    # CVT-headed and had no lane anywhere; the non-CVT endpoint is a real
    # walked entity, so the edge is evidence, not noise.
    # CVT-TAILED edges whose CVT carries WALKED ATTRS are admitted too
    # (user ruling 2026-09-24, 1812 specimen): a pure-literal terminal CVT
    # (Barbados --size_of_armed_forces--> g.xxx [number: 610]) is a legal
    # VALUE-ANSWER shape. When its owner missed the block budget (root-
    # collapsed off the center list; 21 centers filled all 10 blocks), the
    # old `not _cvt(t)` left the submitted relation's terminal hop with NO
    # lane — patterns row promised it, no edge row ever showed it. Bare
    # mids without attrs stay excluded (a bare id is noise, not evidence).
    ctx = [(h, r, t) for h, r, t in all_edges
           if (str(h), _short_rel(r), str(t)) not in rendered_edges
           and (not _cvt(t) or (t in cvt_kv and cvt_kv[t]))
           and not _is_value(t)]
    if ctx:
        _ctx_by = defaultdict(list)
        for h, r, t in ctx[:_GROUP_CAP * 3]:
            _ctx_by[(h, _short_rel(r))].append((r, t))
        for (h, _), rts in sorted(_ctx_by.items()):
            r0 = rts[0][0]
            ts_u = sorted(set(t for _, t in rts))
            # _tail_str: the admitted CVT tails carry their attr bracket
            # inline ([number: 610]) — the value-answer's display form
            shown = " | ".join(_tail_str(t) for t in ts_u[:_TAIL_CAP])
            L.append(f"    {_tail_str(h)} --{r0}--> {shown}")
    # ownerless CVT discriminator values (no named owner block to ride on)
    for mid, srs in sorted(val_by_mid.items()):
        if mid in cvt_owner:
            continue
        for sr, vs in sorted(srs.items()):
            fresh = [v for v in vs
                     if (str(mid), sr, str(v)) not in rendered_edges]
            if not fresh:
                continue
            for v in fresh:
                rendered_edges.add((str(mid), sr, str(v)))
            L.append(f"    {mid} --{sr}--> "
                     f"{' | '.join(str(v) for v in sorted(set(fresh))[:_VAL_CAP])}")

    if _NOTE:
        L.append(_NOTE)
    return "\n".join(L)
