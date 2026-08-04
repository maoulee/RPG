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

from typing import Any, Dict

from kgqa.core.utils import normalize
from kgqa.traversal.cvt import is_cvt_like
from kgqa.agent.tools import (
    _json_result, _gte_for_triple, _reach2_relids, _do_answer, _cvt_attr_summary, _GTE_POOL_MIN,
)
from kgqa.core.case_state import CaseState
from kgqa.stages.stage5_traverse import stage_5_graph_traversal
from kgqa.traversal.path_utils import compress_paths
from kgqa.traversal.logical_paths import materialize_selected_logical_patterns
from kgqa.stages.formatting import build_pattern_evidence_triples, _render_path_tree


# ───────────────────────── helpers ─────────────────────────

def _name_to_idx(name: str, ctx) -> int | None:
    n = normalize(str(name))
    if not n:
        return None
    for i, e in enumerate(ctx.ents):
        if normalize(e) == n:
            return i
    if len(n) >= 3:
        for i, e in enumerate(ctx.ents):
            en = normalize(e)
            if n in en or en in n:
                return i
    return None


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
    n2i = {normalize(e): i for i, e in enumerate(ctx.ents) if e}
    names = set(pe.candidates or [])
    for tr in (pe.triples or []):
        if len(tr) == 3:
            names.add(tr[0]); names.add(tr[2])
    seen_cand = {normalize(c) for c in getattr(ctx, "all_candidates", []) or []}
    for nm in names:
        if not nm:
            continue
        idx = n2i.get(normalize(nm))
        if idx is not None:
            se.add(idx)                  # CVT m-ids are centerable too (the model may start from them)
        if not is_cvt_like(nm):          # only NAMED entities join the answer candidate pool
            nn = normalize(nm)
            if nn not in seen_cand:
                seen_cand.add(nn); ctx.all_candidates.append(nm)


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
                 "retrieve_relations(center, that fact's subquestion), pick the structural "
                 "bridge relation, then retrieve_subgraph(center, picked_relations) to get "
                 "the dense subgraph tree. Pick the next center FROM that tree. The system "
                 "auto-penetrates CVTs — never pick attribute relations. Fact-1 center = anchor."),
    })


# ───────────────────────── retrieve_relations (GTE per entity+question) ─────────────────────────

async def retrieve_relations(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph relation retrieval: entity + question → candidate relations around the
    entity, relevant to the question (GTE, grounded on the entity's reachable pool)."""
    entity = args.get("entity") or ""
    question = args.get("question") or args.get("subquestion") or ""
    idx = _name_to_idx(entity, ctx)
    if idx is None:
        return _json_result({"error": f"entity '{entity}' not found in the subgraph."})
    if not _in_subgraph(idx, ctx):
        return _json_result({"error": (f"'{entity}' is not in the retrieved subgraph. The center "
                                       f"must come from a previous retrieve_subgraph tree (or be "
                                       f"the question's anchor for the first fact).")})
    pool = _reach2_relids(ctx, {idx})
    if len(pool) < _GTE_POOL_MIN:
        pool = set(range(len(ctx.rels)))
    cands = await _gte_for_triple(ctx, session, entity, question, "", pool_relids=pool)
    return _json_result({
        "entity": entity, "question": question,
        "candidate_relations": [ctx.rels[i] for i in cands if 0 <= i < len(ctx.rels)],
        "note": "Pick the structural BRIDGE relation(s) that connect this entity to the next node "
                "type in the chain. Do NOT pick attribute relations (date/name/type/role) — the "
                "system reveals those automatically inside CVTs.",
    })


# ───────────────────────── retrieve_subgraph (mature multi-hop walk + dense tree) ─────────────────────────

async def retrieve_subgraph(args: Dict[str, Any], ctx, session) -> str:
    """Subgraph retrieval for ONE fact: one shared relation set applied to one or more
    center entities (the fact's candidate centers, packed into a single call). For each
    center the proven SAPS walk runs (multi-hop, K-path, CVT-penetrating); results are
    merged — dense tree + a candidate_attrs summary grouped by candidate under the shared
    relation pattern, so the model can compare across candidates (e.g. latest/largest).
    Accumulates seen entities into the subgraph."""
    raw = args.get("entities") or ([args.get("entity")] if args.get("entity") else [])
    entities = [str(e) for e in raw if e]
    rel_names = args.get("relations") or []
    fid = str(args.get("fact_id") or args.get("step") or "")
    if not entities:
        return _json_result({"error": "no entities provided."})
    rel_idxs = [ctx.rels.index(r) for r in rel_names if isinstance(r, str) and r in ctx.rels]
    if not rel_idxs:
        return _json_result({"error": "no valid relations provided. Pick from the candidate_relations "
                                      "returned by retrieve_relations."})

    # resolve + boundary-check each center (skip any not yet in the subgraph, proceed with the rest)
    centers, skipped = [], []
    for e in entities:
        i = _name_to_idx(e, ctx)
        if i is None or not _in_subgraph(i, ctx):
            skipped.append(e)
        else:
            centers.append((e, i))
    if not centers:
        return _json_result({"error": (f"none of {entities} are in the retrieved subgraph. Centers "
                                       f"must come from a previous retrieve_subgraph tree (or the "
                                       f"anchor for the first fact).")})

    # per-center walk + merge into one grouped view
    tree_lines, candidates, all_triples = [], [], []
    for e, i in centers:
        pe = await _run_walk_one_step(ctx, i, rel_idxs, fid)
        if not pe:
            continue
        for p in pe.values():
            tree_lines.extend(_render_path_tree(p.tree_data, max_lines=40))
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

    # candidate_attrs: grouped by candidate under the shared relation pattern (CVT attrs inline,
    # KEEPS has_no_value → "to=(incumbent)"). The cross-candidate comparison view.
    cand_attrs = _cvt_attr_summary(all_triples, candidates)
    multi = len(centers) > 1
    return _json_result({
        "fact_id": fid,
        "entities": [e for e, _ in centers],
        "tree": "\n".join(tree_lines) if tree_lines else "(empty)",
        "candidates": [c for c in candidates if not is_cvt_like(c)][:60],
        "n_candidates": len(candidates),
        "candidate_attrs": cand_attrs,
        "skipped_centers": skipped,
        "note": (("Multiple centers retrieved with one shared relation set — read candidate_attrs "
                  "to COMPARE across candidates (latest/largest; an entry marked to=(incumbent) is "
                  "the current holder). ") if multi else "") +
                 ("Pick the next center FROM this tree/attrs. CVT nodes show attributes inline."),
    })


# ───────────────────────── SEQ dispatch ─────────────────────────

async def dispatch(tool_name: str, args: Dict[str, Any], ctx, session) -> str:
    if tool_name == "decompose":
        return await _do_seq_decompose(args, ctx, session)
    if tool_name == "retrieve_relations":
        return await retrieve_relations(args, ctx, session)
    if tool_name == "retrieve_subgraph":
        return await retrieve_subgraph(args, ctx, session)
    if tool_name == "answer":
        return _do_answer(args, ctx)
    return _json_result({"error": f"unknown tool: {tool_name}"})
