"""ReAct Batch mode — content-only LLM calls with batch optimization.

Instead of tool-call round-trips (agent_call per turn), this mode:
1. Collects ALL active cases' LLM prompts each round
2. Sends them in ONE batch_call_llm request
3. Parses each case's JSON output → (tool_name, args)
4. Dispatches tools (reuses tools.dispatch + harness.validate unchanged)
5. Appends results, updates state, repeats until all cases DONE

The LLM returns content (not tool_calls), in a JSON envelope:
  {"tool": "retrieve", "args": {"fact_id": "f1", "relation_hint": "..."}}

This achieves ~17x throughput vs per-case round-trips, matching baseline's
batch-call pattern while keeping the agent's free orchestration (model decides
which tool to call next, not a fixed stage sequence).

All _do_* tool handlers and harness state machine are reused UNCHANGED.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from kgqa.agent.loop import (
    CaseContext, build_context, _ctx_to_result_dict, _step_dict,
)
from kgqa.agent.harness import AgentState, validate, _allowed_hint
from kgqa.agent import tools as T
from kgqa.agent.loader import agents_md
from kgqa.llm.batch import batch_call_llm


# ---------------------------------------------------------------------------
# Per-case ReAct state (wraps CaseContext + messages + harness state)
# ---------------------------------------------------------------------------
class ReactCase:
    """One case's evolving state through the ReAct batch loop."""

    def __init__(self, sample, pilot_row, idx):
        self.ctx = build_context(sample, pilot_row, idx)
        self.state = AgentState()
        self.messages: List[Dict[str, Any]] = []
        self.failed = False
        self.failure_reason = ""
        self.done = False
        self._init_messages()

    def _init_messages(self):
        sys_prompt = agents_md()
        user = f"Question: {self.ctx.question}"
        if self.ctx.anchor_name:
            user += f"\nAnchor entity (starting point): {self.ctx.anchor_name}"
        self.messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ]

    @property
    def is_active(self):
        return not self.done and not self.failed

    def allowed_tools_hint(self):
        """What tools are legal in the current state (for prompt nudge)."""
        return _allowed_hint(self.state)


# ---------------------------------------------------------------------------
# JSON envelope parsing
# ---------------------------------------------------------------------------
def parse_react_output(content: str) -> Tuple[Optional[str], Optional[dict]]:
    """Parse the LLM's content-only output into (tool_name, args).

    Prompt convention (think-then-act):
      <reasoning>
      tool: {"tool": "<name>", "args": {<args>}}

    The ``tool:`` anchor pins the real tool call, so any hypothetical JSON
    examples inside the reasoning are ignored. If no anchor is present we fall
    back to the first valid tool-JSON anywhere (backward compat with pure-JSON
    output). Anchored parsing takes the FIRST tool call — the harness enforces
    one tool per turn and the model is told to emit only one.
    """
    if not content:
        return None, None
    text = content.strip()

    def _try_parse_tool(seg: str) -> Optional[dict]:
        try:
            obj = json.loads(seg)
        except json.JSONDecodeError:
            return None
        if isinstance(obj, dict) and "tool" in obj:
            return obj
        return None

    def _first_tool_json(s: str) -> Optional[dict]:
        """Return the first balanced {...} in s that parses to a dict with 'tool'.

        Robust to truncated deep JSON: when the model omits trailing ``}`` (a
        common failure on deeply nested ``select_relations`` payloads), we take
        the segment from the first ``{`` to the last ``}`` in s and append the
        missing closing braces to balance the bracket depth before parsing.
        """
        depth, start = 0, -1
        last_close = -1
        for i, c in enumerate(s):
            if c == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    obj = _try_parse_tool(s[start:i + 1])
                    if obj is not None:
                        return obj
                    last_close = i
                    start = -1
                elif depth > 0:
                    last_close = i
        # Truncation recovery: a ``{`` was opened but never closed back to 0.
        # Re-parse from the first ``{`` to the last seen ``}``, padding the
        # missing closers so deeply nested but otherwise-valid payloads survive.
        if start >= 0 and last_close > start:
            seg = s[start:last_close + 1]
            seg += '}' * (seg.count('{') - seg.count('}'))
            obj = _try_parse_tool(seg)
            if obj is not None:
                return obj
        return None

    # 1) Anchor path: look for `tool:` then take the first tool JSON after it.
    for m in re.finditer(r'(?<![A-Za-z])tool:\s*', text, re.IGNORECASE):
        rest = text[m.end():]
        rest = re.sub(r'^\s*```(?:json)?\s*', '', rest)  # strip optional fence
        obj = _first_tool_json(rest)
        if obj is not None:
            return obj["tool"], obj.get("args") or {}

    # 2) Fallback: no anchor — backward-compat first tool JSON anywhere.
    obj = _first_tool_json(text)
    if obj is not None:
        return obj["tool"], obj.get("args") or {}

    return None, None


# ---------------------------------------------------------------------------
# Tool call to harness-compatible format
# ---------------------------------------------------------------------------
def _to_tool_calls(tool_name: str, args: dict) -> list:
    """Wrap parsed (tool_name, args) into the format harness.validate expects."""
    return [{
        "id": "react-call",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(args) if args else "{}",
        },
    }]


# ---------------------------------------------------------------------------
# Batch ReAct main loop
# ---------------------------------------------------------------------------
async def run_react_batch(cases_to_run, args, output_dir: str):
    """Run the ReAct batch agent over all cases.

    Each round:
      1. Collect active cases' current messages
      2. batch_call_llm (one HTTP request for all)
      3. Parse JSON → (tool, args) per case
      4. Dispatch tools (concurrent)
      5. Append results, update states
    """
    total = len(cases_to_run)
    print(f"\n=== ReAct batch mode: {total} cases ===", flush=True)

    wall_start = time.perf_counter()

    # Initialize all cases
    react_cases = []
    for sample, pilot_row, idx in cases_to_run:
        rc = ReactCase(sample, pilot_row, idx)
        react_cases.append(rc)

    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    # When a thinking-token budget is active, reasoning tokens come out of
    # max_tokens — raise the floor so reasoning can't starve the tool-JSON
    # output (which manifests as finish_reason=length with an empty answer).
    from kgqa.llm.client import THINKING_TOKEN_BUDGET as _tb
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)
    batch_chunk = int(getattr(args, "batch_chunk", 25))

    async with aiohttp.ClientSession() as session:
        for round_num in range(max_rounds):
            # 1. Collect active cases
            active = [rc for rc in react_cases if rc.is_active]
            if not active:
                break

            # 2. Build prompts for batch (system prompt is shared, context differs)
            prompts = []
            for rc in active:
                hint = rc.allowed_tools_hint()
                msgs = list(rc.messages)
                msgs.append({"role": "user", "content": hint})
                prompts.append(msgs)

            print(f"  Round {round_num+1}: {len(active)} active cases, "
                  f"batching {len(prompts)} LLM calls...", flush=True)
            t_batch = time.perf_counter()

            # 3. Batch LLM call — split into chunks, dispatch in parallel.
            # The batch endpoint scales poorly beyond ~25 prompts (no cross-prompt
            # KV-cache), so we chunk and fire chunks concurrently.
            chunks = [prompts[i:i+batch_chunk]
                      for i in range(0, len(prompts), batch_chunk)]

            async def _batch_chunk(chunk):
                return await batch_call_llm(session, chunk, max_tokens=max_tokens)

            try:
                chunk_results = await asyncio.gather(*[_batch_chunk(c) for c in chunks])
            except Exception as e:
                print(f"  Batch call failed: {e}", flush=True)
                for rc in active:
                    rc.failed = True
                    rc.failure_reason = f"batch_call error: {e}"
                break

            # Flatten chunked results back to per-case order
            responses = []
            for cr in chunk_results:
                responses.extend(cr)

            dt_batch = time.perf_counter() - t_batch
            print(f"  Batch done in {dt_batch:.1}s ({len(active)/dt_batch:.1f} cases/s)",
                  flush=True)

            # 4. Parse + dispatch per case (concurrent)
            async def process_case(rc, raw_response):
                """Parse LLM output, validate, dispatch tool, append result."""
                if not raw_response or not raw_response.strip():
                    # Empty response — nudge
                    rc.messages.append({"role": "assistant", "content": ""})
                    rc.messages.append({"role": "user",
                                        "content": rc.allowed_tools_hint()})
                    return

                # Append assistant message (content-only, no tool_calls)
                rc.messages.append({"role": "assistant", "content": raw_response})
                rc.ctx.trajectory.append({"role": "assistant", "content": raw_response})

                # Parse JSON envelope
                tool_name, parsed_args = parse_react_output(raw_response)
                if not tool_name:
                    # Failed to parse — nudge
                    rc.messages.append({"role": "user",
                                        "content": f"Could not parse tool call. "
                                        f"Output JSON like: {{\"tool\": \"...\", \"args\": {{...}}}}. "
                                        f"{rc.allowed_tools_hint()}"})
                    return

                parsed_args = parsed_args or {}

                # Validate via harness (reuses existing state machine)
                tool_calls = _to_tool_calls(tool_name, parsed_args)
                ok, err, new_state = validate(rc.state, tool_calls)
                if not ok:
                    rc.messages.append({"role": "user", "content": f"REJECTED: {err}"})
                    rc.ctx.trajectory.append({"role": "tool",
                                              "content": f"REJECTED: {err}"})
                    return

                rc.state = new_state

                # Sync harness state into ctx (like loop.py does)
                rc.ctx.fact_ids = list(getattr(rc.state, "fact_ids", []) or [])
                rc.ctx.fact_satisfies = dict(getattr(rc.state, "fact_satisfies", {}) or {})

                # Dispatch tool (reuses existing _do_* functions)
                try:
                    result_str = await T.dispatch(tool_name, parsed_args, rc.ctx, session)
                except Exception as e:
                    result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

                # Append tool result (as user message in content-only mode)
                rc.messages.append({"role": "user",
                                    "content": f"Tool result ({tool_name}): {result_str}"})
                rc.ctx.trajectory.append({"role": "tool", "name": tool_name,
                                          "content": result_str})

                # Check completion
                if rc.state.state == "DONE":
                    rc.done = True

            # Process all cases concurrently (dispatch is mostly fast except retrieve)
            dispatch_sem = asyncio.Semaphore(16)
            async def process_with_sem(rc, raw):
                async with dispatch_sem:
                    await process_case(rc, raw)

            await asyncio.gather(*[
                process_with_sem(rc, raw) for rc, raw in zip(active, responses)
            ])

            done_count = sum(1 for rc in react_cases if rc.done)
            failed_count = sum(1 for rc in react_cases if rc.failed)
            print(f"  Round {round_num+1} done: {done_count} completed, "
                  f"{failed_count} failed, {total - done_count - failed_count} active",
                  flush=True)

    wall_time = time.perf_counter() - wall_start
    print(f"\n=== {total} cases in {wall_time:.1f}s ({total/wall_time:.1f} cases/s) ===",
          flush=True)

    # Build result dicts (reuse existing _ctx_to_result_dict)
    results = []
    for rc in react_cases:
        if rc.failed or not rc.done:
            # Mark as failed if not done
            if not rc.done:
                rc.failed = True
                rc.failure_reason = f"max_rounds ({max_rounds}) reached at state {rc.state.state}"
        result = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
        result["decomposition_method"] = "react_batch"
        results.append(result)

    # Write results
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results.sort(key=lambda x: x.get("case_num", 0))
    json.dump(results, open(out / "results.json", "w"), indent=2, ensure_ascii=False)

    # Print summary
    _print_summary(results, wall_time)
    return results


def _print_summary(results, wall_time):
    """Print GT/LLM hit + F1 summary (same format as run_agent_mode)."""
    n = len(results)
    gt_hit = sum(1 for r in results if r.get("gt_hit"))
    llm_hit = sum(1 for r in results if r.get("llm_hit"))
    f1 = sum(r.get("llm_f1", 0) for r in results) / n if n else 0
    failed = sum(1 for r in results if r.get("agent_failed"))

    gh = [r for r in results if r.get("gt_hit")]
    n2 = len(gh)
    f1g = sum(r.get("llm_f1", 0) for r in gh) / n2 if n2 else 0
    prec = sum(r.get("llm_precision", 0) for r in gh) / n2 if n2 else 0
    rec = sum(r.get("llm_recall", 0) for r in gh) / n2 if n2 else 0

    print(f"\n{'='*60}")
    print(f"ReAct Batch Results: {n} cases in {wall_time:.1f}s")
    print(f"{'='*60}")
    print(f"GT hit:   {gt_hit}/{n} ({gt_hit/n:.3f})" if n else "GT hit: 0")
    print(f"LLM hit:  {llm_hit}/{n} ({llm_hit/n:.3f})" if n else "LLM hit: 0")
    print(f"Failed:   {failed}")
    print(f"Overall F1:     {f1:.4f}")
    print(f"GT-hit F1:      {f1g:.4f}  (n={n2})")
    print(f"GT-hit Prec:    {prec:.4f}")
    print(f"GT-hit Recall:  {rec:.4f}")


# ---------------------------------------------------------------------------
# Single-case ReAct runner — mirrors loop.run_agent_case's signature but uses
# the CONTENT-ONLY tool: protocol (the format the model was TRAINED on). This
# is the serving path that matches the training data format, unlike
# loop.run_agent_case which uses native tool_calls (which the model never saw
# in training and which drops the model's CoT reasoning).
# ---------------------------------------------------------------------------
async def run_react_case(session: aiohttp.ClientSession, sample: Dict[str, Any],
                         pilot_row: Dict[str, Any], idx: int,
                         args) -> Dict[str, Any]:
    """Run one case through the ReAct content-only loop.

    Each turn: call_llm returns free-form content; parse_react_output extracts
    the ``tool:`` anchor + JSON; harness.validate + tools.dispatch run it.
    Identical parsing to sample_trajectories.py, so training and serving agree.
    """
    from kgqa.llm.client import _call_single_direct

    rc = ReactCase(sample, pilot_row, idx)
    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    # Raise the max_tokens floor when thinking is on (see run_react_batch).
    from kgqa.llm.client import THINKING_TOKEN_BUDGET as _tb
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)

    for _ in range(max_rounds):
        if not rc.is_active:
            break
        # Nudge with the allowed-tools hint (the model needs this since there
        # are no injected tool schemas in content-only mode).
        msgs = list(rc.messages)
        msgs.append({"role": "user", "content": rc.allowed_tools_hint()})

        try:
            # _call_single_direct bypasses the batch coalescer (which deadlocks
            # under per-case async concurrency — it's designed for batch mode).
            raw_response = await _call_single_direct(session, msgs, max_tokens=max_tokens)
        except Exception as e:
            rc.failed = True
            rc.failure_reason = f"call_llm error: {e}"
            break

        if not raw_response or not raw_response.strip():
            rc.messages.append({"role": "assistant", "content": ""})
            rc.messages.append({"role": "user", "content": rc.allowed_tools_hint()})
            continue

        # Append assistant content verbatim (preserves the CoT reasoning).
        rc.messages.append({"role": "assistant", "content": raw_response})
        rc.ctx.trajectory.append({"role": "assistant", "content": raw_response})

        tool_name, parsed_args = parse_react_output(raw_response)
        if not tool_name:
            rc.messages.append({"role": "user",
                                "content": f"Could not parse tool call. "
                                f"Output JSON like: {{\"tool\": \"...\", \"args\": {{...}}}}. "
                                f"{rc.allowed_tools_hint()}"})
            rc.ctx.trajectory.append({"role": "tool", "content": "(unparsed)"})
            continue

        parsed_args = parsed_args or {}
        tool_calls = _to_tool_calls(tool_name, parsed_args)
        ok, err, new_state = validate(rc.state, tool_calls)
        if not ok:
            rc.messages.append({"role": "user", "content": f"REJECTED: {err}"})
            rc.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
            continue
        rc.state = new_state

        rc.ctx.fact_ids = list(getattr(rc.state, "fact_ids", []) or [])
        rc.ctx.fact_satisfies = dict(getattr(rc.state, "fact_satisfies", {}) or {})

        try:
            result_str = await T.dispatch(tool_name, parsed_args, rc.ctx, session)
        except Exception as e:
            result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

        rc.messages.append({"role": "user",
                            "content": f"Tool result ({tool_name}): {result_str}"})
        rc.ctx.trajectory.append({"role": "tool", "name": tool_name,
                                  "content": result_str})

        if rc.state.state == "DONE":
            rc.done = True
            break
    else:
        rc.failed = True
        rc.failure_reason = f"max_iters ({max_rounds}) reached at state {rc.state.state}"

    result = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
    result["decomposition_method"] = "react_single"
    return result
