"""Native tool-calling agent orchestrator.

Self-contained: imports the robust engines (GTE, k_queue, compress_paths) and
the stage pipeline's CaseState only as a data carrier for result-dict shape
compatibility. Does NOT call run_stage_mode or any kgqa/stages/* stage function.

Flow per case:
  build CaseContext (ents/rels/edges from sample, expand CVTs, resolve anchor)
  → messages = [system=AGENTS.md, user="Question: ..."]
  → loop (≤ max_iters):
       msg = agent_call(session, messages, tools_for_state(state), ...)
       if msg.tool_calls: harness.validate → dispatch (if ok) or guidance (if bad)
       if answer accepted: parse + return
  → on failure: return best-effort with agent_failed=True (entry decides fallback)
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from kgqa.core.utils import normalize, candidate_hit, strict_candidate_hit, compute_match_stats
from kgqa.traversal.cvt import is_cvt_like, expand_cvt_leaves
from kgqa.llm.client import agent_call
from kgqa.agent import harness as H
from kgqa.agent import tools as T
from kgqa.agent.loader import agents_md


# ---------------------------------------------------------------------------
# Per-case context (built once from a pipeline sample dict)
# ---------------------------------------------------------------------------

@dataclass
class CaseContext:
    """Holds the per-case KG data + agent-accumulated paths/candidates."""
    case_id: str = ""
    case_num: int = 0
    question: str = ""
    gt_answers: List[str] = field(default_factory=list)
    sample: Dict[str, Any] = field(default_factory=dict)
    pilot_row: Dict[str, Any] = field(default_factory=dict)

    # KG arrays (mirrors CaseState after stage0)
    ents: List[str] = field(default_factory=list)
    rels: List[str] = field(default_factory=list)
    rel_texts: List[str] = field(default_factory=list)
    h_ids: List[int] = field(default_factory=list)
    r_ids: List[int] = field(default_factory=list)
    t_ids: List[int] = field(default_factory=list)
    ent_candidates: List[str] = field(default_factory=list)

    # Anchor
    anchor_idx: Optional[int] = None
    anchor_name: Optional[str] = None
    breakpoints: Dict[int, int] = field(default_factory=dict)

    # Agent-accumulated state
    fact_ids: List[str] = field(default_factory=list)       # ordered fact ids (from decompose)
    fact_texts: Dict[str, str] = field(default_factory=dict)
    fact_relations: Dict[str, set] = field(default_factory=dict)  # fact_id -> GTE relation idx set
    fact_relation_candidates: Dict[str, list] = field(default_factory=dict)  # fact_id -> pruned candidate rel idx (model picks from these)
    fact_paths: Dict[str, list] = field(default_factory=dict)
    all_paths: list = field(default_factory=list)
    all_candidates: List[str] = field(default_factory=list)
    logical_paths: list = field(default_factory=list)
    selected_candidates: List[str] = field(default_factory=list)
    branches: Dict[str, dict] = field(default_factory=dict)  # branch_id -> {candidates, triples, readable}

    # Final answer
    llm_answer_preds: List[str] = field(default_factory=list)
    llm_answer_str: str = ""

    # Diagnostics
    trajectory: list = field(default_factory=list)   # [{role, content/tool_calls}, ...]
    stage_times: Dict[str, float] = field(default_factory=dict)


def build_context(sample: Dict[str, Any], pilot_row: Dict[str, Any], idx: int) -> CaseContext:
    """Build a CaseContext from a pipeline sample dict (same shape run_pipeline uses).

    Replicates stage0's subgraph extraction: ents from text/non-text entity lists,
    rels from relation_list, edges from h/r/t_id_list, CVT-leaf expansion, and
    rel_texts/ent_candidates. Anchor resolution reuses the q_entity→entity-list
    heuristic from stage1_cascade (_resolve_anchor / _fallback_anchor logic).
    """
    gt = pilot_row.get("gt", pilot_row.get("ground_truth", pilot_row.get("gt_answers", [])))
    ctx = CaseContext(
        case_id=pilot_row.get("case_id", sample.get("id", "")),
        case_num=idx,
        question=pilot_row.get("question", sample.get("question", "")),
        gt_answers=gt if isinstance(gt, list) else ([gt] if gt else []),
        sample=sample,
        pilot_row=pilot_row,
    )

    # Subgraph (identical to stage0_ner.resolve)
    ents = list(sample.get("text_entity_list", [])) + list(sample.get("non_text_entity_list", []))
    rels = list(sample.get("relation_list", []))
    h_ids = list(sample.get("h_id_list", []))
    r_ids = list(sample.get("r_id_list", []))
    t_ids = list(sample.get("t_id_list", []))
    ents, rels, h_ids, r_ids, t_ids = expand_cvt_leaves(ents, rels, h_ids, r_ids, t_ids)

    ctx.ents = ents
    ctx.rels = rels
    ctx.h_ids = h_ids
    ctx.r_ids = r_ids
    ctx.t_ids = t_ids
    ctx.rel_texts = list(rels)
    ctx.ent_candidates = [e for e in ents if e and len(e) > 1 and not is_cvt_like(e)]

    _resolve_anchor(ctx)
    return ctx


def _resolve_anchor(ctx: CaseContext):
    """Resolve the anchor from the sample's q_entity, mirroring stage1_cascade.

    Exact normalized match first, then substring (len>=3), then fallback to the
    first q_entity / first entity. Sets ctx.anchor_idx and ctx.anchor_name.
    """
    q_entities = ctx.sample.get("q_entity", []) or []
    if q_entities:
        for qe in q_entities:
            qn = normalize(qe)
            if not qn:
                continue
            for i, e in enumerate(ctx.ents):
                if normalize(e) == qn:
                    ctx.anchor_idx = i
                    ctx.anchor_name = ctx.ents[i]
                    return
            for i, e in enumerate(ctx.ents):
                en = normalize(e)
                if len(qn) >= 3 and (qn in en or en in qn):
                    ctx.anchor_idx = i
                    ctx.anchor_name = ctx.ents[i]
                    return
        # fallback: first q_entity even if no match (anchor_idx stays None)
        ctx.anchor_name = q_entities[0]
        ctx.anchor_idx = None
        return
    if ctx.ents:
        ctx.anchor_idx = 0
        ctx.anchor_name = ctx.ents[0]


# ---------------------------------------------------------------------------
# Single-case agent loop
# ---------------------------------------------------------------------------

async def run_agent_case(session: aiohttp.ClientSession, sample: Dict[str, Any],
                         pilot_row: Dict[str, Any], idx: int,
                         args) -> Dict[str, Any]:
    """Run the tool-calling agent on one case. Returns a result dict whose shape
    matches kgqa.stages.stage8_reason._case_state_to_result_dict so the same
    scoring/summary code path works for both modes."""
    t0 = time.perf_counter()
    ctx = build_context(sample, pilot_row, idx)
    state = H.AgentState()

    system_prompt = agents_md()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Question: {ctx.question}"},
    ]
    if ctx.anchor_name:
        messages[1]["content"] += f"\nAnchor entity (starting point): {ctx.anchor_name}"

    max_iters = int(getattr(args, "agent_max_iters", 16))
    agent_failed = False
    failure_reason = ""

    for _ in range(max_iters):
        offered = T.tools_for_state(state.state)
        if not offered:
            break  # DONE
        try:
            msg = await agent_call(
                session, messages, offered,
                tool_choice="required" if state.state != "ANSWER" else "auto",
                max_tokens=int(getattr(args, "agent_max_tokens", 1024)),
                temperature=float(getattr(args, "agent_temperature", 0.3)),
            )
        except Exception as e:
            agent_failed = True
            failure_reason = f"agent_call error: {e}"
            break

        # Append the assistant message verbatim (preserves tool_calls for the API)
        assistant_msg = {"role": "assistant",
                         "content": msg.get("content") or "",
                         "tool_calls": msg.get("tool_calls") or None}
        # Strip None tool_calls to match OpenAI shape expectations
        if not assistant_msg["tool_calls"]:
            assistant_msg.pop("tool_calls")
        messages.append(assistant_msg)
        ctx.trajectory.append({"role": "assistant",
                               "content": assistant_msg["content"],
                               "tool_calls": assistant_msg.get("tool_calls")})

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # Model emitted plain content with no tool call mid-flow → nudge.
            if state.state != "ANSWER":
                messages.append({"role": "tool", "tool_call_id": "noop",
                                 "content": f"No tool call received. Next expected: "
                                            f"{H._allowed_hint(state)}. Call it now."})
                ctx.trajectory.append({"role": "tool", "content": "(nudge)"})
                continue
            # In ANSWER state, plain content means model gave up — finish.
            agent_failed = True
            failure_reason = "no answer tool_call in ANSWER state"
            break

        ok, err, state = H.validate(state, tool_calls)
        if not ok:
            # Relay the guidance as a tool-role message so the model self-corrects.
            messages.append({"role": "tool", "tool_call_id": tool_calls[0].get("id", "rej"),
                             "content": f"REJECTED: {err}"})
            ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
            continue

        # Accepted — execute via dispatch and feed the result back.
        call = tool_calls[0]
        fn = call.get("function") or {}
        tool_name = fn.get("name", "")
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args) if raw_args.strip() else {}
            except Exception:
                parsed_args = {}
        else:
            parsed_args = raw_args or {}

        # Sync the ordered fact ids (from the harness state) so _do_select can
        # build multi-step step_relations in decompose order.
        ctx.fact_ids = list(getattr(state, "fact_ids", []) or [])
        try:
            result_str = await T.dispatch(tool_name, parsed_args, ctx, session)
        except Exception as e:
            result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

        messages.append({"role": "tool", "tool_call_id": call.get("id", tool_name),
                         "name": tool_name, "content": result_str})
        ctx.trajectory.append({"role": "tool", "name": tool_name, "content": result_str})

        if state.state == H.DONE:
            break
    else:
        agent_failed = True
        failure_reason = f"max_iters ({max_iters}) reached at state {state.state}"

    dt = time.perf_counter() - t0
    ctx.stage_times["agent_total"] = dt

    return _ctx_to_result_dict(ctx, state, agent_failed, failure_reason)


# ---------------------------------------------------------------------------
# Result-dict shape (matches _case_state_to_result_dict so runner scoring works)
# ---------------------------------------------------------------------------

def _ctx_to_result_dict(ctx: CaseContext, state, agent_failed: bool,
                        failure_reason: str) -> Dict[str, Any]:
    preds = ctx.llm_answer_preds
    ans_str = ctx.llm_answer_str
    gt = ctx.gt_answers

    llm_hit = candidate_hit(preds, gt) if preds else False

    # gt_hit should reflect what the model could ACTUALLY see at answer time —
    # i.e. the expand_branch candidates (stage8), not just the stage5 pool.
    # The stage5 pool (ctx.all_candidates) only has last-step BFS candidates
    # WITHOUT sibling-CVT expansion, so it under-counts. We union with all
    # expand_branch candidate lists from the trajectory.
    expand_cands = list(ctx.all_candidates or [])
    for step in ctx.trajectory:
        if step.get("role") == "tool" and step.get("name") == "expand_branch":
            try:
                payload = json.loads(step.get("content", "{}"))
                expand_cands.extend(payload.get("candidates", []))
            except Exception:
                pass

    gt_hit = candidate_hit(expand_cands, gt) if expand_cands else False
    gt_strict = strict_candidate_hit(expand_cands, gt) if expand_cands else False
    llm_stats = compute_match_stats(preds, gt)
    gt_stats = compute_match_stats(ctx.all_candidates, gt)

    return {
        "case_id": ctx.case_id,
        "case_num": ctx.case_num,
        "question": ctx.question,
        "gt_answers": gt,
        "decomposition_method": "agent_toolcall",
        "anchor_idx": ctx.anchor_idx,
        "anchor_name": ctx.anchor_name,
        "breakpoints": {k: ctx.ents[v] for k, v in ctx.breakpoints.items()
                        if v is not None and 0 <= v < len(ctx.ents)},
        "steps_parsed": [{"id": fid, "text": ctx.fact_texts.get(fid, "")}
                         for fid in state.fact_ids],
        "n_paths": len(ctx.all_paths),
        "answer_candidates": ctx.all_candidates,
        "gt_hit": gt_hit,
        "gt_hit_strict": gt_strict,
        "gt_f1": gt_stats.get("f1", 0.0),
        "num_patterns": len(ctx.logical_paths),
        "logical_paths": [lp.get("readable", "") for lp in ctx.logical_paths[:10]],
        "llm_answer": ans_str,
        "llm_hit": llm_hit,
        "llm_f1": llm_stats.get("f1", 0.0),
        "llm_precision": llm_stats.get("precision", 0.0),
        "llm_recall": llm_stats.get("recall", 0.0),
        "agent_failed": agent_failed,
        "agent_failure_reason": failure_reason,
        "agent_state": state.state,
        "agent_trajectory": ctx.trajectory,
        "stage_times": ctx.stage_times,
        "error": failure_reason if agent_failed else None,
    }


# ---------------------------------------------------------------------------
# Batch mode (async gather with limited concurrency)
# ---------------------------------------------------------------------------

async def run_agent_mode(cases_to_run, args):
    """Run the agent over all (sample, pilot_row, idx) tuples.

    Mirrors run_stage_mode's I/O contract: writes results.json + prints a summary
    with the same GT/LLM hit + F1 surface so the two modes are directly comparable.
    """
    total = len(cases_to_run)
    print(f"\n=== Agent tool-call mode: {total} cases ===")
    parallel = max(1, min(int(getattr(args, "parallel", 1)), 32))
    sem = asyncio.Semaphore(parallel)

    async def _one(session, sample, pilot_row, idx):
        async with sem:
            try:
                return await run_agent_case(session, sample, pilot_row, idx, args)
            except Exception as e:
                return {
                    "case_id": pilot_row.get("case_id", ""),
                    "case_num": idx,
                    "question": pilot_row.get("question", ""),
                    "gt_answers": pilot_row.get("gt_answers",
                                                pilot_row.get("gt", [])),
                    "agent_failed": True,
                    "agent_failure_reason": f"unhandled: {e}",
                    "llm_answer": "",
                    "llm_hit": False,
                    "gt_hit": False,
                    "gt_hit_strict": False,
                    "gt_f1": 0.0,
                    "llm_f1": 0.0,
                    "llm_precision": 0.0,
                    "llm_recall": 0.0,
                    "answer_candidates": [],
                    "n_paths": 0,
                    "steps_parsed": [],
                    "stage_times": {},
                    "error": f"unhandled: {e}",
                }

    wall_start = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[
            _one(session, sample, pilot_row, idx)
            for sample, pilot_row, idx in cases_to_run
        ])
    wall_time = time.perf_counter() - wall_start

    _write_results(results, args, wall_time)
    return results


def _write_results(results, args, wall_time):
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    cases = len(results)
    if cases == 0:
        print("\n=== No valid cases processed ===")
        return

    gt_hits = sum(1 for r in results if r.get("gt_hit"))
    llm_hits = sum(1 for r in results if r.get("llm_hit"))
    failures = sum(1 for r in results if r.get("agent_failed"))
    errors = sum(1 for r in results if r.get("error"))

    gt_f1_avg = sum(r.get("gt_f1", 0) for r in results) / cases
    llm_f1_avg = sum(r.get("llm_f1", 0) for r in results) / cases
    llm_p_avg = sum(r.get("llm_precision", 0) for r in results) / cases
    llm_r_avg = sum(r.get("llm_recall", 0) for r in results) / cases
    strict_hits = sum(1 for r in results if r.get("gt_hit_strict"))

    for r in results:
        gt_mark = "✓" if r.get("gt_hit") else "✗"
        llm_mark = "✓" if r.get("llm_hit") else "✗"
        fail_mark = "!" if r.get("agent_failed") else " "
        print(f"  [{r.get('case_num', '?')}] GT{gt_mark} LLM{llm_mark}{fail_mark} "
              f"(F1={r.get('llm_f1', 0):.2f}) facts={len(r.get('steps_parsed', []))} "
              f"paths={r.get('n_paths', 0)} | {r.get('question', '')[:55]}")

    print(f"\n=== Summary: GT_recall={gt_hits}/{cases} ({100*gt_hits/cases:.1f}%) | "
          f"strict={strict_hits}/{cases} | GT_F1={gt_f1_avg:.3f} | "
          f"LLM_reason={llm_hits}/{cases} ({100*llm_hits/cases:.1f}%) | "
          f"LLM_P={llm_p_avg:.3f} R={llm_r_avg:.3f} F1={llm_f1_avg:.3f} | "
          f"agent_failures={failures} | errors={errors} ===")
    print(f"    Wall time: {wall_time:.2f}s")

    if getattr(args, "dump_trajectories", False):
        traj_dir = out / "trajectories"
        traj_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            (traj_dir / f"case_{r.get('case_num', 0):03d}.txt").write_text(
                _format_trajectory(r), encoding="utf-8")
        print(f"    Trajectories: {traj_dir}")


def _format_trajectory(r: Dict[str, Any]) -> str:
    lines = [f"CASE [{r.get('case_num')}] {r.get('case_id')}",
             f"Q: {r.get('question')}",
             f"GT: {r.get('gt_answers')}",
             f"LLM: {r.get('llm_answer')} | hit={r.get('llm_hit')} "
             f"F1={r.get('llm_f1', 0):.2f} failed={r.get('agent_failed')}",
             f"final_state={r.get('agent_state')} "
             f"reason={r.get('agent_failure_reason', '')}",
             "-" * 70]
    for step in r.get("agent_trajectory", []):
        role = step.get("role", "?")
        if role == "assistant":
            tc = step.get("tool_calls") or []
            names = ", ".join((c.get("function") or {}).get("name", "?") for c in tc) if tc else "(no tool call)"
            lines.append(f"[ASSISTANT tools={names}]")
            if step.get("content"):
                lines.append(step["content"][:500])
        else:
            name = step.get("name", "")
            lines.append(f"[TOOL {name}] {step.get('content', '')[:400]}")
    return "\n".join(lines)
