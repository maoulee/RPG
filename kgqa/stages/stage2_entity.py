"""Stage 2: Entity resolution via GTE + LLM.

Provides NER anchor resolution (resolve_anchor_ner), LLM entity disambiguation
(llm_resolve_entity), and the batch entity resolution pipeline stage.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from kgqa.core.case_state import CaseState
from kgqa.core.config import GTE_API_URL
from kgqa.core.utils import normalize, rel_to_text, extract_xml_tag, get_entity_contexts
from kgqa.llm.client import call_llm
from kgqa.llm.batch import batch_call_llm
from kgqa.traversal.cvt import is_cvt_like

import aiohttp


# ---------------------------------------------------------------------------
# GTE retrieval helper
# ---------------------------------------------------------------------------

# Generic doc-similarity task instruct for Qwen3-Embedding (case-free: no
# KG/attribute/answer-type wording). Validated to maximize gold-relation recall
# without overfitting; passed explicitly so it applies regardless of the server
# default (TASK_DESC).
GTE_INSTRUCT = "Given a query, retrieve the document most semantically similar to it"


async def gte_retrieve(session, query, candidates, candidate_texts=None, top_k=10, instruct=GTE_INSTRUCT):
    payload = {"query": query, "candidates": candidates, "candidate_texts": candidate_texts, "top_k": top_k, "instruct": instruct}
    async with session.post(f"{GTE_API_URL}/retrieve", json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
        data = await resp.json()
    return data.get("results", [])


# ---------------------------------------------------------------------------
# NER + GTE scoring for entity resolution
# ---------------------------------------------------------------------------

def _token_overlap(question: str, entity: str) -> float:
    """Ratio of entity tokens found in question."""
    q_tokens = set(normalize(question).split())
    e_tokens = set(normalize(entity).split())
    if not e_tokens:
        return 0.0
    return len(e_tokens & q_tokens) / len(e_tokens)


async def resolve_anchor_ner(session, question, entity_list, rel_list, h_ids, r_ids, t_ids):
    """NER + GTE + token overlap + relation overlap scoring for entity resolution."""
    clean_ents, seen = [], set()
    for e in entity_list:
        if not e or is_cvt_like(e) or len(e) <= 1:
            continue
        if e not in seen:
            clean_ents.append(e)
            seen.add(e)

    rel_texts = [rel_to_text(r) for r in rel_list]

    # GTE entity retrieval
    q_ent_rows = await gte_retrieve(session, question, clean_ents, top_k=12)
    gte_ents = [(r["candidate"], r.get("score", 0)) for r in q_ent_rows
                if r.get("candidate") and r["candidate"] in entity_list]

    # Token overlap filter (min 0.5)
    filtered = [(e, s) for e, s in gte_ents if _token_overlap(question, e) >= 0.5]

    # Relation overlap scoring
    q_rel_rows = await gte_retrieve(session, question, rel_list,
                                    candidate_texts=rel_texts, top_k=5)
    q_top_rel_idx = {rel_list.index(r["candidate"]) for r in q_rel_rows
                     if r.get("candidate") and r["candidate"] in rel_list}

    name_to_ids = defaultdict(list)
    for i, name in enumerate(entity_list):
        name_to_ids[name].append(i)

    scored = []
    for ent, gte_score in filtered:
        ent_idx = set(name_to_ids.get(ent, []))
        ent_rels = set()
        for h, r, t in zip(h_ids, r_ids, t_ids):
            if h in ent_idx or t in ent_idx:
                ent_rels.add(r)
        overlap = len(ent_rels & q_top_rel_idx)
        scored.append({"entity": ent, "gte": round(gte_score, 4), "overlap": overlap})
    scored.sort(key=lambda x: (-x["overlap"], -x["gte"]))

    return scored, name_to_ids


# ---------------------------------------------------------------------------
# LLM entity disambiguation
# ---------------------------------------------------------------------------

async def llm_resolve_entity(session, question, query, candidates_with_ctx):
    """LLM selects the correct entity from GTE top-k candidates using surrounding relation context.
    candidates_with_ctx: list of (name, context_str) tuples.
    Returns selected entity name or None."""
    if not candidates_with_ctx:
        return None
    if len(candidates_with_ctx) == 1:
        return candidates_with_ctx[0][0]

    cand_lines = []
    for i, (name, ctx) in enumerate(candidates_with_ctx, 1):
        cand_lines.append(f"  {i}. {name} [{ctx}]" if ctx else f"  {i}. {name}")

    prompt = f"""Search query: {query}

Candidate entities (with relation context from knowledge graph):
{chr(10).join(cand_lines)}

Which candidate best matches the search query? Use the relation context to identify what each entity actually IS (a person, a location, a schema type, etc). Pick the specific entity, not generic types or schema entries.

<analysis>Brief reasoning about which candidate matches the query</analysis>
<selected>entity name</selected>"""

    for _ in range(2):
        raw = await call_llm(session, [
            {"role": "system", "content": "Select the correct entity from candidates. Output <analysis> and <selected> XML tags."},
            {"role": "user", "content": prompt},
        ], max_tokens=300)
        sel = extract_xml_tag(raw, "selected")
        if sel:
            sel = sel.strip().strip('"').strip("'")
            # Match to candidate names
            for name, _ in candidates_with_ctx:
                if normalize(sel) == normalize(name):
                    return name
            # Fuzzy match
            for name, _ in candidates_with_ctx:
                if normalize(sel) in normalize(name) or normalize(name) in normalize(sel):
                    return name
    # Fallback to GTE top-1
    return candidates_with_ctx[0][0]


# ---------------------------------------------------------------------------
# Stage 2: Batch entity resolution
# ---------------------------------------------------------------------------

async def stage_2_entity_resolution(session, cases: List[CaseState]):
    """Batch entity resolution. Flatten all requests across cases into one batch."""
    _t0 = time.perf_counter()
    active = [cs for cs in cases if cs.active]
    if not active:
        return

    # Phase A: GTE retrieval for all entity queries concurrently
    gte_tasks = []  # (kind, cs, query_str)
    for cs in active:
        if not (cs.use_ner and cs.ner_top_ents) and cs._pending_anchor_eq:
            gte_tasks.append(("anchor", cs, cs._pending_anchor_eq))
        for ep in cs._pending_endpoints:
            gte_tasks.append(("endpoint", cs, ep["query"]))

    _gte_sem = asyncio.Semaphore(3)
    async def _gte_limited(coro):
        async with _gte_sem:
            return await coro
    gte_results = await asyncio.gather(*[
        _gte_limited(gte_retrieve(session, query, cs.ent_candidates, top_k=5 if kind == "anchor" else 3))
        for kind, cs, query in gte_tasks
    ], return_exceptions=True)

    # Phase B: Build LLM prompts for entity resolution
    llm_items = []  # (cs, kind, step_idx, cands_with_ctx)
    for i, (kind, cs, query) in enumerate(gte_tasks):
        result = gte_results[i]
        if isinstance(result, Exception):
            continue
        candidates = [r.get("candidate", "") for r in result if r.get("candidate")]
        if len(candidates) <= 1:
            if kind == "anchor" and candidates:
                cs.anchor_name = candidates[0]
                cs.anchor_idx = cs.ents.index(candidates[0]) if candidates[0] in cs.ents else None
            continue

        ctx = get_entity_contexts(candidates, cs.h_ids, cs.r_ids, cs.t_ids, cs.ents, cs.rels)
        cands_with_ctx = [(n, ctx.get(n, "")) for n in candidates]
        llm_items.append((cs, kind, query, cands_with_ctx))

    # Phase C: Batch LLM call
    if llm_items:
        prompts = []
        for cs, kind, query, cands_with_ctx in llm_items:
            cand_lines = []
            for j, (name, c) in enumerate(cands_with_ctx, 1):
                cand_lines.append(f"  {j}. {name} [{c}]" if c else f"  {j}. {name}")
            prompt = f"""Search query: {query}

Candidate entities (with relation context from knowledge graph):
{chr(10).join(cand_lines)}

Which candidate best matches the search query? Use the relation context to identify what each entity actually IS.

<analysis>Brief reasoning about which candidate matches the query</analysis>
<selected>entity name</selected>"""
            prompts.append([
                {"role": "system", "content": "Select the correct entity from candidates. Output <analysis> and <selected> XML tags."},
                {"role": "user", "content": prompt},
            ])

        responses = await batch_call_llm(session, prompts, max_tokens=300)

        for (cs, kind, query, cands_with_ctx), raw in zip(llm_items, responses):
            sel = extract_xml_tag(raw or "", "selected")
            selected = None
            if sel:
                sel = sel.strip().strip('"').strip("'")
                for name, _ in cands_with_ctx:
                    if normalize(sel) == normalize(name):
                        selected = name; break
                if not selected:
                    for name, _ in cands_with_ctx:
                        if normalize(sel) in normalize(name) or normalize(name) in normalize(sel):
                            selected = name; break
            if not selected and cands_with_ctx:
                selected = cands_with_ctx[0][0]

            if kind == "anchor":
                cs.anchor_name = selected
                cs.anchor_idx = cs.ents.index(selected) if selected and selected in cs.ents else None
                cs.entity_retrieval_details.append({
                    "role": "anchor", "query": query, "selected": selected,
                    "selected_idx": cs.anchor_idx, "llm_resolved": True,
                })
            else:
                # Find which endpoint this resolves
                for ep in cs._pending_endpoints:
                    if ep["query"] == query:
                        step_idx = ep["step_idx"]
                        idx = cs.ents.index(selected) if selected and selected in cs.ents else None
                        if idx is not None:
                            cs.breakpoints[step_idx] = idx
                        cs.entity_retrieval_details.append({
                            "role": f"endpoint_step{step_idx}", "query": query,
                            "selected": selected, "selected_idx": idx, "llm_resolved": True,
                        })
                        break

    dt = time.perf_counter() - _t0
    for cs in active:
        cs.stage_times["entity_resolve"] = dt / len(active)
    print(f"  Stage 2 (Entity resolve): {dt:.2f}s | {sum(1 for cs in active if cs.anchor_idx is not None)} anchored")
