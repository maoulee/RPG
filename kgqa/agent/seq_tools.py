"""SEQ dispatch — iterative subgraph retrieval (two tools) + decompose + answer.

Per declared fact the model runs:
  retrieve_relations(entity, question)  → GTE candidate relations around the entity
  retrieve_subgraph(entity, relations)  → walk + CVT penetration → DENSE tree

CRITICAL: retrieve_subgraph REUSES the proven SAPS walk (stage_5_graph_traversal:
multi-hop, K-path, CVT-penetrating, relation-centric subgraph) — NOT a 1-hop walk.
Scoped to ONE step from the current center. SAPS files stay untouched.

Boundaries enforced here (need ctx):
  - center entity must be in the accumulated subgraph (or the anchor for fact 1).
  - answer entities must be in the accumulated candidates (reused SAPS _do_answer).
"""
from __future__ import annotations

import re
from typing import Any, Dict

from kgqa.core.utils import normalize
from kgqa.traversal.cvt import is_cvt_like
from kgqa.agent.tools import (
    _json_result, _gte_for_triple, _reach2_relids, _do_answer, _cvt_attr_summary,
    _constraint_attr_summary, _GTE_POOL_MIN,
)
from kgqa.core.case_state import CaseState
from kgqa.stages.stage5_traverse import stage_5_graph_traversal
from kgqa.traversal.path_utils import compress_paths
from kgqa.traversal.logical_paths import materialize_selected_logical_patterns
from kgqa.stages.formatting import build_pattern_evidence_triples


# ───────────────────────── helpers ─────────────────────────

def _name_to_idx(name: str, ctx) -> int | None:
    """Map entity name → graph idx. Robust to typos (fuzzy) + diacritics (accent-insensitive)."""
    import difflib, unicodedata
    n = normalize(str(name))
    if not n:
        return None
    norms = [normalize(e) for e in ctx.ents]
    # 1. exact
    for i, en in enumerate(norms):
        if en == n:
            return i
    # 2. substring (both directions) — skip empty norms (Hebrew/CJK normalize to "" →
    # "" in anything = True, which resolves to the wrong entity)
    if len(n) >= 3:
        for i, en in enumerate(norms):
            if en and len(en) >= 2 and (n in en or en in n):
                return i
    # 3. accent-insensitive — strip accents on RAW entity text BEFORE normalize
    #    (normalize corrupts Vietnamese diacritics into spaces; must strip first)
    def _strip_accents(text):
        return ''.join(c for c in unicodedata.normalize('NFKD', text)
                       if not unicodedata.combining(c))
    n_na = _strip_accents(n)
    for i, e in enumerate(ctx.ents):
        if normalize(_strip_accents(e)) == n_na:
            return i
    # 4. fuzzy typo tolerance (Larr Baer → Larry Baer)
    close = difflib.get_close_matches(n, norms, n=1, cutoff=0.85)
    if close:
        return norms.index(close[0])
    return None


def _match_sim(a, b) -> float:
    """Name-similarity ratio (0–1) between an input and a matched entity, to tell a
    confident match from a substring-FRAGMENT match. _name_to_idx's substring step
    matches 'museum' inside 'harvard museum of modern colors' (a fragment → wrong
    entity), which a None-check alone misses. difflib fuzzy in _name_to_idx already
    gates at 0.85, so a real fuzzy/typo match scores ≥0.85; a fragment scores far
    below — 0.80 separates them."""
    import difflib
    return difflib.SequenceMatcher(None, normalize(str(a)), normalize(str(b))).ratio()


def _split_pipe_entities(entities) -> list:
    """Defensively split a '|'-joined center into its intended multiple entities.

    The model sometimes copies the DISPLAY format ('A | B | C') as ONE center string
    (e.g. inside a JSON-array element), and the parser keeps it as one entity name →
    a wrong, unwieldy center. Split on ' | ' (the display separator, which entity
    names essentially never contain) to recover the intended list. System-layer fix:
    recovers the intent silently rather than erroring or nudging (no burned turn)."""
    out = []
    for e in entities:
        e = str(e)
        if " | " in e:
            out.extend([x.strip() for x in e.split(" | ") if x.strip()])
        else:
            out.append(e)
    return out


def _looks_like_value(name) -> bool:
    """True if the input is a literal VALUE (numeric/coordinate/raw date/UTC offset),
    not a named entity. Value-like strings resolve UNRELIABLY via fuzzy/substring —
    'UTC-05:00' fuzzy-matches 'UTC−04:00' (a DIFFERENT timezone, high string-sim but
    wrong entity) — so callers require EXACT match for value-like centers (see the
    resolve loops). Named entities ('2014 World Series', 'Boeing 747') are NOT mostly
    digits and pass through normal resolution."""
    s = str(name).strip().strip("'\"")
    if len(s) < 2:
        return False
    digits = sum(c.isdigit() for c in s)
    if digits >= max(2, len(s) * 0.5):
        return True                          # coordinates, numbers, ISO dates
    # UTC/GMT offsets: 'UTC-05:00', 'UTC+12', 'GMT-5', 'UTC−04:00' (U+2212 minus)
    if re.search(r'\b(UTC|GMT)\s*[+\-−]\s*\d', s, re.IGNORECASE):
        return True
    return False


async def _entity_correction(name, question, ctx, session, top_k_candidates: int = 5,
                             top_k_rels: int = 3):
    """Entity-name CORRECTION (model-in-the-loop, not auto-resolve).

    When an input entity name isn't in the graph (_name_to_idx fails), GTE-find
    candidate entities by NAME similarity, and for each candidate show its TOP-K
    question-relevant NEIGHBOR relations (GTE: original question vs the candidate's
    1-hop relations). The model reads the neighbor relations to disambiguate (a
    battle has commander/participants; a city has population/area) and re-calls with
    the right entity. Name-match alone is unreliable (several high-similarity
    candidates), so the relations are the disambiguation signal — but the MODEL
    decides, the system only informs.

    Only for the initial named entity (literal center), NOT for ?var bindings.
    Returns a list of {name, neighbor_relations} candidates, or None if no
    session / no named entities / GTE fails (caller falls back to a plain error)."""
    from kgqa.stages.stage2_entity import gte_retrieve
    if session is None or not str(name).strip():
        return None
    # named entities only (skip CVT m-ids + short/empty norms that match anything)
    named = [(i, e) for i, e in enumerate(ctx.ents)
             if e and not is_cvt_like(e) and len(normalize(e)) >= 3]
    if not named:
        return None
    idxs = [i for i, _ in named]
    names = [e for _, e in named]
    name2idx = {e: i for i, e in zip(idxs, names)}   # name → graph idx (first occurrence)
    # 1. GTE candidate entities by name similarity to the (wrong) input.
    #    gte_retrieve returns rows with 'candidate' (the matched name) + 'score'.
    try:
        rows = await gte_retrieve(session, str(name), names,
                                  candidate_texts=names, top_k=top_k_candidates)
    except Exception:
        return None
    out = []
    for row in rows:
        ename = row.get("candidate")
        if not ename:
            continue
        eidx = name2idx.get(ename)
        if eidx is None:
            continue
        # 2. this candidate's 1-hop NEIGHBOR relations
        rels_1hop = set()
        for k in range(len(ctx.h_ids)):
            if (ctx.h_ids[k] == eidx or ctx.t_ids[k] == eidx) and 0 <= ctx.r_ids[k] < len(ctx.rels):
                rels_1hop.add(ctx.r_ids[k])
        if not rels_1hop:
            continue
        rel_names = sorted(rels_1hop, key=lambda r: ctx.rels[r])
        # 3. top-K question-relevant NEIGHBOR relations — reuse the proven _gte_for_triple
        #    (raw relation names embed poorly; _gte_for_triple labels them as
        #    'head | rel | ?' triples, which GTE ranks correctly).
        try:
            ranked = await _gte_for_triple(ctx, session, ename, question or str(name),
                                           "", pool_relids=rels_1hop)
            top_rels = [ctx.rels[r] for r in ranked[:top_k_rels] if 0 <= r < len(ctx.rels)]
        except Exception:
            top_rels = [ctx.rels[r] for r in rel_names[:top_k_rels]]
        if top_rels:
            out.append({"name": ename, "neighbor_relations": top_rels[:top_k_rels]})
        if len(out) >= top_k_candidates:
            break
    return out if out else None


def _expand_entities(entities, ctx):
    """Expand any ?variable in an entity-name list to its declared bindings
    (ctx.var_bindings, populated from the model's checkpoints). Literal named
    entities (no `?` prefix) pass through. Returns (names, error). An unresolved
    ?var yields an error nudge telling the model to declare it first. De-dups
    preserving order."""
    vb = getattr(ctx, "var_bindings", {}) or {}
    out = []
    for e in entities:
        e = str(e)
        if e.startswith("?"):
            bound = vb.get(e)
            if not bound:
                return [], (
                    f"variable {e} has no declared bindings. After the "
                    f"retrieve_subgraph that resolves it, declare its values in a "
                    f"checkpoint line `[<fact_id> ✓] {e} = [value1 | value2 | ...]`, "
                    f"then reference {e}.")
            out.extend(bound)
        else:
            out.append(e)
    seen, dedup = set(), []
    for e in out:
        if e not in seen:
            seen.add(e); dedup.append(e)
    return dedup, None


def _variable_nudge(raw_entities, ctx) -> str:
    """If the model passed a LITERAL entity that is one of several bindings of a
    declared ?variable, it picked one representative from a multi-candidate set.
    Nudge it to pass the variable instead so all candidates are carried forward
    (the 832 pipe-string / pick-one failure). Returns the nudge text, or '' ."""
    vb = getattr(ctx, "var_bindings", {}) or {}
    literals = [str(e) for e in (raw_entities or []) if not str(e).startswith("?")]
    if not literals or not vb:
        return ""
    for var, bindings in vb.items():
        bound = [str(b) for b in (bindings or [])]
        if len(bound) <= 1:
            continue
        picked = [e for e in literals if e in bound]
        if picked:
            return (f"⚠ You passed a literal entity ({picked[0]}) but {var} has "
                    f"{len(bound)} declared candidates {bound[:6]}. You picked one from "
                    f"several — pass {var} (\"{var}\") instead so the retrieval carries "
                    f"every candidate. Only use a literal if evidence already narrowed "
                    f"{var} to one.")
    return ""


def _cvt_repipe(name: str) -> str:
    """Repipe a CVT inline-attr node display from comma- to |-separated.
    'm.02xgww5: [actor=X, character=Y]' → 'm.02xgww5: [actor=X | character=Y]'.
    Commas collide with entity names that contain commas (e.g. 'St. John's,
    Montgomery, Alabama'); '|' never appears in Freebase names. Non-CVT names
    (no ': [' marker) pass through unchanged."""
    if not isinstance(name, str) or ": [" not in name or not name.endswith("]"):
        return name
    prefix, attrs = name.split(": [", 1)
    attrs = attrs[:-1]
    parts = [a.strip() for a in attrs.split(",") if a.strip()]
    return f"{prefix}: [{' | '.join(parts)}]" if parts else f"{prefix}: []"


def _is_cvt_node(name) -> bool:
    return (isinstance(name, str)
            and (name.startswith("m.") or name.startswith("g.") or name.startswith("CVT:")))


# Inverse-relation table for display cycle-suppression. Freebase stores directed
# inverses as distinct names (no .inv twin); these are the directional pairs whose
# second traversal re-establishes the first (a containment/administrative loop), plus
# the symmetric (self-inverse) set. A node revisited via a DIFFERENT relation is NOT
# a cycle — only an edge that repeats or whose inverse was already established.
_INVERSE_PAIR = {
    "location.location.contains": "location.location.containedby",
    "location.location.containedby": "location.location.contains",
    "location.location.partially_contains": "location.location.partially_contains",  # treat as symmetric fallback
    "base.aareas.schema.administrative_area.administrative_children": "base.aareas.schema.administrative_area.administrative_parent",
    "base.aareas.schema.administrative_area.administrative_parent": "base.aareas.schema.administrative_area.administrative_children",
    "location.location.contains_major_portion_of": "location.location.containedby",
}
_INVERSE_SYM = {
    "location.location.adjoin_s",
    "location.adjoining_relationship.adjoins",
}


def _edge_inverse(h, r, t):
    """Return the inverse edge of (h,r,t) if r has a known inverse/symmetric twin,
    else None. Symmetric relations invert to (t, r, h); directional pairs to
    (t, r_partner, h)."""
    if r in _INVERSE_SYM:
        return (t, r, h)
    partner = _INVERSE_PAIR.get(r)
    if partner:
        return (t, partner, h)
    return None


def _chain_is_cyclic(nodes, rels, accumulated) -> bool:
    """Edge-level cycle test (node-revisit via a DIFFERENT relation is allowed — a
    node is not unvisitable). A chain is cyclic if any edge (h,r,t):
      - is itself, OR whose inverse is, in `accumulated` (the PRIOR calls' triples —
        subgraph N looping back onto an earlier subgraph's edge), OR
      - repeats, or whose inverse repeats, an edge earlier in the SAME chain.
    `accumulated` must be the snapshot from BEFORE the current call's _accumulate,
    so a call never suppresses its own freshly-retrieved edges. Keys on relation +
    both endpoints, never on a seen node alone — a forward critical path that reuses
    an entity via a new relation (e.g. airport.serves → containedby → Germany) is kept."""
    accumulated = accumulated or set()
    seen_in_path = set()
    for k in range(len(nodes) - 1):
        h, t = nodes[k], nodes[k + 1]
        r = rels[k] if k < len(rels) else ""
        fwd = (h, r, t)
        inv = _edge_inverse(h, r, t)
        if fwd in accumulated or fwd in seen_in_path:
            return True
        if inv is not None and (inv in accumulated or inv in seen_in_path):
            return True
        seen_in_path.add(fwd)
    return False


def _clean_cvt_node(name: str, head: str, rel: str) -> str:
    """Suppress the redundant back-edge attr from a CVT inline-attr display, then
    dedup identical attrs, re-emitting '|'-separated.

    A CVT reached FROM `head` via `rel` lists that same relation pointing back at
    `head` (e.g. 'Denmark --adjoins--> m.02wrxld [adjoins=Denmark | adjoins=Germany]'
    — `adjoins=Denmark` just restates the entity we walked from). That entry is
    dropped; only the new endpoint(s) remain. Safe because the rule is
    relation-aware: it only fires when the attr key == the traversed relation's
    short name AND the value == the predecessor. Forrest-Gump-style CVTs (reached
    via 'starring', attrs actor/character/character_note) match no key → nothing
    dropped. Non-CVT names pass through."""
    if not isinstance(name, str) or ": [" not in name or not name.endswith("]"):
        return _cvt_repipe(name)
    prefix, attrs = name.split(": [", 1)
    attrs = attrs[:-1]
    parts = [a.strip() for a in attrs.split(",") if a.strip()]
    rel_short = (rel.rsplit(".", 1)[-1] if rel else "").replace(".inv", "")
    seen, kept = set(), []
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            k_base = k.strip().replace(".inv", "")
            if rel_short and k_base == rel_short and v.strip() == head:
                continue                       # back-edge to the entity we came from
        if p not in seen:
            seen.add(p); kept.append(p)
    return f"{prefix}: [{' | '.join(kept)}]" if kept else f"{prefix}: []"


_REL_CHAIN_RE = re.compile(r'--\[([^\]]+)\]-->')


def _relation_chain(readable: str) -> str:
    """Extract the PURE relation chain from a PatternEvidence.readable, stripping
    the starting-entity prefix. 'Americas --[location.location.time_zones]--> node1
    [materialized paths=2]' -> 'location.location.time_zones'; a 2-hop readable ->
    'r1 → r2'. The same chain shared across centers thus groups under one header."""
    rels = _REL_CHAIN_RE.findall(readable or "")
    return " → ".join(rels) if rels else (readable or "")


def _pattern_template(readable: str) -> str:
    """The PATTERN header as a node-template path: 'node1 --r1--> node2 [--r2--> node3 …]'.
    Relations live ONLY in the header; the body is pure entity chains that fill the
    slots in order. Center-agnostic, so multi-center (variable) groups merge under it."""
    rels = _REL_CHAIN_RE.findall(readable or "")
    if not rels:
        return readable or ""
    s = "node1"
    for i, r in enumerate(rels):
        s += f" --{r}--> node{i + 2}"
    return s


def _format_pattern_body(pe, accumulated=None, max_tails: int = 60, max_chains: int = 4) -> list:
    """Body lines for ONE PatternEvidence (no header). Length-2 paths group by
    (head, relation) into 'head → t1 | t2 | t3' ('|' avoids comma-in-entity-name
    collisions). ≥3-hop paths render as explicit chains 'head --r1--> mid --r2-->
    leaf' — hops preserved: a named intermediate is a selectable center, so the
    next relation points forward and is NEVER collapsed to an inline '(attr)'.
    CVT m-id nodes inline their radiating entities (hub-style — they are entities).
    Capped to prevent prompt explosion on high-degree relations."""
    paths = (getattr(pe, "tree_data", None) or {}).get("paths") or []
    out = []
    short, chains = [], []           # length-2 paths / length-3+ chains
    for p in paths:
        nodes = p.get("nodes") or []
        rels = p.get("relations") or []
        if len(nodes) < 2:
            continue
        # edge-level cycle filter (RAW nodes/rels, before CVT display-cleaning): skip
        # chains that repeat/inverse a PRIOR-call edge (subgraph N→subgraph 1) or an
        # earlier edge in the same chain. `accumulated` is the snapshot from BEFORE this
        # call's _accumulate, so a call never suppresses its own freshly-retrieved edges.
        # A node revisit via a DIFFERENT relation is allowed — only edge cycles drop.
        if _chain_is_cyclic(nodes, rels, accumulated):
            continue
        # clean each CVT node's inline attrs against its predecessor (drop the
        # back-edge that restates the entity we just came from), then repipe to '|'.
        cleaned = []
        for pos, n in enumerate(nodes):
            if pos > 0 and _is_cvt_node(n):
                prev_rel = rels[pos - 1] if pos - 1 < len(rels) else ""
                cleaned.append(_clean_cvt_node(n, nodes[pos - 1], prev_rel))
            else:
                cleaned.append(_cvt_repipe(n))
        nodes = cleaned
        if len(nodes) == 2:
            short.append((nodes[0], rels[0] if rels else "", nodes[1]))
        else:
            rlen = min(len(rels), len(nodes) - 1)
            chains.append((list(nodes), list(rels[:rlen])))   # keep (nodes, rels) for cycle filter (Part 4)
    # 1-hop body: entity-only (relation lives in the header template); group by head.
    groups = {}
    for head, _rel, tail in short:
        groups.setdefault(head, []).append(tail)
    for head, tails in groups.items():
        if len(tails) > max_tails:
            tails = tails[:max_tails] + [f"... +{len(tails) - max_tails} more (see candidates)"]
        out.append(f"  {head} → {' | '.join(tails)}")
    # multi-hop body: entity-only chains ('n0 → n1 → n2'); dedup by entity sequence, cap.
    seen, kept, dropped = set(), 0, 0
    for cnodes, crels in chains:
        cstr = " → ".join(cnodes)
        if cstr in seen:
            continue
        seen.add(cstr)
        if kept < max_chains:
            out.append(f"  {cstr}"); kept += 1
        else:
            dropped += 1
    if dropped:
        out.append(f"  ... +{dropped} chain paths truncated (walk exploration; see candidates)")
    return out


def _short_rel(r: str) -> str:
    """Last path segment of a relation name (organization.organization.parent → parent)."""
    r = str(r)
    return r.rsplit(".", 1)[-1] if r else r


# Noisy relation short-names to drop from the rendered tree (bookkeeping / type / role
# noise that floods high-degree entities — "Politician --notable_types--> …", "Author
# --profession--> …"). Holds no answer signal.
_EDGE_NOISY_SHORT = {
    "type", "types", "instance", "instances", "notable_types", "notable_type",
    "profession", "webpage", "mid", "guid", "key", "keys", "permission",
    "article", "description", "alias", "name", "topic_equivalent_webpage",
    "is_reviewed", "image", "webpage_topic",
}


def _canonicalize_triples(triples, ctx) -> list:
    """Flip triples whose rendered direction is REVERSED vs the raw graph edge.

    The walk is undirected (DIRECTED_TRAVERSAL=0): an edge is traversed from
    whichever side the center sits on, and the recorded triple puts the CENTER
    first. That reverses relations which canonically point INTO the center — e.g.
    `sports.mascot.team` is mascot→team, but retrieved from the team center it
    renders as 'team --team--> mascot', the wrong way. The base model reads the
    arrow literally, so a reversed arrow misleads it. This flips direct (both
    named, non-CVT) triples back to the raw canonical (h→t) direction. CVT-
    mediated triples keep their traversal direction (the CVT is the raw source
    of its out-edges, so they are already canonical)."""
    raw = set(zip(ctx.h_ids, ctx.r_ids, ctx.t_ids))
    n2i = {normalize(e): i for i, e in enumerate(ctx.ents) if e}
    r2i = {}
    for i, r in enumerate(ctx.rels):
        r2i.setdefault(r, i)
    out = []
    for tr in triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            out.append(tr); continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if is_cvt_like(h) or is_cvt_like(t):
            out.append(tr); continue                       # CVT-mediated: keep
        hi, ri, ti = n2i.get(normalize(h)), r2i.get(r), n2i.get(normalize(t))
        if hi is None or ri is None or ti is None:
            out.append(tr); continue
        if (hi, ri, ti) in raw:
            out.append(tr)                                 # already canonical
        elif (ti, ri, hi) in raw:
            out.append((t, r, h))                          # reversed → flip
        else:
            out.append(tr)
    return out


def _resolve_cvt_edges(triples) -> list:
    """Flatten CVT-mediated 2-paths into named→named edges for display.

    A Freebase compound fact runs (named --r1--> CVT --r2--> named2); the CVT is a
    transparent mediator and r2 is the meaningful role edge. This collapses such
    2-paths to (named, r2, named2). Direct named→named edges are kept. CVT tails
    with no named head and pure CVT↔CVT edges are dropped (not answerable).

    Inverse / variant relations that surface the SAME entity pair via different
    relation names (film.film_subject.films vs film.film.subjects; people.person.
    sibling_s vs people.sibling_relationship.sibling) all collapse onto one named
    edge per entity pair after resolution — the root cause of the 4× pattern
    explosion. Returns [(head_name, rel_short, tail_name)] all named.
    """
    cvt_out = {}                       # cvt_name -> [(rel_short, named_tail)]
    direct = []
    for tr in triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if is_cvt_like(h) and not is_cvt_like(t):
            cvt_out.setdefault(h, []).append((_short_rel(r), t))
        elif not is_cvt_like(h) and not is_cvt_like(t):
            sr = _short_rel(r)
            if sr in _EDGE_NOISY_SHORT or normalize(h) == normalize(t):
                continue                   # drop bookkeeping noise + self-loops
            direct.append((h, sr, t))
    resolved = []
    seen = set()
    for h, r, t in direct:
        k = (normalize(h), r, normalize(t))
        if k not in seen:
            seen.add(k); resolved.append((h, r, t))
    for tr in triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if not is_cvt_like(h) and is_cvt_like(t):     # named → CVT: continue through it
            for r2, t2 in cvt_out.get(t, ()):
                if r2 == "has_no_value":
                    # incumbent signal: t2 names the ABSENT attr (e.g. "To") → render as
                    # 'holder --to--> (incumbent)', the discriminator for current/latest
                    # holder on exclusive relations. Carried as a triple so it survives
                    # without the separate discriminating_attrs view.
                    attr = str(t2).lower()
                    k = (normalize(h), attr, "(incumbent)")
                    if k not in seen:
                        seen.add(k); resolved.append((h, attr, "(incumbent)"))
                    continue
                if is_cvt_like(t2) or r2 in _EDGE_NOISY_SHORT:
                    continue
                if normalize(h) == normalize(t2):
                    continue                           # self-loop (e.g. sibling listing self)
                k = (normalize(h), r2, normalize(t2))
                if k not in seen:
                    seen.add(k); resolved.append((h, r2, t2))
    return resolved


def _merge_edges(edges, max_per_line: int = 8) -> list:
    """Merge resolved edges into compact list-form lines, BOTH directions:
      same (h, r) with differing t      → 'h --r--> t1 | t2 | ...'      (t-list)
      same (r, t-set) with differing h  → 'h1 | h2 | ... --r--> t1|t2'  (h-list)
    Grouping by (r, t-set) catches the multi-t case too: 8 siblings each pointing
    at the same parent-set collapse to '[Ted|Robert|…] --parents--> Joseph|Rose'.
    Entities joined by ' | '. Returns rendered strings (caller indents)."""
    by_hr = {}                          # (h, r) -> [t ...] (ordered, deduped)
    for h, r, t in edges:
        by_hr.setdefault((h, r), [])
        if t not in by_hr[(h, r)]:
            by_hr[(h, r)].append(t)
    # group the per-h t-lists by (r, t-set) so heads sharing the same tail-set merge
    groups = {}                         # (r, tuple(ts)) -> [ts_list, [h...]]
    for (h, r), ts in by_hr.items():
        key = (r, tuple(ts))
        if key not in groups:
            groups[key] = [ts, []]
        groups[key][1].append(h)
    out = []
    for (r, ts), (ts_list, hs) in groups.items():
        hs = list(dict.fromkeys(hs))
        # no per-line cap: leaf entities (tails, and merged heads) are shown in full —
        # truncating them (the old '+N more') lost answer candidates.
        out.append(f"{' | '.join(hs)} --{r}--> {' | '.join(ts_list)}")
    return out


def _shown_edge_key(h: str, r: str, t: str) -> tuple:
    return (normalize(h), r, normalize(t))


def _format_merged(collected, accumulated=None, max_tails: int = 60, max_chains: int = 4) -> list:
    """Cross-center merged display. `collected` = list of (center_name,
    PatternEvidence) across all centers of one retrieve_subgraph call. Group by
    PURE relation chain (anchor stripped) → ONE header per relation pattern; each
    center's body lines follow (every line starts with its own root, so the
    variable's bindings appear as the roots under the shared pattern). Hops
    preserved per center. `accumulated` = PRIOR calls' triples snapshot for
    edge-level cycle suppression (None disables cross-call suppression)."""
    if not collected:
        return []
    groups, order = {}, []
    for _center, pe in collected:
        rc = _relation_chain(getattr(pe, "readable", ""))
        if rc not in groups:
            groups[rc] = []; order.append(rc)
        groups[rc].append(pe)
    out = []
    for rc in order:
        out.append(f"PATTERN: {_pattern_template(groups[rc][0].readable)}")
        for pe in groups[rc]:
            out.extend(_format_pattern_body(pe, accumulated, max_tails, max_chains))
    return out


def _format_pattern(pe, accumulated=None, max_tails: int = 60, max_chains: int = 4) -> list:
    """Single-PatternEvidence display (header + body). Kept for unit tests; the
    production path uses _format_merged for cross-center grouping."""
    body = _format_pattern_body(pe, accumulated, max_tails, max_chains)
    if not body:
        return []
    return [f"PATTERN: {_pattern_template(getattr(pe, 'readable', ''))}"] + body


def _in_subgraph(idx: int, ctx) -> bool:
    return idx in getattr(ctx, "subgraph_entities", set())


def _accumulate(ctx, center_idx: int, pe) -> None:
    """Add every entity the model just saw (the center + all named entities in the
    dense tree, incl. CVT-attribute entities like jurisdiction/actor/note) to
    ctx.subgraph_entities, and named candidates to ctx.all_candidates."""
    se = getattr(ctx, "subgraph_entities", None)
    if se is None:
        se = set(); ctx.subgraph_entities = se
    se.add(center_idx)
    # accumulate edges (h_name, r_name, t_name) for cross-call display cycle-suppression
    at = getattr(ctx, "accumulated_triples", None)
    if at is None:
        at = set(); ctx.accumulated_triples = at
    for tr in (pe.triples or []):
        if len(tr) == 3:
            at.add((str(tr[0]), str(tr[1]), str(tr[2])))
    # MULTI-map: a name may normalize to several entity indices (text + non_text entity
    # lists merge duplicates — 'Catholicism' at idx 69 AND 2007). A single-valued dict
    # keeps only the LAST, but _name_to_idx returns the FIRST → the boundary check
    # (_in_subgraph) looks for the wrong idx and rejects a valid center. Add ALL matches.
    from collections import defaultdict
    n2i_all = defaultdict(list)
    for i, e in enumerate(ctx.ents):
        if e:
            n2i_all[normalize(e)].append(i)
    names = set(pe.candidates or [])
    for tr in (pe.triples or []):
        if len(tr) == 3:
            names.add(tr[0]); names.add(tr[2])
    seen_cand = {normalize(c) for c in getattr(ctx, "all_candidates", []) or []}
    for nm in names:
        if not nm:
            continue
        for idx in n2i_all.get(normalize(nm), ()):   # add ALL entities with this name
            se.add(idx)
        if not is_cvt_like(nm):          # only NAMED entities join the answer candidate pool
            nn = normalize(nm)
            if nn not in seen_cand:
                seen_cand.add(nn); ctx.all_candidates.append(nm)


def _collect_cvt_neighbors_to_pool(ctx) -> None:
    """Ensure ALL non-CVT entities connected to any CVT in the subgraph are in
    all_candidates. The dense tree (_cvt_attr_display) shows ALL of a CVT's edges,
    but pe.triples (_expand_endpoint_cvt) may miss some due to scoring/limits —
    so entities visible in the tree (like an olympic event name) can be absent from
    the answer pool, causing off-pool rejection of a correct answer. This scans the
    raw graph edges of every CVT in subgraph_entities and adds every named neighbor.
    Rule: if an entity appears in any retrieved tree, it's answerable."""
    se = getattr(ctx, "subgraph_entities", None)
    if not se:
        return
    cvt_idxs = {i for i in se if 0 <= i < len(ctx.ents) and is_cvt_like(ctx.ents[i])}
    if not cvt_idxs:
        return
    seen_cand = {normalize(c) for c in getattr(ctx, "all_candidates", []) or []}
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        other = None
        if h in cvt_idxs and 0 <= t < len(ctx.ents) and not is_cvt_like(ctx.ents[t]):
            other = t
        elif t in cvt_idxs and 0 <= h < len(ctx.ents) and not is_cvt_like(ctx.ents[h]):
            other = h
        if other is not None:
            nm = ctx.ents[other]
            nn = normalize(nm)
            if nn not in seen_cand:
                seen_cand.add(nn); ctx.all_candidates.append(nm)
            se.add(other)


def _seq_pool_relids(ctx, entity_set) -> set:
    """SEQ relation-candidate pool = SAPS 2-hop reach (`_reach2_relids`, untouched)
    PLUS one CVT-transparent hop: relations on entities reached THROUGH a CVT
    mediator (E -> CVT -> E2). The flat 2-hop pool stops at the CVT's own edges, so
    a relation sitting BEHIND a CVT bridge (e.g. an org's leadership CVT leads to a
    person whose `people.person.religion` is the answer) is never ranked by GTE.
    Extending one CVT-transparent hop surfaces it. Only affects what GTE can rank
    (the walk's bounds are unchanged)."""
    out = set(_reach2_relids(ctx, entity_set))
    ents = set(e for e in entity_set if e is not None and 0 <= e < len(ctx.ents))
    if not ents:
        return out
    # 1-hop neighbors, isolate the CVT mediators
    direct = set()
    for h, t in zip(ctx.h_ids, ctx.t_ids):
        if h in ents and 0 <= t < len(ctx.ents):
            direct.add(t)
        if t in ents and 0 <= h < len(ctx.ents):
            direct.add(h)
    cvts = {n for n in direct if is_cvt_like(ctx.ents[n])}
    if not cvts:
        return out
    # entities lying behind each CVT (the CVT's other endpoints)
    behind = set()
    for cvt in cvts:
        for h, t in zip(ctx.h_ids, ctx.t_ids):
            if h == cvt and 0 <= t < len(ctx.ents) and t not in ents:
                behind.add(t)
            if t == cvt and 0 <= h < len(ctx.ents) and h not in ents:
                behind.add(h)
    # add relations on those behind-entities' edges (the CVT-transparent hop)
    for mid in behind:
        for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
            if h == mid or t == mid:
                out.add(r)
    from kgqa.traversal.path_utils import _is_noisy_path_relation
    out = {r for r in out if not _is_noisy_path_relation(ctx.rels[r])}
    return out


async def _run_walk_one_step(ctx, center_idx: int, rel_idxs, fid: str):
    """Reuse the proven SAPS walk (stage_5_graph_traversal: multi-hop, K-path,
    CVT-penetrating) scoped to ONE step from center_idx along rel_idxs. Mirrors
    _do_select's cs setup + walk + evidence build (tools.py:1280-1337), but for a
    single step whose anchor is the current center. Returns dict[label -> PatternEvidence]
    (each carries .triples + .candidates + .tree_data for the dense CVT-inline tree)."""
    cs = CaseState(case_id=ctx.case_id or "seq", case_num=ctx.case_num or 0,
                   sample=ctx.sample, pilot_row=ctx.pilot_row)
    cs.anchor_idx = center_idx
    cs.anchor_name = ctx.ents[center_idx] if 0 <= center_idx < len(ctx.ents) else ""
    cs.h_ids, cs.r_ids, cs.t_ids = ctx.h_ids, ctx.r_ids, ctx.t_ids
    cs.ents, cs.rels, cs.rel_texts = ctx.ents, ctx.rels, ctx.rel_texts
    cs.step_relations = [set(rel_idxs)]            # ONE step
    cs.steps = [{"id": fid or "f"}]
    cs.breakpoints = {}
    cs.active = True
    try:
        await stage_5_graph_traversal([cs])
    except Exception:
        return {}
    paths = cs.paths or []
    patterns = (compress_paths(paths, ctx.ents, ctx.rels, center_idx, set())
                if paths else (cs.logical_paths or []))
    valid = [lp for lp in patterns if isinstance(lp, dict) and lp.get("best_raw_path")]
    valid = materialize_selected_logical_patterns(
        valid, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids, center_idx, set())
    if not valid:
        return {}
    return build_pattern_evidence_triples(
        valid, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids, center_idx, max_grouped_lines=120)


# ───────────────────────── decompose (declare + seed anchor; no grounding) ─────────────────────────

async def _do_seq_decompose(args: Dict[str, Any], ctx, session) -> str:
    """SEQ decompose: declare the fact sequence + step-1 anchor. Does NOT ground — each
    fact is grounded by the model's own retrieve_relations call. Seeds ctx.subgraph_entities
    with the anchor so fact-1's center passes the boundary."""
    entities = args.get("entities") or []
    if isinstance(entities, str):
        entities = [a.strip() for a in entities.split(",") if a.strip()]
    if entities and not ctx.anchor_name:
        ctx.anchor_name = entities[0]
    # seed ALL declared entities (not just the anchor) — multi-entity questions have
    # several valid starting centers (e.g. "X and Y" → both X and Y are seedable starts).
    seed = set()
    if getattr(ctx, "anchor_idx", None) is not None:
        seed.add(ctx.anchor_idx)
    for name in entities:
        i = _name_to_idx(name, ctx)
        if i is not None:
            seed.add(i)
    ctx.subgraph_entities = seed
    flow = []
    for fid in ctx.fact_ids:
        txt = ctx.fact_texts.get(fid, "")
        inner = txt.strip().strip("()")
        parts = [p.strip() for p in inner.split("|")] if inner else []
        flow.append({"id": fid, "triple": txt,
                     "subquestion": parts[1] if len(parts) >= 2 else (txt or ctx.question)})
    return _json_result({
        "flow": flow, "entities": entities, "answer": args.get("answer", ""),
        "note": ("Iterative subgraph retrieval. For EACH fact in order: call "
                 "retrieve_relations, pick the structural bridge relation(s), then "
                 "retrieve_subgraph to get the dense subgraph tree. After each "
                 "retrieve_subgraph, declare the resolved variable's bindings "
                 "(`[fid ✓] ?var = [v1 | v2 | ...]`). For every fact after the first, pass "
                 "the VARIABLE (`entities: [\"?var\"]`) to BOTH tools — the runtime expands "
                 "it to all declared bindings; never narrow to one representative. Pick the "
                 "next center FROM the tree. The system auto-penetrates CVTs — their radiating "
                 "entities are themselves selectable centers, so never pick attribute relations "
                 "as bridges. Fact-1 center = the literal named anchor."),
    })


# ───────────────────────── retrieve_relations (GTE per entity+question) ─────────────────────────

async def retrieve_relations(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph relation retrieval: entities + question → candidate relations.
    Accepts a single entity or a LIST of entities. When multiple entities are passed,
    the GTE candidate pool is the UNION of all entities' 2-hop reachable relations —
    ensuring relations visible from ANY candidate are surfaced (not just the first)."""
    raw = args.get("center") or args.get("entities") or ([args.get("entity")] if args.get("entity") else [])
    entities = _split_pipe_entities([str(e) for e in raw if e])
    question = args.get("question") or args.get("subquestion") or ""
    if not entities:
        return _json_result({"error": "no entity provided."})
    entities, _err = _expand_entities(entities, ctx)
    if _err:
        return _json_result({"error": _err})
    _nudge = _variable_nudge(raw, ctx)
    # resolve all entities + boundary check. A value-like input ('-1.61', '747') is NOT
    # special-cased — it flows through _name_to_idx + correction like any name. If it
    # RESOLVES to an entity ('747' -> 'Boeing 747' via substring), use it as a normal
    # center; if it can't resolve AND correction has no candidates, SKIP it (don't break a
    # multi-center call). Only intercept when correction has real candidates.
    idxs, unresolved = [], []
    for e in entities:
        i = _name_to_idx(e, ctx)
        # value-like inputs (UTC offsets, numbers, dates): require a 100% string match.
        # Fuzzy/substring is UNRELIABLE for values — 'UTC-05:00' fuzzy-matches 'UTC−04:00'
        # (a different timezone) = the center/retrieval-inconsistency bug. A value-like
        # name that isn't an EXACT match goes to entity CORRECTION (candidates + NEIGHBOR
        # relations, model re-selects); if no candidates, skip it (never silently use the
        # wrong fuzzy match).
        if _looks_like_value(e) and (i is None or normalize(e) != normalize(ctx.ents[i])):
            cands = await _entity_correction(e, question, ctx, session)
            if cands:
                return _json_result({
                    "entity_error": f"'{e}' is a value-like name that isn't an exact graph entity.",
                    "candidates": cands,
                    "note": "Pick the correct entity from `candidates` (each shows NEIGHBOR "
                            "relations). A raw value (UTC offset / number) matches unreliably — "
                            "prefer the named entity or the ?variable. Re-call with the right one."})
            unresolved.append(e); continue
        # fire CORRECTION only on no-match OR a clear substring-FRAGMENT match (sim<0.5).
        # _name_to_idx matches 'museum' inside 'harvard museum of modern colors' (a fragment
        # → wrong entity). difflib-fuzzy in _name_to_idx gates at 0.85, so a real fuzzy/typo
        # match (≥0.85) and near-matches (plural etc.) pass through; only genuine fragments
        # fire the correction. (A higher threshold over-fires and disrupts good flows — base
        # model is unfamiliar with the correction nudge and burns a turn re-selecting.)
        if i is None or _match_sim(e, ctx.ents[i]) < 0.50:
            cands = await _entity_correction(e, question, ctx, session)
            if cands:
                return _json_result({
                    "entity_error": f"'{e}' is not a confident entity in the graph.",
                    "candidates": cands,
                    "note": "Pick the correct entity from `candidates` — each lists its "
                            "question-relevant NEIGHBOR relations (use them to tell e.g. a "
                            "battle from a city of the same name). Re-call with the right entity."})
            if i is None:
                unresolved.append(e)          # can't resolve, no candidates → skip, keep going
                continue
            # low-conf match but no correction candidates → fall through with the match
        if not _in_subgraph(i, ctx):
            return _json_result({"error": (f"'{e}' is not in any prior retrieve_subgraph result — "
                                           f"it was never retrieved. A center MUST be an entity that "
                                           f"appeared in a previous retrieve_subgraph's triples (or the "
                                           f"plan anchor for fact 1). If '{e}' is a candidate bound to "
                                           f"a variable, pass the ?VARIABLE (e.g. center: [\"?country\"]) "
                                           f"— the runtime expands it to all declared bindings; do NOT "
                                           f"pass one literal entity picked from several.")})
        idxs.append(i)
    if not idxs:
        return _json_result({"error": f"none of {entities} resolved to a graph entity "
                              f"(unresolved: {unresolved}). Pick named entities from a "
                              f"previous retrieve_subgraph tree."})
    # GTE per-entity (NOT a generic "these entities" head). A multi-entity call is a
    # variable expansion (?var → several bindings); each entity's relevant relations
    # differ. One generic-head call on the union pool loses the entity-specific ranking
    # signal — e.g. [San Francisco Giants, Crazy Crab] for "last win World Series"
    # dropped `sports.sports_team.championships` (ranked #1 for the Giants alone) out
    # of the top-15, surfacing only generic season/stats relations. So rank each
    # entity's OWN pool with its OWN name, then union (dedup, per-entity rank order).
    if len(idxs) == 1:
        pool = _seq_pool_relids(ctx, {idxs[0]})
        if len(pool) < _GTE_POOL_MIN:
            pool = set(range(len(ctx.rels)))
        cands = await _gte_for_triple(ctx, session, entities[0], question, "",
                                      pool_relids=pool)
    else:
        cands, seen = [], set()
        for ent, i in zip(entities, idxs):
            ent_pool = _seq_pool_relids(ctx, {i})
            if len(ent_pool) < _GTE_POOL_MIN:
                ent_pool = set(range(len(ctx.rels)))
            ranked = await _gte_for_triple(ctx, session, ent, question, "",
                                           pool_relids=ent_pool)
            for r in ranked:
                if r not in seen:
                    seen.add(r); cands.append(r)
    _note = ("Pick the structural BRIDGE relation(s) whose information advances this fact. "
             "Do NOT pick attribute relations (date/name/type/role) — the system reveals "
             "those automatically inside CVTs. "
             "For any fact after the first, pass the entity variable (?var) — intermediate "
             "facts have multiple candidate entities and the variable carries all of them; "
             "passing one literal entity means you chose one from several.")
    if _nudge:
        _note = _nudge + " " + _note
    return _json_result({
        "entities": entities, "question": question,
        "candidate_relations": [ctx.rels[i] for i in cands if 0 <= i < len(ctx.rels)],
        "note": _note,
    })


# ───────────────────────── retrieve_subgraph (mature multi-hop walk + dense tree) ─────────────────────────

async def retrieve_subgraph(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph retrieval for ONE fact: one shared relation set applied to one or more
    center entities (the fact's candidate centers, packed into a single call). For each
    center the proven SAPS walk runs (multi-hop, K-path, CVT-penetrating); results are
    merged — dense tree + a candidate_attrs summary grouped by candidate under the shared
    relation pattern, so the model can compare across candidates (e.g. latest/largest).
    Accumulates seen entities into the subgraph."""
    raw = args.get("center") or args.get("entities") or ([args.get("entity")] if args.get("entity") else [])
    entities = _split_pipe_entities([str(e) for e in raw if e])
    rel_names = args.get("relations") or []
    fid = str(args.get("sg") or args.get("fact_id") or args.get("step") or "")
    if not entities:
        return _json_result({"error": "no entities provided."})
    entities, _err = _expand_entities(entities, ctx)
    if _err:
        return _json_result({"error": _err})
    _nudge = _variable_nudge(raw, ctx)
    rel_idxs = [ctx.rels.index(r) for r in rel_names if isinstance(r, str) and r in ctx.rels]
    if not rel_idxs:
        return _json_result({"error": "no valid relations provided. Pick from the candidate_relations "
                                      "returned by retrieve_relations."})

    # resolve + boundary-check each center. value-like inputs require EXACT match (fuzzy
    # resolves unreliably: 'UTC-05:00' -> 'UTC−04:00'); skip entities not yet in the
    # subgraph (boundary); flag wrong/low-conf named entities → correction.
    centers, skipped = [], []
    bad_name = None                     # an entity whose NAME is wrong/low-conf → correct
    for e in entities:
        i = _name_to_idx(e, ctx)
        if _looks_like_value(e) and (i is None or normalize(e) != normalize(ctx.ents[i])):
            # value-like + non-exact: don't use the unreliable fuzzy match ('UTC-05:00'->
            # 'UTC−04:00'); route to entity CORRECTION (after loop) so the model re-selects.
            if bad_name is None:
                bad_name = e
            continue
        if i is None or _match_sim(e, ctx.ents[i]) < 0.50:
            if bad_name is None:
                bad_name = e            # no-match or substring-fragment match → correct
            if i is None:
                continue
            # low-conf match present but flagged → still try it as a center below if in-subgraph
        if i is not None and not _in_subgraph(i, ctx):
            skipped.append(e)           # in graph but not yet retrieved → boundary skip
        elif i is not None:
            centers.append((e, i))
    if bad_name is not None:
        # entity-name CORRECTION: wrong/low-conf name → offer GTE candidates + NEIGHBOR relations
        cands = await _entity_correction(bad_name, getattr(ctx, "question", ""), ctx, session)
        if cands:
            return _json_result({
                "entity_error": f"'{bad_name}' is not an entity in the graph.",
                "candidates": cands,
                "note": "Pick the correct entity from `candidates` — each lists its "
                        "NEIGHBOR relations (use them to disambiguate). Re-call with the right entity."})
    if not centers:
        return _json_result({"error": (f"none of {entities} appeared in a prior retrieve_subgraph. "
                                       f"A center MUST be an entity from a previous retrieve_subgraph's "
                                       f"triples (or the plan anchor for fact 1). If any of these is a "
                                       f"variable binding, pass the ?VARIABLE (center: [\"?var\"]) — the "
                                       f"runtime expands it to all declared bindings.")})

    # per-center walk; accumulate evidence inline, collect PatternEvidence for the
    # cross-center merged display (one block per relation pattern, all roots under it)
    # snapshot the PRIOR calls' triples BEFORE this call's _accumulate, so the cycle
    # filter suppresses cross-call loops (subgraph N→subgraph 1) but never this call's
    # own freshly-retrieved edges (which would empty the body — only headers would show).
    prior_triples = set(getattr(ctx, "accumulated_triples", set()) or set())
    candidates, all_triples = [], []
    collected = []   # (center_name, PatternEvidence)
    for e, i in centers:
        pe = await _run_walk_one_step(ctx, i, rel_idxs, fid)
        if not pe:
            continue
        for p in pe.values():
            collected.append((e, p))
            _accumulate(ctx, i, p)
            for tr in (p.triples or []):
                if len(tr) == 3:
                    all_triples.append(tr)
            for c in (p.candidates or []):
                if not is_cvt_like(c) and c not in candidates:
                    candidates.append(c)
    if not all_triples:
        return _json_result({"error": "the walk reached nothing for these relations. Try a different "
                                      "bridge relation (re-call retrieve_relations), or pick different "
                                      "centers from a previous subgraph tree.",
                             "entities": entities, "relations": rel_names})

    # ensure ALL tree-visible entities (incl CVT-attr entities pe.triples may miss) are answerable
    _collect_cvt_neighbors_to_pool(ctx)

    # ── relation-grouped tree (replaces pattern-based _format_merged) ──────────────
    # First flip any triples whose direction is reversed vs the raw graph (the undirected
    # walk records center-first, which reverses relations pointing INTO the center, e.g.
    # mascot.team rendered as 'team --team--> mascot'). Then resolve CVT-mediated edges
    # → named→named, deduped. Inverse / variant relations that surfaced the SAME entity
    # pair via N patterns collapse to ONE edge per entity pair here.
    all_triples = _canonicalize_triples(all_triples, ctx)
    resolved = _resolve_cvt_edges(all_triples)
    # Cross-subgraph dedup: edges already shown in a PRIOR retrieve_subgraph are not
    # re-displayed (sg2 does not repeat sg1's content). Tracked as resolved (entity-pair)
    # keys so semantic duplicates with different relation names are also caught — unlike
    # the old chain-level filter which only knew the few pairs in _INVERSE_PAIR.
    shown = getattr(ctx, "shown_edges", None)
    if shown is None:
        shown = set(); ctx.shown_edges = shown
    new_edges = [(h, r, t) for (h, r, t) in resolved if _shown_edge_key(h, r, t) not in shown]
    n_overlap = len(resolved) - len(new_edges)
    for h, r, t in new_edges:
        shown.add(_shown_edge_key(h, r, t))
    # merge: same (h,r) with differing t → 'h --r--> t1 | t2 | ...'; same (r,t) with
    # differing h → 'h1 | h2 | ... --r--> t'. Either direction, whichever collapses more.
    tree_lines = [f"  {ln}" for ln in _merge_edges(new_edges)]
    if not tree_lines and n_overlap:
        tree_lines = [f"  (all {n_overlap} edges already shown in a prior subgraph — nothing new)"]
    # Generous line budget: leaf entities (answer candidates) must NOT be truncated
    # away. CVT-resolution + inverse-collapse + cross-subgraph dedup already compress
    # the edge set heavily, so this only bites on pathological high-degree centers.
    _TREE_LINE_BUDGET = 200
    if len(tree_lines) > _TREE_LINE_BUDGET:
        dropped = len(tree_lines) - _TREE_LINE_BUDGET
        tree_lines = tree_lines[:_TREE_LINE_BUDGET]
        tree_lines.append(f"  ... +{dropped} lines truncated (see candidates)")

    # The merged triples above ARE the evidence view — discriminator attrs (dates,
    # incumbent) live on their own edges ('Robert --to--> 1968', 'Ted --to-->
    # (incumbent)'), so the model compares candidates directly from the triples.
    # candidate_attrs / discriminating_attrs are intentionally NOT displayed: they
    # re-stated the same triples (tree/attrs overlap) and the present-vs-ABSENT flood
    # over-loaded the prompt. Builders kept (not discarded) for offline scoring.
    multi = len(centers) > 1
    return _json_result({
        "fact_id": fid,
        "entities": [e for e, _ in centers],
        "triples": "\n".join(tree_lines) if tree_lines else "(empty)",
        "candidates": [c for c in candidates if not is_cvt_like(c)][:60],
        "n_candidates": len(candidates),
        "skipped_centers": skipped,
        "note": ((_nudge + " ") if _nudge else "") +
                (("Multiple centers retrieved with one shared relation set — COMPARE them via "
                  "the triples (an edge '--to--> (incumbent)' marks the current holder). ") if multi else "") +
                 ("triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or "
                  "'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. "
                  "Discriminator attributes (dates, incumbent) appear as their own edges — read "
                  "them to pick latest/largest/incumbent. Edges already shown in a PRIOR subgraph "
                  "are NOT repeated. Pick the next center FROM these triples."),
    })


# ───────────────────────── SEQ dispatch ─────────────────────────

async def dispatch(tool_name: str, args: Dict[str, Any], ctx, session) -> str:
    # accept both new SEQ names and old names (backward-compat for stale trajectories)
    if tool_name in ("plan", "decompose"):
        return await _do_seq_decompose(args, ctx, session)
    if tool_name == "retrieve_relations":
        return await retrieve_relations(args, ctx, session)
    if tool_name == "retrieve_subgraph":
        return await retrieve_subgraph(args, ctx, session)
    if tool_name == "answer":
        return _do_answer(args, ctx)
    return _json_result({"error": f"unknown tool: {tool_name}"})
