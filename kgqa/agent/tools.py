"""Tool JSON schemas + dispatch for the native tool-calling agent.

Schemas are the surface the model sees; dispatch executes each accepted tool
against a CaseContext using the ROBUST shared engines (GTE, k_queue_traverse,
compress_paths) — imported, never modified.

Key design: `retrieve` is MODEL-DRIVEN — the model's `relation_hint` is the GTE
query (not the raw question). This is the fix for the 46-47% relation-retrieval
miss diagnosed in the stage pipeline.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from kgqa.core.utils import normalize
from kgqa.stages.stage2_entity import gte_retrieve
from kgqa.traversal.k_queue import k_queue_traverse
from kgqa.traversal.frontier import relation_prior_expand
from kgqa.traversal.cvt import is_cvt_like
from kgqa.stages.stage5_traverse import stage_5_graph_traversal
from kgqa.stages.formatting import build_pattern_evidence_triples, _render_path_tree
from kgqa.core.case_state import CaseState
from kgqa.traversal.path_utils import compress_paths


def _candidates_from_triples(triples, anchor_name: str):
    """Pull answer-entity names out of a PatternEvidence's triples.

    build_pattern_evidence_triples expands CVT mediators into triples like
    (CVT, office_holder, Kasich), so the answer NAME lives as the object of a
    CVT-headed triple. compress_paths, by contrast, only collects candidates
    from a path's non-CVT nodes — so CVT-terminated paths (anchor -> CVT, no
    further non-CVT node in the path) end up with an EMPTY candidate list even
    though the office_holder is present in the triples/tree.

    Rules:
    - take the OBJECT of any triple whose head is a CVT (the CVT attribute value),
    - also take a non-CVT, non-anchor object of a forward (non-CVT) triple,
    - skip CVT ids themselves, the anchor, and bare years/short tokens.
    Returns a deduped list preserving first-seen order.
    """
    anchor_norm = normalize(anchor_name) if anchor_name else ""
    seen = set()
    out = []
    for h, r, t in triples:
        for name in (t, h):
            if not name or is_cvt_like(name):
                continue
            if anchor_norm and normalize(name) == anchor_norm:
                continue
            nc = normalize(name)
            if len(nc) < 2:
                continue
            # Skip bare years / pure numbers (CVT value noise like from=2011).
            cleaned = nc.replace(" ", "")
            if cleaned.isdigit() and len(cleaned) <= 4:
                continue
            if nc not in seen:
                seen.add(nc)
                out.append(name)
    return out


# ---------------------------------------------------------------------------
# Tool JSON schemas (OpenAI tool-calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "decompose",
            "description": (
                "Break the question into atomic lookup facts and any filter "
                "conditions. MUST be the first tool call. Separate every distinct "
                "lookup into its own fact — never merge two lookups into one fact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "description": "Ordered atomic lookups.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string",
                                       "description": "Stable fact id, e.g. 'f1', 'f2'."},
                                "text": {"type": "string",
                                         "description": "Natural-language lookup sentence."},
                                "relation_hint": {
                                    "type": "string",
                                    "description": (
                                        "the specific KG relation type or precise "
                                        "semantic to retrieve, e.g. 'profession / "
                                        "occupation of the person', 'place of birth', "
                                        "'capital', 'director of the film' — be "
                                        "specific, not vague like 'notable_for'"
                                    ),
                                },
                            },
                            "required": ["id", "text", "relation_hint"],
                        },
                        "minItems": 1,
                    },
                    "conditions": {
                        "type": "array",
                        "description": "Filters on the answer (temporal, superlative, type). Empty if none.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {"type": "string",
                                         "description": "e.g. 'before', 'after', 'largest', 'type'."},
                                "value": {"type": "string"},
                            },
                            "required": ["id", "type", "value"],
                        },
                    },
                },
                "required": ["facts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve",
            "description": (
                "Retrieve candidate entities for ONE fact. The system uses your "
                "relation_hint as the retrieval query against KG relations, then "
                "walks the graph from the anchor. Call this once per fact_id, "
                "after decompose, before select."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string",
                                "description": "The id of the fact to retrieve (from decompose)."},
                    "relation_hint": {
                        "type": "string",
                        "description": (
                            "the specific KG relation type or precise semantic to "
                            "retrieve, e.g. 'profession / occupation of the person', "
                            "'place of birth', 'capital' — be specific, not vague "
                            "like 'notable_for'"
                        ),
                    },
                },
                "required": ["fact_id", "relation_hint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_relations",
            "description": (
                "After retrieve, each fact has structurally-pruned candidate "
                "relations (GTE-15 intersected with anchor's reachable edges). "
                "Pick the relation(s) that form the answer chain for each fact. "
                "This is your judgment on chain semantics — the system only "
                "guarantees structural reachability, you decide which relations "
                "actually answer the question. Call ONCE after all facts are "
                "retrieved, before select."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selections": {
                        "type": "array",
                        "description": "One entry per fact.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fact_id": {"type": "string"},
                                "relations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Relation names chosen from that fact's candidate_relations.",
                                },
                            },
                            "required": ["fact_id", "relations"],
                        },
                    },
                },
                "required": ["selections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select",
            "description": (
                "Traverse the KG over all facts' chosen relations and return a "
                "numbered evidence-tree overview. Call exactly ONCE after "
                "select_relations (or after retrieve if you skipped "
                "select_relations). The overview shows each branch with a "
                "right-side number (#1, #2, ...). Use expand_branch(N) to drill "
                "into relevant branches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string",
                             "description": "Optional one-line rationale (ignored by the system)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_branch",
            "description": (
                "Expand one branch of the evidence tree to see its detailed "
                "candidates and CVT attributes. Call for branches whose overview "
                "looks relevant to the question. You may expand multiple branches "
                "or skip directly to answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branch_id": {
                        "type": "string",
                        "description": "The branch number from the tree overview, e.g. '1', '2', '3a'.",
                    },
                },
                "required": ["branch_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": (
                "Emit the final answer entities, copied verbatim from the evidence. "
                "Call LAST. The entities MUST come from the retrieved candidates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity-name strings, verbatim from evidence.",
                    },
                },
                "required": ["entities"],
            },
        },
    },
]


def tools_for_state(state_name: str) -> List[Dict[str, Any]]:
    """Return only the schema(s) allowed in the given harness state.

    Restricting the offered tools each turn makes the model's job trivial and
    makes out-of-order calls impossible at the API layer too.
    """
    allowed = {
        "INIT": {"decompose"},
        "RETRIEVE": {"retrieve"},
        "SELECT_RELATIONS": {"select_relations"},
        "SELECT": {"select"},
        "EXPAND": {"expand_branch", "answer"},
        "ANSWER": {"answer"},
        "DONE": set(),
    }
    names = allowed.get(state_name, set())
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] in names]


# ---------------------------------------------------------------------------
# Dispatch — execute an accepted tool against a CaseContext
# ---------------------------------------------------------------------------


def _json_result(payload: Any) -> str:
    """Serialize a dispatch result to a compact JSON string for the tool role."""
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"error": "non-serializable result"}, ensure_ascii=False)


async def dispatch(tool_name: str, args: Dict[str, Any], ctx, session) -> str:
    """Execute one accepted tool. Returns a JSON-serializable result string."""
    if tool_name == "decompose":
        return _json_result({"facts": args.get("facts", []),
                             "conditions": args.get("conditions", [])})

    if tool_name == "retrieve":
        return await _do_retrieve(args, ctx, session)

    if tool_name == "select_relations":
        return _do_select_relations(args, ctx)

    if tool_name == "select":
        return await _do_select(ctx)

    if tool_name == "expand_branch":
        return _do_expand_branch(args, ctx)

    if tool_name == "answer":
        return _do_answer(args, ctx)

    return _json_result({"error": f"unknown tool: {tool_name}"})


async def _do_retrieve(args: Dict[str, Any], ctx, session) -> str:
    """MODEL-DRIVEN GTE + STRUCTURAL PRUNING.

    Pipeline: gte_retrieve(hint, top_k=15) → intersect with anchor's outgoing
    relations (structural reachability) → store as CANDIDATES for the model to
    pick from in select_relations.

    The structural prune removes relations that are semantically close (high GTE
    score) but graph-unreachable from the anchor (e.g. geography.mountain_range.*
    when the answer needs location.location.containedby). It is pure gain —
    validated to drop 0 correct relations while cutting GTE-15 to median 4-5.

    This does NOT decide the final relations — the model picks from these
    pruned candidates via select_relations, because only the model can judge
    whether the full relation chain answers the question.
    """
    fact_id = str(args.get("fact_id", ""))
    hint = (args.get("relation_hint") or "").strip()
    if not hint:
        hint = ctx.fact_texts.get(fact_id, ctx.question)
    if ctx.anchor_idx is None:
        return _json_result({"fact_id": fact_id, "error": "no_anchor",
                             "candidates": []})

    # 1. GTE over ALL case relations — hint as query, keep top-15
    try:
        rows = await gte_retrieve(
            session, hint, ctx.rels,
            candidate_texts=ctx.rel_texts, top_k=15)
    except Exception as e:
        return _json_result({"fact_id": fact_id, "error": f"gte_failed: {e}",
                             "candidates": []})

    gte_rel_ids: List[int] = []
    for r in rows:
        cand = r.get("candidate")
        if cand and cand in ctx.rels:
            gte_rel_ids.append(ctx.rels.index(cand))

    # 2. Structural prune: intersect GTE-15 with the structural scope for this
    #    fact. For fact_1 this is the anchor's neighbors. For fact_i (i>1) it's
    #    the neighbors of entities reached via prior facts' selected relations
    #    (the chain: anchor --[f1]--> entity --[f2]--> ...). This ensures fact2
    #    sees relations matching the entity-type fact1 arrives at, not the
    #    anchor's type — fixing CWQ multi-hop (e.g. person→country→religion:
    #    fact2 gets country.religions, not person.religion).
    scope_rel_ids = _chained_source_rel_ids(ctx, fact_id)
    pruned_rel_ids = [ri for ri in gte_rel_ids if ri in scope_rel_ids]

    # Fallback: if prune empties everything (chain broken or GTE missed all
    # structurally-reachable rels), keep the raw GTE-15 so the model still has
    # something to choose from.
    if not pruned_rel_ids:
        pruned_rel_ids = gte_rel_ids[:8]

    # 3. Store as CANDIDATES (not final). Model picks via select_relations.
    #    Also init fact_relations as the full candidate set so that if the
    #    model skips select_relations, the traversal still has something.
    ctx.fact_relation_candidates[fact_id] = list(pruned_rel_ids)
    ctx.fact_relations[fact_id] = set(pruned_rel_ids)  # default = all candidates

    return _json_result({
        "fact_id": fact_id,
        "relation_hint": hint,
        "gte_relations": [ctx.rels[i] for i in gte_rel_ids[:15]],
        "candidate_relations": [ctx.rels[i] for i in pruned_rel_ids],
        "n_candidates": len(pruned_rel_ids),
        "note": (f"GTE-15 pruned to {len(pruned_rel_ids)} structurally-reachable "
                 "relations. Call select_relations to pick the ones that form "
                 "the answer chain, then select to traverse."),
    })


def _anchor_outgoing_rel_ids(ctx) -> set:
    """Relation indices touching the anchor (undirected: h==anchor OR t==anchor).

    Undirected because Freebase stores some relations with reversed edge
    direction vs semantic intuition (e.g. `book.author.works_written` is stored
    as Work→Author, not Author→Work). Using only directed outgoing (h==anchor)
    would prune these correct relations. Undirected keeps the structural-
    reachability benefit (only relations the anchor actually touches) without
    losing reversed edges.
    """
    out = set()
    ai = ctx.anchor_idx
    if ai is None:
        return out
    for h, r in zip(ctx.h_ids, ctx.r_ids):
        if h == ai:
            out.add(r)
    for t, r in zip(ctx.t_ids, ctx.r_ids):
        if t == ai:
            out.add(r)
    return out


def _reachable_rel_ids_from(entities, ctx) -> set:
    """Relation indices reachable from a set of entity indices (outgoing only).

    Directed (h==entity): we only follow edges where the entity is the HEAD.
    This prevents loops where a CVT reached from anchor connects back to the
    anchor (or to a person entity), which would re-admit all of that person's
    relations into the scope — defeating the chain narrowing.
    """
    out = set()
    ent_set = set(entities)
    for h, r in zip(ctx.h_ids, ctx.r_ids):
        if h in ent_set:
            out.add(r)
    return out


def _entities_via_relations(source_entities, rel_ids, ctx, exclude_source=True) -> set:
    """Entities reachable from source via the given relation set (1 hop).

    Used by chained retrieve: given fact_{i-1}'s selected relations and the
    anchor (or the entities fact_{i-2} reached), compute where fact_{i-1}
    arrives — those entities' neighbors become fact_i's structural scope.

    exclude_source: if True (default), do not return entities that are in the
    source set — prevents the chain from looping back to where it started
    (e.g. anchor→CVT→anchor via the reverse edge of the same relation).
    """
    rel_set = set(rel_ids)
    src = set(source_entities)
    reached = set()
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if r not in rel_set:
            continue
        if h in src:
            reached.add(t)
        if t in src:
            reached.add(h)
    if exclude_source:
        reached -= src  # prevent loops
    return reached


def _chained_source_rel_ids(ctx, fact_id) -> set:
    """Structural scope for fact_i: which relations are reachable?

    - fact_1 (first fact): anchor's neighbor relations (undirected).
    - fact_i (i>1): relations reachable from the entities that fact_{i-1}'s
      selected relations reach from the anchor (or from fact_{i-2}'s endpoint).
      This is the chain: anchor --[f1 rels]--> entity --[f2 rels]--> ...
    """
    # Determine fact order from ctx.fact_ids (all facts from decompose, in order)
    fids = list(ctx.fact_ids)
    if not fids:
        return _anchor_outgoing_rel_ids(ctx)

    try:
        idx = fids.index(fact_id)
    except ValueError:
        return _anchor_outgoing_rel_ids(ctx)

    if idx == 0:
        # First fact: scope = anchor neighbors
        return _anchor_outgoing_rel_ids(ctx)

    # Chained: walk from anchor through each prior fact's best-guess relation.
    # At retrieve time, select_relations hasn't run yet, so we can't use the
    # model's final choice. Instead use each prior fact's TOP-1 GTE candidate
    # (the highest-scoring relation) as the chain link — it's the most likely
    # relation, and keeps the scope tight (using ALL candidates spreads too wide
    # and lets wrong-type relations like person.religion leak back in).
    source = {ctx.anchor_idx} if ctx.anchor_idx is not None else set()
    for prior_fid in fids[:idx]:
        cands = ctx.fact_relation_candidates.get(prior_fid, [])
        if not cands:
            prior_rels = ctx.fact_relations.get(prior_fid, set())
        else:
            # Use only the top-1 GTE candidate (first in the pruned list)
            prior_rels = {cands[0]} if cands else set()
        if prior_rels:
            source = _entities_via_relations(source, prior_rels, ctx)
            if not source:
                break  # chain broken, no entities reachable

    if not source:
        # Chain broken — fall back to anchor neighbors (best effort)
        return _anchor_outgoing_rel_ids(ctx)
    return _reachable_rel_ids_from(source, ctx)


def _do_select_relations(args: Dict[str, Any], ctx) -> str:
    """Model decision: pick the relation(s) forming the answer chain, per fact.

    After retrieve, each fact has structurally-pruned candidate relations
    (GTE-15 ∩ anchor-outgoing). The model sees these and selects which ones
    form a coherent answer chain. This is the model's judgment on chain
    semantics — structure only guarantees reachability, not that the chain
    answers the question.

    Args:
        selections: [{"fact_id": "f1", "relations": ["people.person.parents"]}, ...]
    Each relation must be among that fact's candidates (validated).
    """
    selections = args.get("selections") or []
    if not selections:
        return _json_result({"error": "no selections provided"})

    chosen = {}
    skipped = []
    for sel in selections:
        fid = str(sel.get("fact_id", ""))
        rels_chosen = sel.get("relations") or []
        candidates = ctx.fact_relation_candidates.get(fid, [])
        cand_names = {ctx.rels[i] for i in candidates}
        valid_ids = []
        invalid = []
        for rn in rels_chosen:
            if rn in cand_names:
                valid_ids.append(ctx.rels.index(rn))
            else:
                invalid.append(rn)
        if valid_ids:
            chosen[fid] = set(valid_ids)
            ctx.fact_relations[fid] = set(valid_ids)
        if invalid:
            skipped.append({"fact_id": fid, "invalid": invalid})
        if not valid_ids:
            # model picked nothing valid — keep all candidates as fallback
            chosen[fid] = set(candidates)

    return _json_result({
        "selected": {fid: [ctx.rels[i] for i in ids] for fid, ids in chosen.items()},
        "skipped_invalid": skipped,
        "note": "relations locked. Call select to traverse the relation chain.",
    })


def _paths_to_preview(paths, ctx, limit: int = 10) -> List[str]:
    """Render a few witness paths as 'anchor --[rel]--> cand' for the model."""
    out = []
    anchor_name = ctx.ents[ctx.anchor_idx] if ctx.anchor_idx is not None and 0 <= ctx.anchor_idx < len(ctx.ents) else "?"
    for p in paths[:limit]:
        nodes = p.get("nodes", [])
        rels = p.get("relations", [])
        if not nodes:
            continue
        parts = [anchor_name]
        for i, ni in enumerate(nodes[1:], 1):
            ri = rels[i - 1] if i - 1 < len(rels) else None
            rtxt = ctx.rels[ri] if ri is not None and 0 <= ri < len(ctx.rels) else "?"
            nm = ctx.ents[ni] if 0 <= ni < len(ctx.ents) else "?"
            parts.append(f"--[{rtxt}]--> {nm}")
        out.append(" ".join(parts))
    return out


def _hint_match_rank(patterns, fact_rel_sets, fids):
    """Rank relation-pattern branches by how well they align with the
    decomposed facts' relation hints.

    Coarse ranking (the system does this; the model does the fine selection
    by expanding branches). For each branch path, align the per-fact hint
    relation-id sets against the path's relation-id sequence in order:

        hints = [set_f1, set_f2, ...]   (one id-set per fact, in fact order)
        path  = [r1, r2, ...]           (relation id sequence of the branch)

    Walk the path hops left-to-right; consume hints left-to-right. Hop i
    counts as a "level hit" if it belongs to the next unconsumed hint's set,
    and that hint is then consumed (so a single hint is matched at most once —
    this avoids a step-1 relation matching at both hop 1 and hop 2 and being
    double-counted).

    Rank key: (#level-hits desc, path-length asc) — more aligned hops first,
    shorter paths break ties. Branches with zero hits sink to the bottom but
    are NOT dropped (the model may still want them).

    Returns the patterns list sorted by this key (stable).
    """
    if not fact_rel_sets:
        # No hints available (e.g. decompose/retrieve skipped) — leave as-is.
        return list(patterns)

    def _key(lp):
        rels = (lp.get("best_raw_path") or {}).get("relations", [])
        rel_seq = [r for r in rels if r is not None]
        hints_iter = iter(fact_rel_sets)
        try:
            cur_hint = next(hints_iter)
        except StopIteration:
            cur_hint = None
        hits = 0
        consumed_any = False
        for r in rel_seq:
            if cur_hint is not None and r in cur_hint:
                hits += 1
                consumed_any = True
                try:
                    cur_hint = next(hints_iter)
                except StopIteration:
                    cur_hint = None
                    # remaining hops can't raise hits further
                    break
        return (-hits, len(rel_seq))

    return sorted(patterns, key=_key)


async def _do_select(ctx) -> str:
    """Run the FULL multi-step traversal (stage_5_graph_traversal) over all
    facts' hinted relations, then build a TREE overview of evidence.

    This reuses the proven stage-5 engine (mode-level logical paths + CVT
    expansion + RPE fallback) for traversal, AND the proven Stage-8 evidence
    builders (build_pattern_evidence_triples + _render_path_tree) for
    presentation — so the overview shows CVT-expanded candidates (Kasich, not
    CVT node IDs) and a trie structure, not a flat list.

    The model uses this overview to SELECT which branch to expand (Stage 7's
    role), then expand_branch(N) drills into the chosen branch (Stage 8's role).
    """
    fids = [fid for fid in ctx.fact_ids if fid in ctx.fact_relations]
    if not fids or ctx.anchor_idx is None:
        return _json_result({"error": "no_facts_or_anchor",
                             "evidence": [], "candidates": []})
    step_relations = [ctx.fact_relations[fid] for fid in fids]

    # Build a minimal CaseState and run the proven stage-5 traversal
    cs = CaseState(case_id=ctx.case_id or "agent", case_num=ctx.case_num or 0,
                   sample=ctx.sample, pilot_row=ctx.pilot_row)
    cs.anchor_idx = ctx.anchor_idx
    cs.anchor_name = ctx.anchor_name
    cs.h_ids, cs.r_ids, cs.t_ids = ctx.h_ids, ctx.r_ids, ctx.t_ids
    cs.ents, cs.rels, cs.rel_texts = ctx.ents, ctx.rels, ctx.rel_texts
    cs.step_relations = step_relations
    cs.steps = [{"id": fid} for fid in fids]   # n_steps = n_facts
    cs.breakpoints = ctx.breakpoints or {}
    cs.active = True
    try:
        await stage_5_graph_traversal([cs])
    except Exception as e:
        return _json_result({"error": f"stage5_failed: {e}",
                             "evidence": [], "candidates": []})

    # stage-5 output: cs.paths / cs.logical_paths / cs.answer_candidates
    ctx.all_paths = cs.paths or []
    ctx.all_candidates = list(getattr(cs, "answer_candidates", []) or [])
    bp_indices = set(cs.breakpoints.values()) if cs.breakpoints else set()
    if cs.anchor_idx is not None:
        bp_indices.discard(cs.anchor_idx)
    if ctx.all_paths:
        patterns = compress_paths(ctx.all_paths, ctx.ents, ctx.rels, ctx.anchor_idx, bp_indices)
    else:
        patterns = cs.logical_paths or []
    ctx.logical_paths = patterns

    # ── Coarse rank by hint alignment (system does this; model does fine
    # selection via expand_branch). Aligns each branch's relation-id sequence
    # against the per-fact hint relation sets, in fact order. More aligned
    # hops + shorter path = more relevant. All patterns are kept — the model
    # sees the whole ranked tree and decides which branches to expand.
    fids = [fid for fid in ctx.fact_ids if fid in ctx.fact_relations]
    fact_rel_sets = [ctx.fact_relations[fid] for fid in fids]
    ranked_patterns = _hint_match_rank(patterns, fact_rel_sets, fids)

    # ── Build CVT-aware evidence via the proven Stage-8 builder ──
    # build_pattern_evidence_triples returns dict[label -> PatternEvidence]
    # where each PatternEvidence has:
    #   .candidates  — CVT-expanded named entities (office_holder names, not CVT IDs)
    #   .triples     — full (h, r, t) triples with CVT attributes expanded
    #   .tree_data   — nested trie (display-named nodes) for _render_path_tree
    # This fixes Blocker A (candidates now include CVT-expanded entities) and
    # Blocker B (overview rendered as a tree, not a flat list).
    valid_patterns = [lp for lp in ranked_patterns if isinstance(lp, dict) and lp.get("best_raw_path")]
    pat_evidence = build_pattern_evidence_triples(
        valid_patterns, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids,
        ctx.anchor_idx, max_grouped_lines=120)

    # Preserve the hint-alignment order in the evidence dict output.
    # build_pattern_evidence_triples labels patterns P1, P2, ... in input
    # order, so iterating pat_evidence in insertion order == ranked order.
    ranked = list(pat_evidence.items())

    # Cap the overview to keep it readable (the model can still expand any
    # branch whose #N appears). Hint-aligned order means the most relevant
    # branches are always at the top.
    ranked = ranked[:30]

    # ── Build numbered tree overview (numbers on the RIGHT, per user spec) ──
    ctx.branches = {}
    overview_blocks = []
    anchor_name = ctx.anchor_name or ""
    for i, (label, pe) in enumerate(ranked, 1):
        bid = str(i)
        # Render this branch's evidence as a YAML-like trie (Stage 8 form).
        tree_lines = _render_path_tree(pe.tree_data, max_lines=24)

        # Resolve the branch's candidates. pe.candidates comes from
        # compress_paths (path non-CVT nodes) and is EMPTY for CVT-terminated
        # paths (anchor -> CVT), even though the office_holder NAME is present
        # in pe.triples / the rendered tree. Fall back to deriving candidates
        # from the triples so the overview header reflects what's actually in
        # the branch (Blocker A completion).
        cands = list(pe.candidates)
        if len(cands) < 3 and pe.triples:
            derived = _candidates_from_triples(pe.triples, anchor_name)
            seen_c = {normalize(c) for c in cands}
            for d in derived:
                if normalize(d) not in seen_c:
                    cands.append(d)
                    seen_c.add(normalize(d))

        # Store the full branch data for expand_branch to return verbatim.
        ctx.branches[bid] = {
            "label": label,
            "candidates": cands,
            "triples": pe.triples,
            "readable": pe.readable,
            "tree_lines": tree_lines,
        }

        # Compose the branch block with the #N marker on the RIGHT of each leaf.
        cand_str = ", ".join(cands[:4])
        if len(cands) > 4:
            cand_str += f", ... (+{len(cands) - 4})"
        header = (f"  branch {bid}: {pe.readable}  →  {len(cands)} candidates "
                  f"[{cand_str}]")

        # Append #N to the right of each rendered tree line.
        if tree_lines:
            body = "\n".join(f"    {ln}    #{bid}" for ln in tree_lines)
        else:
            body = ""
        overview_blocks.append(header + ("\n" + body if body else ""))

    # Collect all candidates (for gt_hit + fallback).
    seen = set(); dedup = []
    for c in ctx.all_candidates:
        nc = normalize(c)
        if nc and nc not in seen:
            seen.add(nc); dedup.append(c)
    ctx.selected_candidates = dedup[:60]

    overview_text = (
        f"RETRIEVED CANDIDATES ({len(dedup)} entities, your answer pool):\n"
        + ", ".join(dedup[:40])
        + f"\n\nEVIDENCE TREE (ranked by relevance; #N on the right marks each "
        "branch):\n"
        "Branches are pre-ranked by how well their relation chain aligns with "
        "your decomposed facts (most aligned, shortest paths first). ANALYZE "
        "the tree, decide which branches are relevant to the question, and call "
        "expand_branch(N) on each you choose to see its full triples + CVT "
        "attributes. Then answer from what you expanded.\n\n"
        + "\n\n".join(overview_blocks)
    )

    return _json_result({
        "n_patterns": len(ranked),
        "overview": overview_text,
        "candidates": ctx.selected_candidates[:20],
    })


def _do_expand_branch(args: Dict[str, Any], ctx) -> str:
    """Expand one branch to show its FULL evidence for Stage-8 reasoning.

    Returns (per spec §4 step 2):
    - branch_id / readable: identity + the relation chain.
    - candidates: the CVT-expanded named entities (e.g. Kasich, Strickland —
      NOT the CVT node IDs). This is the PatternEvidence.candidates list.
    - triples: the full (h, r, t) triples with CVT attributes expanded inline.
    - tree: the rendered YAML-like trie (from _render_path_tree) showing the
      CVT attributes at the leaves.
    """
    bid = str(args.get("branch_id", ""))
    br = ctx.branches.get(bid)
    if not br:
        return _json_result({"error": f"unknown branch_id '{bid}'",
                             "valid_branches": list(ctx.branches.keys())})
    cands = br.get("candidates", [])
    triples = br.get("triples", [])
    tree_lines = br.get("tree_lines", [])

    # Triples as ["(h, r, t)", ...] strings for compact, LLM-friendly display.
    triple_strs = [f"({h}, {r}, {t})" for h, r, t in triples[:40]]

    payload = {
        "branch_id": bid,
        "readable": br.get("readable", ""),
        "candidates": cands[:30],
        "n_candidates": len(cands),
        "triples": triple_strs,
        "n_triples": len(triples),
    }
    # Prefer the rendered trie (it folds CVT attributes into the leaves); fall
    # back to bare triples if the trie was empty (e.g. no support paths).
    if tree_lines:
        payload["tree"] = "\n".join(tree_lines)
    return _json_result(payload)


def _do_answer(args: Dict[str, Any], ctx) -> str:
    """Capture the model's answer entities. The `entities` array is the
    authoritative answer surface (schema-required)."""
    entities = args.get("entities") or []
    if not isinstance(entities, list):
        entities = []
    entities = [str(e).strip() for e in entities if str(e).strip()]

    ctx.llm_answer_preds = entities
    ctx.llm_answer_str = " | ".join(entities)
    return _json_result({"entities": entities})
