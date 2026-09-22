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

import os
import re
from typing import Any, Dict

from kgqa.core.utils import normalize
from kgqa.traversal.cvt import is_cvt_like
# attribute-key → answer-type class (display roster alignment, 2026-09-08;
# unknown keys map to "?" = keep — never hide a potential answer)
_ATTR_TYPE_CLASSES = {
    "character": "person", "actor": "person", "person": "person",
    "military_person": "person", "leader": "person", "member": "person",
    "office_holder": "person", "presenter": "person", "director": "person",
    "portrayed_in_films": "person", "employee": "person", "winner": "person",
    "founders": "person", "member": "person", "leader": "person",
    "starring": "film", "members": "organization",
    "film": "film", "movie": "film",
    "language": "language",
    "location": "location", "place": "location",
    "organization": "organization", "employer": "organization",
    "school": "organization",
}
from kgqa.agent.tools import (
    _gte_for_triple, _reach2_relids, _do_answer, _cvt_attr_summary,
    _constraint_attr_summary, _GTE_POOL_MIN,
)
from kgqa.core.case_state import CaseState
from kgqa.stages.stage5_traverse import stage_5_graph_traversal
from kgqa.traversal.path_utils import compress_paths
from kgqa.traversal.logical_paths import materialize_selected_logical_patterns
from kgqa.stages.formatting import build_pattern_evidence_triples

# perf-attribution lanes (values live in core.utils.PHASE_TIMES; registered
# here so utils stays untouched): walk_wait/walk_exec = the affine worker's
# submit→pickup / pickup→done split (perf_counter is CLOCK_MONOTONIC on Linux
# → cross-process comparable), walk_collect = the round-level coordinator's
# batch window (arrival→flush), gte_n = gte_retrieve call count.
from kgqa.core.utils import PHASE_TIMES as _PHASE_TIMES
for _k in ("walk_wait", "walk_exec", "walk_collect", "gte_n"):
    _PHASE_TIMES.setdefault(_k, 0.0)
del _k


# ───────────────────────── helpers ─────────────────────────

def _json_result(payload: Any) -> str:
    """SEQ tool-result renderer: readable key:value text (NOT JSON).
    Overrides tools._json_result so SEQ results read naturally for the model; SAPS
    keeps its own JSON renderer untouched. Skips empty/zero fields; lists → 'a | b';
    multi-line strings (e.g. triples) get their own indented block."""
    if not isinstance(payload, dict):
        return str(payload)
    lines = []
    for k, v in payload.items():
        if v is None or v == "" or v == [] or v == 0:
            continue
        if isinstance(v, list):
            lines.append(f"{k}: {' | '.join(str(x) for x in v)}")
        elif isinstance(v, str) and "\n" in v:
            lines.append(f"{k}:")
            lines.append(v.rstrip())
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) if lines else "(empty)"


def _name_to_idx(name: str, ctx) -> int | None:
    """Map entity name → graph idx. Robust layered resolution:
    1. RAW exact (name == e) — strongest; excludes prefix-noise entities (:Caribbean) that
       normalize-collide with the clean name but are isolated pool=0 nodes. Without this,
       normalize(':Caribbean')=='caribbean'==normalize('Caribbean') and the first collision
       wins → retrieve_relations gets a pool=0 entity → fallback all-rels → GTE returns
       unreachable candidates → walk reaches nothing (idx88 root cause).
    2. normalize exact + COLLISION resolution — when several entities normalize to one key,
       prefer raw==name, else the SHORTEST raw (prefix-noise ':X' is longer than 'X').
    3. accent-insensitive (Vietnamese diacritics — normalize corrupts them, strip first).
    4. substring containment + similarity gate (≥0.85) — variant containment
       ('United States' ⊂ 'United States of America'), gated so a fragment like 'museum'
       ⊂ 'harvard museum' (ratio <0.85) doesn't match.
    5. fuzzy typo (Larr Baer → Larry Baer, difflib ≥0.85).

    PERF (2026-08-23): each step rescanned all ents with fresh normalize calls
    (~10k calls/run, O(V) each, in the event loop). The result depends only on
    (name, ctx.ents) — both immutable per case — so the whole resolution is
    memoized per ctx, and the normalize list is computed once."""
    import difflib, unicodedata
    if not name or not str(name).strip():
        return None
    _memo = getattr(ctx, "_n2i_memo", None)
    if _memo is None:
        _memo = {}
        ctx._n2i_memo = _memo
    _mk = str(name)
    if _mk in _memo:
        return _memo[_mk]
    name = str(name).strip()
    n = normalize(name)
    res = None
    if n:
        norms = getattr(ctx, "_ent_norms", None)
        if norms is None or len(norms) != len(ctx.ents):
            norms = [normalize(e) for e in ctx.ents]
            ctx._ent_norms = norms

        # 1. RAW exact
        for i, e in enumerate(ctx.ents):
            if e == name:
                res = i
                break

        if res is None:
            # 2. normalize exact + collision resolution (multiple entities → one normalize key)
            n_matches = [i for i, en in enumerate(norms) if en == n]
            if n_matches:
                raw_eq = next((i for i in n_matches if ctx.ents[i] == name), None)
                if raw_eq is not None:
                    res = raw_eq
                else:
                    res = min(n_matches, key=lambda i: len(ctx.ents[i]))

        if res is None:
            # 3. accent-insensitive (strip accents on RAW before normalize)
            def _strip_accents(text):
                return ''.join(c for c in unicodedata.normalize('NFKD', text)
                               if not unicodedata.combining(c))
            n_na = normalize(_strip_accents(name))
            if n_na and n_na != n:
                for i, e in enumerate(ctx.ents):
                    if normalize(_strip_accents(e)) == n_na:
                        res = i
                        break

        if res is None and len(n) >= 3:
            # 4. substring containment + similarity gate (variants yes, fragments no)
            for i, en in enumerate(norms):
                if (en and len(en) >= 2 and (n in en or en in n)
                        and _match_sim(name, ctx.ents[i]) >= 0.85):
                    res = i
                    break

        if res is None:
            # 5. fuzzy typo
            close = difflib.get_close_matches(n, norms, n=1, cutoff=0.85)
            if close:
                res = norms.index(close[0])
    _memo[_mk] = res
    return res


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
        from kgqa.core.utils import phase_timer
        with phase_timer("gte"):   # UNTIMED BLIND SPOT closed 2026-08-21: this
            # pool is the FULL case entity list (thousands of texts) — a major
            # dispatch cost that the phase attribution previously missed.
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
    # Seed the candidates into subgraph_entities — when the model re-calls with one,
    # the boundary check (which requires prior retrieve_subgraph) would otherwise reject
    # a correction-picked entity (deadlock: correction → pick candidate → "not in prior
    # retrieve"). The correction sanctions these candidates, so they're valid centers.
    if out:
        se = getattr(ctx, "subgraph_entities", None)
        if se is not None:
            n2i_all = _norm_idx_all(ctx)
            for c in out:
                for idx in n2i_all.get(normalize(c["name"]), ()):
                    se.add(idx)
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
                # CVT-CHAIN DEADLOCK EXIT (Norwood specimen, 2026-08-22): the
                # variable's only declared values were EVENT nodes (stripped by
                # the §7.5 guard) — re-declaring them can never bind it, and a
                # later fact planned to walk FROM this variable is stranded.
                # The event's ATTRIBUTES are the entities: point the model at
                # them instead of the generic re-declare instruction (which
                # caused a 16-turn declare/error loop).
                _cev = getattr(ctx, "cvt_empty_var", None)
                if _cev and _cev[0] == e:
                    return [], (
                        f"variable {e} can NEVER bind: its declared values were "
                        f"EVENT nodes (m./g. ids) and events are not entities "
                        f"(§7.5) — re-declaring them returns here forever. The "
                        f"event's bracketed ATTRIBUTES are the entities (e.g. "
                        f"award_nominee=…). Close the stranded fact "
                        f"`[{_cev[1]} ✗ moot]` (earlier evidence already shows "
                        f"its target inside the brackets) and continue the next "
                        f"fact with an ATTRIBUTE entity as the center.")
                return [], (
                    f"variable {e} has no declared bindings. After the "
                    f"retrieve_subgraph that resolves it, declare its values in a "
                    f"checkpoint line `[<fact_id> ✓] {e} = [value1 | value2 | ...]`, "
                    f"then reference {e}.")
            out.extend(bound)
            # WANDERED-CANDIDATE COMPLETION (user audit 2026-09-08, 1797
            # specimen): the declared bindings are the DISPLAY entities; a
            # walk candidate the display filter showed only as "not shown
            # above" (gold Pemberton — its date_of_death edge is the sole
            # date source in the graph) never joins the centers, so the
            # relation pool and the walk can never reach it. Attach the
            # accumulated not-shown candidates — RECENCY-CAPPED (walk cost
            # audit 2026-09-10): the ledger grows monotonically every sg
            # call, and each ?var expansion re-walks EVERY entry as a full
            # environment traversal (RPE is relset-independent — user cost
            # model: one walk + per-relation accounting). Late-turn ?var
            # calls were walking 30-50 centers (slot count 2343/run, walk
            # exec ×6). The mechanism only ever needed the RECENT wanderers
            # (1797: Pemberton from the immediately prior sg); ancient ones
            # were already reachable when they were fresh.
            _wxcap = int(os.environ.get("SEQ_WALLEXTRA_CAP", "6") or 0)
            _wx = getattr(ctx, "walk_extra", None) or []
            if _wxcap > 0 and len(_wx) > _wxcap:
                _wx = _wx[-_wxcap:]
            out.extend(x for x in _wx if x not in out)
        else:
            out.append(e)
    seen, dedup = set(), []
    for e in out:
        if e not in seen:
            seen.add(e); dedup.append(e)
    return dedup, None


def _variable_nudge(raw_entities, ctx) -> str:
    """REMOVED (user ruling 2026-09-21): the warning existed because binding
    loss used to mean core-path loss — under the current design, bindings
    feed the relation-discovery pool only, never gate the walk; quantity is
    never limited and the only requirement is non-empty. Always returns ''.
    Wiring sites (2957, 3605 + 6 prepend points) call this for future
    re-enablement; the function body is inert."""
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


# Noisy relation short-names to drop from the rendered tree — BOOKKEEPING and
# COMMON-TOPIC noise ONLY (zero answer signal), plus the role/type HUB quartet:
# member/organization/role/appointees radiate from title entities (Governor,
# team, organization) to EVERY holder across the graph — via LEGAL pattern
# paths (they are the answer edge for what-group questions), so the path
# discipline cannot stop them; measured 2026-08-18: removing them cost −3.5pp
# (0.8186→0.7834) — flooding beats the 30 what-group questions it would serve.
# "profession" REMOVED (answer edge, +1.5pp); alias/name still blocked — alias
# floods every entity, and the 6 another-name questions pay less than the noise.
_EDGE_NOISY_SHORT = {
    "type", "types", "instance", "instances", "notable_types", "notable_type",
    "webpage", "mid", "guid", "key", "keys", "permission",
    "article", "description", "is_reviewed", "image", "webpage_topic",
    "topic_equivalent_webpage", "alias", "name", "descriptive_name",
    "organization", "appointees",
    # "member"/"role" REMOVED (user audit 2026-08-26, Randy Jackson specimen):
    # these are RECORD-SEMANTIC edges (group_membership.member/.role carry who
    # played what in which group), not bookkeeping — filtering them from the
    # render indexes (a) killed the CVT record's inline attrs ([member=Randy;
    # role=Vocals; group=Journey] — the gold), (b) broke direction resolution
    # and instance reconstruction for membership-bridge chains, and (c) silently
    # dropped musical_group.member from tier-1 blocks even when the model
    # SELECTED it. Unselected member/role edges still never render standalone
    # (selection discipline in blocks/facts); they surface only inside CVT
    # brackets and as chain hops, both sanctioned.
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
    of its out-edges, so they are already canonical).

    PERF (2026-08-23): the raw edge set + both name maps were rebuilt per call
    (O(E)+O(V) in the event loop); the arrays are immutable per case, so all
    three are cached on ctx."""
    raw = getattr(ctx, "_canon_raw_edges", None)
    if raw is None:
        raw = set(zip(ctx.h_ids, ctx.r_ids, ctx.t_ids))
        ctx._canon_raw_edges = raw
    n2i = getattr(ctx, "_canon_n2i", None)
    if n2i is None:
        n2i = {normalize(e): i for i, e in enumerate(ctx.ents) if e}
        ctx._canon_n2i = n2i
    r2i = getattr(ctx, "_canon_r2i", None)
    if r2i is None:
        r2i = {}
        for i, r in enumerate(ctx.rels):
            r2i.setdefault(r, i)
        ctx._canon_r2i = r2i
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


_MERGE_TAIL_CAP = 120   # per-line tail cap; beyond it advertise a branch ref (below)


def _inline_events(edges):
    """Replace CVT/MID endpoints with inline attribute blocks gathered from the
    same edge set: 'FC --starring--> Portrayal' + 'Portrayal --character--> Denver'
    + 'Portrayal --actor--> JF' renders as 'FC --starring--> [character=Denver;
    actor=JF]' — the event node's IDENTITY is its attributes (user spec: point
    out WHAT the event is, e.g. someone's position/performance), no bare mids.
    ATTR BRACKET PRINTED ONCE per CVT per render (2026-08-21, Angelina awards
    specimen): hub CVTs appear under several heads (nominee/ceremony/award/
    work spokes) — inlining attrs at EVERY appearance quadrupled the display.
    First appearance carries the block; later spokes reference the bare id."""
    cvt_attrs = {}
    for h, r, t in edges:
        if is_cvt_like(h) and not is_cvt_like(t):
            cvt_attrs.setdefault(h, []).append((_short_rel(r), t))
    inlined = set()

    def _repl(name):
        if is_cvt_like(name) and name in cvt_attrs:
            if name in inlined:
                return name
            inlined.add(name)
            attrs = cvt_attrs[name][:4]
            return name + " [" + "; ".join(f"{a}={v}" for a, v in attrs) + "]"
        return name
    # drop the CVT-headed attribute edges (their content now lives in the inline
    # block); keep named↔named and named→CVT edges with the CVT inlined
    return [(_repl(h), r, _repl(t)) for h, r, t in edges
            if not (is_cvt_like(h) and not is_cvt_like(t))]


def _merge_edges(edges, max_per_line: int = 8) -> list:
    """Merge resolved edges into compact list-form lines, BOTH directions:
      same (h, r) with differing t      → 'h --r--> t1 | t2 | ...'      (t-list)
      same (r, t-set) with differing h  → 'h1 | h2 | ... --r--> t1|t2'  (h-list)
    Grouping by (r, t-set) catches the multi-t case too: 8 siblings each pointing
    at the same parent-set collapse to '[Ted|Robert|…] --parents--> Joseph|Rose'.
    Entities joined by ' | '. Returns rendered strings (caller indents).

    List-type patterns larger than _MERGE_TAIL_CAP render the first cap entities +
    a '#center|relation' BRANCH REF: the model submits that ref as one answer
    entity and the backend expands it to the FULL pattern (see _do_answer) —
    compressed submission, system-level expansion."""
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
        if len(ts_list) > _MERGE_TAIL_CAP:
            extra = len(ts_list) - _MERGE_TAIL_CAP
            # '::' separator — the flat protocol splits on '|', a '|' ref would
            # parse as two entities.
            branch = (f"+{extra} more (total {len(ts_list)}). To answer with ALL of "
                      f"them, include \"#{hs[0]}::{r}\" as one answer entity — the "
                      f"system expands the ref to the full list.")
            out.append(f"{' | '.join(hs)} --{r}--> {' | '.join(ts_list[:_MERGE_TAIL_CAP])} {branch}")
        elif len(hs) > _MERGE_TAIL_CAP:
            extra = len(hs) - _MERGE_TAIL_CAP
            out.append(f"{' | '.join(hs[:_MERGE_TAIL_CAP])} +{extra} more --{r}--> {' | '.join(ts_list)}")
        else:
            out.append(f"{' | '.join(hs)} --{r}--> {' | '.join(ts_list)}")
    return out


def _shown_edge_key(h: str, r: str, t: str) -> tuple:
    return (normalize(h), r, normalize(t))


def layer_evidence(fid, ctx, paths, all_triples, centers, entities):
    """EVIDENCE SEMANTIC LAYERS (user ruling 2026-08-24, V4 / Codex synthesis):
    the harness — not the model — knows which slot of the fact is the ANSWER
    role (the plan's ?var side in fact_edges). Partition THIS call's evidence
    into answer-role / attribute-values / source layers so the model reads
    "what satisfies the fact" before the graph soup. Evidence-derived only:
    no decision-making, bindings stay the model's checkpoint job.
    Returns dict of display lines (empty strings when not derivable)."""
    from kgqa.core.utils import normalize as _nz

    def _disp_name(n):
        return str(n).split(":", 1)[0].strip()

    fk = None
    for cand in (fid, str(fid).lower()):
        if cand in (getattr(ctx, "fact_key_map", None) or {}):
            fk = ctx.fact_key_map[cand]
            break
    if fk is None or fk not in edges:
        # model omitted `sg:` (the placeholder family): fall back to the
        # first OPEN fact — display-layer heuristic, same shape as the purity
        # detector's open-fact pick
        _taken = set(getattr(ctx, "declared_facts", None) or {}) | \
            set(getattr(ctx, "closed_facts", None) or {})
        for cand in reversed(getattr(ctx, "fact_ids", None) or []):
            if cand not in _taken:
                fk = cand
                break
        if fk is None:
            fids_l = getattr(ctx, "fact_ids", None) or []
            fk = fids_l[0] if fids_l else None
    edges = getattr(ctx, "fact_edges", None) or {}
    ftext = (getattr(ctx, "fact_texts", None) or {}).get(fk or fid, "")
    head_t, tail_t = (edges.get(fk) or (None, None)) if fk else (None, None)
    # answer side: the fact's ?var slot (usually tail); head-var facts answer
    # at the anchor side
    if tail_t and str(tail_t).startswith("?"):
        var = str(tail_t)
    elif head_t and str(head_t).startswith("?"):
        var = str(head_t)
    else:
        var = None

    center_names = [e for e in (entities or []) if not str(e).startswith("?")]
    term_by_rel = {}
    for p in paths or []:
        nodes = p.get("nodes") or []
        rels = p.get("relations") or []
        if not nodes or not rels:
            continue
        n = _disp_name(nodes[-1])
        if n and not is_cvt_like(n) and _nz(n) not in {_nz(c) for c in center_names}:
            term_by_rel.setdefault(_short_rel(rels[-1]), []).append(n)
    answer = list(dict.fromkeys(t for ts in term_by_rel.values() for t in ts))
    attrs = []
    for tr in (all_triples or []):
        if isinstance(tr, (tuple, list)) and len(tr) == 3:
            h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
            if is_cvt_like(h) and not is_cvt_like(t) and t not in attrs:
                attrs.append(t)
    attrs = attrs[:40]
    # head-var facts: the anchor entities ARE the answer-role instances
    answer_role = answer if (var and str(tail_t or "").startswith("?")) else (
        center_names if (var and str(head_t or "").startswith("?")) else [])
    mids = []
    for p in paths or []:
        for n in (p.get("nodes") or [])[1:-1]:
            n = _disp_name(n)
            if n and not is_cvt_like(n) and n not in answer and n not in mids:
                mids.append(n)
    return {
        "fact": ftext,
        "var": var,
        "answer": answer_role[:60],
        "by_rel": [(rel, list(dict.fromkeys(ts))[:60])
                   for rel, ts in term_by_rel.items()],
        "n_answer": len(answer_role),
        "attrs": attrs,
        "source": (center_names + mids)[:15],
    }


def render_pattern_chains(paths, selected_rels=None, max_shapes=6,
                          lines_per_shape=30):
    """MULTI-HOP PATTERN EVIDENCE (SUPERSEDED in production by
    render_evidence_sections, 2026-08-25; kept as the A/B before-arm for
    scripts/render_ab_report.py — do not wire back into _sg_finalize).
    User rulings 2026-08-24/25:
    ① SELECTION DISCIPLINE — a shape renders only when EVERY hop's relation
    is in the model's selected set (no extra unselected-relation edges swept
    in by the walk's enumeration); facts section filters likewise.
    ② INSTANCE COHESION — one line per instance chain (anchor --r1--> n1
    --r2--> n2), instances sharing all-but-the-terminal node fold their
    tails with ' | '. The old (h,r) fan-out grouping mixed edges from
    different instances under one shape and broke path continuity
    (Fitzgerald specimen). Global (h,r,t) dedup + CVT back-edge suppression
    retained; attrs single-print."""
    from kgqa.core.utils import normalize as _nz

    def _disp(n):
        s = str(n)
        if ": [" in s and s.endswith("]"):
            i, attrs = s.split(": [", 1)
            attrs = "; ".join(a.strip() for a in attrs[:-1].split(", ") if a.strip())
            return f"{i} [{attrs}]" if attrs else i
        return s

    printed = set()

    def _once(n):
        s = _disp(n)
        rid = s.split(" [", 1)[0]
        if " [" in s and rid in printed:
            return rid
        if " [" in s:
            printed.add(rid)
        return s

    sel = {_short_rel(r) for r in (selected_rels or []) if r}
    shapes = {}
    for p in paths or []:
        rels = p.get("relations") or []
        nodes = p.get("nodes") or []
        shorts = [_short_rel(r) for r in rels]
        if len(shorts) < 2 or len(nodes) < 2:
            continue
        if sel and not all(s in sel for s in shorts):
            continue          # selection discipline: no unselected hops
        shapes.setdefault(tuple(shorts), []).append(nodes)
    out, covered = [], set()

    def _edge_key(a, r, b):
        return (_nz(str(a).split(":", 1)[0].strip()), r,
                _nz(str(b).split(":", 1)[0].strip()))

    ordered = sorted(shapes.items(), key=lambda kv: -len(kv[1]))[:max_shapes]
    for key, insts in ordered:
        # fold instances sharing all-but-terminal nodes: one line, tails '|'
        groups, order = {}, []
        for nodes in insts:
            gk = tuple(nodes[:-1])
            if gk not in groups:
                groups[gk] = []
                order.append(gk)
            groups[gk].append(nodes[-1])
        sh_lines = []
        for gk in order:
            prefix, tails0 = gk, groups[gk]
            tails = list(dict.fromkeys(str(t).split(":", 1)[0].strip()
                                       for t in tails0))
            if len(prefix) != len(key):
                continue          # malformed instance — conservative skip
            # backtrack guard on the prefix edges (same-rel swapped ends)
            pre_eks = [_edge_key(prefix[k], key[k], prefix[k + 1])
                       for k in range(len(key) - 1)]
            if any((ek[2], ek[1], ek[0]) in covered for ek in pre_eks):
                continue
            line = _once(prefix[0])
            for k in range(len(key) - 1):
                covered.add(pre_eks[k])
                line += f" --{key[k]}--> {_once(prefix[k + 1])}"
            shown = " | ".join(_disp(t) for t in tails[:120])
            more = f" …(+{len(tails)} instances)" if len(tails) > 120 else ""
            for t0 in tails0:
                covered.add(_edge_key(prefix[-1], key[-1], t0))
            line += f" --{key[-1]}--> {shown}{more}"
            sh_lines.append(line)
            if len(sh_lines) >= lines_per_shape:
                break
        if not sh_lines:
            continue
        out.append(f"[{' --'.join(key)}]  ({len(insts)} instances)")
        out.extend(f"  {l}" for l in sh_lines)
    return out, covered


_SHAPE_INSTANCE_CAP = 3000   # complete instances enumerated per shape; overflow is
                              # explicitly marked (I5: no silent truncation)


def _select_uncovered(all_triples, covered, sel_rels):
    """FACTS INPUT SELECTION for _render_records (user rulings 2026-08-20/25).

    ① Selection discipline (ruling ⑧): only edges whose relation ∈ the
    selected set (empty selection = no filter; matching on FULL dotted
    names — covered keys and the selected set share the full-name form) and
    not consumed by a structured block (`covered`).
    ② WITHIN-CALL dedup only: duplicates arriving via multiple patterns/
    channels collapse by exact (h, r, t) key — cross-call suppression is
    FORBIDDEN (each subgraph re-renders the full evidence its pattern paths
    justify); the old `(all N already shown in a prior subgraph)` message
    counted these within-call duplicates on a FRESH shown-set and lied about
    a "prior subgraph" (Kim Richards specimen, first retrieval of the case).
    ③ CVT ATTR REVIVAL (ruling ④, the specimen's real failure): when a CVT
    is displayed via a selected-rel edge (e.g. `Show --regular_cast--> m.x`),
    its attribute edges (unselected relation names like actor/series) are
    fed to the record renderer as PAYLOAD — _render_records only ever shows
    them inside the inline `[k=v; …]` bracket, never as standalone edge
    lines, so the selection discipline's letter (no unselected relation
    LINES) holds while the record's content stays visible. Without this the
    record renders as a bare CVT tail and the legacy BARE-CVT TAIL DROP
    discards it — an empty evidence section.
    """
    from kgqa.core.utils import normalize as _nz
    sel = set(sel_rels or [])
    seen = set()
    out = []
    for tr in all_triples or []:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        r = str(tr[1])
        if sel and r not in sel:
            continue
        k = (_nz(str(tr[0])), r, _nz(str(tr[2])))
        if k in covered or k in seen:
            continue
        seen.add(k)
        out.append(tr)
    # ③ revive attr edges of CVTs that the facts section will display
    need = set()
    for h, _r, t in out:
        if is_cvt_like(str(h)):
            need.add(_nz(str(h)))
        if is_cvt_like(str(t)):
            need.add(_nz(str(t)))
    if need:
        for tr in all_triples or []:
            if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
                continue
            h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
            if not is_cvt_like(h) or is_cvt_like(t) \
                    or _short_rel(r) in _EDGE_NOISY_SHORT:
                continue
            k = (_nz(h), r, _nz(t))
            if k in covered or k in seen or _nz(h) not in need:
                continue
            seen.add(k)
            out.append(tr)
    return out


_FACT_REL_RE = re.compile(r"--<?\s*([A-Za-z0-9_.]+)\s*>?--")


def _group_facts_by_rel(lines):
    """FACTS BY RELATION (user ruling 2026-08-25, Debussy specimen: "the
    facts marker has weak semantics"): after the selected-relation sweep the
    facts section holds only true remainders (record renderings, revived
    payload, residual edges) — group them under per-relation headers so no
    unorganized pipe list remains. Lines without a relation token (record
    group headers, (all:) uplifts, indented sub-entries) inherit the
    PRECEDING line's relation; a single group keeps its lines unchanged
    under one header."""
    groups, order, cur = {}, [], None
    for ln in lines:
        m = _FACT_REL_RE.search(ln)
        rel = m.group(1) if m else cur
        if rel is None:
            rel = "records"
        cur = rel
        if rel not in groups:
            groups[rel] = []
            order.append(rel)
        groups[rel].append(ln)
    out = []
    for rel in order:
        out.append(f"  {rel}:")
        out.extend(groups[rel])
    return out


def render_evidence_sections(paths, centers, var_label, all_triples, selected_rels,
                             per_rel=3, total_cap=12, lines_per_shape=30):
    """UNIFIED EVIDENCE RENDERER (user ruling 2026-08-25: audit the mechanism,
    then redesign once). Supersedes build_pattern_overview + render_pattern_chains
    in production (both kept below for the A/B before-arm).

    PRINCIPLE 1 (per selected relation, short-to-long): ① one 1-hop block per
    selected relation FIRST (anchor-anchored dense line, synthesized from the
    anchor's own selected-relation edges even when the walk enumerated no
    1-hop pattern), then ② k-hop path blocks, length ASCENDING, within one
    length by instance count desc. The overview is the shape INDEX of exactly
    the blocks that render, in the same order (概览与细节同源: same instance
    sets, consistent counts).

    PRINCIPLE 2 (path consistency): a k-hop block contains ONLY instances that
    COMPLETE the block's path shape — every row traces back to a full
    anchor→terminal chain. Instances are RECONSTRUCTED from the canonicalized
    evidence edges (tree paths are bounded witnesses; the flattened edge set
    carries the walk's full leaf enumeration), so a hop-2 continuation edge of
    a non-witness hop-1 entity lands INSIDE the 2-hop block behind its hop-1
    anchor — never in facts as an anchorless fragment. An entity reached by
    hop 1 with no hop-2 continuation stays in the 1-hop block only.

    Standing rulings kept: selection discipline (every hop ∈ selected set;
    unselected relations reach neither blocks nor facts), start anchoring +
    ?slots + `<--r--` reverse notation in the overview, dense line grammar +
    CVT attrs inline + (all:) uplift + 120 cap + branch refs, CVT back-edge
    suppression (canonical-direction reconstruction: a same-rel swapped-end
    backtrack cannot re-enter as a forward hop), attr single-print, shared-
    prefix tail folding with tail dedup, separator hierarchy ('|' = hop/tail
    axis, never inside a cell).
    Returns (overview_lines, block_lines, covered_edge_keys)."""
    from kgqa.core.utils import normalize as _nz

    def _node_key(n):
        # tree paths carry expanded display names ("m.xxx: [attrs]") — keys use
        # the id/name before the colon
        return _nz(str(n).split(":", 1)[0].strip())

    sel_full = [str(r) for r in (selected_rels or []) if r]
    sel = set(sel_full)
    centers = list(centers or [])
    center_set = {_nz(str(c)) for c in centers if _nz(str(c))}

    # SHORT-NAME COLLISION DISAMBIGUATION (user ruling 2026-08-25, Debussy
    # specimen): two selected FULL relations may share a short name
    # (music.composition.composer vs base.musiteca.composition.composer) —
    # short-name display would merge them indistinguishably. All INTERNAL
    # keys (indexes, shape hops, selection discipline, coverage) use the FULL
    # dotted name; only DISPLAY tokens shorten, and a short shared by ≥2
    # selected relations renders as `short[family]` (family = first segment).
    from collections import Counter as _Ctr
    _short_n = _Ctr(_short_rel(r) for r in sel_full)

    def _disp_rel(rfull):
        s = _short_rel(rfull)
        if _short_n.get(s, 0) > 1:
            return f"{s}[{str(rfull).split('.', 1)[0]}]"
        return s

    # ── canonical edge indexes (graph direction) + display names + CVT attrs ──
    # NOTE on CVT detection: normalize() maps '_'→' ' ("m.02sd_zh"→"m.02sd zh")
    # which breaks is_cvt_like on NORMALIZED keys — collect cvt_keys from the
    # RAW names instead and test membership.
    fwd_idx, rev_idx, disp, cvt_attrs = {}, {}, {}, {}
    by_rel = {}      # full rel -> [(hn, tn)] — the selected-relation sweep
    cvt_keys = set()
    edge_keys = set()

    def _is_cvt_key(nk):
        return nk in cvt_keys

    for tr in all_triples or []:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if _short_rel(r) in _EDGE_NOISY_SHORT:
            continue                       # bookkeeping noise (mirror facts filter)
        hn, tn = _nz(h), _nz(t)
        if not hn or not tn or hn == tn:
            continue                       # empty / self-loop
        edge_keys.add((hn, r, tn))
        disp.setdefault(hn, h)
        disp.setdefault(tn, t)
        if tn not in fwd_idx.setdefault((hn, r), []):
            fwd_idx[(hn, r)].append(tn)
        if hn not in rev_idx.setdefault((tn, r), []):
            rev_idx[(tn, r)].append(hn)
        by_rel.setdefault(r, []).append((hn, tn))
        if is_cvt_like(h):
            cvt_keys.add(hn)
        if is_cvt_like(t):
            cvt_keys.add(tn)
        if is_cvt_like(h) and not is_cvt_like(t):
            k, v = (r, t)
            lst = cvt_attrs.setdefault(hn, [])
            if (k, _nz(v)) not in [(a, _nz(w)) for a, w in lst]:
                lst.append((k, v))

    # ── shapes from tree paths (the walk's pattern vocabulary; hop direction
    #    resolved against the canonical edges) ─────────────────────────────────
    # SHAPE KEY = the hop sequence ALONE (user audit 2026-08-26, Randy Jackson
    # specimen): keying on (hops, term_cvt) split one shape into two entries
    # whose instance reconstruction (edge-based, witness-independent) was
    # IDENTICAL — the same block rendered twice verbatim. Terminal-CVT-ness
    # is a DISPLAY decision computed from the reconstructed instances.
    shapes = {}   # (hops) -> {hops, anchors, order}
    for p in paths or []:
        rels = p.get("relations") or []
        nodes = p.get("nodes") or []
        if not rels or len(nodes) < 2 or len(nodes) > len(rels) + 1:
            continue
        # NO-FREE-HEAD GATE (user calibration 2026-08-26, Poetic Justice /
        # Vocals / Sonora specimens): a tree path may anchor a shape only
        # when its FIRST node is a CENTER. The sibling-CVT display mirror
        # (formatting.py) roots continuation paths at the path's MID node,
        # and those previously registered as non-center 1-hop shapes that
        # rendered as free-head rows detached from the chain that produced
        # them (`Vocals --instrumentalists--> ...` while the center's own
        # connection lived in the chain). The same edges stay visible INSIDE
        # the center-rooted chain shapes; truly centerless selected-relation
        # edges fall to the terminal-anchored sweep below (Debussy ruling).
        a0 = _node_key(nodes[0])
        if not a0 or a0 not in center_set:
            continue
        # LAST-HOP discipline replaces whole-path selection discipline (user
        # calibration 2026-08-26, "绕道链归各自真实锚的形状或长度正确的多跳
        # 形状"): a detour chain whose bridge hops are unselected relations is
        # the REAL provenance of its last-hop selected edge — rendering it as
        # a correctly-lengthed multi-hop chain row is the only form in which
        # that edge stays attached to its center. An unselected LAST hop
        # still never renders (ruling ⑧ core); detour chains order AFTER
        # all-selected shapes below.
        if sel and str(rels[-1]) not in sel:
            continue
        hops = []
        for k in range(len(nodes) - 1):
            rf = str(rels[k])
            a, b = _node_key(nodes[k]), _node_key(nodes[k + 1])
            rev = (a, rf, b) not in edge_keys and (b, rf, a) in edge_keys
            hops.append((rf, rev))
        key = tuple(hops)
        ent = shapes.setdefault(key, {"hops": hops,
                                      "anchors": [], "seen": set(),
                                      "order": len(shapes)})
        if a0 not in ent["seen"]:
            ent["seen"].add(a0)
            ent["anchors"].append(a0)

    # 1-hop synthesis (principle 1): every selected relation gets its
    # anchor-anchored 1-hop block whenever the anchor itself has such edges —
    # anchor-headed selected edges always live in tier-1 blocks, never
    # scattered through facts.
    center_keys = [_nz(str(c)) for c in centers if _nz(str(c))]
    for ri, rf in enumerate(dict.fromkeys(sel_full)):
        for rev in (False, True):
            tails = []
            for ck in center_keys:
                tails.extend(rev_idx.get((ck, rf), []) if rev
                             else fwd_idx.get((ck, rf), []))
            if not tails:
                continue
            hops_1 = [(rf, rev)]
            key = tuple(hops_1)
            ent = shapes.setdefault(key, {"hops": hops_1,
                                          "anchors": [], "seen": set(),
                                          "order": len(shapes) + ri})
            for ck in center_keys:
                if ck not in ent["seen"]:
                    ent["seen"].add(ck)
                    ent["anchors"].append(ck)

    # ── instance reconstruction per shape (principle 2: complete paths only) ──
    for ent in shapes.values():
        prefixes = [(a,) for a in ent["anchors"]]
        overflow = False
        for sr, rev in ent["hops"]:
            nxt, seenp = [], set()
            for pfx in prefixes:
                nbrs = rev_idx.get((pfx[-1], sr), ()) if rev \
                    else fwd_idx.get((pfx[-1], sr), ())
                for n in nbrs:
                    npfx = pfx + (n,)
                    if npfx not in seenp:
                        seenp.add(npfx)
                        nxt.append(npfx)
            if len(nxt) > _SHAPE_INSTANCE_CAP:
                nxt = nxt[:_SHAPE_INSTANCE_CAP]
                overflow = True
            prefixes = nxt
            if not prefixes:
                break
        ent["instances"] = prefixes
        ent["overflow"] = overflow

    # ── ordering (principle 1): 1-hop per selected relation first (selected
    #    order, fwd before rev), then length ascending / instance count desc.
    #    Detour chains (unselected bridge hops, admitted by the last-hop
    #    discipline above) order AFTER all-selected shapes of any length —
    #    the direct selected-relation evidence always reads first. ──────────
    sel_order = {r: i for i, r in enumerate(dict.fromkeys(sel_full))}
    enriched = []
    for key, ent in shapes.items():
        n = len(ent["instances"])
        if n == 0:
            continue                       # no complete instance → no block
        hops = ent["hops"]
        if len(hops) == 1:
            sort_k = (0, sel_order.get(hops[0][0], len(sel_order)),
                      1 if hops[0][1] else 0, ent["order"])
        else:
            all_sel = all(h[0] in sel for h in hops) if sel else True
            sort_k = (0 if all_sel else 1, len(hops), -n, ent["order"])
        enriched.append((sort_k, key, ent))
    enriched.sort(key=lambda x: x[0])
    per_first, kept = {}, []
    for _sk, key, ent in enriched:
        fr = key[0][0]
        per_first[fr] = per_first.get(fr, 0) + 1
        if per_first[fr] > per_rel or len(kept) >= total_cap:
            continue
        kept.append((key, ent))

    # ── CHAIN-BEATS-ORPHAN PROMOTION (user calibration 2026-08-26, VOG /
    #    Lost-Symbol specimens): a selected-relation edge whose endpoints are
    #    both non-centers must surface as a COMPLETE chain row whenever a
    #    center-rooted shape instance carries it. The per_rel/total_cap cuts
    #    could drop exactly that shape, and the completeness sweep would then
    #    re-render the edge as a detached terminal-anchored row — the
    #    free-head form the audit banned. Promote (bounded) capped-out shapes
    #    whose instances would otherwise land in the sweep; only truly
    #    orphan edges (no covering shape at all — the Debussy family) keep
    #    the terminal-anchored sweep form. ─────────────────────────────────
    def _inst_edges(ent):
        out = set()
        for inst in ent["instances"]:
            for k, (sr, rv) in enumerate(ent["hops"]):
                out.add((inst[k + 1], sr, inst[k]) if rv
                        else (inst[k], sr, inst[k + 1]))
        return out

    kept_keys = {key for key, _ent in kept}
    kept_edges = set()
    for _k, ent in kept:
        kept_edges |= _inst_edges(ent)

    def _sweep_leftovers(edges):
        out = []
        for rf in dict.fromkeys(sel_full):
            for hn, tn in by_rel.get(rf, ()):
                if ((hn, rf, tn) in edges or hn in center_set or tn in center_set
                        or _is_cvt_key(hn) or _is_cvt_key(tn)):
                    continue
                out.append((hn, rf, tn))
        return out

    for _promo_round in range(2):
        leftovers = _sweep_leftovers(kept_edges)
        if not leftovers:
            break
        promoted = 0
        for _sk, key, ent in enriched:
            if key in kept_keys or promoted >= 4:
                continue
            ie = _inst_edges(ent)
            if ie & set(leftovers):
                kept.append((key, ent))
                kept_keys.add(key)
                kept_edges |= ie
                promoted += 1
                if not _sweep_leftovers(kept_edges):
                    break
        if not promoted:
            break

    # ── display helpers ───────────────────────────────────────────────────────
    printed = set()   # CVT keys whose attr bracket already printed (ruling ⑦)

    def _disp_node(nk):
        base = disp.get(nk, nk)
        if not _is_cvt_key(nk) or nk in printed:
            return base
        printed.add(nk)
        attrs = cvt_attrs.get(nk, [])[:4]
        if attrs:
            # attr KEYS display short (payload, not a selected-relation arrow
            # — no disambiguation needed; internal keys stay full for coverage)
            return f"{base} [" + "; ".join(f"{_short_rel(a)}={v}" for a, v in attrs) + "]"
        return base

    def _cover_cvt(nk, covered):
        # a displayed CVT's attr edges are consumed by its node display
        for a, v in cvt_attrs.get(nk, []):
            covered.add((nk, a, _nz(v)))

    def _tails_display(tails):
        """CVT tail list with uniform-attr uplift (ruling ③): an attr that is
        present in EVERY tail with the SAME SINGLE value hoists to one
        '(all: k=v)' prefix; multi-valued / non-uniform attrs stay in the
        per-record brackets (no last-wins collapse — values must survive)."""
        attrs = [cvt_attrs.get(t, [])[:4] for t in tails]
        if len(attrs) >= 2 and all(attrs):
            uniform = {}
            for k in set(attrs[0]):
                vs = [[v for a, v in lst if a == k] for lst in attrs]
                if all(len(v) == 1 for v in vs) and len({v[0] for v in vs}) == 1:
                    uniform[k] = vs[0][0]
        else:
            uniform = {}
        hoist = ""
        if uniform:
            hoist = "(all: " + "; ".join(f"{_short_rel(k)}={str(v)[:24]}"
                                        for k, v in uniform.items()) + ") "
        outs = []
        for t, lst in zip(tails, attrs):
            base = disp.get(t, t)
            if not _is_cvt_key(t) or t in printed:
                outs.append(base)          # bare id — attr payload printed earlier
                continue
            kept = [(a, v) for a, v in lst if a not in uniform]
            outs.append(base + (" [" + "; ".join(f"{_short_rel(a)}={v}" for a, v in kept) + "]"
                                if kept else ""))
            printed.add(t)
        return hoist, outs

    covered = set()

    def _mark_hop(a, sr, b, rev):
        covered.add((b, sr, a) if rev else (a, sr, b))

    def _center_first(seq):
        """④③ CENTER-PRIORITY TRUNCATION (user audit 2026-08-26, Randy
        Jackson specimen): when a fold truncates a member/tail list, CENTER
        entities survive first — the center's own presence inside a shared
        list is exactly the evidence a fold must never cut (the center was
        dropped from a 6-member instrumentalists row, and with him the gold
        binding). Stable sort: non-centers keep their arrival order."""
        return sorted(seq, key=lambda x: _nz(str(x)) not in center_set)

    def _anchor_head(ent):
        """②a SAME-ANCHOR ATTRIBUTION (user audit 2026-08-26, ABM specimen):
        the overview head is the shape's REAL first-node population — the
        declared variable label when there is one (a variable head honestly
        stands for all its bindings), else the distinct anchors folded in
        the dense multi-head grammar. centers[0] is never borrowed for
        instances it does not anchor: `A Beautiful Mind --subjects--> ?x
        (4 instances)` previously claimed four instances anchored at OTHER
        films while ABM itself had none."""
        heads = []
        for inst in ent["instances"]:
            if inst[0] not in heads:
                heads.append(inst[0])
        if var_label:
            return str(var_label)
        if len(heads) == 1:
            return disp.get(heads[0], heads[0])
        shown = " | ".join(disp.get(h, h) for h in heads[:4])
        if len(heads) > 4:
            shown += f" | …(+{len(heads) - 4} centers)"
        return shown

    # ── render: overview lines + detail blocks, same order, same counts ──────
    ov_lines, block_lines = [], []
    tier1_end = 0        # splice point for the selected-relation sibling sweep
    for key, ent in kept:
        hops = key
        instances = ent["instances"]

        # overview line (ruling ① grammar; counts = block instance counts);
        # head = the shape's real anchor population (see _anchor_head)
        line = _anchor_head(ent)
        slot = ord("x")
        # terminal-CVT notation is a display decision over the RECONSTRUCTED
        # instances (all-terminal-CVT → `[N records]`), not a witness property
        term_cvt = bool(instances) and all(_is_cvt_key(i[-1]) for i in instances)
        for k, (rf, rev) in enumerate(hops):
            last = k == len(hops) - 1
            if last and term_cvt:
                nxt = f"[{len(instances)} records]"
            else:
                nxt = f"?{chr(slot)}"
                slot += 1
            line += f" <--{_disp_rel(rf)}-- {nxt}" if rev \
                else f" --{_disp_rel(rf)}--> {nxt}"
        if not term_cvt and len(instances) > 1:
            line += f"  ({len(instances)} instances)"
        ov_lines.append(line)

        # detail block header (multi-hop only — a 1-hop dense line names its
        # own shape; header = relation sequence, legacy grammar). Direction
        # is part of the shape: two shapes differing only in a hop's
        # direction must not render identical headers (reads as a duplicate
        # block with inconsistent counts — ④'s twin-block report). Reverse
        # hops carry the `<--` prefix, mirroring the dense-line grammar.
        if len(hops) > 1:
            block_lines.append("[{}]  ({} instances)".format(
                " --".join(_disp_rel(rf) if not rv else f"<--{_disp_rel(rf)}"
                           for rf, rv in hops), len(instances)))

        if len(hops) == 1:
            rf, rev = hops[0]
            # fold members sharing a tail-set (dense grammar, ruling ③/⑨)
            by_ts, order = {}, []
            for inst in instances:
                a, t = inst[0], inst[1]
                if a not in by_ts:
                    by_ts[a] = []
                    order.append(a)
                if t not in by_ts[a]:
                    by_ts[a].append(t)
            ts_group, ts_order = {}, []
            for a in order:
                gk = tuple(by_ts[a])
                if gk not in ts_group:
                    ts_group[gk] = []
                    ts_order.append(gk)
                ts_group[gk].append(a)
            n_lines = 0
            for gk in ts_order:
                if n_lines >= lines_per_shape:
                    break
                members = _center_first(ts_group[gk])
                hoist, tdisp = _tails_display(_center_first(list(gk)))
                m_shown = " | ".join(disp.get(m, m) for m in members[:_MERGE_TAIL_CAP])
                if len(members) > _MERGE_TAIL_CAP:
                    m_shown += f" +{len(members) - _MERGE_TAIL_CAP} more"
                t_list = " | ".join(tdisp[:_MERGE_TAIL_CAP])
                if len(tdisp) > _MERGE_TAIL_CAP:
                    extra = len(tdisp) - _MERGE_TAIL_CAP
                    t_list += (f" +{extra} more (total {len(tdisp)}). To answer with "
                               f"ALL of them, include \"#{disp.get(members[0], members[0])}::{_short_rel(rf)}\" "
                               f"as one answer entity — the system expands the ref to "
                               f"the full list.")
                arrow = f" <--{_disp_rel(rf)}-- " if rev else f" --{_disp_rel(rf)}--> "
                block_lines.append(f"  {m_shown}{arrow}{hoist}{t_list}")
                n_lines += 1
                for m in members:
                    for t in gk:
                        _mark_hop(m, rf, t, rev)
                        if _is_cvt_key(t):
                            _cover_cvt(t, covered)
            tier1_end = len(block_lines)
            continue

        # multi-hop: shared-prefix tail folding, one line per prefix (ruling ⑨);
        # additionally, prefixes sharing the SAME tail-set whose nodes differ
        # in exactly ONE position merge into a single fanout line — the
        # _merge_edges (relation, tail-set) semantics carried to chains (the
        # round-trip family 'A --r--> X1..Xn --r2--> A' collapses to one line)
        groups, order = {}, []
        for inst in instances:
            gk = inst[:-1]
            if gk not in groups:
                groups[gk] = []
                order.append(gk)
            if inst[-1] not in groups[gk]:
                groups[gk].append(inst[-1])
        by_ts, ts_order = {}, []
        for gk in order:
            ts = tuple(groups[gk])
            if ts not in by_ts:
                by_ts[ts] = []
                ts_order.append(ts)
            by_ts[ts].append(gk)
        entries = []   # (rep_prefix, vary_pos|None, vary_ents, tails)
        for ts in ts_order:
            gks = by_ts[ts]
            if len(gks) == 1:
                entries.append((gks[0], None, [], list(ts)))
                continue
            vary = [i for i in range(len(gks[0]))
                    if len({g[i] for g in gks}) > 1]
            if len(vary) == 1:
                ents = list(dict.fromkeys(g[vary[0]] for g in gks))
                entries.append((gks[0], vary[0], ents, list(ts)))
            else:
                for g in gks:
                    entries.append((g, None, [], list(ts)))
        n_shown_inst = 0
        rendered = 0
        # FRONTIER MEMBER CAP (user audit 2026-09-17, 567_df97 specimen: a
        # story_by layer instantiated 8 films' writer blocks — structurally
        # unnecessary bulk). K>0 caps the DISTINCT prefix members RENDERED
        # per multi-hop shape; 0 (default) keeps the full render. Display-
        # only: the _mark_hop/_cover_cvt loop still runs for every entry,
        # so licensing and CVT coverage are unchanged.
        _fk = int(os.environ.get("SEQ_FRONTIER_RENDER_K", "0") or 0)
        _fk_hidden = 0
        for _ei, (rep, vpos, vents, tails) in enumerate(entries):
            if _fk and _ei >= _fk:
                _fk_hidden += 1
                tails = _center_first(tails)
                if vpos is not None:
                    vents = _center_first(vents)
                prefixes = ([tuple(x if i == vpos else p for i, p in enumerate(rep))
                             for x in vents] if vpos is not None else [rep])
                for pfx in prefixes:
                    for k in range(len(hops) - 1):
                        rf, rev = hops[k]
                        _mark_hop(pfx[k], rf, pfx[k + 1], rev)
                    lrf, lrev = hops[-1]
                    for t in tails:
                        _mark_hop(pfx[-1], lrf, t, lrev)
                        if _is_cvt_key(t):
                            _cover_cvt(t, covered)
                    for m in pfx[1:]:
                        if _is_cvt_key(m):
                            _cover_cvt(m, covered)
                continue
            if rendered >= lines_per_shape:
                break
            tails = _center_first(tails)
            if vpos is not None:
                vents = _center_first(vents)
            tdisp = [_disp_node(t) for t in tails[:_MERGE_TAIL_CAP]]
            shown = " | ".join(tdisp)
            if len(tails) > _MERGE_TAIL_CAP:
                shown += f" …(+{len(tails)} instances)"
            segs = []
            for k in range(len(hops)):           # prefix node positions
                if k == 0:
                    segs.append(" | ".join(_disp_node(x) for x in
                                           (vents if vpos == 0 else [rep[0]])))
                    continue
                rf, rev = hops[k - 1]
                nodes = (vents if vpos == k else [rep[k]])
                segs.append((f" <--{_disp_rel(rf)}-- " if rev else f" --{_disp_rel(rf)}--> ")
                            + " | ".join(_disp_node(x) for x in nodes))
            lrf, lrev = hops[-1]
            segs.append((f" <--{_disp_rel(lrf)}-- " if lrev else f" --{_disp_rel(lrf)}--> ")
                        + shown)
            block_lines.append("  " + "".join(segs))
            rendered += 1
            n_shown_inst += (len(vents) if vpos is not None else 1) * len(tails)
            # cover the instance edges of every folded prefix/tail (incl.
            # beyond-cap — the cap marker owns the disclosure)
            prefixes = ([tuple(x if i == vpos else p for i, p in enumerate(rep))
                         for x in vents] if vpos is not None else [rep])
            for pfx in prefixes:
                for k in range(len(hops) - 1):
                    rf, rev = hops[k]
                    _mark_hop(pfx[k], rf, pfx[k + 1], rev)
                lrf, lrev = hops[-1]
                for t in tails:
                    _mark_hop(pfx[-1], lrf, t, lrev)
                    if _is_cvt_key(t):
                        _cover_cvt(t, covered)
                for m in pfx[1:]:
                    if _is_cvt_key(m):
                        _cover_cvt(m, covered)
        if _fk_hidden:
            block_lines.append(
                f"  …(+{_fk_hidden} members follow the same relation — not shown; "
                f"discriminate from the shown ones or retrieve their edges "
                f"explicitly)")
        rest = len(instances) - n_shown_inst
        if rendered < len(entries) and (rest > 0 or ent.get("overflow")):
            suffix = "+" if ent.get("overflow") else ""
            block_lines.append(f"  …(+{rest}{suffix} more instances)")

    # ── SELECTED-RELATION COMPLETENESS SWEEP (user ruling 2026-08-25, Debussy
    #    specimen): a selected relation's instances may be sibling edges whose
    #    NEITHER endpoint is a center (works --author--> Claude Debussy while
    #    the center is one particular work) — previously they all fell into
    #    facts as one unlabeled merged line. Each selected relation must have
    #    a STRUCTURAL presentation: group the leftovers by shared terminal and
    #    render terminal-anchored reverse dense lines, spliced right after the
    #    tier-1 blocks (same 1-hop grammar, no overview line — the overview
    #    indexes center-anchored shapes only, ruling ①). Selected-relation
    #    edges never reach facts unsemantically.
    sib_lines = []
    for rf in dict.fromkeys(sel_full):
        groups, g_order = {}, []
        for hn, tn in by_rel.get(rf, ()):
            if ((hn, rf, tn) in covered or hn in center_set or tn in center_set
                    or _is_cvt_key(hn) or _is_cvt_key(tn)):
                continue
            if tn not in groups:
                groups[tn] = []
                g_order.append(tn)
            if hn not in groups[tn]:
                groups[tn].append(hn)
        n_ln = 0
        for tn in g_order:
            if n_ln >= lines_per_shape:
                remaining = sum(len(groups[x]) for x in g_order[n_ln:])
                sib_lines.append(f"  …(+{remaining} more via {_disp_rel(rf)})")
                break
            heads = _center_first(groups[tn])
            h_list = " | ".join(disp.get(h, h) for h in heads[:_MERGE_TAIL_CAP])
            if len(heads) > _MERGE_TAIL_CAP:
                extra = len(heads) - _MERGE_TAIL_CAP
                h_list += (f" +{extra} more (total {len(heads)}). To answer with "
                           f"ALL of them, include \"#{disp.get(tn, tn)}::{_short_rel(rf)}\" "
                           f"as one answer entity — the system expands the ref to "
                           f"the full list.")
            sib_lines.append(f"  {disp.get(tn, tn)} <--{_disp_rel(rf)}-- {h_list}")
            n_ln += 1
            for hn in heads:
                covered.add((hn, rf, tn))
    if sib_lines:
        block_lines[tier1_end:tier1_end] = sib_lines
    # EXPLICIT ZERO-COVERAGE (user ruling 2026-08-25, Kim Richards specimen):
    # a selected relation with NO instance anywhere in the evidence must SAY
    # so — silence lets the model conclude "no instance exists" from absence.
    # (Instance may live in the remainder section rather than blocks — check
    # all_triples.) ALL-∅ (user ruling 2026-08-25, repair hook): when every
    # selected relation is empty the output must also carry the cross-subgraph
    # repair guidance (same family as the walk-empty RELATION_MISMATCH note)
    # — a non-empty return whose selected relations are ALL silent is exactly
    # the Kim-Richards-class miss that previously self-healed only when the
    # walk returned nothing at all.
    _present_rels = {str(tr[1]) for tr in (all_triples or [])
                     if isinstance(tr, (tuple, list)) and len(tr) == 3}
    _sel_uniq = list(dict.fromkeys(sel_full))
    for rf in _sel_uniq:
        if rf not in _present_rels:
            ov_lines.append(f"  --{_disp_rel(rf)}--> ∅ (no instances from these centers)")
    if _sel_uniq and all(rf not in _present_rels for rf in _sel_uniq):
        ov_lines.append(
            "  selected relations hit NOTHING from these centers — consider "
            "re-calling with OTHER candidate relations, or with a center "
            "BORROWED from any earlier subgraph's evidence (cross-subgraph "
            "center: any prior retrieve_subgraph's entities are legal centers).")
    return ov_lines, block_lines, covered


def build_pattern_overview(paths, centers, var_label, all_triples,
                            selected_rels, per_rel=3, total_cap=12):
    """PATTERN OVERVIEW (SUPERSEDED in production by render_evidence_sections,
    2026-08-25; kept as the A/B before-arm for scripts/render_ab_report.py).
    User ruling 2026-08-24, V3: at most `per_rel` pattern
    lines per first-hop relation — path-terminal shapes FIRST (last hop is one
    of the SELECTED relations, i.e. the walk ended by entering what the model
    asked for), then by instance count. Anchor = the walk start (single entity
    or the ?var set label); every line is start-anchored, slots are ?x/?y.
    Direction per hop is resolved against the flattened edges (reverse hops
    render `<--r--`). Terminal CVT nodes render `[records]`. Dense by design:
    this is an index, the detail below carries the payload."""
    from kgqa.core.utils import normalize as _nz

    def _node_key(n):
        # tree paths carry expanded display names ("m.xxx: [attrs]") — match
        # flattened edges on the id/name before the colon
        return _nz(str(n).split(":", 1)[0].strip())

    edge_dir = set()
    for tr in all_triples or []:
        if isinstance(tr, (tuple, list)) and len(tr) == 3:
            edge_dir.add((_nz(str(tr[0])), _short_rel(tr[1]), _nz(str(tr[2]))))

    anchor = var_label or (centers[0] if centers else "?start")
    sel_short = {_short_rel(r) for r in (selected_rels or [])}

    shapes = {}   # shape key -> [count, terminal_last, rels_line, first_rel]
    for p in paths or []:
        rels = p.get("relations") or []
        nodes = p.get("nodes") or []
        if not rels or len(nodes) < 2:
            continue
        hops, terminal_last = [], False
        for k, r in enumerate(rels):
            sr = _short_rel(r)
            a, b = _node_key(nodes[k]), _node_key(nodes[k + 1]) if k + 1 < len(nodes) else ""
            rev = (a, sr, b) not in edge_dir and (b, sr, a) in edge_dir
            hops.append((sr, rev))
        last_rel = hops[-1][0]
        if last_rel in sel_short:
            terminal_last = True
        key = (tuple(hops), str(nodes[-1]).startswith(("m.", "g.")))
        if key not in shapes:
            shapes[key] = [0, terminal_last, hops, _short_rel(rels[0])]
        shapes[key][0] += 1

    # group by first-hop relation; per group: terminal-first, then count desc
    groups = {}
    for key, (cnt, term, hops, first_rel) in shapes.items():
        groups.setdefault(first_rel, []).append((not term, -cnt, key, hops, cnt))
    out = []
    for first_rel, items in sorted(groups.items(), key=lambda kv: -sum(i[4] for i in kv[1])):
        items.sort()
        for _prio, _ncnt, key, hops, cnt in items[:per_rel]:
            if len(out) >= total_cap:
                return out
            ends_record = key[1]
            line = str(anchor)
            slot = ord("x")
            for k, (sr, rev) in enumerate(hops):
                last = k == len(hops) - 1
                if last and ends_record:
                    nxt = f"[{cnt} records]"
                else:
                    nxt = f"?{chr(slot)}"; slot += 1
                line += f" <--{sr}-- {nxt}" if rev else f" --{sr}--> {nxt}"
            if not ends_record:
                line += f"  ({cnt} instances)" if cnt > 1 else ""
            out.append(line)
    return out


def _render_records(all_triples, shown_edges):
    """Record-centric renderer (replaces _resolve_cvt_edges + _merge_edges).

    CVT-with-holder → record `holder → title [from=..; to=..; ..]`, direction-normalized:
    holder = the person reached via an `office_holder` (singular) or `positions_held` edge
    in EITHER direction; `office_holders` (plural) is the title→CVT reverse and is skipped
    (it was the source of the holder/title direction confusion). CVT-without-holder
    (non-record schemas) → flattened named→named. Direct named→named edges → merged lines.
    `has_no_value` → `to=(incumbent)`. Cross-subgraph dedup by record key or edge key.
    Returns (lines, n_overlap)."""
    cvt_attrs = {}         # cvt -> [(attr_short, val)]  (CVT→named, excl has_no_value)
    cvt_holders = {}       # cvt -> [holder name]  (either direction, holder edge)
    cvt_incumbent = set()  # cvt with a has_no_value edge
    direct = []

    def _is_holder_rel(r):
        return r.endswith("office_holder") or "positions_held" in r

    for tr in all_triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        sr = _short_rel(r)
        if is_cvt_like(h) and not is_cvt_like(t):
            if sr == "has_no_value" or "has_no_value" in r:
                cvt_incumbent.add(h); continue
            cvt_attrs.setdefault(h, []).append((sr, t))
            if _is_holder_rel(r):
                cvt_holders.setdefault(h, []).append(t)
        elif not is_cvt_like(h) and is_cvt_like(t):
            if _is_holder_rel(r):
                cvt_holders.setdefault(t, []).append(h)
            # title→CVT (office_holders plural) reverse: skip — holder/title surface via CVT attrs
        elif not is_cvt_like(h) and not is_cvt_like(t):
            if sr in _EDGE_NOISY_SHORT or normalize(h) == normalize(t):
                continue
            direct.append((h, sr, t))

    # build records (CVT with holder)
    records = []
    seen_rec = set()
    for cvt, holders in cvt_holders.items():
        attrs = cvt_attrs.get(cvt, [])
        title = next((v for a, v in attrs if any(k in a for k in ("basic_title", "office_position_or_title"))), None)
        from_v = next((v for a, v in attrs if a == "from"), None)
        to_v = next((v for a, v in attrs if a == "to"), None)
        if cvt in cvt_incumbent and not to_v:
            to_v = "(incumbent)"
        juris = next((v for a, v in attrs if "jurisdiction" in a), None)
        used = {title, from_v, to_v, juris}
        extra = [(a, v) for a, v in attrs
                 if v not in used and a not in ("office_holder", "office_holders",
                     "office_position_or_title", "basic_title", "from", "to")
                 and "type" not in a and "review" not in a and not a.startswith("is_")]
        for hd in holders:
            key = ("REC", normalize(hd), normalize(title or ""), from_v or "", to_v or "")
            if key in seen_rec:
                continue
            seen_rec.add(key)
            records.append((hd, title, from_v, to_v, juris, extra))

    # fallback: CVT without holder.
    # MEASUREMENT CVTs (dated_percentage/dated_integer/dated_metric_ton — carry a
    # date+rate/number pair) are kept as PRESERVED EVENT ENTITIES so the (date, value)
    # pairing survives: render as `head --rel--> rec[date=D; value=V]` instead of
    # flattening to two independent `head --date--> D` / `head --rate--> V` lists
    # (which destroys the date↔value correspondence the model needs to pick a year).
    # Other holder-less CVTs → flatten their attrs onto the named head (edge-centric).
    _MEAS_ATTRS = {"rate", "number", "index", "amount", "cubic_meters", "days", "tons",
                   "percentage", "metric_tons", "kgoe"}
    _DATE_ATTRS = {"date", "year", "initial_date", "final_date", "valid_date",
                   "valid_from", "valid_to", "start_date", "end_date"}
    measurement_records = []   # (head, rel_short, [(attr, val)]) — one per CVT, attrs paired
    seen_meas = set()
    # a CVT is a PURE measurement (date+value, no named-entity answer) ONLY if ALL its
    # attrs are date/value/literal — if it carries a named entity (e.g. religion_percentage
    # has religion=Islam + percentage=86.1 + date), it is an ENTITY-bearing CVT and must
    # keep the old flatten path (the named entity IS the answer; the value is auxiliary).
    def _is_pure_measurement_cvts(cvt_name):
        attrs = cvt_attrs.get(cvt_name, [])
        if not attrs:
            return False
        attr_keys = {a for a, _ in attrs}
        if not (attr_keys & _MEAS_ATTRS) or not (attr_keys & _DATE_ATTRS):
            return False
        # every attr must be a meas/date attr (no named-entity-bearing attr like religion/holder/title)
        non_meas = attr_keys - _MEAS_ATTRS - _DATE_ATTRS
        return len(non_meas) == 0
    fallback = []
    for tr in all_triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if not is_cvt_like(h) and is_cvt_like(t) and t not in cvt_holders:
            if _is_pure_measurement_cvts(t):
                # preserve as one event-record line keyed by the CVT (pairing kept)
                # use the incoming relation short-name as the record type
                rel_short = _short_rel(r)
                key = ("MEAS", normalize(h), t)
                if key in seen_meas:
                    continue
                seen_meas.add(key)
                # pick the value attr (first meas attr) + the date attr
                m_attrs = cvt_attrs.get(t, [])
                val = next((v for a, v in m_attrs if a in _MEAS_ATTRS), None)
                dt = next((v for a, v in m_attrs if a in _DATE_ATTRS), None)
                if val is not None:
                    measurement_records.append((h, rel_short, dt, val))
                continue
            # CVT stays VISIBLE as the path intermediate (path fidelity — the
            # rollout data keeps CVTs as intermediate nodes; flattening attrs
            # onto the named head fabricated direct named↔named edges and hid
            # the path structure). Keep the incoming edge + hang the CVT's
            # attrs ON the CVT.
            fallback.append((h, _short_rel(r), t))
            for a, v in cvt_attrs.get(t, []):
                if is_cvt_like(v) or a in _EDGE_NOISY_SHORT or normalize(h) == normalize(v):
                    continue
                fallback.append((t, a, v))

    # dedup against shown_edges (records by record key, edges by edge key)
    n_overlap = 0
    new_records = []
    for rec in records:
        hd, title, fv, tv, juris, extra = rec
        rkey = ("REC", normalize(hd), normalize(title or ""), fv or "", tv or "")
        if rkey in shown_edges:
            n_overlap += 1; continue
        shown_edges.add(rkey)
        new_records.append(rec)
    new_direct = []
    for h, r, t in direct + fallback:
        ekey = _shown_edge_key(h, r, t)
        if ekey in shown_edges:
            n_overlap += 1; continue
        shown_edges.add(ekey)
        new_direct.append((h, r, t))

    # render
    def _attrs_str(fv, tv, juris, extra):
        parts = []
        if fv:
            parts.append(f"from={fv[:10]}")
        if tv:
            if tv == "(incumbent)":
                parts.append("to=incumbent")
            else:
                parts.append(f"to={tv[:10] if isinstance(tv, str) and len(tv) > 10 else tv}")
        if juris:
            parts.append(f"jurisdiction={juris}")
        for a, v in extra[:2]:
            parts.append(f"{a}={v}")
        return "; ".join(parts)

    # zero-information-gain compression (user principle): within a comparison
    # group, an attribute IDENTICAL across all records cannot discriminate the
    # candidates — repeating it per record only pollutes the prompt. Collapse
    # uniform attrs (jurisdiction + extra keys; from/to stay per-record — they
    # are the usual discriminators and often the literal answer) into ONE
    # "(all: k=v)" clause on the group header; varying attrs stay per-record.
    def _uniform_attrs(recs):
        def _normv(v):
            return normalize(str(v)) if v is not None else None
        uniform = []
        juris_vals = [_normv(j) for _, _, _, j, _ in recs]
        has_juris = any(v is not None for v in juris_vals)
        if has_juris and len(set(v for v in juris_vals if v is not None)) == 1 \
                and all(v is not None for v in juris_vals):
            uniform.append(("jurisdiction", recs[0][3]))
        keys = []
        for _, _, _, _, ex in recs:
            for a, _v in (ex or []):
                if a not in keys:
                    keys.append(a)
        for a in keys:
            vals = [next((v for k, v in (ex or []) if k == a), None) for _, _, _, _, ex in recs]
            if all(v is not None for v in vals) and len(set(_normv(v) for v in vals)) == 1:
                uniform.append((a, vals[0]))
        return set(a for a, _ in uniform), uniform

    lines = []
    by_title = {}
    for hd, title, fv, tv, juris, extra in new_records:
        by_title.setdefault(title or "(office)", []).append((hd, fv, tv, juris, extra))
    for title, recs in by_title.items():
        if len(recs) == 1:
            hd, fv, tv, juris, extra = recs[0]
            astr = _attrs_str(fv, tv, juris, extra)
            lines.append(f"  {hd} → {title}" + (f"  [{astr}]" if astr else ""))
        else:
            hide, uniform_kv = _uniform_attrs(recs)
            hdr = f"  {title}"
            if uniform_kv:
                hdr += f" (all: {'; '.join(f'{a}={str(v)[:24]}' for a, v in uniform_kv)})"
            lines.append(hdr + ":")
            for hd, fv, tv, juris, extra in recs:
                extra = [(a, v) for a, v in (extra or []) if a not in hide]
                if "jurisdiction" in hide:
                    juris = None
                astr = _attrs_str(fv, tv, juris, extra)
                lines.append(f"    - {hd}" + (f"  [{astr}]" if astr else ""))
    # measurement records: render as preserved event entities, (date, value) PAIRED.
    # group by (head, rel) so one country's CPI records list together, each as
    # `head --rel--> rec[date=D; value=V]` — the date↔value correspondence the model
    # needs to pick a year. Values truncated for readability.
    meas_by_hr = {}
    for h, rel, dt, val in measurement_records:
        meas_by_hr.setdefault((h, rel), []).append((dt, val))
    for (h, rel), pairs in meas_by_hr.items():
        # sort by date if present (chronological), else keep order
        def _yr(d):
            m = re.match(r"(\d{4})", str(d or ""))
            return int(m.group(1)) if m else 9999
        pairs.sort(key=lambda dv: _yr(dv[0]))
        rec_strs = []
        for dt, val in pairs:
            d = str(dt)[:7] if dt else "?"
            v = str(val)
            if re.match(r"^-?\d+\.\d{4,}$", v):
                v = str(round(float(v), 2))
            rec_strs.append(f"date={d}; value={v}")
        # cap per line to avoid explosion (many years of data)
        if len(rec_strs) > 12:
            rec_strs = rec_strs[:12] + [f"... +{len(rec_strs)-12} more"]
        lines.append(f"  {h} --{rel}--> " + " | ".join(f"[{rs}]" for rs in rec_strs))
    # BARE-CVT TAIL DROP (2026-08-19 audit): tails that are still raw m./g.
    # IDs after inlining carry NO attributes — pure noise (the Gingrich/Nordic
    # dumps showed dozens per line). Attribute-inlined CVTs ('m.xxx [k=v;..]')
    # keep their block; the walk path edges in records are unaffected.
    # UNIFORM-ATTR COLLAPSE (2026-08-21, user original design extended to the
    # inline path): CVTs on ONE pattern path often share identical attributes
    # (every personal-appearance event carries type_of_appearance=Him/Herself;
    # person=X) — zero information gain, repeated N times per line. Post-merge
    # string transform: attrs common to ALL bracketed CVTs of a line are
    # hoisted into one '(all: k=v; …)' prefix; each bracket keeps only its
    # DISCRIMINATING attrs.
    import re as _re_line
    _cvt_tok = _re_line.compile(r'\b([mg]\.[0-9a-z_]+) \[([^\]]+)\]')

    def _collapse_uniform_line(ln: str) -> str:
        toks = _cvt_tok.findall(ln)
        if len(toks) < 2:
            return ln

        def _kv(s):
            return {p.partition("=")[0].strip(): p.partition("=")[2].strip()
                    for p in s.split("; ") if "=" in p}
        first = _kv(toks[0][1])
        if not first:
            return ln
        uniform = {k: v for k, v in first.items()
                   if all(_kv(t[1]).get(k) == v for t in toks[1:])}
        if not uniform:
            return ln

        def _strip_bracket(m):
            keep = [p for p in m.group(2).split("; ")
                    if p.partition("=")[0].strip() not in uniform]
            return m.group(1) + (f" [{'; '.join(keep)}]" if keep else "")
        body = _cvt_tok.sub(_strip_bracket, ln)
        hdr = "(all: " + "; ".join(f"{k}={str(v)[:24]}" for k, v in uniform.items()) + ") "
        # attach the header right after the line's relation arrow when present
        m = _re_line.search(r'^(.*?--[^>]+-->\s*)', body)
        return (m.group(1) + hdr + body[m.end():]) if m else hdr + body

    _evs = [(h, r, t) for h, r, t in _inline_events(new_direct)
            if not (is_cvt_like(t) and "[" not in t)]
    for ln in _merge_edges(_evs):
        lines.append(f"  {_collapse_uniform_line(ln)}")
    return lines, n_overlap


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


def _norm_idx_all(ctx):
    """normalize(name) → [all entity idxs with that name] (multi-map), built
    once per ctx — the MULTI-map matters: a single-valued dict drops duplicate
    names ('Catholicism' at two idxs). Shared by _accumulate and
    _entity_correction (both rebuilt it O(V) per call in the event loop)."""
    m = getattr(ctx, "_norm_idx_multi", None)
    if m is None:
        from collections import defaultdict
        m = defaultdict(list)
        for i, e in enumerate(ctx.ents):
            if e:
                m[normalize(e)].append(i)
        ctx._norm_idx_multi = m
    return m


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
    n2i_all = _norm_idx_all(ctx)
    # DETERMINISTIC FIRST-APPEARANCE ORDER (perf-4 replay oracle, 2026-08-23):
    # the old `names = set(...)` + `for nm in names` made all_candidates
    # ordering hash-seed-dependent PER PROCESS — the same case replayed in a
    # new process emitted a differently-ordered candidate_pool (same SET).
    # dict.fromkeys dedups identically while preserving arrival order.
    ordered = list(dict.fromkeys(
        list(pe.candidates or [])
        + [x for tr in (pe.triples or []) if len(tr) == 3
           for x in (tr[0], tr[2])]))
    seen_cand = {normalize(c) for c in getattr(ctx, "all_candidates", []) or []}
    for nm in ordered:
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
    (the walk's bounds are unchanged).

    PERF (2026-08-23): the CVT expansion rescanned ALL edges 3× per call with no
    memo — a hub first call measured 324ms IN THE EVENT LOOP (blocking every
    concurrent dispatcher). The pool is deterministic per (ctx, center set), so
    the whole result is memoized per ctx; the expansion itself runs on the
    per-ctx adjacency index instead of full edge scans."""
    _memo = getattr(ctx, "_seq_pool_memo", None)
    if _memo is None:
        _memo = {}
        ctx._seq_pool_memo = _memo
    ents = frozenset(e for e in entity_set
                     if e is not None and 0 <= e < len(ctx.ents))
    if ents in _memo:
        return set(_memo[ents])
    out = set(_reach2_relids(ctx, ents))
    if ents:
        from kgqa.agent.tools import _full_adj
        adj = _full_adj(ctx)
        n_ents = len(ctx.ents)
        # 1-hop neighbors, isolate the CVT mediators
        direct = set()
        for e in ents:
            for _r, other in adj[e]:
                if 0 <= other < n_ents:
                    direct.add(other)
        cvts = {x for x in direct if is_cvt_like(ctx.ents[x])}
        if cvts:
            # entities lying behind each CVT (the CVT's other endpoints)
            behind = set()
            for cvt in cvts:
                for _r, other in adj[cvt]:
                    if 0 <= other < n_ents and other not in ents:
                        behind.add(other)
            # add relations on those behind-entities' edges (the CVT-transparent hop)
            for mid in behind:
                for r, _other in adj[mid]:
                    out.add(r)
        from kgqa.traversal.path_utils import _is_noisy_path_relation
        out = {r for r in out if not _is_noisy_path_relation(ctx.rels[r])}
    _memo[ents] = out
    return set(out)


# Walk parallelism (rollout throughput): the graph walk is pure-CPU Python, so
# gather() over cases is SERIAL under the GIL — with CASE_BATCH=1000 the LLM
# batch takes 84s while the per-round walk pile-up takes 150-200s. WALK_POOL=<n>
# runs the one-step pipeline (walk + compress + materialize + evidence build)
# in n single-worker SPAWN lanes, ONE POOL TASK PER retrieve_subgraph CALL: a
# call's centers share the case arrays, so they traverse together in one worker
# stage_5 batch (task count = calls, not centers — 7416 → ~1814 on 267×3).
# Per-CASE affinity: lane = hash(case_key) % n, each lane keeps its OWN
# sent-set — a case's ~1MB arrays ship exactly once and stay resident in that
# lane's worker cache (a shared pool paired a GLOBAL sent-set with PER-WORKER
# caches → ~2/3 of tasks MISSed and reshipped the arrays). Spawn, NOT fork:
# forked children corrupt a live vLLM EngineCore ("WorkerProc initialization
# failed"). Off by default (production HTTP eval keeps the inline path).
_WALK_LANES = None
_SENT_BY_LANE = []


def _walk_worker_init():
    """Lane-worker GC policy (walk-perf, 2026-09-07): the per-case adjacency
    memo (logical_paths/frontier/k_queue) parks large container graphs that
    make gen-2 collections scan-happy — a dense-case walk showed 300ms GC
    spikes between 4ms walks. Raise the gen-0 threshold so collections stay
    rare (walk objects are mostly acyclic; the pool recycles the worker if
    memory ever grows)."""
    import gc
    gc.set_threshold(2_000_000, 100, 100)


def _get_walk_lanes(n: int):
    """n single-worker spawn executors + the matching per-lane sent-sets.
    Created once; a later n mismatch keeps the existing lanes (same contract
    as the old shared pool)."""
    global _WALK_LANES, _SENT_BY_LANE
    if _WALK_LANES is None:
        import concurrent.futures as cf
        import multiprocessing as mp
        _spawn = mp.get_context("spawn")
        _WALK_LANES = [cf.ProcessPoolExecutor(max_workers=1, mp_context=_spawn,
                                              initializer=_walk_worker_init)
                       for _ in range(n)]
        _SENT_BY_LANE = [set() for _ in range(n)]
    return _WALK_LANES


# worker-side: case_key -> (sample, pilot_row, ents, rels, h_ids, r_ids, t_ids,
# rel_texts). Simple bounded cache (spawn workers are long-lived within a run).
_W_CASE_CACHE = {}


def _walk_case_steps(case_key, d, steps):
    """Worker-side traversal of ONE case's steps (d = its cached arrays).
    Pure: identical inputs → identical output list (per-center dict[label ->
    PatternEvidence], {} when the walk reached nothing). Shared by the
    per-call lane task (_walk_call_spawn) and the round-level batch task
    (_walk_batch_spawn).
    Step tuples are (center_idx, rel_idxs, fid) or, for a PATTERN-PREFIX
    continuation (user design 2026-09-10), (center_idx, rel_idxs, fid,
    prefix_names): the center is a tail of an earlier pattern and the
    prefix = the earlier walk's node NAMES — RPE records target edges INTO
    that territory but never expands through it (状态保持,不重复回去)."""
    sample, pilot_row, ents, rels, h_ids, r_ids, t_ids, rel_texts = d
    import asyncio as _aio
    n2i = None
    cases = []
    for step in steps:
        center_idx, rel_idxs, fid = step[0], step[1], step[2]
        cs = CaseState(case_id=case_key[0], case_num=case_key[1],
                       sample=sample, pilot_row=pilot_row)
        cs.anchor_idx = center_idx
        cs.anchor_name = ents[center_idx] if 0 <= center_idx < len(ents) else ""
        cs.h_ids, cs.r_ids, cs.t_ids = h_ids, r_ids, t_ids
        cs.ents, cs.rels, cs.rel_texts = ents, rels, rel_texts
        if isinstance(rel_idxs, tuple):
            # MULTI-STEP derived pattern (realignment spec pillar 2+3):
            # rel_idxs is a tuple of per-hop frozensets — the engine walks
            # the sequence with forward validation (chain_expand lookahead);
            # RPE falls back only on weak coverage (n_steps > 1).
            cs.step_relations = [set(x) for x in rel_idxs]
            cs.steps = [{"id": (fid or "f") + f"#s{k}"} for k in range(len(rel_idxs))]
        else:
            cs.step_relations = [set(rel_idxs)]
            cs.steps = [{"id": fid or "f"}]
        cs.breakpoints = {}
        cs.active = True
        if len(step) > 3 and step[3]:
            # names → idx set (once per call: the map is shared by all steps)
            if n2i is None:
                n2i = {}
                for j, e in enumerate(ents):
                    n2i.setdefault(str(e), j)
            cs.prefix_nodes = frozenset(
                n2i[nm] for nm in step[3]
                if nm in n2i and n2i[nm] != center_idx)
        cases.append(cs)
    try:
        _aio.run(stage_5_graph_traversal(cases))
    except Exception:
        return [{} for _ in steps]
    out = []
    for step, cs in zip(steps, cases):
        center_idx, rel_idxs = step[0], step[1]
        _sel_ids = (set().union(*rel_idxs)
                    if isinstance(rel_idxs, tuple) else set(rel_idxs))
        paths = cs.paths or []
        patterns = (compress_paths(paths, ents, rels, center_idx, set())
                    if paths else (cs.logical_paths or []))
        valid = [lp for lp in patterns if isinstance(lp, dict) and lp.get("best_raw_path")]
        valid = materialize_selected_logical_patterns(
            valid, ents, rels, h_ids, r_ids, t_ids, center_idx, set())
        if not valid:
            out.append({})
            continue
        out.append(build_pattern_evidence_triples(
            valid, ents, rels, h_ids, r_ids, t_ids, center_idx,
            max_grouped_lines=120, selected_rel_ids=_sel_ids))
    return out


def _walk_call_spawn(task):
    """Worker body for ONE retrieve_subgraph call: task = (case_key, ctx_data,
    steps) with steps = [(center_idx, rel_idxs, fid), ...]. All centers of the
    call share the case arrays, so they traverse in ONE stage_5 batch (its
    native multi-case mode — per-case state only, thread-isolated inside the
    worker). Returns a per-center list aligned with steps, each entry a
    dict[label -> PatternEvidence], or {} when that center's walk reached
    nothing; "MISS" when the case arrays are not cached (caller reships with
    data)."""
    case_key, ctx_data, steps = task
    if ctx_data is not None:
        if len(_W_CASE_CACHE) > 512:
            _W_CASE_CACHE.clear()
        _W_CASE_CACHE[case_key] = ctx_data
    d = _W_CASE_CACHE.get(case_key)
    if d is None:
        return "MISS"          # sentinel: caller reships this task with data
    return _walk_case_steps(case_key, d, steps)


def _walk_batch_spawn(payload):
    """Worker body for ONE FLUSH of the round-level coordinator: payload =
    [(case_key, ctx_data_or_None, steps), ...] — every case the flush assigned
    to THIS lane, one stage_5 batch per case. Returns a list aligned with
    payload; each entry is "MISS" (case arrays evicted — caller reships that
    one case with data) or the per-step evidence list."""
    out = []
    for case_key, ctx_data, steps in payload:
        if ctx_data is not None:
            if len(_W_CASE_CACHE) > 512:
                _W_CASE_CACHE.clear()
            _W_CASE_CACHE[case_key] = ctx_data
        d = _W_CASE_CACHE.get(case_key)
        out.append("MISS" if d is None else _walk_case_steps(case_key, d, steps))
    return out


async def _run_walk_one_step(ctx, center_idx: int, rel_idxs, fid: str,
                             prefix_names=None):
    """Inline (in-process) one-center walk: the WALK_POOL=0 path, and the exact
    per-center unit the packed worker (_walk_call_spawn) replicates off-process.
    Reuses the proven SAPS walk (stage_5_graph_traversal: multi-hop, K-path,
    CVT-penetrating) scoped to ONE step from center_idx along rel_idxs
    (prefix_names: pattern-prefix continuation, see _walk_case_steps). Mirrors
    _do_select's cs setup + walk + evidence build (tools.py:1280-1337), but for a
    single step whose anchor is the current center. Returns dict[label -> PatternEvidence]
    (each carries .triples + .candidates + .tree_data for the dense CVT-inline tree)."""
    cs = CaseState(case_id=ctx.case_id or "seq", case_num=ctx.case_num or 0,
                   sample=ctx.sample, pilot_row=ctx.pilot_row)
    cs.anchor_idx = center_idx
    cs.anchor_name = ctx.ents[center_idx] if 0 <= center_idx < len(ctx.ents) else ""
    cs.h_ids, cs.r_ids, cs.t_ids = ctx.h_ids, ctx.r_ids, ctx.t_ids
    cs.ents, cs.rels, cs.rel_texts = ctx.ents, ctx.rels, ctx.rel_texts
    if isinstance(rel_idxs, tuple):
        cs.step_relations = [set(x) for x in rel_idxs]
        cs.steps = [{"id": (fid or "f") + f"#s{k}"} for k in range(len(rel_idxs))]
    else:
        cs.step_relations = [set(rel_idxs)]        # ONE step
        cs.steps = [{"id": fid or "f"}]
    cs.breakpoints = {}
    cs.active = True
    if prefix_names:
        _n2i = {}
        for j, e in enumerate(ctx.ents):
            _n2i.setdefault(str(e), j)
        cs.prefix_nodes = frozenset(
            _n2i[nm] for nm in prefix_names
            if nm in _n2i and _n2i[nm] != center_idx)
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
        valid, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids, center_idx,
        max_grouped_lines=120,
        # tuple (multistep layer sets) must FLATTEN — set(rel_idxs) on a
        # tuple yields a set of frozensets the filter never matches (the
        # worker path at _walk_case_steps already unions; this inline
        # WALK_POOL=0 path silently lost the whole selection)
        selected_rel_ids=(set().union(*rel_idxs)
                          if isinstance(rel_idxs, tuple) else set(rel_idxs)))


def _walk_call_spawn_timed(task):
    """Affine-lane wrapper around _walk_call_spawn splitting the lane timer:
    wait = submit→worker pickup (queue depth behind other cases' tasks), exec =
    actual traversal time. task carries the parent-side submit timestamp;
    time.perf_counter() is CLOCK_MONOTONIC on Linux, so the difference is
    valid across processes. Returns (result, wait_s, exec_s)."""
    import time as _t
    t0 = _t.perf_counter()
    res = _walk_call_spawn(task[:3])
    return res, t0 - task[3], _t.perf_counter() - t0


def _walk_batch_spawn_timed(task):
    """Same timing split for a whole flush's multi-case lane task."""
    import time as _t
    t0 = _t.perf_counter()
    res = _walk_batch_spawn(task[0])
    return res, t0 - task[1], _t.perf_counter() - t0


# ─── round-level walk coordinator (perf2 2026-08-23) ─────────────────────
# The rollout is round-synchronized: after each LLM batch, every dispatcher's
# retrieve_subgraph call arrives within one burst. The per-call lane path let
# dozens of concurrent submits pile onto 3 single-worker lanes — the measured
# walk lane is ~98% queue wait. The coordinator ports the GTE server's
# ADAPTIVE two-stage window: the first arrival opens a short FIRST slice; a
# second arrival within it extends the deadline to the FULL window counted
# from the first arrival (a burst); a LONE request flushes right after the
# first slice — no fixed full-window tax on single/tail requests. At flush:
# identical (center, rels) steps across the batch share one execution slot
# (G=3 lockstep trajectories emit identical deterministic walks), cases are
# grouped and sticky-balanced onto the affine lanes by slot count, and each
# lane receives ONE packed multi-case task (queue depth 1/lane per flush).
# Completed slots are memoized for cross-batch reuse (reworded loops).
# Env: WALK_BATCH_WINDOW (full window s, default 1.0; <=0 = legacy per-call
# lane path), WALK_BATCH_FIRST (first slice s, default 0.3).
_WALK_BATCH = None                       # open collection batch or None
_WALK_CASE_LANE = {}                     # case_key -> lane idx (sticky residency)
_WALK_MEMO = {}                          # case_key -> {(center_idx, frozenset): pe}
_WALK_MEMO_MAX_CASES = 96
_WALK_BATCH_STATS = {"batches": 0, "single": 0, "burst": 0, "reqs": 0,
                     "slots": 0, "memo_hits": 0, "dedup_shares": 0,
                     "ipc_bytes": 0.0, "collect_s": 0.0, "burst_span_s": 0.0}


def _walk_batch_enqueue(loop, ctx, case_key, steps):
    """Register one request on the open batch (opening one if none) and return
    its future. The flush callback is scheduled here (see the adaptive window
    above). ctx rides along only to ship the case arrays on first sight."""
    global _WALK_BATCH
    import time as _t
    if _WALK_BATCH is None:
        _first = float(os.environ.get("WALK_BATCH_FIRST", "0.3") or 0)
        _WALK_BATCH = {"loop": loop, "reqs": [], "t_first": _t.perf_counter()}
        _WALK_BATCH["cb"] = loop.call_later(
            max(_first, 0.001), _walk_flush_check)
    fut = loop.create_future()
    _WALK_BATCH["reqs"].append({"ctx": ctx, "case_key": case_key,
                                "steps": steps, "t0": _t.perf_counter(),
                                "fut": fut})
    return fut


def _walk_flush_check():
    """Fires at the end of the FIRST slice: flush now unless the slice saw a
    second arrival — that signals the round's burst, so extend to the FULL
    window counted from the first arrival (mirrors the GTE _collect_batch
    adaptive two-stage window)."""
    b = _WALK_BATCH
    if b is None:
        return
    if len(b["reqs"]) > 1:
        import time as _t
        _full = float(os.environ.get("WALK_BATCH_WINDOW", "1.0") or 0)
        remain = (b["t_first"] + _full) - _t.perf_counter()
        if remain > 0:
            b["loop"].call_later(remain, _walk_flush_now)
            return
    _walk_flush_now()


def _walk_flush_now():
    """Close the open batch (later arrivals open a fresh one) and hand it to
    the async flusher."""
    global _WALK_BATCH
    b, _WALK_BATCH = _WALK_BATCH, None
    if b is not None and b["reqs"]:
        b["loop"].create_task(_walk_flush_async(b))


async def _walk_flush_async(batch):
    """One flush: dedup → memo lookup → sticky lane grouping (ONE packed task
    per lane) → MISS reship → memo fill → resolve every request future."""
    import asyncio as _aio
    import pickle as _pkl
    import time as _t
    from kgqa.core.utils import PHASE_TIMES
    reqs = batch["reqs"]
    st = _WALK_BATCH_STATS
    n_req_steps = sum(len(r["steps"]) for r in reqs)
    t_flush = _t.perf_counter()
    st["batches"] += 1
    st["single" if len(reqs) == 1 else "burst"] += 1
    st["reqs"] += len(reqs)
    st["collect_s"] += sum(t_flush - r["t0"] for r in reqs)
    st["burst_span_s"] += max(r["t0"] for r in reqs) - min(r["t0"] for r in reqs)
    PHASE_TIMES["walk_collect"] += sum(t_flush - r["t0"] for r in reqs)
    # flush WALL (first arrival → every future resolved) — the batch-view cost;
    # flushes overlap each other/GTE, so the SUM upper-bounds the walk share.
    _t_first = min(r["t0"] for r in reqs)
    try:
        # 1. unique execution slots per case, memo hits served for free.
        # slot key = (center_idx, frozenset(rel_idxs), prefix) — the walk
        # consumes rel_idxs as a SET, so order never affects the result; the
        # PATTERN-PREFIX set (continuation walks, user design 2026-09-10) is
        # part of the identity: the same center+rels walked with a different
        # prefix is a different result.
        def _step_key(s):
            i, rel_idxs = s[0], s[1]
            _pf = s[3] if len(s) > 3 else None
            # MULTI-STEP sequences (tuple of per-hop frozensets) key by the
            # ordered sequence itself — hop ORDER is the pattern's identity
            return (i, rel_idxs if isinstance(rel_idxs, tuple)
                    else frozenset(rel_idxs), _pf)

        case_slots, case_ctx = {}, {}
        for r in reqs:
            ck = r["case_key"]
            slots = case_slots.setdefault(ck, {})
            case_ctx.setdefault(ck, r["ctx"])
            for s in r["steps"]:
                slots.setdefault(_step_key(s), (s[0], s[1],
                                                s[3] if len(s) > 3 else None))
        # memo-covered slots are NOT re-executed: drop them from the lane
        # payload, and resolve requests whose steps are ALL memo hits right
        # now (they must not wait out the lane tasks).
        n_memo = 0
        pending = {}
        for ck, slots in case_slots.items():
            mcase = _WALK_MEMO.get(ck) or {}
            pend = {}
            for k, step in slots.items():
                if k in mcase:
                    n_memo += 1
                else:
                    pend[k] = step
            pending[ck] = pend
        done_reqs = []
        for r in reqs:
            ck = r["case_key"]
            mcase = _WALK_MEMO.get(ck) or {}
            if all(_step_key(s) in mcase for s in r["steps"]):
                if not r["fut"].done():
                    r["fut"].set_result([mcase[_step_key(s)] for s in r["steps"]])
                done_reqs.append(r)
        done_ids = {id(r) for r in done_reqs}
        reqs = [r for r in reqs if id(r) not in done_ids]
        n_slots = sum(len(p) for p in pending.values())
        st["memo_hits"] += n_memo
        st["slots"] += n_slots
        st["dedup_shares"] += n_req_steps - n_slots - n_memo
        if not reqs:
            return
        # 2. sticky lane assignment over the PENDING (non-memo) slots:
        # existing map / resident sent-set first, then NEW cases greedy-LPT
        # by slot count (balanced AND resident).
        lanes = _get_walk_lanes(int(os.environ.get("WALK_POOL", "0") or 0))
        n = len(lanes)
        load = [0] * n
        by_lane = [[] for _ in range(n)]
        run_cases = [ck for ck in case_slots if pending[ck]]
        for ck in run_cases:
            lane = _WALK_CASE_LANE.get(ck)
            if lane is None:
                lane = next((i for i, s in enumerate(_SENT_BY_LANE) if ck in s),
                            None)
            if lane is not None and 0 <= lane < n:
                _WALK_CASE_LANE[ck] = lane
                by_lane[lane].append(ck)
                load[lane] += len(pending[ck])
        for ck in sorted((c for c in run_cases if c not in _WALK_CASE_LANE),
                         key=lambda c: -len(pending[c])):
            lane = min(range(n), key=lambda i: load[i])
            _WALK_CASE_LANE[ck] = lane
            by_lane[lane].append(ck)
            load[lane] += len(pending[ck])
        # 3. one packed task per lane: ship the arrays of cases this lane has
        # not seen yet (sticky lanes keep them resident across rounds).
        loop = batch["loop"]
        t_submit = _t.perf_counter()
        lane_jobs = []
        for li in range(n):
            if not by_lane[li]:
                continue
            payload = []
            for ck in by_lane[li]:
                ctx_data = None
                if ck not in _SENT_BY_LANE[li]:
                    ctx = case_ctx[ck]
                    ctx_data = (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                                ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts)
                    _SENT_BY_LANE[li].add(ck)
                payload.append((ck, ctx_data,
                                [(i, rel_idxs, "", pf) for i, rel_idxs, pf
                                 in pending[ck].values()]))
            lane_jobs.append((li, payload, loop.run_in_executor(
                lanes[li], _walk_batch_spawn_timed, (payload, t_submit))))
        results = await _aio.gather(*(j[2] for j in lane_jobs),
                                    return_exceptions=True)
        # lane results are (entry_list, lane_wait, lane_exec) — accumulate the
        # wait/exec split (queue wait behind other lanes' tasks vs traversal).
        slot_pe = {}
        reship = {}
        for (li, payload, _f), res in zip(lane_jobs, results):
            if isinstance(res, BaseException):
                # crashed lane job (huge-flush pickling/OOM) — visible, not
                # silent: affected slots resolve {} ("walk reached nothing")
                import sys as _sys
                print(f"  ⚠ walk lane job failed (lane {li}, {len(payload)} cases): "
                      f"{type(res).__name__}: {res}", file=_sys.stderr, flush=True)
                continue                       # crashed lane → {} per slot below
            entries, _wait, _exec = res
            PHASE_TIMES["walk_wait"] += _wait
            PHASE_TIMES["walk_exec"] += _exec
            st["ipc_bytes"] += len(_pkl.dumps(entries, protocol=4))
            for (ck, _d, steps), entry in zip(payload, entries):
                if entry == "MISS":
                    reship.setdefault(li, []).append(ck)
                else:
                    for s, pe in zip(steps, entry):
                        _pf = s[3] if len(s) > 3 else None
                        slot_pe.setdefault(
                            (ck, s[0], frozenset(s[1]), _pf), pe)
        if reship:
            # 4. worker cache evicted for these cases → reship WITH data on the
            # SAME lanes (sticky), one follow-up task per affected lane.
            jobs2 = []
            for li, cks in reship.items():
                payload = []
                for ck in cks:
                    ctx = case_ctx[ck]
                    payload.append((ck,
                                    (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                                     ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts),
                                    [(i, rel_idxs, "", pf) for i, rel_idxs, pf
                                     in pending[ck].values()]))
                jobs2.append((payload, loop.run_in_executor(
                    lanes[li], _walk_batch_spawn_timed,
                    (payload, _t.perf_counter()))))
            for (payload, _f), res in zip(
                    jobs2, await _aio.gather(*(f for _, f in jobs2),
                                             return_exceptions=True)):
                if isinstance(res, BaseException):
                    continue
                entries, _wait, _exec = res
                PHASE_TIMES["walk_wait"] += _wait
                PHASE_TIMES["walk_exec"] += _exec
                for (ck, _d, steps), entry in zip(payload, entries):
                    if entry == "MISS":
                        continue
                    for s, pe in zip(steps, entry):
                        _pf = s[3] if len(s) > 3 else None
                        slot_pe.setdefault(
                            (ck, s[0], frozenset(s[1]), _pf), pe)
        # 5. fill the cross-batch memo (evict whole oldest cases when bound).
        for (ck, i, rels_fs, _pf), pe in slot_pe.items():
            mcase = _WALK_MEMO.get(ck)
            if mcase is None:
                if len(_WALK_MEMO) >= _WALK_MEMO_MAX_CASES:
                    _WALK_MEMO.pop(next(iter(_WALK_MEMO)))
                mcase = _WALK_MEMO[ck] = {}
            mcase[(i, rels_fs, _pf)] = pe
        # 6. resolve every request from memo + fresh slots.
        for r in reqs:
            ck = r["case_key"]
            mcase = _WALK_MEMO.get(ck) or {}
            out = []
            for s in r["steps"]:
                _pf = s[3] if len(s) > 3 else None
                k = (s[0], frozenset(s[1]), _pf)
                pe = mcase.get(k)
                if pe is None:
                    pe = slot_pe.get((ck, s[0], k[1], _pf), {})
                out.append(pe)
            if not r["fut"].done():
                r["fut"].set_result(out)
    except Exception:
        # never leave a waiter hanging: the legacy per-call path returned
        # [{} for steps] on failure — resolve the same way.
        for r in reqs:
            if not r["fut"].done():
                r["fut"].set_result([{} for _ in r["steps"]])
    finally:
        PHASE_TIMES["walk_flush_wall"] = \
            PHASE_TIMES.get("walk_flush_wall", 0.0) + (_t.perf_counter() - _t_first)


async def _run_walk_coordinated(ctx, case_key, steps):
    """Coordinator entry: enqueue and await the flush's result."""
    import asyncio as _aio
    fut = _walk_batch_enqueue(_aio.get_running_loop(), ctx, case_key, steps)
    try:
        return await fut
    except Exception:
        return [{} for _ in steps]


async def _run_walk_lane(ctx, case_key, steps, pool_n):
    """Legacy per-call lane path (WALK_POOL>0, WALK_BATCH_WINDOW<=0): ONE
    packed task per retrieve_subgraph CALL on the case's hash-affine lane.
    Kept for non-round-synced callers (per-case runner)."""
    lanes = _get_walk_lanes(pool_n)
    lane_i = hash(case_key) % len(lanes)
    lane, sent = lanes[lane_i], _SENT_BY_LANE[lane_i]
    ctx_data = None
    if case_key not in sent:
        ctx_data = (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                    ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts)
        sent.add(case_key)
    import asyncio as _aio
    import time as _t
    from kgqa.core.utils import PHASE_TIMES
    loop = _aio.get_running_loop()

    async def _submit(ctx_data):
        return await loop.run_in_executor(
            lane, _walk_call_spawn_timed,
            (case_key, ctx_data, steps, _t.perf_counter()))

    try:
        res, _wait, _exec = await _submit(ctx_data)
    except Exception:
        return [{} for _ in steps]
    if res == "MISS":
        # worker cache was evicted — reship once WITH the case arrays, on the
        # SAME lane (affinity must not wobble on the retry)
        sent.add(case_key)
        try:
            res, _wait2, _exec2 = await _submit(
                (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                 ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts))
        except Exception:
            return [{} for _ in steps]
        _wait += _wait2
        _exec += _exec2
    # wait = lane-queue time (submit→pickup); exec = traversal time in the
    # worker. walk − (wait+exec) is parent-side pickle/event-loop overhead.
    PHASE_TIMES["walk_wait"] += _wait
    PHASE_TIMES["walk_exec"] += _exec
    return res


async def _run_walk_packed(ctx, steps):
    """All centers of ONE retrieve_subgraph call → per-center evidence dicts
    aligned with steps (accumulate/collect side effects stay in the caller —
    they write ctx). WALK_POOL=0/unset: inline per-center walk. WALK_POOL>0 +
    WALK_BATCH_WINDOW>0: the round-level coordinator (rollout path). WALK_POOL>0
    otherwise: the legacy per-call affine-lane submit."""
    _pool_n = int(os.environ.get("WALK_POOL", "0") or 0)
    if _pool_n <= 0:
        return [await _run_walk_one_step(
                    ctx, s[0], s[1], s[2],
                    s[3] if len(s) > 3 else None)
                for s in steps]
    case_key = (ctx.case_id or "seq", ctx.case_num or 0)
    if float(os.environ.get("WALK_BATCH_WINDOW", "0") or 0) > 0:
        return await _run_walk_coordinated(ctx, case_key, steps)
    return await _run_walk_lane(ctx, case_key, steps, _pool_n)


# ───────────────────────── decompose (declare + seed anchor; no grounding) ─────────────────────────

def _do_seq_decompose(args: Dict[str, Any], ctx, session=None) -> str:
    """SEQ decompose: declare the fact sequence + step-1 anchor. Does NOT ground — each
    fact is grounded by the model's own retrieve_relations call. Seeds ctx.subgraph_entities
    with the anchor so fact-1's center passes the boundary.
    Plan-contract v2 (2026-08-21): the plan is IMMUTABLE after declaration — a second
    plan call is rejected with a close-only directive (facts may be closed ✓/✗, never
    added). The declared answer_type word is captured and echoed at answer time."""
    # immutability gate: one plan per episode
    if getattr(ctx, "plan_declared", False):
        return _json_result({
            "error": "REJECTED: the plan was already declared — do NOT re-emit it. "
                     "To ADD evidence for an uncovered contract requirement, emit "
                     "an append-only extension instead:\n"
                     "[PLAN EXTEND]\ncovers: R2\n\nsg2.anchor: <question entity>\n"
                     "sg2.f1: <head> | <sub-question> | ?var\n\n"
                     "To change RELATIONS or CENTER of an existing fact, just "
                     "re-call retrieve_relations/retrieve_subgraph — the plan "
                     "locks facts, not retrieval choices.",
            "note": ("The plan is a closed contract. Its only legal transitions are "
                     "checkpoints (one md line per fact): `- fid ✓ ?var = v1 | v2` (resolved), "
                     "`- fid ✗ empty` (the reachable pool holds no relation advancing "
                     "this fact), `[fid ✗ moot]` (earlier evidence already bound this "
                     "fact's target). Continue the workflow with retrieve_relations / "
                     "retrieve_subgraph on the next OPEN fact. Answer when "
                     "every fact that can constrain/discriminate the answer variable "
                     "is closed — binding the variable early is AVAILABLE, not READY.")})
    # answer_type REQUIRED (2026-08-21, CH specimen: the model planned ?language
    # for a "which COUNTRIES" question — the optional type word let the inverted
    # answer slot through). The gate forces the turn-0 type commitment; a plan
    # whose answer slot contradicts the type word surfaces immediately.
    # (harness validate pre-checks this so a rejection never leaves the state
    # machine in RETRIEVE — kept here as the backstop.)
    _at = str(args.get("answer_type", "") or "").strip()
    if not _at:
        return _json_result({
            "error": "REJECTED: plan requires `answer_type` — ONE word for what the "
                     "question asks for (person, country, movie, year, language, ...), "
                     "derived from the question's interrogative. Re-emit the plan with it.",
        })
    ctx.plan_answer_type = _at
    # set only AFTER every rejection gate: a rejected plan must not poison the
    # immutability flag (the model's corrected re-emission must go through)
    ctx.plan_declared = True
    entities = args.get("entities") or []
    if isinstance(entities, str):
        entities = [a.strip() for a in entities.split(",") if a.strip()]
    if entities and not ctx.anchor_name:
        ctx.anchor_name = entities[0]
    # declared plan entities — the answer-time consumption gate compares
    # these against ctx.consumed_anchors (retrieval starts)
    ctx.plan_entities = [str(e).strip() for e in entities if str(e).strip()]
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
    # MULTI-ANCHOR REMINDER (user ruling 2026-09-01, 1171 specimen): a declared
    # entity that never LITERALLY heads a fact can only arrive as a constraint
    # tail — its own neighborhood (roster/members/siblings) never gets walked,
    # so the fact that filters on it discriminates nothing (single-candidate
    # binding + empty filter → satisficed wrong answer). One short nudge at
    # plan time (Arizona gate lesson: keep nudge text minimal).
    # Wave-1: nudge text aligned with the dual PLAN EXTEND gate — extending is
    # legal either to COVER_MISSING or to ADD_ANCHOR_VIEW, not only to cover.
    anchored = set()
    for fid in ctx.fact_ids:
        head = (ctx.fact_texts.get(fid, "").strip("()")
                .split("|") + [""])[0].strip().lower()
        if head and not head.startswith("?"):
            anchored.add(head)
    for k, v in (args or {}).items():          # sgN.anchor specs, any format
        if str(k).endswith(".anchor") and isinstance(v, str) \
                and v.strip() and not v.strip().startswith("?"):
            anchored.add(v.strip().lower())
        if isinstance(v, list):                 # structured subgraphs payload
            for sg in v:
                if isinstance(sg, dict):
                    a = str(sg.get("anchor") or "").strip()
                    if a and not a.startswith("?"):
                        anchored.add(a.lower())
    unused = [str(e).strip() for e in entities
              if str(e).strip() and str(e).strip().lower() not in anchored]
    _ma = ""
    if len(entities) >= 2 and unused:
        _ma = ("declared entity " +
               " | ".join(f"'{u}'" for u in unused[:3]) +
               " never anchors a fact — it can only filter. When its own "
               "roster/membership is the candidate pool, anchor a fact ON it "
               "([PLAN EXTEND]) and intersect; anchored retrieval "
               "discriminates better than tail-filtering. [PLAN EXTEND] is "
               "legal for either reason: COVER_MISSING (the requirement is "
               "not yet covered) or ADD_ANCHOR_VIEW (a second anchored "
               "evidence view on a DIFFERENT declared question entity — "
               "legal even when the requirement is already covered).")
    result = {
        "flow": flow, "entities": entities, "answer": args.get("answer", ""),
        "answer_type": str(args.get("answer_type", "") or "").strip(),
    }
    if _ma:
        # SEPARATE FIELD (2026-09-01: buried in the note the model ignored
        # it — 1171 V37e specimen, reminder present, plan unchanged)
        result["multi_anchor"] = _ma
    result["note"] = ("Iterative subgraph retrieval. For EACH OPEN fact: call "
                      "retrieve_relations to find question-RELEVANT relations (all that "
                      "match, typically ≤3, max 5 — not just the single best), then "
                      "retrieve_subgraph with ALL of them together. After each "
                      "retrieve_subgraph, close the fact with ONE of three checkpoints: "
                      "resolve it `- fid ✓ ?var = v1 | v2`; close it EMPTY "
                      "`- fid ✗ empty` when no candidate relation advances it; close it "
                      "MOOT `[fid ✗ moot]` when earlier evidence already bound its target. "
                      "MULTI-TREE (question names SEVERAL entities): prefer a "
                      "separate anchor view per entity when the entities provide "
                      "independent constraints, and let the system JOIN them (an "
                      "entity reachable from both sides intersects the candidate "
                      "sets); an entity that adds no independent constraint does "
                      "not need its own tree. For later facts continuing the "
                      "SAME tree, just pass the ANCHOR or any retrieved entity + the "
                      "new relation — the system walks the full chain from the root "
                      "automatically. Fact-1 center = the literal named anchor. "
                      "The system auto-penetrates CVTs.")
    return _json_result(result)


# ───────────────────────── retrieve_relations (GTE per entity+question) ─────────────────────────
# THREE-PHASE SPLIT (perf-4, 2026-08-23): _rr_prepare (A: pure CPU — entity
# resolution + memoized pool construction) → _rr_execute (B: the GTE awaits,
# batched by the round-level collector) → _rr_finalize (C: pure CPU — ranking
# merge + result rendering). The public async retrieve_relations keeps the
# sequential composition; the round-level scheduler drives the phases directly.

def _rr_prepare(args: Dict[str, Any], ctx) -> dict:
    """A段: terminal errors render here (kind="done"); an unresolvable entity
    defers to the GTE correction in execute (kind="corr"); the clean path
    emits the per-entity GTE requests (kind="rr")."""
    raw = args.get("center") or args.get("entities") or ([args.get("entity")] if args.get("entity") else [])
    entities = _split_pipe_entities([str(e) for e in raw if e])
    question = args.get("question") or args.get("subquestion") or ""
    if not entities:
        return {"kind": "done", "result": _json_result({"error": "no entity provided."})}
    entities, _err = _expand_entities(entities, ctx)
    if _err:
        return {"kind": "done", "result": _json_result({"error": _err})}
    _nudge = _variable_nudge(raw, ctx)
    # Entity resolution: for non-resolving centers, offer GTE correction candidates
    # (non-blocking — model picks one OR continues with current evidence). For values
    # and no-candidate cases, skip (lenient — don't block the workflow).
    idxs, unresolved = [], []
    for e in entities:
        i = _name_to_idx(e, ctx)
        if _looks_like_value(e) and (i is None or normalize(e) != normalize(ctx.ents[i])):
            unresolved.append(e); continue                      # value-like → skip
        if i is None or _match_sim(e, ctx.ents[i]) < 0.95:
            return {"kind": "corr", "entity": e, "question": question, "nudge": _nudge}
        if not _in_subgraph(i, ctx):
            # Entity IS in the graph (resolved well) but wasn't retrieved in a prior
            # subgraph — DISTINCT from the resolution error above. Give feedback.
            return {"kind": "done", "result": _json_result({
                "entity_error": f"'{e}' is in the graph but was not retrieved in any "
                    "prior retrieve_subgraph.",
                "note": f"A center must come from a prior retrieve_subgraph's triples "
                    f"(or the plan anchor for fact 1). '{e}' wasn't in any prior result. "
                    "If it's a variable binding, pass the ?VARIABLE. Otherwise, retrieve "
                    "from the question's named entity first. "
                    "WORKFLOW: retrieve_relations → retrieve_subgraph."})}
        idxs.append(i)
    if not idxs:
        return {"kind": "done", "result": _json_result({
            "entities": entities, "question": question,
            "candidate_relations": [],
            "note": ((_nudge + " ") if _nudge else "") +
                    f"No valid center resolved from {entities} "
                    f"(skipped: {unresolved}). Continue with current "
                    "evidence — answer from what you have, or try a "
                    "different entity from the question / a previous "
                    "retrieve_subgraph's triples."})}
    # GTE per-entity (NOT a generic "these entities" head). A multi-entity call is a
    # variable expansion (?var → several bindings); each entity's relevant relations
    # differ. One generic-head call on the union pool loses the entity-specific ranking
    # signal — e.g. [San Francisco Giants, Crazy Crab] for "last win World Series"
    # dropped `sports.sports_team.championships` (ranked #1 for the Giants alone) out
    # of the top-15, surfacing only generic season/stats relations. So rank each
    # entity's OWN pool with its OWN name, then union (dedup, per-entity rank order).
    reqs = []
    for ent, i in zip(entities, idxs):
        ent_pool = _seq_pool_relids(ctx, {i})
        if len(ent_pool) < _GTE_POOL_MIN:
            ent_pool = set(range(len(ctx.rels)))
        reqs.append((ent, ent_pool))
    # SEQUENCE-FRONTIER POOL (SEQ_REL_SEQ): when a passed entity IS an anchor
    # with declared layers, the next-layer relations live on the sequence's
    # CURRENT FRONTIER (its completions) — a discriminator ask over the
    # anchor must rank from there, not from the anchor's own 2-hop pool (the
    # runtime specimen: film.film.runtime is unreachable from Taylor Lautner
    # but first-class from the actor.film completions). One anchor match is
    # enough; the union-then-rank merge folds the extra pool in.
    if os.environ.get("SEQ_REL_SEQ", "1") == "1":
        _ast = getattr(ctx, "anchor_seqs", None) or {}
        for ent, i in zip(entities, idxs):
            _layers = _ast.get(i)
            if not _layers:
                continue
            from kgqa.traversal.pattern_walk import get_pattern_index
            _front = _seq_completions(ctx, get_pattern_index(ctx), i, _layers)[-1]
            if _front and _front != {i}:
                reqs.append((ent, _seq_pool_relids(ctx, _front)))
            break
    return {"kind": "rr", "requests": reqs, "entities": entities,
            "question": question, "nudge": _nudge}


async def _rr_execute(treq, ctx, session):
    """B段: the GTE correction (or the ranking awaits).

    UNION-THEN-RANK (user ruling 2026-09-14): the candidate pool is the
    UNION of all requesting entities' reachable relations, and ONE labeled
    GTE ranking orders that union by the sub-question. The old path ranked
    each entity separately (top-15 each) and concatenated in entity order —
    a relation ranked #16 for every entity never entered the union, and a
    later entity's #1 sat behind the first entity's cluster. Entity
    specificity is preserved by the candidate LABELS ("entity | relation |
    ?" — one label per relation, headed by an entity that actually reaches
    it); the Giants/Crazy Crab failure that motivated per-entity CALLS was
    a generic head, not a specific one. Also saves N-1 GTE round-trips.

    ATTRIBUTE-FIRST RANKING (user design 2026-09-08): one GTE call ranks
    BOTH the attribute names AND the full relation names together. The
    attribute ranking identifies the question's target semantic role; the
    relation ranking provides secondary ordering within each attribute
    group — no extra GTE call needed."""
    if treq["kind"] == "corr":
        cands = await _entity_correction(treq["entity"], treq["question"], ctx, session)
        return {"cands": cands}
    if os.environ.get("SEQ_RR_UNION_RANK", "1") == "1":
        from kgqa.agent.tools import _rel_last2, _TRIPLE_GTE_INSTRUCT
        from kgqa.stages.stage2_entity import gte_retrieve
        pool_ids = sorted({i for _ent, pool in treq["requests"] for i in pool})
        head_of = {}
        for ent, pool in treq["requests"]:
            for i in pool:
                head_of.setdefault(i, ent)
        pool_names = [str(ctx.rels[i]) if 0 <= i < len(ctx.rels) else ""
                      for i in pool_ids]
        labeled = [f"{head_of.get(i, '?')} | {_rel_last2(ctx.rels[i])} | ?"
                   for i in pool_ids]
        name2pos = {n: k for k, n in enumerate(pool_names) if n}
        rows = await gte_retrieve(session, treq["question"], pool_names,
                                  candidate_texts=labeled,
                                  top_k=30, instruct=_TRIPLE_GTE_INSTRUCT)
        cands = []
        for r in rows or []:
            pos = r.get("index")
            try:
                pos = int(pos)
            except (TypeError, ValueError):
                pos = None
            if not (isinstance(pos, int) and 0 <= pos < len(pool_ids)):
                pos = name2pos.get(r.get("candidate"))
            if isinstance(pos, int) and 0 <= pos < len(pool_ids):
                full = pool_ids[pos]
                if full not in cands:
                    cands.append(full)
    else:
        cands, seen = [], set()
        for ent, pool in treq["requests"]:
            ranked = await _gte_for_triple(ctx, session, ent, treq["question"], "",
                                           pool_relids=pool)
            for r in ranked:
                if r not in seen:
                    seen.add(r); cands.append(r)
    # ATTRIBUTE-FIRST: derive attribute names from the ranked relations and
    # rank them in the SAME GTE call (add as extra candidates — piggyback,
    # no second round-trip). We use the /retrieve endpoint directly since
    # _gte_for_triple works on indices, not names.
    try:
        from kgqa.stages.stage2_entity import gte_retrieve, GTE_INSTRUCT
        # cands are relation INDICES — convert to full names first
        pool_rel_names = [str(ctx.rels[i]) for i in cands
                          if 0 <= i < len(ctx.rels)]
        attr_names = sorted({r.rsplit(".", 1)[-1] for r in pool_rel_names
                             if "." in r})
        # GLOBAL SEMANTIC MERGE (user ruling 2026-09-14, deflator specimen):
        # re-rank the WHOLE per-entity union, not the first 15 by entity
        # order. cands is concatenated in ENTITY order (per-entity GTE
        # scores are dropped at _gte_for_triple's boundary), so [:15] is
        # the first entity's cluster — a later entity's #1 (Monaco's
        # gdp_deflator_change, GTE 0.51, union position ~29) never entered
        # the re-rank and the menu showed the first entity's generic
        # relations. Re-ranking all union members by the SAME question
        # restores semantic order for every entity's contributions.
        if os.environ.get("SEQ_RR_GLOBAL_MERGE", "1") == "1":
            merged_pool = pool_rel_names[:int(os.environ.get(
                "SEQ_RR_MERGE_CAP", "80"))]
        else:
            merged_pool = pool_rel_names[:15]
        combined = attr_names + merged_pool
        rows = await gte_retrieve(session, treq["question"], combined,
                                  top_k=len(combined), instruct=GTE_INSTRUCT)
        ranked_combined = [r.get("candidate") for r in (rows or [])
                           if r.get("candidate") in combined]
        attr_set = set(attr_names)
        attr_ranked = [c for c in ranked_combined if c in attr_set]
        rel_ranked = [c for c in ranked_combined if c not in attr_set]
        attr_ranked += [a for a in attr_names if a not in set(attr_ranked)]
        rel_ranked += [r for r in merged_pool if r not in set(rel_ranked)]
        return {"cands": cands, "attr_ranked": attr_ranked, "rel_ranked": rel_ranked}
    except Exception:
        return {"cands": cands}


def _rr_finalize(treq, bres, ctx) -> str:
    """C段: render the correction / ranking result (pure CPU)."""
    if treq["kind"] == "corr":
        e = treq["entity"]
        cands = bres["cands"]
        if cands:
            return _json_result({
                "entity_error": f"'{e}' is not a confident graph entity.",
                "candidates": cands,
                "note": "Pick the correct entity from `candidates` (each shows "
                        "NEIGHBOR relations to disambiguate) and RE-CALL with THAT "
                        "name (a different name passes the repeat gate). If NONE of "
                        "the candidates is the right entity, do NOT re-call with the "
                        "same name (it will be rejected) — declare "
                        "`- fid ✗ empty` for this fact or continue from another "
                        "question entity's evidence. CROSS-SUBGRAPH CENTER: if "
                        "THIS fact's selected relations are right but its anchor "
                        "entity is wrong, re-call retrieve_subgraph with a center "
                        "BORROWED from any prior subgraph's evidence (e.g. an "
                        "earlier fact's binding) plus this fact's relations — the "
                        "boundary check accepts any retrieved entity as a center."})
        # No candidates found — GTE searched and found nothing confident.
        # Give the model FEEDBACK (not silent skip) so it can adjust.
        return _json_result({
            "entity_error": f"'{e}' was not found in the graph and no similar "
                "entities were detected by the system's search.",
            "note": f"The system searched for entities matching '{e}' but found "
                "nothing confident. This entity may not exist in this graph snapshot, "
                "or its name may be very different. Try a different entity from the "
                "question, or if this is a later fact, pick an entity from a previous "
                "retrieve_subgraph's triples. "
                "WORKFLOW: retrieve_relations → retrieve_subgraph."})
    _nudge = treq["nudge"]
    cands = bres["cands"]
    # TYPE+ATTRIBUTE GROUPED DISPLAY (user audit 2026-09-09): grouping by
    # the last component alone collapsed semantically different relations
    # (film.producer.film and film.director.film both showed as 'film';
    # division/facility/league/location all as 'teams') and the model could
    # neither see nor express the from/to difference. Group key is now the
    # TYPE+ATTRIBUTE (last TWO components — freebase domain.type.attribute),
    # so each group is one semantic relation family. Ordering stays
    # attribute-first: the GTE attribute ranking orders groups; within a
    # group, relation GTE rank orders members.
    attr_ranked = bres.get("attr_ranked") or []
    rel_ranked = bres.get("rel_ranked") or []
    _ATTR_GROUP_THRESHOLD = 5
    if attr_ranked and rel_ranked:
        from collections import defaultdict as _dd

        def _typed(r: str) -> str:
            return ".".join(r.rsplit(".", 2)[-2:])

        groups = _dd(list)          # typed key -> [full rel names, GTE-ordered]
        rel_set = set(rel_ranked)
        for r in rel_ranked:
            groups[_typed(r)].append(r)
        # also include relations from the original cands that GTE didn't rank
        # (cands are indices — convert, fill the tail of each group)
        for i in cands[:30]:
            if not isinstance(i, int) or not (0 <= i < len(ctx.rels)):
                continue
            r = str(ctx.rels[i])
            if r not in rel_set and "." in r:
                t = _typed(r)
                if t in groups:
                    groups[t].append(r)
        lines = []
        # ORDERING (user ruling 2026-09-09): ① attributes by GTE rank;
        # ② within an attribute, typed groups sorted by type+attribute key
        # (deterministic — dict insertion order varied with GTE rel rank).
        for attr in attr_ranked:    # attribute GTE rank orders the sections
            for t in sorted(t for t in groups
                            if groups[t] and t.rsplit(".", 1)[-1] == attr):
                members = groups[t]
                shown = members[:_ATTR_GROUP_THRESHOLD]
                more = (f" …(+{len(members)-_ATTR_GROUP_THRESHOLD})"
                        if len(members) > _ATTR_GROUP_THRESHOLD else "")
                # SEMANTIC-EQUIVALENCE MARKER (user ruling 2026-09-15):
                # same domain.type prefix + same attribute base = likely
                # semantic equivalents (adjoins ≡ adjoin_s) — signal "these
                # belong in ONE submission, not split across calls"
                _pref = t.rsplit(".", 1)[0]
                _equiv = [m for m in shown if m.rsplit(".", 1)[0] == _pref]
                _mark = " ≡" if len(_equiv) > 1 else ""
                lines.append(f"{t} ← {', '.join(shown)}{more}{_mark}")
                if len(lines) >= 12:
                    break
            if len(lines) >= 12:
                break
        if lines:
            _grouped = "\n".join(f"  {ln}" for ln in lines)
            _apos = {a: i for i, a in enumerate(attr_ranked)}

            def _order(rn: str):
                t = _typed(rn)
                return (_apos.get(t.rsplit(".", 1)[-1], 999), t)

            _flat = sorted((str(ctx.rels[i]) for i in cands[:30]
                            if isinstance(i, int) and 0 <= i < len(ctx.rels)),
                           key=_order)[:15]
            return _json_result({
                "entities": treq["entities"], "question": treq["question"],
                "candidate_relations": _flat,
                "grouped_relations": _grouped,
                "note": ("Identify ALL question-relevant groups below — typically "
                         "≤3, max 5. Submit the TYPED NAME (e.g. relations: "
                         "baseball_division.teams | producer.film) — it expands "
                         "to that group's relations. ≡ marks semantic equivalents: "
                         "submit them TOGETHER. A BARE attribute (relations: teams) "
                         "expands to ALL relations with that attribute across types. "
                         + (_nudge + " " if _nudge else "")),
            })
    # FALLBACK: no attribute ranking (GTE failure) — flat list as before
    # THREE-WAY RELATION CLASSIFICATION (user + Codex design, 2026-09-03):
    # selection = uncertainty management, not hard filtering. The model
    # classifies candidates Required (fact cannot be evidenced without one
    # of them) / Supporting (alternative or complementary encodings of the
    # SAME fact — equivalent, inverse, sibling schema) / Irrelevant, and
    # the retrieve_subgraph `relations:` field carries Required ∪ Supporting
    # (hard cap 10). Call-level data: live hard selection captured gold 58%
    # per call; three-way recovers 62% of the missed golds at ×4 set size.
    _note = ("Identify ALL question-RELEVANT relations for this fact — "
             "typically ≤3 core relations, max 5. Include every semantically "
             "equivalent encoding (film.director.film and film.film.directed_by "
             "are the same fact from two ends) — never discard an equivalent "
             "merely because its name differs. Reject relations that merely "
             "share vocabulary or topic. Do NOT pick attribute relations "
             "(date/name/type/role) — the system reveals those inside CVTs. "
             "Then call retrieve_subgraph with ALL relevant relations together.")
    if _nudge:
        _note = _nudge + " " + _note
    cand_rel_names = [ctx.rels[i] for i in cands if 0 <= i < len(ctx.rels)]
    return _json_result({
        "entities": treq["entities"], "question": treq["question"],
        "candidate_relations": cand_rel_names,
        "note": _note,
    })


async def retrieve_relations(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph relation retrieval: entities + question → candidate relations.
    Accepts a single entity or a LIST of entities. When multiple entities are passed,
    the GTE candidate pool is the UNION of all entities' 2-hop reachable relations —
    ensuring relations visible from ANY candidate are surfaced (not just the first).
    Sequential composition of the three phases (see _rr_prepare)."""
    treq = _rr_prepare(args, ctx)
    if treq["kind"] == "done":
        return treq["result"]
    bres = await _rr_execute(treq, ctx, session)
    return _rr_finalize(treq, bres, ctx)


_TIME_VALUE_ATTRS = {"from", "to", "date", "year", "rate", "number", "amount",
                     "start_date", "end_date", "initial_date", "final_date"}

def _relation_snapshot(ctx, center_idxs, cand_rel_idxs, top_k: int = 8) -> str:
    """For each top candidate relation, what 2nd-hop attribute relations does it expose
    via 1-hop + CVT penetration from the centers? Returns a hint string tagging candidates
    that reach TIME/VALUE dims (from/to/date/rate/number). Only names relations, not entities.
    `center_idxs`: the entity idxs this call is centered on. `cand_rel_idxs`: GTE-ranked
    candidate relation idxs (ordered)."""
    if not center_idxs or not cand_rel_idxs:
        return ""
    centers = set(center_idxs)
    ents = ctx.ents
    rels = ctx.rels
    H, R, T = ctx.h_ids, ctx.r_ids, ctx.t_ids
    # pre-index edges by head and tail for speed
    out_by_h = {}
    in_by_t = {}
    for i in range(len(H)):
        out_by_h.setdefault(H[i], []).append((R[i], T[i]))
        in_by_t.setdefault(T[i], []).append((R[i], H[i]))
    def _short(ri):
        s = str(rels[ri]) if 0 <= ri < len(rels) else ""
        return s.rsplit(".", 1)[-1] if s else s
    lines = []
    for ri in cand_rel_idxs[:top_k]:
        # 1-hop neighbors of centers via this relation (both directions)
        nbs = set()
        for c in centers:
            for r, t in out_by_h.get(c, []):
                if r == ri:
                    nbs.add(t)
            for r, h in in_by_t.get(c, []):
                if r == ri:
                    nbs.add(h)
        if not nbs:
            continue
        # 2nd-hop relations from those neighbors (collect short-names)
        second = set()
        for nb in list(nbs)[:6]:
            for r, t in out_by_h.get(nb, []):
                second.add(_short(r))
            for r, h in in_by_t.get(nb, []):
                second.add(_short(r))
        exposed_time = sorted(second & _TIME_VALUE_ATTRS)
        if exposed_time:
            lines.append("%s →exposes[%s]" % (_short(ri), ",".join(exposed_time)))
    if not lines:
        return ""
    return ("Relation 2nd-hop hints (which candidates reach time/value dims like from/to/date): "
            + " | ".join(lines) + ".")


# ───────────────────────── retrieve_subgraph (mature multi-hop walk + dense tree) ─────────────────────────
# THREE-PHASE SPLIT (perf-4, 2026-08-23): _sg_prepare (A: center resolution +
# boundary checks + walk step construction) → _sg_execute (B: the walk await,
# batched by the round-level coordinator; GTE correction for bad names first)
# → _sg_finalize (C: accumulate + render + evidence sets, pure CPU).


# ───────────────────────── RELATION-SEQUENCE STATE (SEQ_REL_SEQ, user design 2026-09-15) ─────────────────────────
# The authoritative walk state is the ANCHOR + its accumulated relation LAYERS
# (ctx.anchor_seqs: {anchor_idx: [frozenset(rel_idx), ...]}). A later
# retrieve_subgraph CENTERED ON THE SAME ANCHOR appends: each submitted
# relation joins the deepest layer whose completions make it structurally
# feasible (continuation-first; anchor-direct feasible = layer-1 widening).
# The walk then instantiates the FULL sequence from the anchor — typed entity
# lists never become walk centers (the runtime/tvrage specimens' rosters
# dropped exactly the gold; constructive instantiation cannot). Gate is OFF by
# default: same-anchor call semantics change (repair re-selection becomes
# union-accumulate), so it ships dark until the 48×3 verdict flips it.

def _anchor_seq_layers(ctx) -> dict:
    st = getattr(ctx, "anchor_seqs", None)
    if st is None:
        st = {}
        ctx.anchor_seqs = st
    return st


def _cvt_like_name(n) -> bool:
    s = str(n)
    return s[:2] in ("m.", "g.") and len(s) > 4


def _trans_named_step(ctx, ix, cur, rels) -> set:
    """One layer step with the ENGINE's transparency semantics: raw edges of
    the layer's relations land on endpoints; landed m./g. nodes (event CVTs
    AND id-nodes — actor.film lands on m.0gwrkz0 while the film's attribute
    edges hang on its NAME node one object.name hop away) pass through ALL
    their edges within the same layer, exactly as the walk engine's hop
    layering treats them. Returns the NAMED endpoint set."""
    from kgqa.agent.tools import _full_adj
    adj = _full_adj(ctx)
    ents = ctx.ents
    nxt = set()
    for r in rels:
        f, rv = ix.fwd.get(r, {}), ix.rev.get(r, {})
        for e in cur:
            nxt.update(f.get(e, ()))
            nxt.update(rv.get(e, ()))
    def _cvtl(i):
        return _cvt_like_name(ents[i] if 0 <= i < len(ents) else i)
    named = {n for n in nxt if not _cvtl(n)}
    stack = [n for n in nxt if _cvtl(n)]
    seen = set(nxt) | set(cur)
    while stack:
        n = stack.pop()
        for _rr, o in (adj[n] if 0 <= n < len(adj) else ()):
            if o in seen:
                continue
            seen.add(o)
            if _cvtl(o):
                stack.append(o)
            else:
                named.add(o)
    return named


def _seq_completions(ctx, ix, anchor_idx, layers):
    """[ {anchor}, NAMED completions through L1, ..., through Lk ] — one
    transparent layer step each (see _trans_named_step). Memoized per
    (anchor, layers); deterministic, so the memo is always valid.

    PREFIX REUSE (walk speedup, user request 2026-09-17): completion set k
    depends only on (anchor, layers[:k]) — an EXTEND (new tail layer) or
    UPDATE (replace layer j) invalidates only the SUFFIX, but the old
    whole-tuple key forced a full-chain rewalk on every layer change.
    Every computed prefix is cached with its cross-layer visited set, so
    continuation calls walk only the layers they actually changed."""
    memo = getattr(ctx, "anchor_seq_memo", None)
    if memo is None:
        memo = {}
        ctx.anchor_seq_memo = memo
    lkey = tuple(frozenset(l) for l in layers)
    key = (anchor_idx, lkey)
    hit = memo.get(key)
    if hit is not None:
        return hit[0]
    # longest cached prefix (values: (out_list, visited_set)). A stored
    # value must have k+1 entries (anchor + k walked layers) — a CHAINED-OFF
    # full key (the chain broke at layer j) also matches layer-j prefix
    # lookups by tuple equality but has FEWER entries; reusing it would
    # resume walking from the wrong layer (equivalence harness catch).
    out, visited, k = None, None, 0
    for k in range(len(layers) - 1, 0, -1):
        phit = memo.get((anchor_idx, lkey[:k]))
        if phit is not None and len(phit[0]) == k + 1:
            out, visited = list(phit[0]), set(phit[1])
            break
    if out is None:
        out, visited = [{anchor_idx}], {anchor_idx}
        k = 0
    cur = out[-1]
    for j in range(k, len(layers)):
        nxt = _trans_named_step(ctx, ix, cur, layers[j]) - visited
        if not nxt:
            break
        visited |= nxt
        out.append(nxt)
        cur = nxt
        # out has m entries ⇔ layers[:m-1] walked — cache that prefix
        memo[(anchor_idx, lkey[:len(out) - 1])] = (list(out), set(visited))
    # the full key shares the OUT OBJECT itself (aliasing contract:
    # repeat calls return the same object — test_memo_returns_same_object)
    memo[key] = (out, visited)
    return out


def _feasible_rels_one_hop(ctx, ent_set) -> set:
    """Relation idxs with at least one edge touching ent_set (either
    direction) — the structural half of the layer-assignment judgment."""
    from kgqa.agent.tools import _full_adj
    adj = _full_adj(ctx)
    out = set()
    for e in ent_set:
        if 0 <= e < len(adj):
            for rr, _o in adj[e]:
                out.add(rr)
    return out


def _classify_seq_submit(ctx, ix, anchor_idx, layers, new_rel_idxs):
    """Deepest-feasible-layer assignment for appended relations.
    Returns (updated_layers, {rel_idx: action}, completions). Actions:
    'append' (new layer beyond the last — frontier relations submitted
    TOGETHER share that one new layer), 'join:k' (added to existing layer
    k), 'infeasible' (no layer's completions reach it). Two-pass: every
    relation is assigned against the PRE-update completions, then applied —
    mutating mid-loop would both index past feas and split same-call
    frontier siblings into separate layers."""
    comps = _seq_completions(ctx, ix, anchor_idx, layers)
    feas = [_feasible_rels_one_hop(ctx, comps[k]) for k in range(len(comps))]
    layers = [set(l) for l in layers]
    n0 = len(layers)
    assign = {}
    for r in new_rel_idxs:
        join_at = None
        for k in range(len(feas) - 1, -1, -1):      # deepest first
            if r in feas[k]:
                join_at = k + 1
                break
        assign[r] = join_at
    actions = {}
    for r in new_rel_idxs:
        join_at = assign[r]
        if join_at is None:
            actions[r] = "infeasible"
            continue
        if join_at > n0:
            if n0 >= 3:                             # depth cap = derive's
                actions[r] = "depth_cap"
                continue
            if len(layers) == n0:                   # first frontier rel
                layers.append(set())
            layers[-1].add(r)
            actions[r] = "append"
        else:
            layers[join_at - 1].add(r)
            actions[r] = f"join:{join_at}"
    return [frozenset(l) for l in layers], actions, comps


def _chain_feasible(ctx, ix, anchor_idx, chain) -> bool:
    """Per-layer feasibility of one declared chain. BETWEEN layers the
    handoff uses the transparent named step (id-node → name-node bridging —
    actor.film lands on m.0gwrkz0 while the next relation's edges hang on
    the film's NAME node); the FINAL layer only needs RAW edges nonempty —
    discriminator terminals land on CVT/value nodes (runtime → m.0h100dp)
    and a named-only emptiness check wrongly pruned exactly those."""
    cur = {anchor_idx}
    for k, r in enumerate(chain):
        if k == len(chain) - 1:
            f, rv = ix.fwd.get(r, {}), ix.rev.get(r, {})
            nxt = set()
            for e in cur:
                nxt.update(f.get(e, ()))
                nxt.update(rv.get(e, ()))
        else:
            nxt = _trans_named_step(ctx, ix, cur, [r])
        if not nxt:
            return False
        cur = nxt
    return True


def _patterns_from_layers(ctx, ix, anchor_idx, layers, submitted):
    """Cross-product of the declared layers into multistep pattern tuples
    (existing {rel-idx tuple: tuple(frozenset([r]))} format), keeping only
    patterns whose FINAL relation is among this call's submissions (the call's
    fact) and whose every prefix instantiates from the anchor. Layer widths
    are trimmed (largest first) until the cross product is ≤24 — the B-phase
    per-terminal quota is the real semantic filter; this only bounds
    combinatorics deterministically."""
    from itertools import product as _prod
    lay = [sorted(l) for l in layers if l]
    if not lay:
        return {}
    widths = [len(l) for l in lay]
    n = 1
    for w in widths:
        n *= w
    while n > 24:                     # trim widest layer by one until ≤24
        k = widths.index(max(widths))
        if widths[k] <= 1:
            break
        widths[k] -= 1
        lay[k] = lay[k][:widths[k]]
        n = 1
        for w in widths:
            n *= w
    out = {}
    for combo in _prod(*lay):
        if combo[-1] not in submitted:
            continue
        if _chain_feasible(ctx, ix, anchor_idx, combo):
            out[tuple(combo)] = tuple(frozenset([r]) for r in combo)
    # TOP-K CHAIN SELECTION (user ruling 2026-09-15, 24353bbc specimen):
    # the second subgraph's patterns are the OVERALL top-K chains, not the
    # full layer cross-product — L1(3 rels) × L2(3 rels) = 9 sections was
    # the explosion the trajectory review caught. Rank: (a) shorter chains
    # first (fewer intermediates = tighter evidence); (b) deterministic
    # (rel-idx sorted). K=3 matches the derive path's per-terminal quota.
    _K_CHAINS = int(os.environ.get("SEQ_CHAIN_TOPK", "3"))
    if len(out) > _K_CHAINS:
        _ranked = sorted(out, key=lambda pk: (len(pk), pk))
        out = {k: out[k] for k in _ranked[:_K_CHAINS]}
    return out


def _sg_prepare(args: Dict[str, Any], ctx) -> dict:
    """A段: terminal errors render here (kind="done"); a wrong/low-conf center
    name defers its GTE correction to execute (corr field — when the
    correction yields NO candidates the call still walks the resolved
    centers); the clean path emits the walk steps."""
    raw = args.get("center") or args.get("entities") or ([args.get("entity")] if args.get("entity") else [])
    entities = _split_pipe_entities([str(e) for e in raw if e])
    rel_names = args.get("relations") or []
    fid = str(args.get("sg") or args.get("fact_id") or args.get("step") or "")
    # single-?var call marker for the PATTERN-PATH walk (seq_tools B段):
    # the expansion produced the binding set; _sg_execute may replace the
    # per-binding walks with one set-state pattern walk
    _var_name = ""
    _raw0 = str(raw[0]).strip() if raw else ""
    if _raw0.startswith("?") and len([e for e in raw if e]) == 1:
        _var_name = _raw0
    if not entities:
        return {"kind": "done", "result": _json_result({"error": "no entities provided."})}
    # PATTERN-PREFIX CONTINUATION (user design 2026-09-10): a single-?var
    # call whose variable was declared from a prior single-center retrieval
    # carries that walk's node set as the prefix — the bindings are the
    # prior pattern's tails, so their walks mask the already-walked
    # territory (状态保持,不重复回去) and spend the budget on the novel fringe.
    _prefix = None
    _raw0 = str(raw[0]).strip() if raw else ""
    if (_raw0.startswith("?") and len(entities) == 1
            and os.environ.get("SEQ_PATTERN_PREFIX", "0") == "1"):
        # OFF by default — A/B 2026-09-10: RPE's dominant cost is each
        # binding's 3-hop NOVEL fringe (never in the prefix), so the mask
        # saved only the hop-1 back-edges while cutting legitimate paths
        # through shared territory: speed flat (exec 2408 vs 2152s), f1
        # -2.4pp (0.6930 -> 0.6692). Kept behind the env for the record.
        _pst = getattr(ctx, "pattern_state", None) or {}
        _org = _pst.get(_raw0)
        if _org and _org.get("nodes"):
            _prefix = _org["nodes"]
    entities, _err = _expand_entities(entities, ctx)
    if _err:
        return {"kind": "done", "result": _json_result({"error": _err})}
    _nudge = _variable_nudge(raw, ctx)
    # ATTRIBUTE-FAMILY pre-check: if any submitted name lacks dots, it's an
    # attribute — skip the early validation (the full-name check would reject
    # it here); the expansion after center resolution handles it
    _relset = {str(r) for r in ctx.rels}

    def _is_family(rs: str) -> bool:
        # family name = bare attribute ('actor') OR typed name that is not a
        # full relation ('baseball_division.teams' — the rr display's group key)
        return bool(rs) and ("." not in rs or rs not in _relset)

    _has_attr_name = any(_is_family(str(r).strip()) for r in rel_names)
    if not _has_attr_name:
        rel_idxs = [ctx.rels.index(r) for r in rel_names
                    if isinstance(r, str) and r in ctx.rels]
        if not rel_idxs:
            return {"kind": "done", "result": _json_result({"error": "no valid relations provided. Pick from the candidate_relations "
                                          "returned by retrieve_relations."})}
    else:
        rel_idxs = []  # will be populated after attribute expansion

    # resolve + boundary-check each center. value-like inputs require EXACT match (fuzzy
    # resolves unreliably: 'UTC-05:00' -> 'UTC−04:00'); skip entities not yet in the
    # subgraph (boundary); flag wrong/low-conf named entities → correction.
    centers, skipped = [], []
    bad_name = None                     # an entity whose NAME is wrong/low-conf → correct
    for e in entities:
        i = _name_to_idx(e, ctx)
        if _looks_like_value(e) and (i is None or normalize(e) != normalize(ctx.ents[i])):
            # Values (numbers, UTC offsets, IDs) have no semantic name → GTE returns random
            # entities. Skip GTE; tell the model directly.
            return {"kind": "done", "result": _json_result({
                "entity_error": f"'{e}' is a VALUE (numeric/coordinate/date/ID), not a named "
                    "graph entity — it's stored as an ATTRIBUTE, not a center. Pass the ENTITY "
                    "that carries it, or the ?variable. WORKFLOW: retrieve_relations → retrieve_subgraph."})}
        if i is None or _match_sim(e, ctx.ents[i]) < 0.95:
            if bad_name is None:
                bad_name = e            # no-match or substring-fragment match → correct
            if i is None:
                continue
            # low-conf match present but flagged → still try it as a center below if in-subgraph
        if i is not None and not _in_subgraph(i, ctx):
            skipped.append(e)           # in graph but not yet retrieved → boundary skip
        elif i is not None:
            centers.append((e, i))
    if bad_name is None and not centers:
        return {"kind": "done", "result": _json_result({"error": (f"none of {entities} appeared in a prior retrieve_subgraph. "
                                       f"A center MUST be an entity from a previous retrieve_subgraph's "
                                       f"triples (or the plan anchor for fact 1) — ANY prior subgraph's "
                                       f"entities are legal centers (cross-subgraph borrowing). If any of "
                                       f"these is a variable binding, pass the ?VARIABLE "
                                       f"(center: [\"?var\"]) — the runtime expands it to all declared "
                                       f"bindings.")})}
    # snapshot the PRIOR calls' triples BEFORE this call's _accumulate (which
    # lands in finalize), so the cycle filter suppresses cross-call loops
    # (subgraph N→subgraph 1) but never this call's own freshly-retrieved edges.
    # CONSUMPTION TRACK (user ruling 2026-09-01): record every resolved
    # retrieval START (literal or ?var-expanded) — the answer-time gate
    # intercepts once when a declared plan entity never started anything.
    # ATTRIBUTE-FAMILY EXPANSION (user design 2026-09-08): a submitted
    # family name — BARE attribute ('actor', 'film') or TYPED group name
    # ('baseball_division.teams', the rr display's group key, user audit
    # 2026-09-09) — expands to relations that can serve as a path edge from
    # the centers. MUST run after center resolution: expanding from the full
    # graph picks unreachable relations and the walk dies as
    # RELATION_MISMATCH (30 vs 18 in the first rollout).
    # CVT BRIDGE (user ruling 2026-09-09, position rule): expansion is
    # POSITIONAL, not hop-based — a CVT as the last or second-to-last path
    # entity is expanded; the 2-hop budget governs relation SELECTION only,
    # and a CVT mid-path stretches the window by one edge. The family's
    # terminal edge (film.performance.actor) or its behind-entity
    # (people.person.religion) never touches the center, so the walk needs
    # the BRIDGE (center→CVT) submitted alongside — the existing penetration
    # then reveals the terminal edge. Matching the terminal edge alone walked
    # ZERO edges (sg 707 vs 2884 chars, attrfamily2): the bridge is what
    # makes a family walkable.
    # UNIFIED EXPANSION (typedgroup audit 2026-09-09): every submitted
    # relation — bare attribute, typed group, OR full name — goes through
    # the same pool-match + bridge attachment. Bridges are a reachability
    # property of (center, relation), not of the name form: the model
    # copying a full terminal name from the display walked ZERO edges
    # exactly like a bare family did before bridges existed (29/35
    # mismatches in the typedgroup rollout were full-name submissions).
    _fam_echo = {}
    if centers and rel_names:
        from kgqa.agent.tools import _full_adj
        _adj = _full_adj(ctx)
        _n_ents = len(ctx.ents)
        _lmemo = getattr(ctx, "_rel_last_memo", None)
        if _lmemo is None:
            _lmemo = ctx._rel_last_memo = {}
        _fmemo = getattr(ctx, "_fam_expand_memo", None)
        if _fmemo is None:
            _fmemo = ctx._fam_expand_memo = {}
        _ckey = tuple(sorted(_ci for _cn, _ci in centers))

        def _last(ri):
            lc = _lmemo.get(ri)
            if lc is None:
                lc = _lmemo[ri] = (str(ctx.rels[ri]).rsplit(".", 1)[-1]
                                   if 0 <= ri < len(ctx.rels) else "?")
            return lc

        def _typed(ri):
            rn = str(ctx.rels[ri]) if 0 <= ri < len(ctx.rels) else "?"
            return ".".join(rn.rsplit(".", 2)[-2:])

        _expanded = []
        _fam0 = ""
        for r in rel_names:
            rs = str(r).strip()
            if not rs:
                continue
            _fam = _is_family(rs)
            if _fam:
                _fam0 = _fam0 or rs
            _typedq = _fam and "." in rs   # typed query: match last TWO comps
            _mk = (_ckey, rs)
            if _mk in _fmemo:
                _names, _bids = _fmemo[_mk]
            else:
                # MATCHED SET for this name, from the centers' 2-hop pool —
                # a pool relation is a legal PATH edge (hop-2 relations are
                # walk-selectable; CVT-transparent reach included). A FULL
                # name that is not in the pool is genuinely unreachable:
                # passthrough without bridges (the walk's RELATION_MISMATCH
                # feedback is then correct).
                _pool = set()
                for _cn, _ci in centers:
                    _pool |= _seq_pool_relids(ctx, {_ci})
                if _fam:
                    _names = sorted(ri for ri in _pool
                                    if ((_typed(ri) == rs) if _typedq
                                        else (_last(ri) == rs)))[:10]
                else:
                    _ri = ctx.rels.index(rs)
                    _names = [_ri] if _ri in _pool else []
                # BRIDGE part (adjacency): the center→carrier edge when the
                # carrier — the terminal edge's own CVT, or a holder behind
                # it — touches the matched set. Terminal pool matches never
                # touch the center (hop-1 death); the bridge is what makes
                # them walkable. Bridges are a reachability property of the
                # (center, relation) pair, NOT of the name form — a FULL
                # name copied verbatim from the display gets the same
                # bridges as its typed/bare family (typedgroup rollout:
                # 29/35 mismatches were full-name submissions bypassing
                # this).
                # DIRECT-FIRST (user audit 2026-09-10, Belgium specimen):
                # bridges exist to REACH a family the center cannot touch
                # at hop 1. When a center ALREADY carries a matched
                # relation on its own edges, bridges for this name are
                # pure noise — the behind-CVT carrier test is loose (any
                # co-endpoint touching the family fires), so a hub center
                # surrounded by CVTs whose co-endpoints are big entities
                # (Belgium: adjoin/combat/partial-containment CVTs whose
                # co-endpoints all carry countries.continent) pulled a
                # dozen irrelevant relations into rel_idxs and the render
                # labeled them "(retrieved)" — evidence unrelated to the
                # asked relations. Skip bridges whenever ANY center has a
                # direct matched edge.
                _mset = set(_names)
                _bids = set()
                # A/B verdict 2026-09-10: skipping bridges when the center
                # carries the family directly cleans the render (Belgium's
                # adjoin/combat sections) but costs -4.4pp — the bridged
                # walks' penetrations feed discrimination evidence. Gated
                # OFF by default; SEQ_DIRECT_FIRST=1 enables.
                _center_direct = False
                if os.environ.get("SEQ_DIRECT_FIRST", "0") == "1":
                    _center_direct = any(
                        ri in _mset
                        for _cn, _ci in centers
                        if 0 <= _ci < len(_adj)
                        for ri, _ni in _adj[_ci])
                if not _center_direct:
                    for _cn, _ci in centers:
                        if not (0 <= _ci < len(_adj)):
                            continue
                        _scanned = set()
                        for _ri, _ni in _adj[_ci]:
                            if (_ni in _scanned or not (0 <= _ni < _n_ents)
                                    or len(_bids) >= 6):
                                continue
                            _scanned.add(_ni)
                            _hit = any(_rj in _mset
                                       for _rj, _nj in _adj[_ni] if _nj != _ci)
                            if not _hit and is_cvt_like(ctx.ents[_ni]):
                                for _rj, _mj in _adj[_ni]:
                                    if _mj == _ci or not (0 <= _mj < _n_ents):
                                        continue
                                    if any(_rk in _mset
                                           for _rk, _nk in _adj[_mj]):
                                        _hit = True
                                        break
                            if _hit:
                                _bids.add(_ri)
                _fmemo[_mk] = (_names, _bids)
            _name_set = set(_names)
            _dnames = [str(ctx.rels[i]) for i in _names]
            _bridges = [str(ctx.rels[i]) for i in sorted(_bids)
                        if i not in _name_set][:6]
            if _fam or _bridges:
                # echo every family expansion; for full names echo only when
                # bridges were attached (the surprising, audit-worthy case)
                _fam_echo[rs] = {"direct": _dnames or [rs], "bridge": _bridges}
            _expanded.extend(_dnames if _dnames else [rs])
            # BRIDGES = TRAVERSAL-ONLY (user design 2026-09-11, Ron-Howard
            # awards specimen): a relation path must END with the SUBMITTED
            # relation — bridge carrier edges are mid-segment hops, never
            # segment termini. RPE's bridge hops already permit ANY non-
            # target relation mid-path, so bridges need no rel_idxs entry
            # for traversal; putting them there made every award edge in
            # the 3-hop environment a legal TERMINATING segment (award
            # sections rendered as "(retrieved)"). The echo still records
            # them for audit. Prior A/Bs (direct-first -4.4pp etc.) removed
            # bridges ENTIRELY; this keeps their traversal while stripping
            # terminal status — a configuration not measured before.
            if os.environ.get("SEQ_BRIDGE_TERMINAL", "1") == "1":
                _expanded.extend(_bridges)
        rel_names = list(dict.fromkeys(_expanded))
        rel_idxs = [ctx.rels.index(r) for r in rel_names
                    if isinstance(r, str) and r in ctx.rels]
        if not rel_idxs:
            return {"kind": "done", "result": _json_result({
                "error": f"attribute '{_fam0 or (rel_names[0] if rel_names else '?')}' "
                         f"has no matching relations "
                         f"in this center's reachable pool. Try a different "
                         f"attribute or the full relation name."})}

    _cons = getattr(ctx, "consumed_anchors", None)
    if _cons is None:
        _cons = ctx.consumed_anchors = set()
    for _cn, _ci in centers:
        if _cn:
            _cons.add(str(_cn).strip().lower())
    # MULTI-STEP PATTERN DERIVATION (realignment spec pillar 1+2+3): for
    # centers WITHOUT direct 1-hop family support, derive the relation
    # SEQUENCE center→…→family-terminal (BFS ≤2 named hops, CVT-free) —
    # submitted to the walk as multi-step step_relations so the engine's
    # forward validation enforces path consistency and reach stops needing
    # bridges-as-termini.
    _multistep = {}
    _ms_cov = {}                 # (center_idx, pattern) -> step coverage
    _ast = {}                    # anchor tree layers (guarded: REL_SEQ may be off)
    _root_of = {}
    # UNCONDITIONAL INIT (crash fix 2026-09-19): the return at the end of
    # _sg_prepare references these unconditionally; they used to be born
    # inside the SEQ_MULTISTEP block, so SEQ_MULTISTEP=0 (e.g. replay
    # without the standing env) raised UnboundLocalError on EVERY sg call.
    _seq_echo = ""
    _cont_compare = False
    _cont_frontier = {}
    _layer_action = ""
    if centers and os.environ.get("SEQ_MULTISTEP", "0") == "1":
        try:
            from kgqa.traversal.pattern_walk import get_pattern_index
            _ix = get_pattern_index(ctx)
            # PATTERN FAMILY = the SUBMITTED relations, resolved by name
            # (user ruling 2026-09-22, design realignment): single-hop
            # paths are DIRECTLY PERCEIVABLE — a full submitted name
            # resolves to itself, and the derivation enumerates 1..3-hop
            # realizable sequences ending in a submitted relation, ranked
            # by (length, semantics). The expansion's direct/bridge BUCKETS
            # are name-resolution + reachability machinery for the WALK
            # layer; they must never feed the pattern layer (the 567
            # specimen: 'film.director.film | film.film.directed_by'
            # expanded to a 7-relation pool whose bridge relations became
            # pattern terminals → 60 enumerated patterns, 20+ rendered —
            # vs the design's direct + ≤3/terminal ≈ a handful).
            # Resolution precedence: (1) exact full name; (2) family/bare
            # name → the expansion's direct members (the bucket's intended
            # use — typed groups and bare attributes have no exact match);
            # (3) short-name equivalence. Bridges are never terminals.
            _matched = set()
            _l1 = lambda rn: str(rn).rsplit(".", 1)[-1]
            _resolved_any = False
            for _rs in [str(r) for r in (args.get("relations") or [])]:
                for _ri, _rn in enumerate(ctx.rels):
                    if str(_rn) == _rs:
                        _matched.add(_ri)
                        _resolved_any = True
                        break
                else:
                    _exp = (_fam_echo or {}).get(_rs) or {}
                    _got = False
                    for _dn in (_exp.get("direct") or []):
                        if _dn in ctx.rels:
                            _matched.add(ctx.rels.index(_dn))
                            _got = _resolved_any = True
                    if not _got:
                        for _ri, _rn in enumerate(ctx.rels):
                            if _l1(_rn) == _rs or _l1(_rs) == _l1(_rn):
                                _matched.add(_ri)
                                _resolved_any = True
                                break
            _fam = _matched if _resolved_any else set(rel_idxs)
            # RELATION-SEQUENCE ACCUMULATION (SEQ_REL_SEQ, user ruling
            # 2026-09-15: DEFAULT-ON TREE CONTINUATION): accumulation is a
            # SYSTEM behavior, not a call form the model opts into. A call
            # whose centers are MEMBERS of an existing anchor tree — the
            # root itself, any layer's completions, a typed roster subset,
            # or a ?var expanding to bindings, all structurally the same —
            # CONTINUES that tree: submitted relations join the deepest
            # feasible layer and the walk instantiates the full sequence
            # from the tree ROOT (typed centers are relation-determination
            # hints only; roster-vs-instantiation divergence cannot occur).
            # Centers outside every tree start a new root. Root preference
            # when several trees contain the center: one whose frontier
            # makes a submitted relation feasible, then the deepest.
            _declared = {}
            _seq_echo = ""      # (re-initialized at function scope — see above)
            _cont_compare = False
            _cont_frontier = {}
            _layer_action = ""
            _layer_ops = os.environ.get("SEQ_LAYER_OPS", "1") == "1"
            if os.environ.get("SEQ_REL_SEQ", "1") == "1" and rel_idxs:
                _ast = _anchor_seq_layers(ctx)
                _root_of = {}
                _center_layer = {}  # center_idx → layer k it belongs to
                for _cn, _ci in centers:
                    if not (0 <= _ci < len(ctx.ents)):
                        continue
                    _cands = []
                    for _a, _l in _ast.items():
                        if _a == _ci:
                            _cands.append((True, len(_l), _a))
                            _center_layer[_ci] = 0  # the root itself
                            continue
                        _comps = _seq_completions(ctx, _ix, _a, _l)
                        for _lk, _s in enumerate(_comps):
                            if _ci in _s:
                                _center_layer[_ci] = _lk
                                _fe = (_feasible_rels_one_hop(ctx, _comps[-1])
                                       if len(_comps) > 1 else set())
                                _hit = any(_r in _fe for _r in rel_idxs)
                                _cands.append((_hit, len(_l), _a))
                                break
                    if not _cands:
                        _ast[_ci] = [frozenset(rel_idxs)]    # new root
                        continue
                    _cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
                    _root_of[_ci] = _cands[0][2]
                if _root_of:
                    # collapsing several typed centers into one root drops
                    # the multi-center COMPARE framing — the frontier members
                    # are still the comparison subjects, so the contract must
                    # survive the replacement (1278d3da specimen: 9-country
                    # roster answered whole after continuation reframed it)
                    _cont_compare = True
                    _newc, _seen = [], set()
                    for _cn, _ci in centers:
                        _r = _root_of.get(_ci, _ci)
                        if _r in _seen:
                            continue
                        _seen.add(_r)
                        _newc.append((str(ctx.ents[_r]), _r))
                    centers = _newc
                for _a in sorted(set(_root_of.values())):
                    _layers = _ast[_a]
                    _have = set().union(*_layers) if _layers else set()
                    _new = [r for r in rel_idxs if r not in _have]
                    if not _new and _layer_ops:
                        _layer_action = "repeat"
                        continue
                    if not _new:
                        continue                        # pure repeat → derive path

                    # UPDATE vs EXTEND (user ruling 2026-09-15): the center's
                    # POSITION in the tree determines the intent —
                    #   center ∈ last layer's completions = model moving
                    #     FORWARD → EXTEND (deepest-feasible append/join)
                    #   center ∈ earlier layer (or is the root = layer 0) =
                    #     model re-working that step → UPDATE: REPLACE the
                    #     relations of the layer that FOLLOWS the center's
                    #     layer, dropping old ones not in this submission
                    _comps = _seq_completions(ctx, _ix, _a, _layers)
                    _cl = min((_center_layer.get(_ci, len(_comps) - 1)
                               for _ci in _root_of if _root_of[_ci] == _a),
                              default=len(_comps) - 1)
                    _is_extend = (_cl >= len(_comps) - 1)

                    if not _is_extend and _layer_ops:
                        # UPDATE (user ruling 2026-09-20): the step a
                        # submission adjusts is decided by the subgraph's
                        # ACTUAL START ENTITY (idx-level, ?var-expanded —
                        # never text parsing): start == the prior round's
                        # start (the root) ⇒ this optimizes the CURRENT
                        # step — the whole submitted set replaces that
                        # layer's relations (a next-step relation submitted
                        # from the root, like person.religion here, is a
                        # layer-1 ADJUSTMENT, not a new layer). Start on the
                        # frontier ⇒ EXTEND (branch below). Root matching is
                        # idx-level (_a == _ci / _ci in completion sets).
                        _target = _cl  # layer index to replace (0-based)
                        _old_layer = set(_layers[_target]) if _target < len(_layers) else set()
                        _repl = set(rel_idxs)
                        _layers_up = [set(l) for l in _layers]
                        if _target < len(_layers_up):
                            _layers_up[_target] = _repl
                        else:
                            _layers_up.append(_repl)
                        _up = [frozenset(l) for l in _layers_up]
                        _acts = {r: ("update:%d" % (_target + 1))
                                 for r in rel_idxs}
                        _layer_action = "update layer %d (replaced %s)" % (
                            _target + 1,
                            ", ".join(str(ctx.rels[r])[-40:]
                                      for r in (_old_layer - _repl)) or "none")
                    else:
                        # EXTEND: existing deepest-feasible classification
                        _up, _acts, _comps2 = _classify_seq_submit(
                            ctx, _ix, _a, _layers, _new)
                        _layer_action = "extend"
                    _ast[_a] = _up
                    # FRONTIER for the plain direct step = the PRE-update
                    # last layer's completions (the members the new relation
                    # applies to), never the anchor itself.
                    if len(_comps) > 1 and _comps[-1]:
                        _fr = sorted(_comps[-1] - {_a})[:12]
                        if _fr:
                            _cont_frontier[_a] = _fr
                    _pats_d = _patterns_from_layers(
                        ctx, _ix, _a, _up, set(rel_idxs))
                    if _pats_d:
                        _declared[_a] = _pats_d
                        _short = lambda ri: ".".join(
                            str(ctx.rels[ri]).rsplit(".", 2)[-2:]) \
                            if 0 <= ri < len(ctx.rels) else str(ri)
                        _parts = [str(ctx.ents[_a])]
                        for _li, _lay in enumerate(_up):
                            _lbl = " | ".join(_short(r) for r in sorted(_lay))
                            _cnt = len(_comps[_li + 1]) if _li + 1 < len(_comps) else 0
                            _parts.append(f"{_lbl} ({_cnt})")
                        _seq_echo = " ⭢ ".join(_parts)
            # SEMANTIC IDEMPOTENCE (user ruling 2026-09-15, trajectory
            # review): the model re-called the same walk with surface-
            # different args (typed roster → ?country → short rel name →
            # full rel name) four times, each producing the same evidence.
            # The repeat gate catches exact-match only. Check the RESOLVED
            # (root, relation-set) — if already served this rollout, return
            # the cached result with a note instead of re-walking.
            _sem_key = tuple(sorted((ci, frozenset(rel_idxs))
                                    for _n, ci in centers))
            _served = getattr(ctx, "_sg_served", None)
            if _served is None:
                _served = {}
                ctx._sg_served = _served
            _hit = _served.get(_sem_key)
            if _hit and os.environ.get("SEQ_SEM_IDEMPOTENT", "1") == "1":
                # KEY-ORDER FIX (user review 2026-09-22, repeat-audit
                # finding): the check used to read the centers tuple's
                # FIRST element (the NAME) while the mark read the SECOND
                # (the INDEX) — str vs int keys never matched, so the
                # idempotency cache was structurally dead. Both sides now
                # key on the center INDEX (canonical across surface forms).
                # RESPONSE (user ruling): do NOT re-paste cached evidence —
                # a byte-identical re-call is information-less (its scoring
                # block is removed at evaluation time); one concise
                # submission-first note is the whole reply.
                _rep = {
                    "evidence_repeat": True,
                    "note": ("This retrieval is IDENTICAL to your previous "
                             "call (same centers + same resolved relations — "
                             "surface-form changes do not alter it) and "
                             "returns nothing new. The evidence from that "
                             "call is already in your context. NEXT, one of: "
                             "(1) discriminate the candidates using the "
                             "values/dates/symbols already displayed; (2) "
                             "submit the answer from the standing bindings; "
                             "(3) pick a DIFFERENT relation or move to the "
                             "next fact.")}
                return {"kind": "done", "result": _json_result(_rep)}
            for _cn, _ci in centers:
                if not (0 <= _ci < len(ctx.ents)):
                    continue
                # CHAIN-CONSTRAINED (user ruling 2026-09-15, trajectory
                # review): when a sequence exists the second subgraph is a
                # RE-WALK of the full chain — patterns must go THROUGH the
                # accumulated layers, satisfying the entire relation chain.
                # Free derivation (which produced military_combatant→co2
                # chains that bypass L1) only applies when NO sequence
                # exists. The declared-only chains now survive because the
                # render pipeline fixes (collapse matching, out-and-back
                # guard with node-return, section-scoped attrs) landed.
                # DERIVE ALWAYS (user audit 2026-09-12, Belgium/GMT specimen):
                # the top-K PATTERN PATHS ending in the submitted relation —
                # applies to first-call anchors only.
                if _ci in _declared:
                    _multistep[_ci] = _declared[_ci]
                    continue
                _sem = os.environ.get("SEQ_PAT_SEMANTIC", "1") == "1"
                # STEP-COVERAGE (user ruling 2026-09-22): the ranking's
                # PRIMARY key is how many of the anchor tree's accumulated
                # step relation-sets the pattern path hits — a pattern
                # covering step1 AND step2 outranks one covering only
                # step2; semantics rank WITHIN equal coverage. Hit count
                # counts STEPS, never entities.
                _steps_now = None
                _root = _root_of.get(_ci, _ci) if isinstance(_root_of, dict) else _ci
                _steps_now = (_ast.get(_root) if isinstance(_ast, dict) else None)
                _der, _der_cov = _derive_multistep_seq(
                    _ix, ctx, _ci, _fam, topk=0 if _sem else 3,
                    steps=_steps_now)
                if _der:
                    _multistep[_ci] = _der
                    for _pk, _cv in (_der_cov or {}).items():
                        _ms_cov[(_ci, _pk)] = _cv
        except Exception:
            _multistep = {}
    return {"kind": "sg", "corr": bad_name, "centers": centers, "skipped": skipped,
            "rel_idxs": rel_idxs, "rel_names": rel_names, "fid": fid,
            "entities": entities, "nudge": _nudge, "attr_expansion": _fam_echo,
            "prefix": _prefix, "var_name": _var_name, "multistep": _multistep,
            "multistep_cov": _ms_cov,
            "anchor_seq": _seq_echo, "cont_compare": _cont_compare,
            "cont_frontier": _cont_frontier, "layer_action": _layer_action,
            "prior": set(getattr(ctx, "accumulated_triples", set()) or set())}


def _derive_multistep_seq(ix, ctx, ci, fam_idxs, topk=3, steps=None):
    """PATTERN-LEVEL enumeration (user design 2026-09-11, corrected): distinct
    relation-sequences (r1, …, rk→family) from ci — pure relation pairs, not
    entity BFS. One hop = the pattern set; GTE/support ranks within the same
    hop count; top-K patterns survive. Each pattern = multi-step
    step_relations for the engine's forward validation.

    Cost: relation-set operations, milliseconds — no entity-path enumeration
    (the entity-BFS version exploded exponentially on wide hop sets).
    Returns {pattern_key: tuple(frozenset, ...)} — multiple patterns, the
    caller submits each as a separate step."""
    from kgqa.traversal.cvt import is_cvt_like as _icl
    from collections import defaultdict
    from kgqa.agent.tools import _full_adj
    n = len(ctx.ents)
    # PER-NODE INVERTED ADJACENCY (walk speedup, user request 2026-09-17):
    # the O(|rels|) full-relation scans below (hop1/_behind/_reach each
    # enumerated every relation dict per node) dominated the walk profile —
    # 64% of walk time on dense cases. _full_adj is the same edge set as
    # (fwd, rev) indexed by node, so the scans become O(deg(node)).
    # Equivalence: same edges, same named-filter; pattern SETS and the
    # final (len, tuple) ranking make ordering deterministic.
    _adj_all = _full_adj(ctx)

    def _named(i):
        return 0 <= i < n and not _icl(str(ctx.ents[i]))

    # local adjacency (center's 1-hop only, with CVT transparency)
    hop1 = defaultdict(set)          # rel_idx -> {named entity idxs reached}
    # CVT transparency: a CVT 1-hop neighbor contributes ALL its named
    # neighbors (any relation, both directions — a performance CVT's actor
    # edge points BACK to the person while its film edge points forward,
    # so a same-relation-forward-only pass-through sees nothing; The-Ledge
    # specimen: film.actor.film edges live in rev, gold pattern support
    # counted 0, never enumerated). One level only, named nodes only.
    _behind_memo = {}

    def _behind(cvt_idx):
        out = _behind_memo.get(cvt_idx)
        if out is None:
            out = set()
            if 0 <= cvt_idx < n:
                for _r2, o in _adj_all[cvt_idx]:
                    if _named(o):
                        out.add(o)
            _behind_memo[cvt_idx] = out
        return out

    if 0 <= ci < n:
        for r, t2 in _adj_all[ci]:
            if 0 <= t2 < n and _icl(str(ctx.ents[t2])):
                hop1[r].update(x for x in _behind(t2) if x != ci)
            elif 0 <= t2 < n:
                hop1[r].add(t2)
    if not hop1:
        return None
    # PATTERN ENUMERATION, ANY HOP DEPTH 1..3 (user ruling 2026-09-13):
    # patterns are pure RELATION sequences ending in a submitted relation —
    # 1-hop (the direct pattern, forward+reverse), 2-hop, 3-hop. Enumeration
    # is CONSTRUCTIVE from index reachability: every yielded pattern has at
    # least one entity-level instantiation by construction (顺延 is inherent
    # — selection ranks only realizable patterns and fills the quota down
    # the ranking). Fan-out counts are never tracked (support is not in the
    # design); same-rel out-and-back steps are skipped (trivial loops).
    fams = fam_idxs
    patterns = set()

    # depth 1: the direct pattern
    for f in fams:
        if (((ix.head_mask.get(f, 0) >> ci) & 1)
                or ((ix.tail_mask.get(f, 0) >> ci) & 1)):
            patterns.add((f,))

    # named-reach helper for one more hop from a node set (per-node inverted
    # adjacency — same O(deg) rewrite as hop1/_behind above)
    def _reach(nodes):
        out = defaultdict(set)          # rel -> {named idx}
        for x in nodes:
            if not (0 <= x < n):
                continue
            for r2, o in _adj_all[x]:
                if _named(o):
                    out[r2].add(o)
        return out

    def _fam_incident(node):
        return any(f in fams and (node in ix.fwd[f] or node in ix.rev[f])
                   for f in fams)

    # depth 2: (r1, fam)
    for r1, reach in hop1.items():
        for node in reach:
            if not (0 <= node < n) or node == ci:
                continue
            for f in fams:
                if f == r1:
                    continue
                if node in ix.fwd[f] or node in ix.rev[f]:
                    patterns.add((r1, f))

    # depth 3: (r1, r2, fam) — hop2 named reach from hop1 nodes, bounded
    hop2_cache = {}
    for r1, reach in hop1.items():
        for node in reach:
            if not (0 <= node < n) or node == ci:
                continue
            if node not in hop2_cache:
                hop2_cache[node] = _reach({node})
            for r2, reach2 in hop2_cache[node].items():
                if r2 == r1:
                    continue
                for node2 in reach2:
                    if node2 == ci or node2 == node:
                        continue
                    for f in fams:
                        if f == r2 or f == r1:
                            continue
                        if node2 in ix.fwd[f] or node2 in ix.rev[f]:
                            patterns.add((r1, r2, f))
    # STEP COVERAGE (user ruling 2026-09-22): primary rank = number of the
    # tree's accumulated step relation-SETS the pattern hits (step1 then
    # step2 beats step2-only); semantics rank within equal coverage (B
    # phase). Counting STEPS, never entities.
    def _cov(pk):
        if not steps:
            return 0
        return sum(1 for st in steps
                   if any(r in st for r in pk))
    cov = {pk: _cov(pk) for pk in patterns}
    if not patterns:
        return None, None
    # ORDERING: (hops, name) — length first, semantics second (B phase);
    # support never influences selection.
    # ENUMERATION CEILING (user audit 2026-09-19): topk=0 (semantic mode)
    # used to become [:None] — the FULL enumeration returned, and when the
    # B-phase selection failed (its exception was swallowed) every
    # enumerated pattern walked and rendered (567: 39 sections for 4
    # submitted relations). Cap the semantic-mode candidate pool at 60 so
    # selection failure degrades gracefully instead of exploding.
    _cap = max(topk, 0) or 60
    ranked = sorted(patterns, key=lambda p: (len(p), p))[:_cap]
    out = {p: tuple(frozenset([r]) for r in p) for p in ranked}
    return out, cov


# ───────────────── RECONSTRUCTION LANE (user ruling 2026-09-19) ─────────────────
# The pattern layer has ALREADY searched (enumerate → rank → select); the
# instance layer must RECONSTRUCT, not search again: walk each selected
# pattern hop by hop deterministically, keep only THROUGH chains (an
# h-r1-neighbor that cannot continue r2 is not on the path), CVT landings
# pass through their edges (the CVT stays on the chain so the renderer can
# inline its attributes), no beam, no witness collection.

_REBUILD_BUDGET = 400          # per-hop breadth flood control (hub safety)


def _rebuild_paths(ctx, ix, start_idx, hops, budget=_REBUILD_BUDGET):
    """Deterministic through-chain reconstruction for ONE selected pattern.

    hops: tuple of frozensets (rel idxs) — one per pattern hop (a plain
    direct step is a single hop with the full submitted rel set).
    Returns (chains, edges): chains = [{"nodes": [idx...],
    "edges": [(h_idx, rel_idx, t_idx)...]}] — nodes include CVT mids,
    edges include CVT pass-through edges with their real relations;
    edges = the union of directed triples. Only chains reaching the LAST
    hop survive."""
    from kgqa.agent.tools import _full_adj
    adj_all = _full_adj(ctx)
    n = len(ctx.ents)
    parents = {}                        # node -> (prev, rel_idx, passthru)
    level = {start_idx}
    for hop in hops:
        _last_hop = hop is hops[-1]
        nxt, found = set(), False
        for u in sorted(level):
            for r in sorted(hop):
                f, rv = ix.fwd.get(r, {}), ix.rev.get(r, {})
                for v in sorted(set(f.get(u, ())) | set(rv.get(u, ()))):
                    if not (0 <= v < n) or v == start_idx:
                        continue
                    if _cvt_like_name(ctx.ents[v]):
                        # pass through ALL the CVT's edges to NAMED nodes
                        # (the CVT itself stays on the chain as a node);
                        # passthrough edges are marked — they feed
                        # triples/candidates but NOT the pattern hops of
                        # the chain (license path-admission requires the
                        # chain's last hop to be a submitted relation, and
                        # the user ruling puts CVT expansion at render)
                        if v not in parents:
                            parents[v] = (u, r, False)
                        for r2, w in adj_all[v]:
                            if 0 <= w < n and not _cvt_like_name(ctx.ents[w]) \
                                    and w not in parents and w != start_idx:
                                parents[w] = (v, r2, True)
                                nxt.add(w)
                                found = True
                            elif (_last_hop and 0 <= w < n
                                    and not _cvt_like_name(ctx.ents[w])
                                    and w in parents and w != start_idx):
                                # TERMINAL RE-DISCOVERY (audit ③ specimen
                                # 576/1812, 2026-09-21): a node discovered at
                                # an EARLIER hop (single-parent DAG) could
                                # never be a chain TERMINAL — the 18-of-23
                                # country rosters silently dropped exactly the
                                # members pre-parented by a reverse bridge
                                # (Panama in 576, Barbados in 1812), while
                                # the walk itself was complete. On the LAST
                                # hop an already-parented node may join the
                                # terminal level; its backtrack follows the
                                # original (real) parent path.
                                nxt.add(w)
                                found = True
                    elif v not in parents or _last_hop:
                        if v not in parents:
                            parents[v] = (u, r, False)
                        nxt.add(v)
                        found = True
        if not found:
            return [], set()
        if len(nxt) > budget:
            nxt = set(sorted(nxt)[:budget])
        level = nxt
    # backtrack every final-level node to the start (chains share prefixes
    # through the parent DAG; each end yields its own chain)
    chains, edge_set = [], set()
    for end in sorted(level)[:budget]:
        nodes, rev_edges = [end], []
        node = end
        while node != start_idx:
            _par = parents.get(node)
            if _par is None:
                break                    # orphan (budget-severed) — drop
            prev, rel, _ps = _par
            rev_edges.append((prev, rel, node, _ps))
            nodes.append(prev)
            node = prev
        if node != start_idx:
            continue
        nodes.reverse()
        edges = list(reversed(rev_edges))
        if not edges:
            continue
        # PATTERN HOPS end at the last submitted-relation edge: passthrough
        # edges beyond it are expansion context (triples/candidates only)
        _last_pat = max((i for i, e in enumerate(edges) if not e[3]),
                        default=-1)
        if _last_pat < 0:
            continue
        hops_edges = [(h, r, t) for (h, r, t, _ps) in edges[:_last_pat + 1]]
        hop_nodes = [start_idx] + [t for (_h, _r, t) in hops_edges]
        chains.append({"nodes": hop_nodes, "edges": hops_edges,
                       "full_nodes": nodes, "full_edges":
                       [(h, r, t) for (h, r, t, _ps) in edges]})
        for e in [(h, r, t) for (h, r, t, _ps) in edges]:
            edge_set.add(e)
    return chains, edge_set


def _rebuild_pe_list(ctx, treq, _mseq, _ms_map):
    """Rebuild pe_list directly from the SELECTED patterns (no search lane,
    no PG completeness block). Also archives treq["confirmed"] =
    {(center_idx, pattern-name-tuple): [chain...]} — the render layer reads
    this instead of re-inferring the pattern↔path mapping by name matching
    (the old mismatch that killed heterogeneous multi-hop sections).
    UNIFIED (user ruling 2026-09-21): every call is pattern → rebuild →
    expand. Derived patterns walk from the center; a plain direct query is
    the trivial single-hop pattern walking from the step's starts (frontier
    members on a continuation, else the center). Both lanes share ONE
    assembly: paths = pattern hops only (license path-admission needs a
    submitted last hop), triples = full_edges (the terminal-CVT passthrough
    expansion rides along — the renderer inlines it at the CVT node),
    candidates = named full terminals."""
    from kgqa.stages.formatting import PatternEvidence
    from kgqa.traversal.pattern_walk import get_pattern_index
    ix = get_pattern_index(ctx)
    # RENDER DELTA (user ruling 2026-09-20, superseding the 2026-08-20
    # full-re-render): a continuation call renders only what is NEW —
    # chains whose every edge was already displayed by a prior subgraph of
    # this case render nothing. First calls (empty accumulation) render
    # everything; EXTEND naturally shows the new layer's chains.
    _shown_triples = {(str(h), str(r), str(t))
                      for (h, r, t) in (getattr(ctx, "accumulated_triples",
                                                None) or set())}
    confirmed = {}
    out = []
    for (_cn, _ci) in treq["centers"]:
        combined = {}
        if not (0 <= _ci < len(ctx.ents)):
            out.append({})
            continue
        _raw_fallback = None      # (chains, names-key) when the delta filter
                                  # ate everything — see the empty-fallback below

        def _delta_new(chains):
            # RENDER DELTA: drop chains whose EVERY edge was already
            # displayed by a prior subgraph (all-old chains render nothing;
            # a chain with at least one new edge keeps — its rows carry the
            # new relation's context)
            return [ch for ch in chains
                    if not all(
                        (str(ctx.ents[h]), str(ctx.rels[r]),
                         str(ctx.ents[t])) in _shown_triples
                        for (h, r, t) in ch["full_edges"])]

        def _assemble(names, chains):
            """The ONE PatternEvidence assembly. triples = full_edges (the
            terminal-CVT passthrough expansion rides along — the renderer
            inlines it at the CVT node); paths = the PATTERN HOPS ONLY
            (ending at the submitted relation — license path-admission
            requires it); candidates = NAMED full terminals. The retired
            plain-direct branch — born before the edges/full_edges split
            (e9a10fd) redefined ch["edges"] to pattern hops — assembled
            triples from the pattern-hop edges and candidates from mid
            terminals, silently losing the passthrough evidence (2784
            specimen: Tupac's performance CVTs rendered nameless)."""
            edges = {e for ch in chains for e in ch["full_edges"]}
            label = " ⭢ ".join(
                ".".join(str(r).rsplit(".", 2)[-2:]) for r in names)
            triples = sorted(
                (str(ctx.ents[h]), str(ctx.rels[r]), str(ctx.ents[t]))
                for (h, r, t) in edges)
            paths = [{"nodes": [str(ctx.ents[i]) for i in ch["nodes"]],
                      "relations": [str(ctx.rels[r])
                                    for (_h, r, _t) in ch["edges"]]}
                     for ch in chains]
            _cands = {str(ctx.ents[ch["full_nodes"][-1]])
                      for ch in chains
                      if not _cvt_like_name(
                          str(ctx.ents[ch["full_nodes"][-1]]))}
            combined[label] = PatternEvidence(
                label, label, sorted(_cands), triples, {"paths": paths})
            confirmed[(_ci, names)] = list(
                (confirmed.get((_ci, names)) or [])) + chains

        # lane 1 — derived patterns (multi-hop or layered), from the center.
        # SINGLE-LAYER declared chains (pattern key len==1, the most common
        # continuation shape) ride here too: a 1-layer chain IS one hop from
        # the root — the old len>1 guard dropped them entirely (block
        # renders empty).
        for _pk, _seq in (_mseq.get(_ci) or {}).items():
            chains, _edges = _rebuild_paths(ctx, ix, _ci, _seq)
            if not chains:
                continue
            _new = _delta_new(chains)
            if not _new:
                # EMPTY-RENDER FALLBACK (user ruling 2026-09-21): an
                # all-old call used to render NOTHING — the model then held
                # NO evidence in context for these relations and exploded
                # into reasoning/re-asking loops. When the whole call would
                # render empty, the REPEATED evidence is shown again
                # (marked) instead.
                if _raw_fallback is None:
                    _raw_fallback = (
                        chains, tuple(str(ctx.rels[r]) for r in _pk))
                continue
            _assemble(tuple(str(ctx.rels[r]) for r in _pk), _new)

        # lane 2 — the trivial pattern: the submitted rel set, ONE hop from
        # the step's starts (tree FRONTIER members on a continuation, else
        # the center — the same targeting rule the old _ms_steps used).
        # Grouped per first-hop relation; CONFIRMED KEY IS PER RELATION
        # (not per frontier member — a 49-member frontier × 5 rels minted
        # 245 keys and blew the render budget through sheer key count).
        _fr = (treq.get("cont_frontier") or {}).get(_ci)
        starts = [i for i in (_fr or [_ci]) if 0 <= i < len(ctx.ents)]
        hop = frozenset(treq["rel_idxs"])
        _direct_new, _direct_all = {}, {}
        for _si in starts:
            chains, _edges = _rebuild_paths(ctx, ix, _si, (hop,))
            if not chains:
                continue
            for ch in chains:
                if ch["edges"]:
                    _direct_all.setdefault(ch["edges"][0][1], []).append(ch)
            for ch in _delta_new(chains):
                if ch["edges"]:
                    _direct_new.setdefault(ch["edges"][0][1], []).append(ch)
        for _r in sorted(_direct_new):
            _assemble((str(ctx.rels[_r]),), _direct_new[_r])

        # EMPTY-RENDER FALLBACK: the delta filter ate every chain of every
        # lane but the walk DID produce chains — re-show the repeated
        # evidence (first candidate, marked) instead of an empty render.
        # Covers the trivial lane too: its all-old repeats used to fall
        # through to a spurious NO_EVIDENCE — the walk had evidence, it was
        # merely repeated.
        if not combined and _raw_fallback is None and _direct_all:
            _r0 = min(_direct_all)
            _raw_fallback = (_direct_all[_r0], (str(ctx.rels[_r0]),))
        if not combined and _raw_fallback is not None:
            _assemble(_raw_fallback[1], _raw_fallback[0])
            treq["_repeat_evidence"] = True
        out.append(combined)
    treq["confirmed"] = confirmed
    return out


async def _sg_execute(treq, ctx, session):
    """B段: entity-name correction (GTE) when a bad name was flagged — with
    candidates the turn ends with the correction result; otherwise (and when
    the correction found nothing) the packed walk runs (coordinator batches)."""
    # CVT ATTR-KEY GTE RANKING (user design 2026-09-08): pre-compute the
    # question→attribute-key relevance ONCE per case (cached on ctx), so the
    # renderer can show only the top-K most question-relevant attributes per
    # CVT instead of flooding every bracket. Avg 96 keys/case — random top-3
    # covers 5% of gold keys; GTE top-3 covers 50%.
    _rank = getattr(ctx, "_cvt_key_rank", None)
    _qnow = str(getattr(ctx, "question", "") or "")
    if _rank is None or _rank[0] != _qnow:
        _keys = set()
        for _h, _r, _t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
            _hn = str(ctx.ents[_h]) if 0 <= _h < len(ctx.ents) else str(_h)
            _tn = str(ctx.ents[_t]) if 0 <= _t < len(ctx.ents) else str(_t)
            if is_cvt_like(_hn) != is_cvt_like(_tn):
                _keys.add(str(ctx.rels[_r]).rsplit(".", 1)[-1]
                          if 0 <= _r < len(ctx.rels) else "?")
        if _keys and _qnow:
            try:
                from kgqa.stages.stage2_entity import gte_retrieve
                _kl = sorted(_keys)
                _rows = await gte_retrieve(session, _qnow, _kl, top_k=len(_kl))
                _ranked = [r.get("candidate") for r in (_rows or [])
                           if r.get("candidate") in _keys]
                _ranked += [k for k in _kl if k not in _ranked]
                ctx._cvt_key_rank = (_qnow, _ranked)
            except Exception:
                ctx._cvt_key_rank = (_qnow, sorted(_keys))
        else:
            ctx._cvt_key_rank = (_qnow, [])
    if treq.get("corr") is not None:
        bad_name = treq["corr"]
        cands = await _entity_correction(bad_name, getattr(ctx, "question", ""), ctx, session)
        if cands:
            return {"corr_cands": cands, "bad_name": bad_name}
        if not treq["centers"]:
            # correction found nothing AND no center survived resolution — the
            # original flow's `if not centers` error (never reaches the walk)
            return {"no_centers": True}
    from kgqa.core.utils import phase_timer
    # PATTERN-PATH WALK (user design 2026-09-10, A+ integration): a call
    # whose centers are one ?var's binding set (≥4) walks ONCE at the
    # relation level — set-state transitions, bridge = any non-target
    # relation, terminal = the model's selected relations; witnesses are
    # materialized for the top-K ranked patterns (先模式,再实例化). Empty
    # pattern result falls back to the per-binding walks.
    _pf = treq.get("prefix")
    _steps = [(i, treq["rel_idxs"], treq["fid"], _pf) if _pf is not None
              else (i, treq["rel_idxs"], treq["fid"])
              for _, i in treq["centers"]]
    if (os.environ.get("SEQ_PATTERN_WALK", "0") == "1"
            and treq.get("var_name") and len(treq["centers"]) >= 4):
        try:
            _pw = _pattern_walk_evidence(ctx, treq)
        except Exception:
            _pw = None
        if _pw is not None:
            return _pw
    # MULTI-STEP PATTERN WALK (realignment spec 2026-09-11, pillar 1+2+3):
    # when the submitted family has NO direct 1-hop support on a center
    # (the case bridges were computed for), derive the relation SEQUENCE
    # center→…→family-terminal from the pattern index (≤2 named hops,
    # CVT-transparent) and submit it as MULTI-STEP step_relations — the
    # engine's forward validation (chain_expand lookahead) enforces the
    # path-consistency pillar natively, RPE falls back only on weak
    # coverage (n_steps>1), and reach no longer needs bridges-as-termini.
    _mseq = treq.get("multistep")     # {center_idx: {pat_key: (fs1, fs2)}}
    _ms_map = {}                      # bound OUTSIDE the gate (audit F1: an
                                      # env flip between phases left it unbound
                                      # and crashed the merge below)
    if _mseq and os.environ.get("SEQ_MULTISTEP", "0") == "1":
      if os.environ.get("SEQ_PAT_SEMANTIC", "1") == "1":
        # SEMANTIC PATTERN SELECTION (user ruling 2026-09-12): the derivation
        # layer enumerates ALL 2-hop patterns; HERE (B phase, GTE available)
        # they are ranked semantically against the question and each center
        # keeps top-3 MULTI-HOP patterns total (the 1-hop direct rides the
        # plain step). GATED OFF after two 48x3 A/Bs: offline it retains
        # gold patterns better (6/6 vs 5/6 top-3) but end-to-end it costs
        # -2.0pp hit / -4.4pp f1 vs the support-topk (semantic 78.5/0.641
        # with section filter, 79.2/0.657 without vs pattern4 81.2/0.701) —
        # high-fan-out patterns carry discrimination context beyond the
        # gold. DEFAULT ON after the 3-run mean verdict (2026-09-12):
        # semantic 78.7±1.4 hit / 65.1±2.0 f1 vs support 77.3±3.1 / 64.6±2.7
        # — better mean AND half the variance; pattern4's 81.2 was the top
        # of support's variance band. SEQ_PAT_SEMANTIC=0 restores support.
        try:
            from kgqa.stages.stage2_entity import gte_retrieve
            _q = str(getattr(ctx, "question", "") or "")
            _cands, _cmap = [], {}
            for _ci, _pats in _mseq.items():
                for _pk in _pats:
                    if len(_pk) == 1:
                        continue        # 1-hop direct: first-class, no quota
                    _s = " -> ".join(str(ctx.rels[_r]) for _r in _pk)
                    _k = (_ci, _s)     # per-center (audit F14: a shared
                                        # pattern string deduped centers away)
                    if _k not in _cmap:
                        _cmap[_k] = _pk
                        _cands.append(_s)
            _rank = {}
            if _cands and _q and session is not None:
                _rows = await gte_retrieve(session, _q, sorted(set(_cands)),
                                           top_k=len(set(_cands)))
                _rank = {r.get("candidate"): i
                         for i, r in enumerate(_rows or [])}
            _sel = {}
            _per_term = {}
            _cov = treq.get("multistep_cov") or {}
            # ranking = STEP COVERAGE first (user ruling 2026-09-22: a
            # pattern hitting step1 AND step2 outranks one hitting only
            # step2 — layer-2 calls have no direct connection so multi-hop
            # is the norm and through-chain coverage is the signal), then
            # GTE semantics WITHIN equal coverage, then length; 顺延 = walk
            # down the ranking until the quota fills. QUOTA IS PER
            # SUBMITTED TERMINAL RELATION (user ruling 2026-09-13,
            # Charlie-Hunnam specimen: two submitted relations must EACH
            # get their share — a per-center quota let one relation's
            # patterns crowd the other out entirely)
            for (_ci, _s) in sorted(
                    _cmap,
                    key=lambda k: (-_cov.get(k, 0),
                                   _rank.get(k[1], 999),
                                   len(_cmap[k]), k[1], k[0])):
                _term = _cmap[(_ci, _s)][-1]     # terminal relation idx
                n = _per_term.get((_ci, _term), 0)
                if n >= 3:
                    continue
                _per_term[(_ci, _term)] = n + 1
                _sel.setdefault(_ci, {})[_cmap[(_ci, _s)]] = _mseq[_ci][_cmap[(_ci, _s)]]
            # 1-hop direct patterns always survive (first-class, no quota)
            for _ci, _pats in _mseq.items():
                for _pk, _v in _pats.items():
                    if len(_pk) == 1:
                        _sel.setdefault(_ci, {})[_pk] = _v
            treq["multistep"] = _mseq = _sel
        except Exception:
            # SELECTION-FAILURE FALLBACK (user audit 2026-09-19): swallowing
            # the error left derive's UNBOUNDED enumeration (topk=0 under
            # SEQ_PAT_SEMANTIC) as treq["multistep"] — a hub case then
            # rendered every enumerated pattern. Fall back to length-first
            # top-3, the quota the selection was supposed to enforce.
            _fb = {}
            for _ci, _pats in (treq.get("multistep") or {}).items():
                for _pk in sorted(_pats, key=lambda k: (len(k), k))[:3]:
                    _fb.setdefault(_ci, {})[_pk] = _pats[_pk]
            treq["multistep"] = _fb
        if os.environ.get("SEQ_DEBUG_CHAIN", "0") == "1":
            import sys as _sys
            for _ci, _pats in (treq.get("multistep") or {}).items():
                _multi = {("->".join(str(ctx.rels[r]) for r in k)): len(k)
                          for k in _pats if len(k) > 1}
                print(f"[CHAIN-SEL] center={str(ctx.ents[_ci])[:24]!r} "
                      f"2hop+={_multi}", file=_sys.stderr, flush=True)
      # PATTERN-LEVEL MULTI-STEP (user design corrected 2026-09-11):
        # each center's top-K patterns become separate multi-step steps;
        # their pe results merge at finalize (same center, same fid).
      _ms_steps = []
      from kgqa.traversal.pattern_walk import get_pattern_index as _gpi
      _ix2 = _gpi(ctx)
      # direct family edges per center (the 1-hop pattern — shortest, so it
      # keeps its plain walk step ALONGSIDE the derived 2-hop patterns;
      # Belgium specimen: the CET/CEST direct row and the
      # containedby→time_zones chain both render, length-first ordered)
      _direct_fam = set()
      _echo_sh = set()
      for _rs, _exp in (treq.get("attr_expansion") or {}).items():
          _echo_sh.add(str(_rs))
          for _dn in (_exp.get("direct") or []):
              if _dn in ctx.rels:
                  _direct_fam.add(ctx.rels.index(_dn))
      # echo-less submitted names count too (same fallback as prepare's
      # _matched — Charlie-Hunnam specimen lost the plain direct step)
      _l1x = lambda rn: str(rn).rsplit(".", 1)[-1]
      for _rs in (treq.get("rel_names") or []):
          if str(_rs) in _echo_sh:
              continue
          for _ri, _rn in enumerate(ctx.rels):
              if (str(_rn) == str(_rs) or _l1x(_rn) == str(_rs)
                      or _l1x(_rs) == _l1x(_rn)):
                  _direct_fam.add(_ri)
                  break
      _fr_of = treq.get("cont_frontier") or {}
      for _cn, _ci in treq["centers"]:
          _pats = _mseq.get(_ci) or {}
          if _pats:
              _n_walk = 0
              for _pk, _seq in _pats.items():
                  if len(_pk) == 1:
                      continue     # 1-hop direct: the plain step walks it
                  _ms_steps.append((_ci, _seq, treq["fid"]))
                  _n_walk += 1
              _ms_map[_ci] = _n_walk
              # SEQUENCE CONTINUATION: the plain direct step applies the
              # submitted relation to the tree's FRONTIER members (per-member
              # rows, the per-binding compare render) — never to the root
              # (the root's OWN edges on the submitted relation flood the
              # render: France's 100 co2 edges swamped the 9-country rows)
              _fr = _fr_of.get(_ci)
              if _fr:
                  for _fi in _fr:
                      if any((((_ix2.head_mask.get(r, 0) >> _fi) & 1)
                              or ((_ix2.tail_mask.get(r, 0) >> _fi) & 1))
                             for r in _direct_fam):
                          _ms_steps.append((_fi, treq["rel_idxs"], treq["fid"]))
                          _ms_map[_ci] += 1
              elif (0 <= _ci < len(ctx.ents)) and any(
                      (((_ix2.head_mask.get(r, 0) >> _ci) & 1)
                       or ((_ix2.tail_mask.get(r, 0) >> _ci) & 1))
                      for r in _direct_fam):
                  _ms_steps.append((_ci, treq["rel_idxs"], treq["fid"]))
                  _ms_map[_ci] += 1
          else:
              _fr = _fr_of.get(_ci)
              if _fr:
                  for _fi in _fr:
                      _ms_steps.append((_fi, treq["rel_idxs"], treq["fid"]))
                      _ms_map[_ci] = _ms_map.get(_ci, 0) + 1
              else:
                  _ms_steps.append((_ci, treq["rel_idxs"], treq["fid"]))
                  _ms_map[_ci] = 1
      if _ms_steps:
          _steps = _ms_steps
    if os.environ.get("SEQ_REBUILD", "1") == "1":
        # RECONSTRUCTION LANE (user ruling 2026-09-19): the pattern layer
        # already searched; rebuild the selected patterns' through-chains
        # deterministically (no beam lane, no PG completeness block) and
        # archive treq["confirmed"] for the renderer.
        with phase_timer("walk"):
            pe_list = _rebuild_pe_list(ctx, treq, _mseq, _ms_map)
    else:
        with phase_timer("walk"):
            pe_list = await _run_walk_packed(ctx, _steps)
        # merge multi-pattern pe back per-center (concatenate pattern dicts)
        if _mseq and _ms_map:
            _merged, _idx = [], 0
            for _cn, _ci in treq["centers"]:
                _n = _ms_map.get(_ci, 1)
                _combined = {}
                for _pe in pe_list[_idx:_idx + _n]:
                    if isinstance(_pe, dict):
                        _combined.update(_pe)
                _merged.append(_combined if _combined else {})
                _idx += _n
            pe_list = _merged
    # PATTERN-COMPLETENESS GUARANTEE (user ruling 2026-09-13: the walk runs
    # on the reconstructed PATTERN graph — pattern branches are few, and
    # ENTITY-layer caps (beam / per-branch / support-path limits) must never
    # sever a SELECTED pattern's instantiations). Every selected 2-hop
    # pattern is instantiated EXHAUSTIVELY from the pattern index (bounded
    # only by a generous per-pattern budget; display caps apply later in the
    # render) and any hop the capped walk missed joins the pe paths.
    # [2026-09-19: reconstruction lane already rebuilds every selected
    #  pattern exhaustively-with-budget — this block only runs on the old
    #  search lane, and is DELETED on the rebuild lane per user ruling]
    if _mseq and _ms_map and os.environ.get("SEQ_REBUILD", "1") != "1":
        try:
            from kgqa.traversal.pattern_walk import get_pattern_index as _gpi2
            from kgqa.stages.formatting import PatternEvidence as _PE
            _ixg = _gpi2(ctx)
            _n = len(ctx.ents)
            for (_cn, _ci) in treq["centers"]:
                _pats = _mseq.get(_ci) or {}
                if not _pats or not (0 <= _ci < _n):
                    continue
                _slot = next((k for k, (_c2, _i2) in enumerate(treq["centers"])
                              if _i2 == _ci), None)
                if _slot is None or _slot >= len(pe_list):
                    continue
                _pe = pe_list[_slot]
                _have = set()
                for _p in (_pe.values() if isinstance(_pe, dict) else []):
                    for _tp in ((getattr(_p, "tree_data", None) or {})
                                .get("paths") or []):
                        _have.add((tuple(str(x) for x in (_tp.get("nodes") or [])),
                                   tuple(str(x) for x in (_tp.get("relations") or []))))
                _add = []
                for _pk in _pats:
                    if len(_pk) == 1:
                        continue     # 1-hop direct: plain step owns it
                    _budget = 200

                    def _enum(level, cur_nodes, chain):
                        if len(_add) >= _budget:
                            return
                        if level == len(_pk):
                            _nodes = tuple([str(ctx.ents[_ci])]
                                           + [str(ctx.ents[_x]) for _x in chain])
                            _rels = tuple(str(ctx.rels[_r]) for _r in _pk)
                            if (_nodes, _rels) not in _have:
                                _have.add((_nodes, _rels))
                                _add.append({"nodes": list(_nodes),
                                             "relations": list(_rels)})
                            return
                        r = _pk[level]
                        srcs = set()
                        for _cur in cur_nodes:
                            srcs.update(_ixg.fwd[r].get(_cur, ()))
                            srcs.update(_ixg.rev[r].get(_cur, ()))
                        for _x in sorted(srcs):
                            if not (0 <= _x < _n) or _x == _ci or _x in chain:
                                continue
                            _enum(level + 1, {_x}, chain + [_x])

                    _enum(0, {_ci}, [])
                if _add:
                    if not isinstance(_pe, dict):
                        _pe = {}
                    _pe["PG"] = _PE(label="PG", readable="",
                                    candidates=[], triples=[],
                                    tree_data={"paths": _add})
                    pe_list[_slot] = _pe
        except Exception:
            pass
    return {"pe_list": pe_list}


def _pattern_walk_evidence(ctx, treq):
    """Build PatternEvidence-compatible output for the pattern-path walk.
    Returns the bres dict ({"pe_list", "pattern_display"}) or None when the
    walk found no patterns (caller falls back to per-binding walks)."""
    from kgqa.traversal.pattern_walk import (get_pattern_index,
                                             pattern_walk, rank_display)
    from kgqa.stages.formatting import PatternEvidence
    ix = get_pattern_index(ctx)
    seeds = [cn for cn, _ci in treq["centers"]]
    # TERMINALS (1797 postmortem, two iterations): v1 = full rel_idxs
    # (direct+bridge, f1 0.6508); v2 = direct-only (0.6269 — recall loss
    # when the model's pick is off). The measured quality hole was NOT the
    # terminal set but the missing tier-1 rows (weaved below) — back to v1.
    _term_idxs = list(treq["rel_idxs"])
    pats = pattern_walk(ix, seeds, _term_idxs)
    if not pats:
        return None
    triples, candidates, paths = [], [], []
    seen_c = set()
    for k, p in enumerate(pats):
        for ch in p["witnesses"]:
            triples.extend(ch)
            paths.append({
                "nodes": [ch[0][0]] + [tr[2] for tr in ch],
                "relations": [tr[1] for tr in ch],
            })
        for a in p["answer"]:
            if a not in seen_c:
                seen_c.add(a)
                candidates.append(a)
    if not triples:
        return None
    # TIER-1 FEEDING (1797 postmortem, 2nd iteration): the v38 renderer
    # builds rows ONLY from pe tree paths — the per-binding DIRECT
    # (binding, terminal-rel) edges that _guarantee_center_direct_edges
    # appends to all_triples never reach it, so discrimination facts lost
    # the binding→value mapping entirely. Weave those edges in as paths
    # (capped per binding): the model reads the pattern groups AND every
    # binding's own terminal values.
    _n2i = {}
    for _j, _e in enumerate(ctx.ents):
        _n2i.setdefault(str(_e), _j)
    for _cn, _ci in treq["centers"]:
        if not (0 <= _ci < len(ctx.ents)):
            continue
        _n_add = 0
        for _ri in _term_idxs:
            for _t2 in ix.fwd[_ri].get(_ci, ()):
                paths.append({"nodes": [str(ctx.ents[_ci]),
                                        str(ctx.ents[_t2])],
                              "relations": [str(ctx.rels[_ri])]})
                triples.append((str(ctx.ents[_ci]), str(ctx.rels[_ri]),
                                str(ctx.ents[_t2])))
                _n_add += 1
                if _n_add >= 12:
                    break
            if _n_add >= 12:
                break
    pe = {"pat%d" % k: PatternEvidence(
        label="pat%d" % k,
        readable=" → ".join(str(ctx.rels[r]).rsplit(".", 2)[-1]
                            for r, _f in p["rels"]),
        candidates=[a for a in p["answer"][:20]],
        triples=[tr for p in pats for ch in p["witnesses"] for tr in ch],
        tree_data={"paths": paths}) for k, p in enumerate(pats)}
    pe_list = [pe] + [{} for _ in treq["centers"][1:]]
    return {"pe_list": pe_list,
            "pattern_display": rank_display(ctx, pats, _term_idxs)}


def _select_patterns_for_render(pe_values, center_name, sel_names, top_n=5):
    """① FEEDING GUARANTEE (user calibration 2026-08-26, walk-starvation
    audit): the renderer's tier-1 blocks are synthesized from the CENTER'S
    OWN selected-relation edges, so those edges must survive this
    collection. The top-N rank cut could starve them when a center's walk
    produced more detour patterns than N above its 1-hop one — every
    pattern that carries a center-anchored 1-hop selected-relation witness
    is therefore kept BEYOND the cut (bounded: at most 2 extras per selected
    relation, fwd+rev). Pure/bottom-level so the guarantee is testable."""
    keep = list(pe_values)[:top_n]
    sel = {str(r) for r in (sel_names or []) if r}
    if len(keep) == top_n and len(pe_values) > top_n and sel:
        from kgqa.core.utils import normalize as _nz
        ck = _nz(str(center_name))
        cap = top_n + 2 * len(sel)
        rest = list(pe_values)[top_n:]
        for p in rest:
            if len(keep) >= cap:
                break
            for tp in ((getattr(p, "tree_data", None) or {}).get("paths") or []):
                nds = tp.get("nodes") or []
                rls = tp.get("relations") or []
                if len(nds) == 2 and len(rls) == 1 and str(rls[0]) in sel:
                    k0 = _nz(str(nds[0]).split(":", 1)[0].strip())
                    k1 = _nz(str(nds[1]).split(":", 1)[0].strip())
                    if ck in (k0, k1):
                        keep.append(p)
                        break
    return keep


def _guarantee_center_direct_edges(ctx, centers, rel_idxs, all_triples):
    """① WALK-SIDE FEEDING GUARANTEE (multi-center starvation audit,
    2026-08-26): collect every DIRECT (center, selected relation) edge of the
    case graph that the walk's evidence missed, so it can be appended to
    all_triples. The renderer's tier-1 rows synthesize from exactly these
    edges, and the walk can drop them wholesale WITHOUT its patterns going
    empty: the 24-path support cap bounds a center's INVERSE 1-hop family
    (center = TAIL of the selected relation — 'Film --produced_by--> Ron'
    walked from center Ron Howard anchors Option-B's leaf enumeration on the
    witness's own HEAD, so the center's remaining same-relation partners
    never enumerate; Ron Howard specimen: 35 graph edges, 24 carried, 7
    producer credits invisible). Qualification is the definition of a 1-hop
    pattern instance — relation SELECTED + one endpoint a CENTER of this
    call — so the pattern-path discipline holds by construction. 补采 scans
    ctx's full edge arrays; dedup covers both orientations (the walk records
    hops in path order). Also lands the new endpoints in the same pools
    _accumulate feeds (subgraph_entities / all_candidates) so they are
    answerable and legal future centers. Pure w.r.t. the walk: same inputs →
    same additions."""
    _SCHEMA_PREFIXES = ("type.", "common.", "freebase.", "kg.", "user.",
                        "base.ontologies.", "owl#", "rdf-schema#")
    seen = set()
    for h, r, t in all_triples:
        nh, nt = normalize(str(h)), normalize(str(t))
        seen.add((nh, str(r), nt))
        seen.add((nt, str(r), nh))
    cset = {i for _n, i in centers if i is not None}
    rset = set(rel_idxs or ())
    if not cset or not rset:
        return []
    ents, rels = ctx.ents, ctx.rels
    se = getattr(ctx, "subgraph_entities", None)
    if se is None:
        se = set(); ctx.subgraph_entities = se
    at = getattr(ctx, "accumulated_triples", None)
    if at is None:
        at = set(); ctx.accumulated_triples = at
    seen_cand = {normalize(c) for c in getattr(ctx, "all_candidates", []) or []}
    added = []
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if r not in rset or (h not in cset and t not in cset):
            continue
        if not (0 <= h < len(ents) and 0 <= t < len(ents)):
            continue
        r_name = str(rels[r]) if 0 <= r < len(rels) else ""
        if not r_name or r_name.lower().startswith(_SCHEMA_PREFIXES):
            continue                       # class-based schema filter (mirrors
                                          # the walk's evidence admission)
        h_name, t_name = str(ents[h]), str(ents[t])
        if len(normalize(h_name)) < 2 or len(normalize(t_name)) < 2:
            continue
        nh, nt = normalize(h_name), normalize(t_name)
        if (nh, r_name, nt) in seen or (nt, r_name, nh) in seen:
            continue
        seen.add((nh, r_name, nt)); seen.add((nt, r_name, nh))
        added.append((h_name, r_name, t_name))
        at.add((h_name, r_name, t_name))
        se.update((h, t))
        for nm in (h_name, t_name):
            if not is_cvt_like(nm):
                nn = normalize(nm)
                if nn not in seen_cand:
                    seen_cand.add(nn); ctx.all_candidates.append(nm)
    return added



def _display_license_filter(treq, bres, centers, all_triples, candidates):
    """DISPLAY LICENSE FILTER (user ruling 2026-09-07): edges/candidates the
    walk wandered to OUT of license — riding relations NOT submitted by this
    call, beyond the centers' relation-licensed + CVT/identity-mirror
    transparent path — are removed from every display variable and never
    rendered (the 567 language-hub escape specimen). Display-only: ctx
    accumulation, bindings and the answer-time join gate are untouched.
    Transparency: CVT endpoints always pass (two-hop + CVT-extension scope);
    common.topic.*/user.* plumbing and same-name identity mirrors
    (representations_in_fiction / based_on between name-mirrored nodes) pass
    (1379:s1: person facts hang on the topic-mirror node).

    PATH-LEVEL ADMISSION (user ruling 2026-09-12, pattern-walk era): the
    edge-level rule below belongs to the OLD architecture (walk entities,
    induce patterns afterwards) — it evaluates every hop against the
    submitted names, so an engine-DERIVED pattern's mid hop (行政辖属→属地
    before the submitted time_zones terminal) reads as drift and the whole
    2-hop path is dropped, both hops, even though the walk succeeded (the
    realign5 UK/ETZ specimens: walk fine, evidence zeroed, misreported as
    RELATION_MISMATCH). Under the pattern-first architecture the unit of
    admission is the PATH: a path is legal iff its LAST hop is a submitted
    relation; mid hops are the pattern's own segments and license their
    nodes by path membership. Filtering still runs AFTER the walk completes
    (walk full, then filter). Active only for calls that carried derived
    patterns (treq.multistep) — plain calls keep the legacy rule, so the
    standing config's behavior is unchanged."""
    from kgqa.core.utils import normalize as _nz
    subs = {str(r) for r in (treq.get("rel_names") or [])}
    subs_typed = {".".join(r.rsplit(".", 2)[-2:]) for r in subs}
    center_names = [str(e) for e, _i in centers]

    def _cvt(x):
        return is_cvt_like(str(x))

    def _head(s):
        s = str(s)
        h = s.split(":", 1)[0].strip()
        return h if h != s else s

    def _mirror(a, b):
        a, b = str(a), str(b)
        return (a in b or b in a) and min(len(a), len(b)) >= 5

    def _transparent(r, a, b):
        r = str(r)
        if r.startswith(("common.topic.", "user.")):
            return True
        if r.endswith(("representations_in_fiction", "fictional_character.based_on")):
            return _mirror(a, b)
        return False

    edges = [(str(tr[0]), str(tr[1]), str(tr[2])) for tr in all_triples
             if len(tr) == 3]
    path_mode = bool(treq.get("multistep"))
    _path_admitted = None
    if path_mode:
        # license = nodes of paths whose LAST hop is a submitted relation
        # (full or typed-name match; CVT endpoints stay transparent)
        def _path_admitted(tp):
            rels = tp.get("relations") or []
            nodes = tp.get("nodes") or []
            if not rels or not nodes:
                return False
            last = str(rels[-1])
            last_typed = ".".join(last.rsplit(".", 2)[-2:])
            return (last in subs or last_typed in subs_typed
                    or _cvt(nodes[-1]) or _cvt(nodes[0]))

        lic = set(center_names)
        for pe in (bres.get("pe_list") or []):
            if not isinstance(pe, dict):
                continue
            for p in pe.values():
                for tp in ((getattr(p, "tree_data", None) or {}).get("paths")
                           or []):
                    if _path_admitted(tp):
                        for n in (tp.get("nodes") or []):
                            lic.add(str(n))
                            lic.add(_head(n))
        kept_triples = [tr for tr in all_triples
                        if len(tr) == 3
                        and (str(tr[0]) in lic or str(tr[2]) in lic)]
        kept_candidates = [c for c in candidates if str(c) in lic]
    else:
        lic = set(center_names)
        frontier = list(center_names)
        while frontier:
            x = frontier.pop()
            for h, r, t in edges:
                for a, b in ((h, t), (t, h)):
                    if a == x and b not in lic:
                        if (r in subs or _cvt(a) or _cvt(b)
                                or _transparent(r, a, b)):
                            lic.add(b)
                            frontier.append(b)
        kept_triples = [tr for tr in all_triples
                        if len(tr) == 3
                        and (str(tr[1]) in subs or _cvt(tr[0]) or _cvt(tr[2]))
                        and (str(tr[0]) in lic or str(tr[2]) in lic)]
        kept_candidates = [c for c in candidates if str(c) in lic]
    # filtered pe_list copy for the renderers (V38 reads pe_list directly)
    import copy as _copy

    def _node_ok(n):
        s = str(n)
        if s in lic or _cvt(s):
            return True
        head = _head(s)
        return head != s and (head in lic or _cvt(head))

    bres2 = dict(bres)
    pe2 = []
    for pe in (bres.get("pe_list") or []):
        if not isinstance(pe, dict):
            pe2.append(pe)
            continue
        pe2.append({lbl: p for lbl, p in pe.items()})
    for pe in pe2:
        if not isinstance(pe, dict):
            continue
        for lbl, p in pe.items():
            tris = [tr for tr in (getattr(p, "triples", None) or [])
                    if len(tr) == 3
                    and (path_mode or str(tr[1]) in subs
                         or _cvt(tr[0]) or _cvt(tr[2]))
                    and (str(tr[0]) in lic or str(tr[2]) in lic)]
            cands = [c for c in (getattr(p, "candidates", None) or [])
                     if str(c) in lic]
            try:
                p.triples = tris
                p.candidates = cands
            except AttributeError:
                pass
            # tree-path nodes carry the RENDER form 'm.xxx: [attr=.., ..]' —
            # strip the attribute tail before the lic/cvt test, or every
            # CVT-mediated path fails both tests and the V38 renderer (which
            # synthesizes its rows from these paths) goes empty (537 specimen:
            # --film--> edges present in kept_triples yet "triples: (empty)").
            # MUST stay INSIDE the lbl loop: an empty pattern-dict otherwise
            # reads a stale/unbound p (UnboundLocalError killed the whole
            # dispatch — 48 crashes / 14 cases, 2026-09-07 audit).
            td = getattr(p, "tree_data", None)
            if isinstance(td, dict):
                td["paths"] = [tp for tp in (td.get("paths") or [])
                               if (_path_admitted(tp) if path_mode else
                                   all(_node_ok(n) for n in (tp.get("nodes") or [])))]
    bres2["pe_list"] = pe2
    return kept_triples, kept_candidates, bres2


_SG_SERVED_CAP = 4000        # cached finalize result per semantic walk key —
                             # bounds _sg_served memory across an episode's
                             # walks while keeping the repeat reply's
                             # cached_evidence field self-sufficient


def _sg_finalize(treq, bres, ctx) -> str:
    """C段: correction result render OR the post-walk CPU — per-center
    accumulation, CVT-neighbor pool seeding, canonicalization, record-centric
    rendering, per-subgraph evidence sets."""
    if "corr_cands" in bres:
        return _json_result({
            "entity_error": f"'{bres['bad_name']}' is not an entity in the graph.",
            "candidates": bres["corr_cands"],
            "note": "Pick the correct entity from `candidates` (each shows NEIGHBOR "
                    "relations to disambiguate). Re-call THIS retrieve_subgraph with the "
                    "correct entity + your selected relations. CROSS-SUBGRAPH CENTER: "
                    "if this fact's RELATIONS are right but its anchor entity is wrong, "
                    "re-call with a center BORROWED from any prior subgraph's evidence "
                    "(e.g. an earlier fact's binding) plus these relations. WORKFLOW: "
                    "retrieve_relations → retrieve_subgraph per fact."})
    if bres.get("no_centers"):
        entities = treq["entities"]
        return _json_result({"error": (f"none of {entities} appeared in a prior retrieve_subgraph. "
                                       f"A center MUST be an entity from a previous retrieve_subgraph's "
                                       f"triples (or the plan anchor for fact 1) — ANY prior subgraph's "
                                       f"entities are legal centers (cross-subgraph borrowing). If any of "
                                       f"these is a variable binding, pass the ?VARIABLE "
                                       f"(center: [\"?var\"]) — the runtime expands it to all declared "
                                       f"bindings.")})
    centers = treq["centers"]
    entities = treq["entities"]
    rel_names = treq["rel_names"]
    fid = treq["fid"]
    _nudge = treq["nudge"]
    skipped = treq["skipped"]
    prior_triples = treq["prior"]
    # SEMANTIC IDEMPOTENCE: mark this (center-set, relation-set) as served
    # (see the check in _sg_prepare — same resolved walk returns cached note).
    # Wave-2 (2026-09-20): the mark is the finalize RESULT STRING (capped at
    # _SG_SERVED_CAP), written at each return below — a repeat hit replays the
    # cached evidence (cached_evidence field), not just the advice to re-read
    # what the context may already have dropped.
    _sem_key = tuple(sorted((ci, frozenset(treq.get("rel_idxs") or ()))
                            for _n, ci in (treq.get("centers") or ())))

    def _mark_served(_res_str: str) -> None:
        _served = getattr(ctx, "_sg_served", None)
        if _served is None:
            _served = {}
            ctx._sg_served = _served
        _served[_sem_key] = _res_str[:_SG_SERVED_CAP]
    # per-center walk; accumulate evidence inline, collect PatternEvidence for the
    # cross-center merged display (one block per relation pattern, all roots under it)
    candidates, all_triples = [], []
    collected = []   # (center_name, PatternEvidence)
    _TOP_PATTERNS = 5   # keep only the top-N patterns (ordered by the walk: path length +
                        # relation hit) per center — excess patterns are noise; the walk already
                        # prunes partial-pattern paths (full-pattern only), this caps the count.
    # SUBMITTED-TERMINAL EVIDENCE DISCIPLINE (user design 2026-09-11,
    # Ron-Howard awards specimen): the walk keeps loose bridge targets for
    # REACH (traversal-only measured mismatch 39 vs 1 — the loose terminal
    # IS the mismatch fix), but the EVIDENCE admits only paths TERMINATED
    # by the model's SUBMITTED relations: bridge carrier edges may appear
    # mid-path, yet segments ENDING at a bridge relation (every award edge
    # in the 3-hop environment) are not answer paths — they are what blew
    # tens of triples into hundreds on hub centers and, over turns, the
    # context. Filter AFTER _accumulate (legality pool keeps the full walk
    # enumeration — the answer gate is unchanged), BEFORE pattern
    # collection for render.
    _sub_terms = set()
    for _exp in (treq.get("attr_expansion") or {}).values():
        for _dn in (_exp.get("direct") or []):
            _sub_terms.add(".".join(str(_dn).rsplit(".", 2)[-2:]))
    _has_bridges = (os.environ.get("SEQ_SUBTERM", "0") == "1"
                    and any(_exp.get("bridge") for _exp in
                            (treq.get("attr_expansion") or {}).values()))

    def _pe_filter(p):
        """Keep only tree paths whose LAST relation is a submitted terminal
        (+ their CVT-penetration edges). Returns a filtered PatternEvidence
        copy, or the original when nothing to filter (no bridges, or the
        filter keeps everything)."""
        if not _has_bridges or not _sub_terms:
            return p
        from kgqa.stages.formatting import PatternEvidence as _PE
        paths = (p.tree_data or {}).get("paths") or []
        keep_p = [tp for tp in paths
                  if tp.get("relations")
                  and ".".join(str(tp["relations"][-1]).rsplit(".", 2)[-2:])
                  in _sub_terms]
        if len(keep_p) == len(paths):
            return p
        keep_nodes = {str(_pn.split(":", 1)[0].strip())
                      for tp in keep_p
                      for _pn in (tp.get("nodes") or [])}
        keep_tr = []
        for tr in (p.triples or []):
            if len(tr) != 3:
                continue
            h, _r, t = str(tr[0]), str(tr[1]), str(tr[2])
            if h in keep_nodes or t in keep_nodes:
                keep_tr.append(tr)
        keep_c = [c for c in (p.candidates or []) if str(c) in keep_nodes]
        if not keep_p and not keep_tr:
            return None
        return _PE(label=p.label, readable=p.readable,
                   candidates=keep_c, triples=keep_tr,
                   tree_data={"paths": keep_p})

    for (e, i), pe in zip(centers, bres["pe_list"]):
        if not pe:
            continue
        # ① feeding guarantee (see _select_patterns_for_render): the top-N
        # cut alone could starve a center's direct selected-relation edges
        # when its walk produced many higher-ranked detour patterns.
        for p in _select_patterns_for_render(pe.values(), e, rel_names,
                                             _TOP_PATTERNS):
            _accumulate(ctx, i, p)      # legality pool: FULL walk output
            pf = _pe_filter(p)
            if pf is None:
                continue
            collected.append((e, pf))
            for tr in (pf.triples or []):
                if len(tr) == 3:
                    all_triples.append(tr)
            for c in (pf.candidates or []):
                if not is_cvt_like(c) and c not in candidates:
                    candidates.append(c)
    # NOTE: leaf-set full enumeration now lives in the evidence builder
    # (build_pattern_evidence_triples, Option B) — same-prefix/different-leaf
    # paths are one pattern with N leaves; the support-path cap no longer
    # bounds leaf cardinality. No parallel enumeration here.
    # ① walk-side feeding guarantee (see _guarantee_center_direct_edges): the
    # renderer's tier-1 rows synthesize from the centers' OWN selected-relation
    # edges — those edges must be in all_triples whatever the walk's support
    # caps did to their patterns (inverse 1-hop families were silently capped).
    # Under the submitted-terminal discipline the guarantee is scoped to the
    # SUBMITTED relations (full rel_idxs would re-admit bridge edges).
    if _has_bridges and _sub_terms:
        _guar_rels = set()
        for _exp in (treq.get("attr_expansion") or {}).values():
            for _dn in (_exp.get("direct") or []):
                if _dn in ctx.rels:
                    _guar_rels.add(ctx.rels.index(_dn))
        _guar_idxs = sorted(_guar_rels) or treq["rel_idxs"]
    else:
        _guar_idxs = treq["rel_idxs"]
    for tr in _guarantee_center_direct_edges(ctx, centers, _guar_idxs,
                                             all_triples):
        all_triples.append(tr)
        for x in (tr[0], tr[2]):
            if not is_cvt_like(x) and x not in candidates:
                candidates.append(x)
    if os.environ.get("SEQ_LICENSE_FILTER", "1") != "0":
        # ANSWER-LEGALITY LEDGER (user ruling 2026-09-08): record every entity
        # the walk enumerated BEFORE the display filter — the answer may be any
        # entity that appeared in the walk, not only what the render showed
        # (the filter is anti-drift for the model's eyes, not an answer gate).
        _seen = getattr(ctx, "walk_seen_entities", None)
        if _seen is None:
            _seen = ctx.walk_seen_entities = []
        _seen_len0 = len(_seen)      # PATTERN-STATE provenance: this call's delta
        _seen_n = {str(c) for c in _seen}
        for _tr in all_triples:
            if len(_tr) == 3:
                for _x in (_tr[0], _tr[2]):
                    if str(_x) not in _seen_n:
                        _seen_n.add(str(_x))
                        _seen.append(str(_x))
        for _c in candidates:
            if str(_c) not in _seen_n:
                _seen_n.add(str(_c))
                _seen.append(str(_c))
        # PATTERN-STATE (user design 2026-09-10): remember THIS walk's node set
        # (the ledger delta) per fact — when the model binds a ?var from this
        # fact, later single-?var calls from that var continue with this
        # territory as the prefix mask instead of re-walking it per binding.
        _fp = getattr(ctx, "fid_pattern", None)
        if _fp is None:
            _fp = ctx.fid_pattern = {}
        _fp[fid] = {
            "nodes": frozenset(str(x) for x in _seen[_seen_len0:]),
            "single_center": (centers[0][1] if len(centers) == 1 else None),
        }
        all_triples, candidates, bres = _display_license_filter(
            treq, bres, centers, all_triples, candidates)
    if not all_triples:
        # WALK-NOTHING (Wave-1): observation only — the old text asserted
        # "the fact is right" (a verdict an empty walk cannot support) and
        # jumped straight to relation substitution. Layered diagnosis,
        # cheapest layer first: unused sibling relations → one reworded
        # retrieve_relations → borrow a center from earlier evidence →
        # close the fact as mismatched and continue.
        _err = {"error": "NO_EVIDENCE: this center + relation selection "
                "produced no advancing evidence. Diagnosis, cheapest layer "
                "first: (1) unused sibling relations from your last "
                "retrieve_relations output? retrieve_subgraph with those. "
                "(2) else re-call retrieve_relations once with the same "
                "question reworded. (3) else if only the center was wrong, "
                "borrow a center from earlier evidence. (4) else the planned "
                "fact itself may be off-target — close it as "
                "[fid ✗ mismatch] and continue.",
                "entities": entities, "relations": rel_names}
        if treq.get("attr_expansion"):
            _err["relation_expansion"] = treq["attr_expansion"]
        _ne_str = _json_result(_err)
        _mark_served(_ne_str)   # NO_EVIDENCE walks are served too — a repeat
        return _ne_str          # replays the diagnosis instead of re-walking

    # ensure ALL tree-visible entities (incl CVT-attr entities pe.triples may miss) are answerable
    _collect_cvt_neighbors_to_pool(ctx)

    # ── relation-grouped tree (replaces pattern-based _format_merged) ──────────────
    # First flip any triples whose direction is reversed vs the raw graph (the undirected
    # walk records center-first, which reverses relations pointing INTO the center, e.g.
    # mascot.team rendered as 'team --team--> mascot'). Then resolve CVT-mediated edges
    # → named→named, deduped. Inverse / variant relations that surfaced the SAME entity
    # pair via N patterns collapse to ONE edge per entity pair here.
    all_triples = _canonicalize_triples(all_triples, ctx)
    # record-centric rendering (replaces _resolve_cvt_edges + _merge_edges):
    # CVT-with-holder → record `holder → title [from=..; to=..]` (direction-normalized);
    # CVT-without-holder → flattened named→named; direct edges → merged.
    # CROSS-CALL DEDUP REMOVED (user ruling, 2026-08-20): the old suppression
    # (ctx.shown_edges persisting across calls, keyed (h,r,t)) was born as an
    # economy hack for walk-bloated subgraphs; admission now lives in the walk
    # layer (pattern-path discipline). Suppressing a triple that is a link of
    # THIS subgraph's pattern path severs the path and masks entities from an
    # edge's displayed extension (the Faroese/Denmark bug: sg2 rendered only
    # the new tails of Denmark--languages_spoken, hiding the discriminating
    # Faroese|Danish). The set is now per-call: duplicates arriving via multi-
    # ple channels/patterns within ONE call still collapse; every subgraph
    # re-renders the full evidence its own pattern paths justify.
    shown = set()
    from kgqa.core.utils import phase_timer
    with phase_timer("render"):
        # EVIDENCE DISPLAY (2026-08-24, user ruling V3): DENSE legacy detail
        # lines (h --r--> t1 | t2 | …, CVT records inline [attr=val], 120 cap
        # + branch refs) + a CAPPED pattern overview (≤3 shapes per relation,
        # path-terminal first, start-anchored). The V2 wide-table experiment
        # (SEQ_RENDER_V2=1) lost density and hid CVT attrs — kept for A/B only.
        _al = next((e for e in entities if str(e).startswith("?")), None)
        _paths = []
        for _e2, _p2 in collected:
            _paths.extend((_p2.tree_data or {}).get("paths") or [])
        if os.environ.get("SEQ_RENDER_V38", "") == "1":
            # V3.8 (2026-09-02, user + Codex design ①): TRIPLE-FORM rows —
            # only two legal compression shapes (same h+r→many tails /
            # many heads→same r+t); CVT attrs inline; no pattern-paths
            # overview, no forced candidates line (row entities are
            # candidates). Walk-faithful edges, V37h dedup discipline.
            from kgqa.agent.seq_render_v38 import render_v38_ack
            v38 = render_v38_ack(treq, bres, ctx)
            if v38 and v38 != "(empty)":
                tree_lines = v38.split("\n")
                _ov, _blocks, _covered = [], [], set()
            else:
                _ov, _blocks, _covered = render_evidence_sections(
                    _paths, [e for e, _i in centers], _al, all_triples,
                    rel_names or [])
                _uncovered = _select_uncovered(all_triples, _covered,
                                               set(rel_names or []))
                tree_lines, n_overlap = _render_records(_uncovered, shown)
                if tree_lines:
                    tree_lines = _group_facts_by_rel(tree_lines)
        elif os.environ.get("SEQ_RENDER_V37", "") == "1":
            # V3.7 (2026-08-31): candidate-centric lines — the candidate leads,
            # its instantiated pattern path follows (user design: Iowa ◂
            # Missouri River ←partially_contains─ m.xxx ─partially_contained_by→).
            # Entity-terminal-first combo selection + all centers render.
            from kgqa.agent.seq_render_v37 import render_v37_ack
            v37 = render_v37_ack(treq, bres, ctx)
            if v37 and v37 != "(empty)":
                tree_lines = v37.split("\n")
                _ov, _blocks, _covered = [], [], set()
            else:
                _ov, _blocks, _covered = render_evidence_sections(
                    _paths, [e for e, _i in centers], _al, all_triples,
                    rel_names or [])
                _uncovered = _select_uncovered(all_triples, _covered,
                                               set(rel_names or []))
                tree_lines, n_overlap = _render_records(_uncovered, shown)
                if tree_lines:
                    tree_lines = _group_facts_by_rel(tree_lines)
        elif os.environ.get("SEQ_RENDER_V36", "") == "1":
            from kgqa.agent.seq_render_v36 import render_v36_ack
            v36 = render_v36_ack(treq, bres, ctx)
            if v36 and v36 != "(empty)":
                tree_lines = v36.split("\n")
                _ov, _blocks, _covered = [], [], set()
            else:
                _ov, _blocks, _covered = render_evidence_sections(
                    _paths, [e for e, _i in centers], _al, all_triples,
                    rel_names or [])
                _uncovered = _select_uncovered(all_triples, _covered,
                                               set(rel_names or []))
                tree_lines, n_overlap = _render_records(_uncovered, shown)
                if tree_lines:
                    tree_lines = _group_facts_by_rel(tree_lines)
        elif os.environ.get("SEQ_RENDER_V35", "") == "1":
            # V3.5 (2026-08-31): relation-signature groups + name-trie with
            # R3 sibling merge + zero-loss folds + CVT attribute brackets
            from kgqa.agent.seq_render_v35 import render_v35_ack
            v35 = render_v35_ack(treq, bres, ctx)
            if v35 and v35 != "(empty)":
                tree_lines = v35.split("\n")
                n_overlap = 0
        elif os.environ.get("SEQ_RENDER_V2", "") == "1":
            from kgqa.stages.evidence_display import render_records_compat
            tree_lines, n_overlap = render_records_compat(
                all_triples, shown, anchors=[e for e, _i in centers],
                anchor_label=_al, patterns=_paths)
        else:
            # V3.3 (2026-08-25 redesign): ONE unified renderer organizes ALL
            # structured evidence — 1-hop blocks per selected relation first,
            # then k-hop blocks length-ascending (principle 1), each block
            # holding only instances that COMPLETE its path shape,
            # reconstructed from the canonicalized edges (principle 2).
            # Facts = legacy dense remainder (_render_records), fed by
            # _select_uncovered (within-call dedup + CVT attr revival — the
            # Kim Richards specimen: selection filtered the record attrs,
            # every remaining edge collapsed as a bare-CVT tail, and the
            # fresh shown-set counted the duplicates as "already shown in a
            # prior subgraph" on the case's FIRST retrieval).
            if os.environ.get("SEQ_RENDER_V35", "") == "1":
                _ov, _blocks, _covered = [], [], set()
                tree_lines = v35.split("\n")
            else:
                _ov, _blocks, _covered = render_evidence_sections(
                    _paths, [e for e, _i in centers], _al, all_triples,
                    rel_names or [])
            _uncovered = _select_uncovered(all_triples, _covered,
                                           set(rel_names or []))
            tree_lines, n_overlap = _render_records(_uncovered, shown)
            # REMAINDER BY RELATION (user rulings 2026-08-25, Debussy + naming
            # specimens): the leftover section is per-relation grouped and its
            # name is decoupled from the plan's fact vocabulary (f1/f2/sg) —
            # "facts" as a section name is BANNED; selected-relation edges were
            # already swept into blocks, so this holds only true remainders
            if tree_lines:
                tree_lines = _group_facts_by_rel(tree_lines)
            # V4 semantic layers (user ruling: candidates are the core; the
            # answer ROLE is harness-known from the fact's ?var slot).
            # SEQ_EVIDENCE_LAYERS=1 enables; DEFAULT OFF after two cohort
            # runs showed the header costs ~4pp without gain (V4 0.6634 /
            # V4b 0.6490 vs V3.2 0.7037) — kept as experimental arm.
            _layers_on = os.environ.get("SEQ_EVIDENCE_LAYERS", "0") == "1"
            _lay = (layer_evidence(fid, ctx, _paths, all_triples,
                                   centers, entities) if _layers_on else {})
            _head = []
            if _lay.get("fact"):
                _head.append(f"fact: {_lay['fact']}")
            if _lay.get("var") and _lay.get("answer"):
                _head.append(f"answer-role: {_lay['var']}")
                _head.append("── answer candidates (this subgraph) ──")
                # per-LAST-HOP-RELATION groups (Lala Anthony specimen): multi-
                # relation selection mixes terminals of different semantics
                # (place_of_birth → Red Hook vs people_born_here → its
                # residents) — attribute each group to its relation so the
                # model filters by the fact's semantics itself
                for _r3, _ts in _lay.get("by_rel") or []:
                    _shown = " | ".join(_ts[:40])
                    _more = f" …(+{len(_ts) - 40})" if len(_ts) > 40 else ""
                    _head.append(f"via {_r3}: {_shown}{_more}")
            if _ov or _blocks:
                tree_lines = ([f"  {l}" for l in _head] + ["pattern paths:"]
                              + [f"  {l}" for l in _ov]
                              + [f"  {l}" for l in _blocks]
                              + (["  ── other relations ──"] + tree_lines if tree_lines else [])
                              + ([f"  attribute values: {' | '.join(_lay['attrs'])}"]
                                 if _lay.get("attrs") else [])
                              + ([f"  source/intermediate: {' | '.join(_lay['source'])}"]
                                 if _lay.get("source") else [])
                              + ([f"  {_lay['var']} (this call): {_lay['n_answer']} entities"]
                                 if _lay.get("var") else []))
    # NO "already shown in a prior subgraph" message (user ruling 2026-08-20
    # restated 2026-08-25, Kim Richards specimen): cross-call suppression is
    # forbidden — every subgraph re-renders the full evidence its pattern
    # paths justify. n_overlap now only reflects _render_records' internal
    # record-key collapse (the record itself still renders), never a hidden
    # prior display.
    # GRAPH-STRUCTURE GATE attempted 2026-08-18 (Arizona audit: reworded-subquestion
    # iteration burning the budget) and REVERTED after measurement: unconditional
    # 2-strike −1.6pp, same-centers-conditioned −2.7pp (3-seed 0.7850 vs 0.8117
    # base). The nudge text perturbs the retrieval distribution more than the rare
    # budget-exhaustion event costs. Budget-exhaustion fallback belongs in the
    # answer rules (§18 fallback clause), not in the retrieval layer.
    _TREE_LINE_BUDGET = 200
    if len(tree_lines) > _TREE_LINE_BUDGET:
        dropped = len(tree_lines) - _TREE_LINE_BUDGET
        tree_lines = tree_lines[:_TREE_LINE_BUDGET]
        tree_lines.append(f"  ... +{dropped} lines truncated")
    # CANDIDATE PROVENANCE REMOVED (user ruling 2026-09-12, asked repeatedly):
    # the "candidates not shown above" annotation listed bare entity names —
    # valid information renders as TRIPLES (the subgraph's atom), anything
    # without a visible edge is removed. The answer-legality pool and the
    # wandered-candidate ledger below are unchanged.
    _fe = getattr(ctx, "fact_evidence", None)
    if _fe is None:
        _fe = {}; ctx.fact_evidence = _fe
    # WANDERED-CANDIDATE LEDGER (see _expand_entities): remember the walk
    # candidates that have NO visible edge in this render — they stay legal
    # answer entities and future ?var expansions carry them as centers
    _blob = "\n".join(tree_lines)
    _wx = getattr(ctx, "walk_extra", None)
    if _wx is None:
        _wx = ctx.walk_extra = []
    _wxset = {str(x) for x in _wx}
    for _c in candidates:
        _cs = str(_c)
        if (not is_cvt_like(_cs) and _cs not in _blob
                and _cs not in _wxset):
            _wxset.add(_cs)
            _wx.append(_cs)

    # The merged triples above ARE the evidence view — discriminator attrs (dates,
    # incumbent) live on their own edges ('Robert --to--> 1968', 'Ted --to-->
    # (incumbent)'), so the model compares candidates directly from the triples.
    # candidate_attrs / discriminating_attrs are intentionally NOT displayed: they
    # re-stated the same triples (tree/attrs overlap) and the present-vs-ABSENT flood
    # over-loaded the prompt. Builders kept (not discarded) for offline scoring.
    multi = len(centers) > 1
    # PER-SUBGRAPH EVIDENCE SET (2026-08-21, user proposal — hallucination check):
    # record the named entities THIS subgraph displayed, keyed by fact id. The
    # checkpoint validator rejects bindings that never appeared in the declaring
    # fact's subgraph (Kevin Costner specimen: the sg1.f1 re-declaration merged
    # the OTHER actor's films into sg1 — cross-subgraph contamination passed
    # the global pool check but dies against sg1's own evidence set).
    _fe = getattr(ctx, "fact_evidence", None)
    if _fe is None:
        _fe = {}; ctx.fact_evidence = _fe
    from kgqa.core.utils import normalize as _nz
    _fe[fid] = _fe.get(fid, set()) | \
        {_nz(c) for c in candidates if not is_cvt_like(c)} | \
        {_nz(x) for h, r, t in all_triples for x in (h, t) if not is_cvt_like(x)}
    # TOOL-SIDE CANDIDATE POOL (Wave-2, 2026-09-20): the SYSTEM JOIN source.
    # Same names the per-subgraph hallucination filter admits (candidates +
    # triple endpoints, CVT records excluded) but kept in ORIGINAL casing and
    # UNIONed across this fid's retrievals — the pool is the walk's full
    # enumeration, never the model's curated checkpoint subset. Keyed through
    # fact_key_map so `sg1.f2`-style call args land on the canonical fid the
    # join reads (fact_bindings/fact_vars keys); a fid with no pool falls back
    # to its declared bindings there.
    _fcp = getattr(ctx, "fact_candidate_pool", None)
    if _fcp is None:
        _fcp = ctx.fact_candidate_pool = {}
    _fid_c = (getattr(ctx, "fact_key_map", None) or {}).get(fid, fid)
    _fcp[_fid_c] = (_fcp.get(_fid_c) or set()) | \
        {str(c) for c in candidates if not is_cvt_like(c)} | \
        {str(x) for h, r, t in all_triples for x in (h, t) if not is_cvt_like(x)}
    # retrieval sequence per fid (variable-freezing clock): each NEW subgraph
    # retrieval for this fid advances it; a frozen declaration may only be
    # replaced after the clock advanced (fresh evidence for the same fact).
    # Evidence set is a UNION across retrievals — the legal binding domain is
    # "original sg1 ∪ new sg1 retrievals" (user ruling: 注册必须基于对应的子图).
    _fseq = getattr(ctx, "fact_evidence_seq", None)
    if _fseq is None:
        _fseq = {}; ctx.fact_evidence_seq = _fseq
    _fseq[fid] = _fseq.get(fid, 0) + 1
    _v36 = (os.environ.get("SEQ_RENDER_V36", "") == "1"
            or os.environ.get("SEQ_RENDER_V37", "") == "1"
            or os.environ.get("SEQ_RENDER_V38", "") == "1")
    # ANSWER-TYPE ALIGNMENT of the display roster (user audit 2026-09-08):
    # CVT attribute VALUES (character role names in a film question) flooded
    # the flat candidates line. A value appearing ONLY as a CVT attribute —
    # never as a named direct-edge endpoint — is dropped unless its
    # attribute key's type class matches the plan's answer_type (a person
    # question KEEPS actor= values — 1171's gold is one; a film question
    # DROPS character= names — 25 specimen). Display-only: the legality
    # pool (walk_seen_entities / all_candidates) is untouched.
    _res = {
        "fact_id": fid,
        "entities": [e for e, _ in centers] if not _v36 else "",
        "triples": "\n".join(tree_lines) if tree_lines else "(empty)",

        "skipped_centers": skipped,
        "note": ((_nudge + " ") if _nudge else "") +
                (("UNCHANGED EVIDENCE (repeat): these relations produced no NEW edges since "
                  "your previous subgraph — the same evidence is displayed again so it stays "
                  "in context. ACT on it (checkpoint / answer / move to the next fact); "
                  "re-retrieving will return the same. ") if treq.get("_repeat_evidence") else "") +
                (("Multiple centers retrieved with one shared relation set — COMPARE them via "
                  "the triples (an edge '--to--> (incumbent)' marks the current holder). ") if multi else "") +
                (("SEQUENCE EXTENSION applied to several frontier members — the new layer's "
                  "edges are per-candidate: COMPARE them across the candidates (values, dates, "
                  "ids) and declare the values the evidence supports (any non-empty count). "
                  "Final discrimination happens at answer analysis. "
                  "Mid-chain entities are HOPS, not answers. ") if treq.get("cont_compare") else "") +
                ("Evidence blocks group triples by entity: 'h --rel--> t1 | "
                  "t2' merges tails, 'h1 | h2 --rel--> t' merges heads. "
                  "m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; "
                  "use their named ATTRIBUTES (actor, character, office "
                  "holder, jurisdiction), shown inline in brackets. "
                  "Discriminator attributes (dates, incumbent) appear as "
                  "their own edges — compare them to pick. Pick the next "
                  "center FROM these triples."),
    }
    if treq.get("attr_expansion"):
        # FAMILY EXPANSION ECHO (user audit 2026-09-09): show what each
        # submitted attribute was expanded to — direct matches (relations
        # touching the center) plus CVT bridges (center→carrier) — so the
        # model audits its own selection and the trajectory shows the
        # expansion instead of hiding it.
        _res["relation_expansion"] = treq["attr_expansion"]
    if treq.get("anchor_seq"):
        # SEQUENCE-STATE ECHO (SEQ_REL_SEQ): the anchor's accumulated
        # relation layers + per-layer completion counts — the model's cue
        # that a later fact continuing this subgraph just re-calls with the
        # ANCHOR + the new relation (the system appends the layer).
        _res["anchor_sequence"] = treq["anchor_seq"]
    if treq.get("layer_action"):
        # LAYER-ACTION ECHO (user ruling 2026-09-15): the model's first
        # visibility into what the system DID with its submission —
        # extend (new layer), update:k (replaced layer k's relations), or
        # repeat (already in layers, pick different relations)
        _res["layer_action"] = treq["layer_action"]
    if bres.get("pattern_display"):
        # PATTERN-PATH WALK echo (2026-09-10): the call ran as ONE set-state
        # walk over the binding set; this is the ranked pattern list the
        # witness chains below re-instantiate
        _res["pattern_paths"] = bres["pattern_display"]
    _res_str = _json_result(_res)
    _mark_served(_res_str)
    return _res_str


async def retrieve_subgraph(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph retrieval for ONE fact: one shared relation set applied to one or more
    center entities (the fact's candidate centers, packed into a single call). For each
    center the proven SAPS walk runs (multi-hop, K-path, CVT-penetrating); results are
    merged — dense tree + a candidate_attrs summary grouped by candidate under the shared
    relation pattern, so the model can compare across candidates (e.g. latest/largest).
    Accumulates seen entities into the subgraph.
    Sequential composition of the three phases (see _sg_prepare)."""
    treq = _sg_prepare(args, ctx)
    if treq["kind"] == "done":
        return treq["result"]
    bres = await _sg_execute(treq, ctx, session)
    return _sg_finalize(treq, bres, ctx)


# ───────────────────────── SEQ dispatch ─────────────────────────
# THREE-PHASE SPLIT (perf-4, 2026-08-23): dispatch_prepare (A: pure CPU —
# decompose/answer compute fully, the retrieval tools resolve entities and
# build their GTE/walk requests) → dispatch_execute (B: the IO — GTE calls and
# walk-lane submits, batched by the round-level collectors) → dispatch_finalize
# (C: pure CPU — evidence accumulation, rendering, result assembly). dispatch()
# keeps the sequential composition for the per-case runner and every existing
# caller; the round-level scheduler (seq_rollout / replay_dispatch) drives the
# phases directly so one round runs A for all cases, fires every GTE/walk
# request together, then runs C.

def dispatch_prepare(tool_name: str, args: Dict[str, Any], ctx) -> dict:
    """A段: returns a tool request. kind="done" carries the fully-computed
    result (no IO); kind="rr"/"sg" carry the GTE/walk request for
    dispatch_execute; kind="unknown" defers the error render to finalize."""
    if tool_name in ("plan", "decompose"):
        return {"kind": "done", "result": _do_seq_decompose(args, ctx)}
    if tool_name == "retrieve_relations":
        return _rr_prepare(args, ctx)
    if tool_name == "retrieve_subgraph":
        return _sg_prepare(args, ctx)
    if tool_name == "answer":
        return {"kind": "done", "result": _do_answer(args, ctx)}
    return {"kind": "unknown", "tool": tool_name}


async def dispatch_execute(treq: dict, ctx, session):
    """B段: the IO half of the prepared request (no-op for done/unknown)."""
    k = treq.get("kind")
    if k in ("rr", "corr"):
        return await _rr_execute(treq, ctx, session)
    if k == "sg":
        return await _sg_execute(treq, ctx, session)
    return None


def dispatch_finalize(treq: dict, bres, ctx) -> str:
    """C段: render the result string (pure CPU)."""
    k = treq.get("kind")
    if k == "done":
        return treq["result"]
    if k in ("rr", "corr"):
        return _rr_finalize(treq, bres, ctx)
    if k == "sg":
        return _sg_finalize(treq, bres, ctx)
    return _json_result({"error": f"unknown tool: {treq.get('tool')}"})


async def dispatch(tool_name: str, args: Dict[str, Any], ctx, session) -> str:
    # accept both new SEQ names and old names (backward-compat for stale trajectories)
    treq = dispatch_prepare(tool_name, args, ctx)
    if treq["kind"] in ("done", "unknown"):
        return dispatch_finalize(treq, None, ctx)
    bres = await dispatch_execute(treq, ctx, session)
    return dispatch_finalize(treq, bres, ctx)
