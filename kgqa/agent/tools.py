"""Tool JSON schemas + dispatch for the native tool-calling agent.

Schemas are the surface the model sees; dispatch executes each accepted tool
against a CaseContext using the ROBUST shared engines (GTE, k_queue_traverse,
compress_paths) — imported, never modified.

Key design: `retrieve` is MODEL-DRIVEN — the model's `subquestion` is the GTE
query (not the raw question). This is the fix for the 46-47% relation-retrieval
miss diagnosed in the stage pipeline.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

# Structural prune was REMOVED (3-run multi-sample A/B, n=45 heldout): the
# chained-scope intersection was net-negative — F1 0.7438 with-prune vs 0.7649
# no-prune, recall 115 vs 121 gold-reached. The scope demands an accurate chain,
# and a contaminated chain (an upstream fact's noisy candidate consumes a
# downstream answer entity) cuts the bridging relation the last hop needs (e.g.
# WebQTest-1483: form_of_government, which GTE ranked #14, was structurally
# pruned). After the G1 instruct optimization GTE recall is strong enough that
# raw top-K suffices. The scope is still computed (scope_rel_ids) and used ONLY
# for candidate-text contextualization (a GTE ranking aid), never for pruning.
#
# GTE top-K (default 30). top-15 was tested and DROPS F1 to 0.6776 (too tight,
# recall 112) — keep 30.
_GTE_TOPK = int(os.environ.get("KGQA_GTE_TOPK", "30"))

from kgqa.core.utils import normalize
from kgqa.stages.stage2_entity import gte_retrieve
from kgqa.traversal.k_queue import k_queue_traverse
from kgqa.traversal.frontier import relation_prior_expand
from kgqa.traversal.cvt import is_cvt_like
from kgqa.stages.stage5_traverse import stage_5_graph_traversal
from kgqa.stages.formatting import build_pattern_evidence_triples, _render_path_tree
from kgqa.core.case_state import CaseState
from kgqa.traversal.path_utils import compress_paths
from kgqa.traversal.logical_paths import materialize_selected_logical_patterns


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
                "Decompose the question STEM into an ordered chain of sub-questions. "
                "Each fact is one sub-question (a full question in the stem's own "
                "words); fact 1's answer feeds fact 2, and so on — the order of "
                "`facts` IS the solving order. Decompose only what the stem asks. "
                "MUST be the first tool call. Never merge two sub-questions into one "
                "fact; emit the sub-question itself, not an action command."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "description": "Ordered sub-questions (the solving chain).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string",
                                       "description": "Stable fact id, e.g. 'f1', 'f2', 'f3'."},
                                "subquestion": {
                                    "type": "string",
                                    "description": (
                                        "this step's sub-question — a full question in "
                                        "the stem's own words (the retrieval query AND "
                                        "the solving step). No bare phrase, no action "
                                        "verb, no inferred vocabulary, no verification fact."
                                    ),
                                },
                                "start_type": {
                                    "type": "string",
                                    "description": "entity TYPE this step's answer is (what the next step starts from, e.g. 'team', 'stadium'); for the first fact, the anchor's type.",
                                },
                            },
                            "required": ["id", "subquestion", "start_type"],
                        },
                        "minItems": 1,
                    },
                    "anchor": {
                        "type": "string",
                        "description": "known concrete entity the chain starts from (lowest-ambiguity name). Optional — the system derives it if omitted.",
                    },
                    "question_chains": {
                        "type": "array",
                        "description": "OMIT for a single sequential question (facts in order are the chain). Include only for: (a) same-layer conjunctive constraints — wrap those facts in one step {\"con\":[fact ids]}; or (b) 2+ independent questions — one entry per question, each with its own anchor.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "anchor": {"type": "string",
                                           "description": "known entity this chain starts from (omit to use the top-level anchor)."},
                                "steps": {
                                    "type": "array",
                                    "description": "ordered solving steps. Each element is a fact id (a sequential step) or {\"con\":[fact ids]} (conjunctive: those facts' relations are unioned at one layer, not chained). Every fact id here MUST be declared in facts[].",
                                    "items": {},
                                },
                            },
                            "required": ["steps"],
                        },
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
                "subquestion as the retrieval query against KG relations, then "
                "walks the graph from the anchor. Call this once per fact_id, "
                "after decompose, before select."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string",
                                "description": "The id of the fact to retrieve (from decompose)."},
                    "subquestion": {
                        "type": "string",
                        "description": (
                            "a rephrased sub-question for this fact, closer to the "
                            "question's own words (the retrieval query)"
                        ),
                    },
                },
                "required": ["fact_id", "subquestion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_relations",
            "description": (
                "Each fact from decompose lists its candidate_relations next to "
                "its text/subquestion (the step's sub-question). Read each "
                "fact's text, then select ALL candidate relations that express "
                "what that step asks for — the system only guarantees the "
                "candidates are structurally reachable, you decide which ones "
                "actually answer the step. Call ONCE after decompose; the system "
                "traverses the chosen relations and returns the evidence tree."
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
                "LEGACY — traversal now runs inline inside select_relations and "
                "its evidence tree is returned there. This tool is kept only for "
                "back-compat and is not offered in any active state. Do not call."
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
            "name": "expand_branches",
            "description": (
                "Expand one or more branches of the evidence tree to see their "
                "detailed candidates and CVT attributes. Pass the branch numbers "
                "whose overview looks relevant to the question, in a single batch "
                "call. You may also skip directly to answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branch_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Branch numbers from the tree overview, e.g. ['1','2']. Pass all branches you want to expand in one call.",
                    },
                },
                "required": ["branch_ids"],
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
        "RETRIEVE": {"retrieve", "select_relations"},  # retrieve = optional fallback
        "SELECT_RELATIONS": {"select_relations", "retrieve"},  # retrieve = fallback
        "EXPAND": {"expand_branches", "answer"},
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
        return await _do_decompose(args, ctx, session)

    if tool_name == "retrieve":
        return await _do_retrieve(args, ctx, session)

    if tool_name == "select_relations":
        return await _do_select_relations(args, ctx, session)

    if tool_name == "select":
        # Legacy: select is now merged into select_relations, but keep for
        # backward compat with any trajectory that calls it directly.
        return await _do_select(ctx)

    if tool_name in ("expand_branch", "expand_branches"):
        return _do_expand_branch(args, ctx)

    if tool_name == "answer":
        return _do_answer(args, ctx)

    return _json_result({"error": f"unknown tool: {tool_name}"})


async def _gte_for_fact(ctx, session, fact_id, hint):
    """Run GTE retrieve + structural prune for one fact. Returns (candidates, gte_raw).

    Mirrors _do_retrieve's candidate construction (start_type + last-two schema
    segments) and structural pruning. If structural prune yields empty, falls
    back to the raw GTE top-15 (relations outside 2-hop scope are better than
    no candidates).
    """
    scope_rel_ids = _chained_source_rel_ids(ctx, fact_id)
    _is_f1 = bool(ctx.fact_ids) and fact_id == ctx.fact_ids[0]
    start_type = (ctx.anchor_name if _is_f1 else (ctx.fact_start_types.get(fact_id) or ctx.anchor_name)) or ""
    if start_type:
        cand_texts = []
        for ri, rid in enumerate(ctx.rels):
            if ri in scope_rel_ids:
                parts = rid.split('.')
                tail = ' '.join(p.replace('_', ' ') for p in parts[-2:])
                cand_texts.append(f"{start_type} {tail}")
            else:
                cand_texts.append(rid)
    else:
        cand_texts = ctx.rel_texts
    try:
        rows = await gte_retrieve(
            session, hint, ctx.rels,
            candidate_texts=cand_texts, top_k=_GTE_TOPK)
    except Exception as _e:
        # Log the error so GTE failures are visible (don't silently return empty)
        import sys as _sys
        print(f"  GTE error in _gte_for_fact({fact_id}): {_e}", file=_sys.stderr)
        return [], []
    gte_rel_ids = []
    gte_raw = []
    for r in rows:
        rid = r.get("candidate")
        idx = r.get("index")
        # GTE returns either an int index or the candidate value itself.
        # If index is present and valid, use it; otherwise look up by name.
        if isinstance(idx, int) and 0 <= idx < len(ctx.rels):
            gte_rel_ids.append(idx)
            gte_raw.append(ctx.rels[idx])
        elif isinstance(rid, str) and rid in ctx.rels:
            ri = ctx.rels.index(rid)
            gte_rel_ids.append(ri)
            gte_raw.append(rid)
        elif isinstance(rid, int) and 0 <= rid < len(ctx.rels):
            gte_rel_ids.append(rid)
            gte_raw.append(ctx.rels[rid])
    # No structural prune (see module note): candidates = raw GTE top-K. The
    # scope is still used above only for candidate-text contextualization.
    pruned = list(gte_rel_ids)
    return pruned, gte_raw


async def _do_decompose(args: Dict[str, Any], ctx, session) -> str:
    """Decompose the question into facts + run GTE retrieve for each fact.

    Merges the old decompose + retrieve into one step: the model writes facts
    (each with subquestion), and the system immediately runs GTE semantic
    search for each fact's hint, returning the structurally-pruned candidate
    relations inline. The model then calls select_relations to pick from these.

    The model also outputs `anchor` and optional `endpoints` (LLM ambiguity
    analysis). These are resolved to graph idx by _resolve_anchor (called in
    react_loop after validate). decompose itself just echoes them back.

    If structural pruning yields empty for a fact (relations outside 2-hop
    scope), falls back to raw GTE top-15 so the model always has candidates.
    """
    facts = args.get("facts", [])
    chains = args.get("question_chains") or []
    chain_anchor = chains[0].get("anchor") if (isinstance(chains, list) and chains) else None
    anchor = args.get("anchor") or chain_anchor
    endpoints = args.get("endpoints") or []
    conditions = args.get("conditions", [])

    # Build candidate_relations for each fact via GTE, then present each fact's
    # question text + subquestion ALONGSIDE its candidate relations so the
    # model can judge each candidate's relevance to that fact's specific
    # question (rather than matching relation names against the whole question).
    candidates_per_fact = {}
    gte_raw_per_fact = {}
    for f in facts:
        fid = str(f.get("id") or f.get("fact_id") or "")
        if not fid:
            continue
        hint = f.get("subquestion") or f.get("relation_hint") or f.get("text") or ctx.question
        cands, gte_raw = await _gte_for_fact(ctx, session, fid, hint)
        candidates_per_fact[fid] = cands
        gte_raw_per_fact[fid] = gte_raw
        # Store on ctx so select_relations can validate picks
        ctx.fact_relation_candidates[fid] = cands

    # Co-locate each fact's question text with its candidate relations. The
    # model reads each fact as a unit: "this step asks for X — which of these
    # relations expresses X?". This avoids the model matching a relation name
    # against the whole-question wording and missing relations that carry the
    # answer but read like attribute labels (e.g. education.institution for a
    # "where did X go to college" question).
    facts_with_candidates = []
    for f in facts:
        fid = str(f.get("id") or f.get("fact_id") or "")
        cands = candidates_per_fact.get(fid, [])
        facts_with_candidates.append({
            "id": fid,
            "text": f.get("text", ""),
            "subquestion": f.get("subquestion") or f.get("relation_hint", ""),
            "start_type": f.get("start_type", ""),
            "candidate_relations": [ctx.rels[i] for i in cands if i < len(ctx.rels)],
        })

    return _json_result({
        "facts": facts_with_candidates,
        "conditions": conditions,
        "anchor": anchor,
        "endpoints": endpoints,
        "note": ("Each fact now lists its candidate_relations next to its text. "
                 "For EACH fact, read its text/subquestion and select ALL "
                 "relations that express what that step asks for. Call "
                 "select_relations with one entry per fact."),
    })


async def _do_retrieve(args: Dict[str, Any], ctx, session) -> str:
    """MODEL-DRIVEN GTE + STRUCTURAL PRUNING.

    Pipeline: gte_retrieve(hint, top_k=30) → intersect with anchor's outgoing
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
    hint = (args.get("subquestion") or args.get("relation_hint") or "").strip()
    if not hint:
        hint = ctx.fact_texts.get(fact_id, ctx.question)
    if ctx.anchor_idx is None:
        return _json_result({"fact_id": fact_id, "error": "no_anchor",
                             "candidates": []})

    # 1. GTE over ALL case relations — hint as query, keep top-15.
    # Candidate texts are contextualized for relations in this fact's structural
    # scope: "<start_type> <last-two-schema-segments>" instead of a bare
    # dot-notation id. The start_type is the anchor name (f1) or the type noun
    # the previous hop arrives at (f2+, e.g. "airport", "country"). Only the
    # LAST TWO schema segments are kept (dropping the leading domain bucket word
    # like "location"/"government" — it disturbs ordinary-case GTE ranking by
    # pulling toward every relation in that domain). This bridges the
    # deep-semantic ↔ surface-wording gap (model writes "bordering", KG stores
    # "adjoining_relationship") without answer leakage: the candidate carries
    # the relation's own schema name (legitimate KG structure), the hint carries
    # only the model's natural-language wording. Relations OUTSIDE the scope
    # keep the bare id. Zero candidate-count change — avoids 2-hop overload.
    scope_rel_ids = _chained_source_rel_ids(ctx, fact_id)
    _is_f1 = bool(ctx.fact_ids) and fact_id == ctx.fact_ids[0]
    start_type = (ctx.anchor_name if _is_f1 else (ctx.fact_start_types.get(fact_id) or ctx.anchor_name)) or ""
    if start_type:
        cand_texts = []
        for ri, rid in enumerate(ctx.rels):
            if ri in scope_rel_ids:
                parts = rid.split('.')
                tail = ' '.join(p.replace('_', ' ') for p in parts[-2:])
                cand_texts.append(f"{start_type} {tail}")
            else:
                cand_texts.append(rid)
    else:
        cand_texts = ctx.rel_texts

    try:
        rows = await gte_retrieve(
            session, hint, ctx.rels,
            candidate_texts=cand_texts, top_k=_GTE_TOPK)
    except Exception as e:
        return _json_result({"fact_id": fact_id, "error": f"gte_failed: {e}",
                             "candidates": []})

    gte_rel_ids: List[int] = []
    for r in rows:
        cand = r.get("candidate")
        if cand and cand in ctx.rels:
            gte_rel_ids.append(ctx.rels.index(cand))

    # 2. Structural prune: intersect GTE-15 with the structural scope for this
    #    fact (scope_rel_ids was computed above for candidate-text anchoring;
    #    reuse it here). For fact_1 this is the anchor's neighbors. For fact_i
    #    (i>1) it's the neighbors of entities reached via prior facts' selected
    #    relations (the chain: anchor --[f1]--> entity --[f2]--> ...). This
    #    ensures fact2 sees relations matching the entity-type fact1 arrives at,
    #    not the anchor's type — fixing CWQ multi-hop (e.g. person→country→
    #    religion: fact2 gets country.religions, not person.religion).
    # No structural prune (see module note): candidates = raw GTE top-K.
    pruned_rel_ids = list(gte_rel_ids)

    # 3. Store as CANDIDATES (not final). Model picks via select_relations.
    #    Also init fact_relations as the full candidate set so that if the
    #    model skips select_relations, the traversal still has something.
    ctx.fact_relation_candidates[fact_id] = list(pruned_rel_ids)
    ctx.fact_relations[fact_id] = set(pruned_rel_ids)  # default = all candidates

    return _json_result({
        "fact_id": fact_id,
        "subquestion": hint,
        "gte_relations": [ctx.rels[i] for i in gte_rel_ids[:15]],
        "candidate_relations": [ctx.rels[i] for i in pruned_rel_ids],
        "n_candidates": len(pruned_rel_ids),
        "note": (f"GTE-15 pruned to {len(pruned_rel_ids)} structurally-reachable "
                 "relations. Call select_relations to pick the ones that form "
                 "the answer chain, then select to traverse."),
    })


def _anchor_outgoing_rel_ids(ctx) -> set:
    """Structural scope for the anchor: 1-hop neighbor relations PLUS
    2-hop relations via ANY intermediate (CVT or regular entity).

    The traversal (build_mode_level_logical_paths, max_hops_per_step=2) allows
    a relation to span one hop, so the GTE candidate scope must match: a gold
    relation sitting on the 2nd hop (e.g. city -> capital -> country, then
    country -> combatants) is walkable by the traversal but would be pruned by
    a strict 1-hop-only scope. Replay-validated: 2-hop-any recalls +3 golds
    with 0 regression vs the prior 1-hop+CVT-only scope.

    1-hop: relations where anchor is h or t (undirected — Freebase stores some
    relations with reversed edge direction).
    2-hop: relations touching any of the anchor's direct neighbors (CVT or
    regular), mirroring the traversal's hop-spanning.
    """
    out = set()
    ai = ctx.anchor_idx
    if ai is None:
        return out

    # 1. Direct neighbors (undirected); collect ALL neighbors (CVT + regular)
    neighbors = set()
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if h == ai or t == ai:
            out.add(r)
            other = t if h == ai else h
            if 0 <= other < len(ctx.ents):
                neighbors.add(other)

    # 2. 2-hop via ANY intermediate (CVT or regular), matching the traversal's
    # max_hops_per_step=2 hop-spanning.
    for mid in neighbors:
        for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
            if h == mid or t == mid:
                out.add(r)

    return out


def _reachable_rel_ids_from(entities, ctx) -> set:
    """Relation indices reachable from a set of entity indices (outgoing only),
    PLUS CVT-bridged 2-hop relations.

    Directed (h==entity): only follow edges where the entity is the HEAD.
    CVT-bridged: if entity → CVT → X, the CVT→X edge relations are also
    included (same logic as _anchor_outgoing_rel_ids — CVT mediates one
    logical step).
    """
    from kgqa.traversal.cvt import is_cvt_like
    out = set()
    ent_set = set(entities)
    cvt_neighbors = set()
    for h, r in zip(ctx.h_ids, ctx.r_ids):
        if h in ent_set:
            out.add(r)
    # Also find CVT nodes directly connected to these entities (undirected)
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if h in ent_set and 0 <= t < len(ctx.ents) and is_cvt_like(ctx.ents[t]):
            cvt_neighbors.add(t)
        if t in ent_set and 0 <= h < len(ctx.ents) and is_cvt_like(ctx.ents[h]):
            cvt_neighbors.add(h)
    # Add CVT-bridged relations
    for cvt_idx in cvt_neighbors:
        for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
            if h == cvt_idx or t == cvt_idx:
                out.add(r)
    return out


def _entities_via_relations(source_entities, rel_ids, ctx, exclude=None) -> set:
    """Entities reachable from source via the given relation set (1 hop).

    Used by chained retrieve: given fact_{i-1}'s selected relations and the
    anchor (or the entities fact_{i-2} reached), compute where fact_{i-1}
    arrives — those entities' neighbors become fact_i's structural scope.

    exclude: a set of entity indices that have ALREADY been visited earlier in
    the chain. These are never returned, preventing loops where the chain
    revisits an entity via a different relation (e.g. anchor→CVT→Israel→CVT).
    """
    rel_set = set(rel_ids)
    src = set(source_entities)
    excl = set(exclude) if exclude else set()
    reached = set()
    for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
        if r not in rel_set:
            continue
        if h in src and t not in excl:
            reached.add(t)
        if t in src and h not in excl:
            reached.add(h)
    # Also exclude the source itself (don't stay in place)
    reached -= src
    return reached


def _passthrough_cvts(entities, ctx, exclude=None) -> set:
    """Extend through CVT nodes to reach the named entities beyond them.

    When the chain arrives at a CVT (e.g. national_anthem_of → CVT), the
    actual entity of interest (e.g. the country) is one more hop beyond the
    CVT. Without this passthrough, fact_i's scope is limited to the CVT's
    own attributes (country, anthem, start_date...) and misses the named
    entity's domain relations (form_of_government, capital, etc.).

    This extends each CVT node one hop forward to its named (non-CVT) neighbors,
    adding them to the entity set. Non-CVT entities pass through unchanged.
    """
    from kgqa.traversal.cvt import is_cvt_like
    excl = set(exclude) if exclude else set()
    result = set()
    for idx in entities:
        if idx >= len(ctx.ents):
            continue
        name = ctx.ents[idx]
        if is_cvt_like(name):
            # CVT: extend one hop to non-CVT neighbors
            for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
                if h == idx and t not in excl:
                    t_name = ctx.ents[t] if t < len(ctx.ents) else ""
                    if t_name and not is_cvt_like(t_name):
                        result.add(t)
                if t == idx and h not in excl:
                    h_name = ctx.ents[h] if h < len(ctx.ents) else ""
                    if h_name and not is_cvt_like(h_name):
                        result.add(h)
        else:
            result.add(idx)
    return result


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

    # Chained: walk from anchor through each prior fact's FULL candidate set.
    # At retrieve time, select_relations hasn't run yet, so we use all of each
    # prior fact's GTE-pruned candidates as the chain link — NOT just top-1
    # (top-1 is too fragile: if it's the wrong relation, the whole chain breaks
    # and fact2's scope becomes garbage). Using ALL candidates means the chain
    # reaches every entity reachable via any plausible first-hop relation,
    # giving fact2 a complete picture of what entity-types it might need to
    # handle. The scope stays tight because _reachable_rel_ids_from is directed
    # (only outgoing edges), so CVT→person back-links don't re-admit person
    # relations.
    #
    # Loop prevention: track ALL entities visited across the chain (visited
    # set). Each hop excludes everything in visited.
    source = {ctx.anchor_idx} if ctx.anchor_idx is not None else set()
    visited = set(source)
    for prior_fid in fids[:idx]:
        cands = ctx.fact_relation_candidates.get(prior_fid, [])
        if cands:
            prior_rels = set(cands)
        else:
            prior_rels = ctx.fact_relations.get(prior_fid, set())
        if prior_rels:
            source = _entities_via_relations(source, prior_rels, ctx, exclude=visited)
            # CVT passthrough: extend through CVT nodes to named entities.
            source = _passthrough_cvts(source, ctx, exclude=visited)
            visited |= source
            if not source:
                # Boundary 2: chain broken — model may have under-planned steps
                # (e.g. needed 3 facts but decomposed 2). Relax: try a 2-hop
                # structural connectivity check from the PREVIOUS source (before
                # this hop failed) through ALL its outgoing edges, not just the
                # GTE-pruned candidates. This lets the chain skip a missed step
                # by exploring one extra hop structurally.
                # Recover the source from before this hop:
                prev_source = visited - {ctx.anchor_idx} if len(visited) > 1 else {ctx.anchor_idx}
                # Walk one hop from prev_source via ANY relation (not just GTE candidates)
                relaxed = set()
                for h_idx, r_idx in zip(ctx.h_ids, ctx.r_ids):
                    if h_idx in prev_source:
                        relaxed.add(r_idx)
                if relaxed:
                    source = _entities_via_relations(prev_source, relaxed, ctx, exclude=visited)
                    source = _passthrough_cvts(source, ctx, exclude=visited)
                    visited |= source
                if not source:
                    break  # chain truly broken

    if not source:
        # Chain broken — fall back to anchor neighbors (best effort)
        return _anchor_outgoing_rel_ids(ctx)
    return _reachable_rel_ids_from(source, ctx)


def _compact_overview(overview: str) -> str:
    """Secondary compaction pass on the evidence tree overview.

    The main compaction (≤3 candidates per branch, no entity list in the
    RETRIEVED CANDIDATES header) is done inside _do_select. This function
    is a safety net: if _do_select produced a long overview, cap each branch
    block's tree lines to keep the total readable. No-op if already compact.
    """
    # _do_select already produces compact output; this is a placeholder for
    # future additional compaction if needed.
    return overview


async def _do_select_relations(args: Dict[str, Any], ctx, session) -> str:
    """Model decision: pick the relation(s) forming the answer chain, per fact,
    THEN run the graph traversal (formerly the separate `select` tool) and
    return the evidence tree inline.

    This merges select_relations + select into one step:
    1. Validate the model's relation picks against each fact's candidates.
    2. Lock the chosen relations into ctx.fact_relations.
    3. Run stage_5_graph_traversal + build the evidence tree overview.
    4. Return the tree (compact: ≤3 candidates per branch + ellipsis).

    Args:
        selections: [{"fact_id": "f1", "relations": ["people.person.parents"]}, ...]
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
            ctx.fact_relations[fid] = set(candidates)

    selected_summary = {fid: [ctx.rels[i] for i in ids] for fid, ids in chosen.items()}

    # ── Run the traversal (merged from _do_select) ──
    traverse_result = await _do_select(ctx)

    # Parse the traverse result to merge with selection summary
    try:
        traverse_obj = json.loads(traverse_result)
    except Exception:
        traverse_obj = {"error": "traverse failed"}

    # Compact the candidate display: ≤3 per branch + ellipsis
    if "overview" in traverse_obj:
        traverse_obj["overview"] = _compact_overview(traverse_obj["overview"])

    traverse_obj["selected"] = selected_summary
    traverse_obj["skipped_invalid"] = skipped
    return _json_result(traverse_obj)


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


def _steps_to_groups(fact_steps, fact_relations, fids):
    """Build ordered (step_fids, step_relations) from the explicit chain structure.

    ``fact_steps`` comes from harness parsing ``question_chains[].steps``: a list
    where each entry is either ``[fid]`` (a sequential step — its answer feeds the
    next) or ``[fid, fid, ...]`` (a conjunctive ``con`` layer — those facts
    constrain the SAME entity reached by the prior step, so their selected
    relations are UNIONED at one layer, not chained in series).

    Sequential facts each stay their own step; conjunctive facts merge into one
    step (relation union). This replaces the old ``_group_parallel_facts``, which
    INFERRED siblings from ``f{N}.k`` id naming — grouping is now explicit (the
    model writes ``con``), which keeps the decomposition (facts) and the structure
    (steps) from diverging.

    Falls back to all-facts-sequential when ``fact_steps`` is empty (single
    sequential question with no ``question_chains``). Only fids that have selected
    relations are walked; empty groups are dropped.
    """
    if not fact_steps:
        fact_steps = [[fid] for fid in fids]

    step_fids = []
    step_relations = []
    for grp in fact_steps:
        if isinstance(grp, str):
            grp = [grp]
        fids_in = [f for f in grp if f in fact_relations]
        if not fids_in:
            continue
        merged = []
        seen = set()
        for fid in fids_in:
            for r in fact_relations.get(fid, []):
                if r not in seen:
                    seen.add(r)
                    merged.append(r)
        step_fids.append(fids_in[0] if len(fids_in) == 1 else fids_in)
        step_relations.append(merged)

    if not step_fids:
        for fid in fids:
            step_fids.append(fid)
            step_relations.append(list(fact_relations.get(fid, [])))
    return step_fids, step_relations


async def _do_select(ctx) -> str:
    """Run the FULL multi-step traversal (stage_5_graph_traversal) over all
    facts' hinted relations, then build a TREE overview of evidence.

    This reuses the proven stage-5 engine (mode-level logical paths + CVT
    expansion + RPE fallback) for traversal, AND the proven Stage-8 evidence
    builders (build_pattern_evidence_triples + _render_path_tree) for
    presentation — so the overview shows CVT-expanded candidates (Kasich, not
    CVT node IDs) and a trie structure, not a flat list.

    The model uses this overview to SELECT which branch to expand (Stage 7's
    role), then expand_branches(['N']) drills into the chosen branch (Stage 8's role).

    Conjunctive layers: a step group with several fids (a ``con`` group from
    ``question_chains``) means those facts constrain the SAME entity reached by
    the prior step — they are NOT sequential hops. Their selected relations are
    UNIONED into one step, mirroring stage's ``_merge_constraint_steps``. Without
    this merge the traversal would walk them in series (f2 → entity → f3), which
    is semantically wrong: both filters read attributes of the entity reached by
    the prior step, they don't chain. Grouping is explicit (the model writes
    ``con``), parsed into ``ctx.fact_steps`` by the harness.
    """
    fids = [fid for fid in ctx.fact_ids if fid in ctx.fact_relations]
    if not fids or ctx.anchor_idx is None:
        return _json_result({"error": "no_facts_or_anchor",
                             "evidence": [], "candidates": []})
    # Build ordered steps from the explicit question_chains structure parsed in
    # harness (ctx.fact_steps): each entry is [fid] (sequential step) or
    # [fid, ...] (a conjunctive `con` layer — those facts' relations are unioned
    # at one layer, not chained in series). Falls back to all-facts-sequential
    # when no chains were declared.
    step_fids, step_relations = _steps_to_groups(
        getattr(ctx, "fact_steps", None) or [], ctx.fact_relations, fids)

    # Build a minimal CaseState and run the proven stage-5 traversal
    cs = CaseState(case_id=ctx.case_id or "agent", case_num=ctx.case_num or 0,
                   sample=ctx.sample, pilot_row=ctx.pilot_row)
    cs.anchor_idx = ctx.anchor_idx
    cs.anchor_name = ctx.anchor_name
    cs.h_ids, cs.r_ids, cs.t_ids = ctx.h_ids, ctx.r_ids, ctx.t_ids
    cs.ents, cs.rels, cs.rel_texts = ctx.ents, ctx.rels, ctx.rel_texts
    cs.step_relations = step_relations
    cs.steps = [{"id": "+".join(g) if isinstance(g, list) else g}
                for g in step_fids]   # n_steps = n_groups (siblings merged)
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
    # selection via expand_branches). Aligns each branch's relation-id sequence
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
    # ── Materialize logical patterns into ALL raw paths (Stage-7→8 bridge) ──
    # The logical pattern carries one witness path; the proven Stage-8 builder
    # expands evidence from the pattern's raw_paths. Without materialization,
    # only the single witness is seen (e.g. only 1 of 5 languages). This mirrors
    # the baseline case_runner exactly — keep the verified mechanism intact.
    valid_patterns = materialize_selected_logical_patterns(
        valid_patterns, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids,
        ctx.anchor_idx, set((ctx.breakpoints or {}).values()))
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
        tree_lines = _render_path_tree(pe.tree_data, max_lines=200)

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

        # Store the full branch data for expand_branches to re-render later.
        # Key: store the materialized pattern (with raw_paths) so expand can
        # re-run build_pattern_evidence_triples and get ALL candidates (not just
        # the witness). Without this, expand only sees the single witness path.
        ctx.branches[bid] = {
            "label": label,
            "candidates": cands,
            "triples": pe.triples,
            "readable": pe.readable,
            "tree_lines": tree_lines,
            "pattern": valid_patterns[i] if i < len(valid_patterns) else None,
        }

        # Compose the branch block with the #N marker on the RIGHT of each leaf.
        # overview shows FEW candidates per branch — this display is only to help
        # the model CHOOSE which branches to expand, NOT to answer from. The full
        # candidate set (the answer leaves) is surfaced by expand_branches (which
        # the model must call to answer). Keep this small to avoid clutter.
        cand_str = ", ".join(cands[:5])
        if len(cands) > 5:
            cand_str += f", ... (+{len(cands) - 5})"
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
        f"RETRIEVED CANDIDATES: {len(dedup)} entities in the answer pool "
        "(expand branches to see them).\n\n"
        f"EVIDENCE TREE (ranked by relevance; #N on the right marks each "
        "branch):\n"
        "Branches are pre-ranked by how well their relation chain aligns with "
        "your decomposed facts (most aligned, shortest paths first). ANALYZE "
        "the tree, decide which branches are relevant to the question, and call "
        "expand_branches(['1','2']) on those you choose to see their full triples "
        "+ CVT attributes. Then answer from what you expanded.\n\n"
        + "\n\n".join(overview_blocks)
    )

    return _json_result({
        "n_patterns": len(ranked),
        "overview": overview_text,
        "candidates": ctx.selected_candidates[:50],
    })


def _cvt_attr_summary(triples, max_lines: int = 60) -> str:
    """Per-CVT attribute summary for the answer step.

    Inline-resolves CVT nodes so each holder's tenure attrs sit on one line
    (e.g. "Abdullah al-Thani: from=2014-06-09, to=(incumbent), basic_title=Prime minister").
    Unlike format_subgraph_with_cvt, KEEPS `has_no_value` (rendered as
    `<attr>=(incumbent)`) — that "no end date" marker is the signal that picks
    the current office-holder, and stripping it (as noise) is exactly why the
    model cannot tell who is incumbent on exclusive relations like Libya PMs.
    Filters only true noise (type./common./freebase bookkeeping minus has_no_value).
    """
    from kgqa.traversal.cvt import is_cvt_like
    _NOISY_PREFIX = ("type.", "common.", "kg.", "user.", "base.ontologies.")
    _NOISY_SHORT = {"type", "types", "instance", "instances", "notable_types",
                    "topic_equivalent_webpage", "webpage", "mid", "guid",
                    "key", "keys", "permission", "is_reviewed", "no_value"}
    _HOLDER_RELS = {"office_holder", "actor", "director", "spouse"}

    def _short(r):
        return r.rsplit(".", 1)[-1] if r else r

    def _noisy(r):
        r = str(r)
        return r.startswith(_NOISY_PREFIX) or _short(r) in _NOISY_SHORT

    cvt_attrs = {}   # cvt_name -> [(short_rel, value)]
    cvt_holder = {}  # cvt_name -> holder entity (the named entity it points to)
    for tr in triples:
        if not (isinstance(tr, (tuple, list)) and len(tr) == 3):
            continue
        h, r, t = str(tr[0]), str(tr[1]), str(tr[2])
        if not (is_cvt_like(h) and not is_cvt_like(t)):
            continue
        if _noisy(r):
            continue
        s = _short(r)
        cvt_attrs.setdefault(h, []).append((s, t))
        if s in _HOLDER_RELS:
            cvt_holder[h] = t

    lines = []
    # incumbents (has_no_value = no end date) first so the current holder surfaces
    def _sort_key(item):
        cvt, attrs = item
        has_incumbent = any(s == "has_no_value" for s, _ in attrs)
        holder = cvt_holder.get(cvt, cvt)
        return (0 if has_incumbent else 1, holder)

    for cvt, attrs in sorted(cvt_attrs.items(), key=_sort_key):
        holder = cvt_holder.get(cvt, cvt)
        parts = []
        for s, v in attrs:
            if s == "has_no_value":
                # value names the attribute that is absent (e.g. "To") → incumbent
                parts.append(f"{str(v).lower()}=(incumbent)")
            else:
                parts.append(f"{s}={v}")
        if parts:
            lines.append(f"  - {holder}: {', '.join(parts[:8])}")
    return "\n".join(lines[:max_lines])


def _do_expand_branch(args: Dict[str, Any], ctx) -> str:
    """Expand one or more branches to show their FULL evidence.

    Accepts both the batch form (branch_ids: ['1','2']) and the legacy single
    form (branch_id: '1'). Returns merged evidence across all selected branches
    using the pre-built triples + tree from select (no re-build needed — the
    select stage already ran build_pattern_evidence_triples with CVT expansion).
    """
    bids = args.get("branch_ids") or args.get("branch_id_list") or []
    if isinstance(bids, str):
        bids = [bids]
    bids = [str(b) for b in bids if str(b).strip()]
    if not bids:
        bids = [str(args.get("branch_id", ""))]
    bids = [b for b in bids if b]
    if not bids:
        return _json_result({"error": "no branch_ids provided. Pass a list like ['1','2'].",
                             "valid_branches": list(ctx.branches.keys())})

    unknown = [b for b in bids if b not in ctx.branches]
    if unknown:
        return _json_result({"error": f"unknown branch_ids {unknown}",
                             "valid_branches": list(ctx.branches.keys())})

    # Use pre-built evidence from select (triples + tree_lines already contain
    # the full CVT-expanded data). Just merge across selected branches.
    all_triples = []
    seen_t = set()
    all_cands = []
    seen_c = set()
    per_branch = []
    tree_sections = []
    for bid in bids:
        br = ctx.branches[bid]
        cands = br.get("candidates", [])
        triples = br.get("triples", [])
        tree_lines = br.get("tree_lines", [])
        readable = br.get("readable", "")
        for cand in cands:
            nc = normalize(cand)
            if nc not in seen_c:
                seen_c.add(nc); all_cands.append(cand)
        for tr in triples:
            key = tuple(str(x) for x in tr)
            if key not in seen_t:
                seen_t.add(key); all_triples.append(tr)
        per_branch.append({"branch_id": bid, "readable": readable,
                           "candidates": cands[:30], "n_triples": len(triples)})
        if tree_lines:
            tree_sections.append(f"=== branch {bid}: {readable} ===\n" +
                                 "\n".join(tree_lines))

    triple_strs = [f"({h}, {r}, {t})" for h, r, t in all_triples[:80]]
    cand_attrs = _cvt_attr_summary(all_triples)
    payload = {
        "branches_expanded": bids,
        "n_branches": len(bids),
        "candidates": all_cands[:100],
        "n_candidates": len(all_cands),
        "triples": triple_strs,
        "n_triples": len(all_triples),
        "candidate_attrs": cand_attrs,
        "per_branch": per_branch,
    }
    if tree_sections:
        payload["tree"] = "\n\n".join(tree_sections)
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
