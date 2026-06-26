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
            "name": "select",
            "description": (
                "Traverse the KG over all facts' hinted relations and return a "
                "numbered evidence-tree overview. Call exactly ONCE after every "
                "fact has been retrieved. The overview shows each branch with a "
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

    if tool_name == "select":
        return await _do_select(ctx)

    if tool_name == "expand_branch":
        return _do_expand_branch(args, ctx)

    if tool_name == "answer":
        return _do_answer(args, ctx)

    return _json_result({"error": f"unknown tool: {tool_name}"})


async def _do_retrieve(args: Dict[str, Any], ctx, session) -> str:
    """MODEL-DRIVEN GTE: relation_hint is the query, not the raw question.

    Pipeline: gte_retrieve(hint) → top relation ids → relation_prior_expand
    (CVT-aware, same engine as stage_5_graph_traversal) from anchor → collect
    candidate entities + witness paths into ctx.
    """
    fact_id = str(args.get("fact_id", ""))
    hint = (args.get("relation_hint") or "").strip()
    if not hint:
        # Fall back to the fact text if the model forgot the hint
        hint = ctx.fact_texts.get(fact_id, ctx.question)
    if ctx.anchor_idx is None:
        return _json_result({"fact_id": fact_id, "error": "no_anchor",
                             "candidates": []})

    # 1. Model-driven GTE over relations — hint as query
    top_k = 15
    try:
        rows = await gte_retrieve(
            session, hint, ctx.rels,
            candidate_texts=ctx.rel_texts, top_k=top_k)
    except Exception as e:
        return _json_result({"fact_id": fact_id, "error": f"gte_failed: {e}",
                             "candidates": []})

    # Map GTE candidates (relation names) to indices in ctx.rels
    rel_indices: List[int] = []
    for r in rows:
        cand = r.get("candidate")
        if cand and cand in ctx.rels:
            rel_indices.append(ctx.rels.index(cand))
        if len(rel_indices) >= 8:
            break

    # 2. Store the hinted relations for THIS fact only (NO traversal here).
    #    The multi-step traversal runs ONCE in `select` via
    #    stage_5_graph_traversal, which chains across all facts and expands
    #    CVTs — per-fact single-step traverse from the anchor cannot reach
    #    multi-hop / CVT candidates (the cause of the 2-hop regression).
    ctx.fact_relations[fact_id] = set(rel_indices)

    return _json_result({
        "fact_id": fact_id,
        "relation_hint": hint,
        "top_relations": [ctx.rels[i] for i in rel_indices],
        "n_relations": len(rel_indices),
        "note": "relations stored; multi-step traversal runs at select()",
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

    # ── Build CVT-aware evidence via the proven Stage-8 builder ──
    # build_pattern_evidence_triples returns dict[label -> PatternEvidence]
    # where each PatternEvidence has:
    #   .candidates  — CVT-expanded named entities (office_holder names, not CVT IDs)
    #   .triples     — full (h, r, t) triples with CVT attributes expanded
    #   .tree_data   — nested trie (display-named nodes) for _render_path_tree
    # This fixes Blocker A (candidates now include CVT-expanded entities) and
    # Blocker B (overview rendered as a tree, not a flat list).
    valid_patterns = [lp for lp in patterns if isinstance(lp, dict) and lp.get("best_raw_path")]
    pat_evidence = build_pattern_evidence_triples(
        valid_patterns, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids,
        ctx.anchor_idx, max_grouped_lines=120)

    # Rank by candidate count desc (most informative branches first) → top-20
    ranked = sorted(
        pat_evidence.items(),
        key=lambda kv: (-len(kv[1].candidates), kv[0]),
    )[:20]

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
        + f"\n\nEVIDENCE TREE OVERVIEW ({len(ranked)} branches; #N on the right "
        "marks each branch):\n"
        "This overview is your PATH SELECTION (Stage 7). ANALYZE which branch "
        "best answers the question. Call expand_branch(N) on the branch you "
        "chose to see its full triples + CVT attributes, then answer.\n\n"
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
