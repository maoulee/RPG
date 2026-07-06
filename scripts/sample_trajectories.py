#!/usr/bin/env python3
"""Sample N trajectories per case for offline GRPO/DPO.

For each case, creates N independent ReactCase instances and runs them through
the ReAct batch loop with a high temperature (diversity). Each completed
trajectory is scored with the three headline scores (gt_hit/llm_hit/llm_f1)
plus the decomposed stage scores (S_select/S_reason via agent_stage_scorer),
and written as one JSONL record in chat format.

Output record shape:
    {
      "case_id": "...",
      "sample_id": 0,
      "question": "...",
      "gt_answers": [...],
      "messages": [{"role":"system",...}, {"role":"user",...}, <trajectory>],
      "gt_hit": bool, "llm_hit": bool, "llm_f1": float,
      "S_select": float|None, "S_reason": float|None,
      "agent_failed": bool, "n_steps": int
    }

Usage:
    KGQA_LLM_BATCH_TEMPERATURE=0.8 python scripts/sample_trajectories.py \
        --pilot-results reports/cwq_matfix_100/results.json \
        --cwq-pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \
        --output data/offline_grpo/traj_cwq.jsonl \
        --limit 20 --num-samples 8 --batch-chunk 25

The temperature is read from KGQA_LLM_BATCH_TEMPERATURE (default 0.8) and fed
into batch_call_llm via the env-overridable path added to batch.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from kgqa.core.config import DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.agent.react_loop import ReactCase, parse_react_output
from kgqa.agent.harness import validate, _allowed_hint
from kgqa.agent import tools as T
from kgqa.agent.loop import _ctx_to_result_dict
from kgqa.llm.batch import batch_call_llm

# Stage scorer lives under scripts/ — import by path to avoid package coupling.
import importlib.util
_scorer_path = os.path.join(_PROJECT_ROOT, "scripts", "agent_stage_scorer.py")
_spec = importlib.util.spec_from_file_location("agent_stage_scorer", _scorer_path)
_scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scorer)
score_case = _scorer.score_case


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------
def load_cases(args) -> List[tuple]:
    """Load cases from a pilot-results JSON + pkl (legacy, single dataset)."""
    pilot_rows = json.loads(Path(args.pilot_results).read_text())
    samples = pickle.loads(Path(args.cwq_pkl).read_bytes())
    sample_map = {}
    for s in samples:
        sid = s.get("id") or s.get("question_id")
        if sid:
            sample_map[sid] = s

    masked = set()
    if args.mask_wrong_type and MASK_WRONG_TYPE and Path(MASK_WRONG_TYPE).exists():
        masked = set(json.loads(Path(MASK_WRONG_TYPE).read_text()))

    cases = []
    for idx, pr in enumerate(pilot_rows[:args.limit], 1):
        sample = sample_map.get(pr["case_id"])
        if not sample:
            for s in samples:
                if s.get("question", "") == pr.get("question", ""):
                    sample = s
                    break
        if not sample or pr["case_id"] in masked:
            continue
        cases.append((sample, pr, idx))
    return cases


def _sample_to_pilot_row(s: Dict, dataset_tag: str) -> Dict:
    """Build a pilot_row dict from a raw pkl sample (no pilot file needed)."""
    gt = s.get("a_entity") or s.get("answers") or []
    if isinstance(gt, str):
        gt = [gt]
    return {
        "case_id": s.get("id") or s.get("question_id") or "",
        "question": s.get("question", ""),
        "gt_answers": list(gt) if isinstance(gt, list) else ([gt] if gt else []),
        "dataset": dataset_tag,
    }


def load_mixed_cases(args) -> List[tuple]:
    """Load cases from multiple pkls directly (no pilot file needed).

    Reads --cwq-pkl and --webqsp-pkl, samples up to --cwq-limit / --webqsp-limit
    from each, tags each with its dataset. Used for large-scale mixed sampling.
    """
    cases: List[tuple] = []
    idx = 0
    sources = [
        (args.cwq_pkl, getattr(args, "cwq_limit", args.limit), "cwq",
         getattr(args, "cwq_mask", None)),
        (args.webqsp_pkl, getattr(args, "webqsp_limit", 0), "webqsp",
         getattr(args, "webqsp_mask", None)),
    ]
    for pkl_path, limit, tag, mask_path in sources:
        if not pkl_path or not Path(pkl_path).exists() or limit <= 0:
            continue
        samples = pickle.loads(Path(pkl_path).read_bytes())
        masked = set()
        if mask_path and Path(mask_path).exists():
            masked = set(json.loads(Path(mask_path).read_text()))
        for s in samples[:limit]:
            sid = s.get("id") or s.get("question_id") or ""
            if sid in masked:
                continue
            idx += 1
            cases.append((s, _sample_to_pilot_row(s, tag), idx))
    return cases


# ---------------------------------------------------------------------------
# Trajectory → chat messages conversion
# ---------------------------------------------------------------------------
def trajectory_to_messages(rc: ReactCase) -> List[Dict[str, str]]:
    """Reconstruct the full chat conversation from a ReactCase.

    system + user come from rc.messages[0:2]; the rest is rc.messages[2:]
    interleaved with trajectory tool results. In react_loop, rc.messages holds
    the live conversation (system, user, assistant, user-toolresult, ...),
    where tool results are injected as user-role messages prefixed with
    'Tool result (name): ...'. We keep that shape — it is a valid chat format
    the model can be trained on (no tool_call_id plumbing needed for SFT/DPO).

    Assistant messages carry an optional ``reasoning`` key (vLLM separates
    <think> into a `reasoning` field). We preserve it so SFT/GRPO training
    data includes the full chain-of-thought alongside the tool-call content.
    """
    out = []
    for m in rc.messages:
        msg = {"role": m["role"], "content": m["content"]}
        if m.get("reasoning"):
            msg["reasoning"] = m["reasoning"]
        out.append(msg)
    return out


def to_result_dict(rc: ReactCase) -> Dict[str, Any]:
    """Build a result dict (with agent_trajectory) for scoring."""
    failed = rc.failed or (not rc.done)
    reason = rc.failure_reason or ("" if rc.done else f"max_rounds reached at {rc.state.state}")
    return _ctx_to_result_dict(rc.ctx, rc.state, failed, reason)


def _adapt_trajectory_for_scorer(result: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a react-mode result dict for agent_stage_scorer.parse_trajectory.

    Two naming/shape mismatches to fix:
      1. react tool name is ``expand_branches`` (batch) but scorer expects
         ``expand_branch`` (singular).
      2. ``expand_branches`` returns ``{branches_expanded:[ids], candidates:[...],
         per_branch:{id->[cands]}}`` for ALL expanded branches in one call, but
         ``parse_trajectory`` expects one ``expand_branch`` step per branch with
         ``{branch_id, candidates}``. We split the batch call into per-branch
         steps so the scorer's branch_cand / expanded_ids populate correctly.
    """
    import json as _json
    traj = list(result.get("agent_trajectory") or [])
    adapted = []
    all_expand_cands = []
    for step in traj:
        s = dict(step)
        name = s.get("name", "")
        if name == "expand_branches":
            try:
                d = _json.loads(s.get("content", "{}"))
            except Exception:
                d = {}
            per_branch = d.get("per_branch") or []
            # per_branch is a LIST of {branch_id, candidates, readable, ...}
            # (expand_branches batch call). Normalize to scorer's per-branch steps.
            branch_items = []
            if isinstance(per_branch, list):
                for item in per_branch:
                    if isinstance(item, dict):
                        bid = str(item.get("branch_id", ""))
                        bc = item.get("candidates") or []
                        if bid:
                            branch_items.append((bid, bc))
            elif isinstance(per_branch, dict):
                for bid, bc in per_branch.items():
                    branch_items.append((str(bid), bc if isinstance(bc, list) else []))
            flat_cands = d.get("candidates") or []
            all_expand_cands.extend(flat_cands)
            if branch_items:
                for bid, bc in branch_items:
                    adapted.append({
                        "role": "tool",
                        "name": "expand_branch",
                        "content": _json.dumps({"branch_id": bid, "candidates": bc}),
                    })
            else:
                adapted.append({
                    "role": "tool",
                    "name": "expand_branch",
                    "content": _json.dumps({"branch_id": "1", "candidates": flat_cands}),
                })
        else:
            # Ensure name present (react already has it; defensive for tool results)
            if s.get("role") == "tool" and "name" not in s:
                c = s.get("content", "")
                if c.startswith("Tool result ("):
                    s["name"] = c.split("(", 1)[1].split(")", 1)[0]
            adapted.append(s)

    out = dict(result)
    out["agent_trajectory"] = adapted
    ac = list(result.get("answer_candidates") or [])
    out["answer_candidates"] = ac if ac else all_expand_cands
    return out


# ---------------------------------------------------------------------------
# Batch sampling loop (adapted from react_loop.run_react_batch)
# ---------------------------------------------------------------------------
async def sample_all(cases: List[tuple], num_samples: int, max_rounds: int,
                     max_tokens: int, batch_chunk: int, output_path: str):
    """Run num_samples ReactCase instances per case, batched across all cases."""
    # Build N instances per case
    instances: List[tuple] = []  # (case_meta, sample_id, ReactCase)
    for sample, pr, idx in cases:
        for sid in range(num_samples):
            rc = ReactCase(sample, pr, idx)
            meta = {
                "case_id": pr.get("case_id", sample.get("id", "")),
                "sample_id": sid,
                "question": pr.get("question", sample.get("question", "")),
                "gt_answers": (pr.get("gt_answers") or pr.get("gt")
                               or ([pr["gt"]] if pr.get("gt") else [])),
            }
            instances.append((meta, sid, rc))

    total = len(instances)
    print(f"\n=== Sampling {total} trajectories ({len(cases)} cases × {num_samples}) ===",
          flush=True)
    wall_start = time.perf_counter()
    records: List[Dict[str, Any]] = []

    dispatch_sem = asyncio.Semaphore(16)

    async with aiohttp.ClientSession() as session:
        for round_num in range(max_rounds):
            active = [t for t in instances if t[2].is_active]
            if not active:
                break

            prompts = []
            for meta, sid, rc in active:
                hint = rc.allowed_tools_hint()
                msgs = list(rc.messages) + [{"role": "user", "content": hint}]
                prompts.append(msgs)

            print(f"  Round {round_num+1}: {len(active)} active, "
                  f"batching {len(prompts)} calls...", flush=True)
            t_batch = time.perf_counter()

            chunks = [prompts[i:i + batch_chunk]
                      for i in range(0, len(prompts), batch_chunk)]

            async def _batch_chunk(chunk):
                return await batch_call_llm(session, chunk, max_tokens=max_tokens)

            try:
                chunk_results = await asyncio.gather(*[_batch_chunk(c) for c in chunks])
            except Exception as e:
                print(f"  Batch failed: {e}", flush=True)
                for meta, sid, rc in active:
                    rc.failed = True
                    rc.failure_reason = f"batch error: {e}"
                break

            responses = []
            for cr in chunk_results:
                responses.extend(cr)
            print(f"  Batch done in {time.perf_counter()-t_batch:.1f}s", flush=True)

            async def process(meta, sid, rc, raw):
                async with dispatch_sem:
                    await _process_one(meta, sid, rc, raw, session)

            await asyncio.gather(*[process(m, s, rc, r)
                                   for (m, s, rc), r in zip(active, responses)])

            done = sum(1 for _, _, rc in instances if rc.done)
            failed = sum(1 for _, _, rc in instances if rc.failed)
            print(f"  Round {round_num+1}: done={done} failed={failed} "
                  f"active={total-done-failed}", flush=True)

    # Build records for all instances
    for meta, sid, rc in instances:
        result = to_result_dict(rc)
        # Stage scores (S_select / S_reason) — react trajectory needs conversion
        # to the {role:tool, name, content} shape parse_trajectory expects.
        result_for_scoring = _adapt_trajectory_for_scorer(result)
        try:
            stage = score_case(result_for_scoring)
            s_plan = stage.get("S_plan")
            s_select = stage.get("S_select")
            s_reason = stage.get("S_reason")
            scorer_notes = stage.get("notes", [])
        except Exception:
            s_plan = s_select = s_reason = None
            scorer_notes = ["scorer_error"]

        rec = {
            "case_id": meta["case_id"],
            "sample_id": sid,
            "question": meta["question"],
            "gt_answers": meta["gt_answers"],
            "messages": trajectory_to_messages(rc),
            "gt_hit": result.get("gt_hit", False),
            "llm_hit": result.get("llm_hit", False),
            "llm_f1": result.get("llm_f1", 0.0),
            "llm_answer": result.get("llm_answer", ""),
            "S_plan": s_plan,
            "S_select": s_select,
            "S_reason": s_reason,
            "scorer_notes": scorer_notes,
            "agent_failed": result.get("agent_failed", False),
            "n_steps": len(result.get("agent_trajectory", [])),
        }
        records.append(rec)

    wall = time.perf_counter() - wall_start
    _write_and_summarize(records, output_path, wall, num_samples)
    return records


async def _process_one(meta, sid, rc: ReactCase, raw_response, session):
    """Parse one LLM response, validate, dispatch tool, append to rc.messages."""
    if not raw_response or not raw_response.strip():
        rc.messages.append({"role": "assistant", "content": ""})
        rc.messages.append({"role": "user", "content": rc.allowed_tools_hint()})
        return

    rc.messages.append({"role": "assistant", "content": raw_response})
    rc.ctx.trajectory.append({"role": "assistant", "content": raw_response})

    tool_name, parsed_args = parse_react_output(raw_response)
    if not tool_name:
        rc.messages.append({"role": "user",
                            "content": f"Could not parse tool call. Output JSON like: "
                                       f"{{\"tool\": \"...\", \"args\": {{...}}}}. "
                                       f"{rc.allowed_tools_hint()}"})
        return

    parsed_args = parsed_args or {}
    tool_calls = [{
        "id": "react-call", "type": "function",
        "function": {"name": tool_name,
                     "arguments": json.dumps(parsed_args) if parsed_args else "{}"},
    }]
    ok, err, new_state = validate(rc.state, tool_calls)
    if not ok:
        rc.messages.append({"role": "user", "content": f"REJECTED: {err}"})
        rc.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
        return

    rc.state = new_state
    rc.ctx.fact_ids = list(getattr(rc.state, "fact_ids", []) or [])
    rc.ctx.fact_satisfies = dict(getattr(rc.state, "fact_satisfies", {}) or {})

    try:
        result_str = await T.dispatch(tool_name, parsed_args, rc.ctx, session)
    except Exception as e:
        result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

    rc.messages.append({"role": "user", "content": f"Tool result ({tool_name}): {result_str}"})
    rc.ctx.trajectory.append({"role": "tool", "name": tool_name, "content": result_str})

    if rc.state.state == "DONE":
        rc.done = True


def _write_and_summarize(records, output_path, wall, num_samples):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(records)
    by_case = {}
    for r in records:
        by_case.setdefault(r["case_id"], []).append(r)

    # Group variance check (GRPO needs within-group score spread)
    var_cases = 0
    for cid, recs in by_case.items():
        f1s = [r["llm_f1"] for r in recs]
        if max(f1s) - min(f1s) > 0.01:
            var_cases += 1

    done = sum(1 for r in records if not r["agent_failed"])
    mean_f1 = sum(r["llm_f1"] for r in records) / n if n else 0
    hit = sum(1 for r in records if r["llm_hit"])

    print(f"\n{'='*60}")
    print(f"Sampled {n} trajectories ({len(by_case)} cases × {num_samples}) "
          f"in {wall:.1f}s")
    print(f"{'='*60}")
    print(f"Completed (not failed): {done}/{n}")
    print(f"LLM hit: {hit}/{n} ({hit/n:.3f})" if n else "LLM hit: 0")
    print(f"Mean llm_f1: {mean_f1:.3f}")
    print(f"Cases with within-group score variance (GRPO-useful): "
          f"{var_cases}/{len(by_case)}")
    print(f"Written to: {out}")


# ---------------------------------------------------------------------------
async def two_stage_sample_all(cases, max_rounds, max_tokens, batch_chunk,
                               output_path, sample_temp, n_extra,
                               variance_thresh):
    """Two-stage sampling: coarse-filter then precision-sample.

    Stage 1 (coarse): run 2 samples/case at sample_temp. Cheap and broad —
        covers ALL cases to find which ones have within-case variance.
    Stage 2 (precision): for cases WITH variance (f1 spread > thresh), run
        n_extra MORE samples. Cases with zero variance (all-correct or
        all-wrong) are skipped — they carry no GRPO signal.

    This concentrates compute on the ~20% of cases that actually produce
    advantage signal, ~3x more efficient than uniform N-samples-everywhere.
    """
    import os
    os.environ["KGQA_LLM_BATCH_TEMPERATURE"] = str(sample_temp)
    os.environ["KGQA_LLM_BATCH_TOP_P"] = "0.95"

    # ---- Stage 1: 2 samples/case ----
    print(f"\n=== Stage 1: coarse filter ({len(cases)} cases × 2 samples) ===",
          flush=True)
    s1_instances = []
    for sample, pr, idx in cases:
        for sid in range(2):
            rc = ReactCase(sample, pr, idx)
            meta = {
                "case_id": pr.get("case_id", sample.get("id", "")),
                "sample_id": sid,
                "question": pr.get("question", sample.get("question", "")),
                "gt_answers": (pr.get("gt_answers") or pr.get("gt")
                               or ([pr["gt"]] if pr.get("gt") else [])),
            }
            s1_instances.append((meta, sid, rc))
    s1_records = await _run_instances(s1_instances, max_rounds, max_tokens,
                                      batch_chunk, "stage1")

    # classify: which cases have variance?
    by_case = {}
    for r in s1_records:
        by_case.setdefault(r["case_id"], []).append(r)
    var_cases = set()
    for cid, recs in by_case.items():
        if len(recs) < 2:
            continue
        f1s = [r["llm_f1"] for r in recs]
        if max(f1s) - min(f1s) > variance_thresh:
            var_cases.add(cid)
    print(f"\n  Stage 1 result: {len(var_cases)}/{len(by_case)} cases have "
          f"variance (>{variance_thresh})", flush=True)

    # ---- Stage 2: n_extra samples for variance cases ----
    if n_extra <= 0 or not var_cases:
        print(f"\n  Stage 2 skipped (n_extra={n_extra})", flush=True)
        all_records = s1_records
    else:
        print(f"\n=== Stage 2: precision sample ({len(var_cases)} cases × "
              f"{n_extra} extra) ===", flush=True)
        case_map = {pr.get("case_id", s.get("id", "")): (s, pr, idx)
                    for s, pr, idx in cases}
        s2_instances = []
        for cid in sorted(var_cases):
            if cid not in case_map:
                continue
            sample, pr, idx = case_map[cid]
            for sid in range(2, 2 + n_extra):  # continue sample_id from 2
                rc = ReactCase(sample, pr, idx)
                meta = {
                    "case_id": cid, "sample_id": sid,
                    "question": pr.get("question", sample.get("question", "")),
                    "gt_answers": (pr.get("gt_answers") or pr.get("gt")
                                   or ([pr["gt"]] if pr.get("gt") else [])),
                }
                s2_instances.append((meta, sid, rc))
        s2_records = await _run_instances(s2_instances, max_rounds, max_tokens,
                                          batch_chunk, "stage2")
        all_records = s1_records + s2_records

    _write_and_summarize(all_records, output_path, 0.0, 2 + n_extra)
    return all_records


# ---------------------------------------------------------------------------
async def stratified_sample_all(cases, max_rounds, max_tokens, batch_chunk,
                                output_path, probe_temp_env, buckets):
    """Difficulty-stratified sampling to maximize GRPO signal.

    Phase 1 (probe): run ONE trajectory per case at temperature=0 to estimate
        each case's difficulty (llm_f1).
    Phase 2 (sample): allocate more samples to "medium" cases (0 < f1 < 1),
        where sampling diversity produces non-trivial within-group advantage.
        Easy (f1=1) and hard (f1=0) cases get fewer samples.

    buckets: dict like {"easy": 2, "medium": 8, "hard": 4} mapping difficulty
        to per-case sample count (excluding the probe).

    The probe trajectory is reused as sample 0 for its case (not wasted).
    """
    import os
    # ---- Phase 1: probe each case at t=0 ----
    print(f"\n=== Phase 1: probing {len(cases)} cases at t=0 ===", flush=True)
    os.environ["KGQA_LLM_BATCH_TEMPERATURE"] = "0.0"
    os.environ["KGQA_LLM_BATCH_TOP_P"] = "1.0"
    probe_instances = []
    for sample, pr, idx in cases:
        rc = ReactCase(sample, pr, idx)
        meta = {
            "case_id": pr.get("case_id", sample.get("id", "")),
            "sample_id": 0,
            "question": pr.get("question", sample.get("question", "")),
            "gt_answers": (pr.get("gt_answers") or pr.get("gt")
                           or ([pr["gt"]] if pr.get("gt") else [])),
        }
        probe_instances.append((meta, 0, rc))

    probe_records = await _run_instances(probe_instances, max_rounds, max_tokens,
                                         batch_chunk, "probe")
    # classify difficulty
    difficulty = {}  # case_id -> "easy"/"medium"/"hard"
    for r in probe_records:
        f1 = r["llm_f1"]
        if f1 >= 0.99:
            difficulty[r["case_id"]] = "easy"
        elif f1 <= 0.01:
            difficulty[r["case_id"]] = "hard"
        else:
            difficulty[r["case_id"]] = "medium"

    from collections import Counter
    dist = Counter(difficulty.values())
    print(f"  difficulty: easy={dist.get('easy',0)} medium={dist.get('medium',0)} "
          f"hard={dist.get('hard',0)}", flush=True)

    # ---- Phase 2: allocate samples by difficulty ----
    print(f"\n=== Phase 2: stratified sampling (buckets={buckets}) ===", flush=True)
    os.environ["KGQA_LLM_BATCH_TEMPERATURE"] = str(probe_temp_env)
    os.environ["KGQA_LLM_BATCH_TOP_P"] = "0.95"
    sample_instances = []
    for sample, pr, idx in cases:
        cid = pr.get("case_id", sample.get("id", ""))
        diff = difficulty.get(cid, "medium")
        n_extra = buckets.get(diff, 4)
        for sid in range(1, n_extra + 1):  # sid=0 is the probe
            rc = ReactCase(sample, pr, idx)
            meta = {
                "case_id": cid, "sample_id": sid,
                "question": pr.get("question", sample.get("question", "")),
                "gt_answers": (pr.get("gt_answers") or pr.get("gt")
                               or ([pr["gt"]] if pr.get("gt") else [])),
            }
            sample_instances.append((meta, sid, rc))

    sample_records = await _run_instances(sample_instances, max_rounds, max_tokens,
                                          batch_chunk, "sample")
    all_records = probe_records + sample_records
    wall = 0  # _run_instances prints its own timing
    _write_and_summarize(all_records, output_path, wall,
                         max(buckets.values()) + 1)
    return all_records


async def _run_instances(instances, max_rounds, max_tokens, batch_chunk, tag):
    """Run a batch of ReactCase instances through the ReAct loop. Shared by
    sample_all and stratified_sample_all."""
    total = len(instances)
    if total == 0:
        return []
    print(f"  [{tag}] {total} instances", flush=True)
    wall_start = time.perf_counter()
    dispatch_sem = asyncio.Semaphore(16)

    async with aiohttp.ClientSession() as session:
        for round_num in range(max_rounds):
            active = [t for t in instances if t[2].is_active]
            if not active:
                break
            prompts = []
            for meta, sid, rc in active:
                hint = rc.allowed_tools_hint()
                msgs = list(rc.messages) + [{"role": "user", "content": hint}]
                prompts.append(msgs)
            chunks = [prompts[i:i + batch_chunk]
                      for i in range(0, len(prompts), batch_chunk)]

            async def _batch_chunk(chunk):
                return await batch_call_llm(session, chunk, max_tokens=max_tokens)
            try:
                chunk_results = await asyncio.gather(*[_batch_chunk(c) for c in chunks])
            except Exception as e:
                print(f"  [{tag}] batch failed: {e}", flush=True)
                for meta, sid, rc in active:
                    rc.failed = True
                    rc.failure_reason = f"batch error: {e}"
                break
            responses = []
            for cr in chunk_results:
                responses.extend(cr)

            async def process(meta, sid, rc, raw):
                async with dispatch_sem:
                    await _process_one(meta, sid, rc, raw, session)
            await asyncio.gather(*[process(m, s, rc, r)
                                   for (m, s, rc), r in zip(active, responses)])
            done = sum(1 for _, _, rc in instances if rc.done)
            failed = sum(1 for _, _, rc in instances if rc.failed)
            print(f"  [{tag}] round {round_num+1}: done={done} failed={failed} "
                  f"active={total-done-failed}", flush=True)

    # Build records
    records = []
    for meta, sid, rc in instances:
        result = to_result_dict(rc)
        result_for_scoring = _adapt_trajectory_for_scorer(result)
        try:
            stage = score_case(result_for_scoring)
            s_plan = stage.get("S_plan")
            s_select = stage.get("S_select")
            s_reason = stage.get("S_reason")
            scorer_notes = stage.get("notes", [])
        except Exception:
            s_plan = s_select = s_reason = None
            scorer_notes = ["scorer_error"]
        records.append({
            "case_id": meta["case_id"], "sample_id": sid,
            "question": meta["question"], "gt_answers": meta["gt_answers"],
            "messages": trajectory_to_messages(rc),
            "gt_hit": result.get("gt_hit", False),
            "llm_hit": result.get("llm_hit", False),
            "llm_f1": result.get("llm_f1", 0.0),
            "llm_answer": result.get("llm_answer", ""),
            "S_plan": s_plan, "S_select": s_select, "S_reason": s_reason,
            "scorer_notes": scorer_notes,
            "agent_failed": result.get("agent_failed", False),
            "n_steps": len(result.get("agent_trajectory", [])),
        })
    print(f"  [{tag}] done in {time.perf_counter()-wall_start:.1f}s", flush=True)
    return records


# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Sample N trajectories/case for offline RL")
    # Single-dataset mode (legacy)
    p.add_argument("--pilot-results", default="reports/cwq_matfix_100/results.json")
    p.add_argument("--cwq-pkl", default=str(DEFAULT_CWQ))
    p.add_argument("--mask-wrong-type", default=str(MASK_WRONG_TYPE))
    p.add_argument("--limit", type=int, default=10)
    # Mixed-dataset mode (large-scale)
    p.add_argument("--mixed", action="store_true",
                   help="load from --cwq-pkl + --webqsp-pkl directly (no pilot file)")
    p.add_argument("--webqsp-pkl", default="")
    p.add_argument("--cwq-limit", type=int, default=0,
                   help="max CWQ cases for mixed mode (0 = skip)")
    p.add_argument("--webqsp-limit", type=int, default=0,
                   help="max WebQSP cases for mixed mode (0 = skip)")
    p.add_argument("--cwq-mask", default="")
    p.add_argument("--webqsp-mask", default="")
    # Common
    p.add_argument("--output", required=True)
    p.add_argument("--num-samples", type=int, default=8)
    p.add_argument("--agent-max-iters", type=int, default=16)
    p.add_argument("--agent-max-tokens", type=int, default=1024)
    p.add_argument("--batch-chunk", type=int, default=25)
    p.add_argument("--stratify", action="store_true",
                   help="difficulty-stratified sampling (probe at t=0, then "
                        "allocate more samples to medium-difficulty cases)")
    p.add_argument("--two-stage", action="store_true",
                   help="two-stage: 2 samples/case to find variance cases, "
                        "then n-extra samples only for those. Concentrates "
                        "compute on GRPO-signal-bearing cases.")
    p.add_argument("--n-extra", type=int, default=6,
                   help="[two-stage] extra samples per variance case")
    p.add_argument("--variance-thresh", type=float, default=0.1,
                   help="[two-stage] min f1 spread to count a case as variance")
    p.add_argument("--sample-temp", type=float, default=0.8,
                   help="sampling temperature for the non-probe phase")
    args = p.parse_args()

    if args.mixed:
        cases = load_mixed_cases(args)
    else:
        cases = load_cases(args)
    print(f"Loaded {len(cases)} cases", flush=True)
    if args.two_stage:
        asyncio.run(two_stage_sample_all(
            cases, args.agent_max_iters, args.agent_max_tokens, args.batch_chunk,
            args.output, args.sample_temp, args.n_extra, args.variance_thresh))
    elif args.stratify:
        buckets = {"easy": 1, "medium": args.num_samples, "hard": 3}
        asyncio.run(stratified_sample_all(
            cases, args.agent_max_iters, args.agent_max_tokens, args.batch_chunk,
            args.output, args.sample_temp, buckets))
    else:
        asyncio.run(sample_all(cases, args.num_samples, args.agent_max_iters,
                               args.agent_max_tokens, args.batch_chunk, args.output))


if __name__ == "__main__":
    main()
