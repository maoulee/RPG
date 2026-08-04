"""SEQ ReAct loop — the per-fact sequential pipeline (parallel to react_loop).

Copies react_loop's GENERIC turn body (parse → validate → dispatch → append) and
rewires three things only:
  - state machine  → seq_harness (INIT → decompose → RESOLVE_FACT loop → ANSWER)
  - dispatch       → seq_tools (decompose grounds f1; resolve_fact walks one hop +
                     auto-penetrates CVTs + grounds the next fact on real entities)
  - system prompt  → SEQ_AGENTS.md

parse_react_output / _to_tool_calls / _call_single_with_reasoning / build_context /
_ctx_to_result_dict are REUSED from the SAPS code paths unchanged. SAPS react_loop,
harness, tools, AGENTS.md are not touched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

from kgqa.agent.loop import build_context, _ctx_to_result_dict
from kgqa.agent.seq_harness import (
    SeqAgentState, validate as seq_validate, _allowed_hint as seq_allowed_hint,
)
from kgqa.agent import seq_tools as ST
from kgqa.agent.react_loop import parse_react_output, _to_tool_calls  # reuse verbatim

_AGENT_DIR = Path(__file__).resolve().parent


def seq_agents_md() -> str:
    """The SEQ system prefix (loaded once per process)."""
    return (_AGENT_DIR / "SEQ_AGENTS.md").read_text()


class SeqReactCase:
    """One case's evolving state through the SEQ per-fact loop."""

    def __init__(self, sample, pilot_row, idx):
        self.ctx = build_context(sample, pilot_row, idx)
        self.state = SeqAgentState()
        self.messages: List[Dict[str, Any]] = []
        self.failed = False
        self.failure_reason = ""
        self.done = False
        self._empty_answer_retried = False
        self._init_messages()

    def _init_messages(self):
        self.messages = [
            {"role": "system", "content": seq_agents_md()},
            {"role": "user", "content": f"Question: {self.ctx.question}"},
        ]

    @property
    def is_active(self):
        return not self.done and not self.failed

    def allowed_tools_hint(self):
        return seq_allowed_hint(self.state)


async def run_seq_react_case(session: aiohttp.ClientSession, sample: Dict[str, Any],
                             pilot_row: Dict[str, Any], idx: int, args) -> Dict[str, Any]:
    """Run one case through the SEQ per-fact loop (content-only `tool:` protocol).

    Each turn: LLM returns free-form content; parse_react_output extracts the
    `tool:` anchor + JSON; seq_harness.validate + seq_tools.dispatch run it.
    """
    from kgqa.llm.client import _call_single_with_reasoning, THINKING_TOKEN_BUDGET as _tb

    rc = SeqReactCase(sample, pilot_row, idx)
    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)

    for _ in range(max_rounds):
        if not rc.is_active:
            break
        msgs = list(rc.messages)
        msgs.append({"role": "user", "content": rc.allowed_tools_hint()})

        try:
            raw_response, reasoning = await _call_single_with_reasoning(
                session, msgs, max_tokens=max_tokens)
        except Exception as e:
            rc.failed = True
            rc.failure_reason = f"call_llm error: {e}"
            break

        if not raw_response or not raw_response.strip():
            rc.messages.append({"role": "assistant", "content": ""})
            rc.messages.append({"role": "user", "content": rc.allowed_tools_hint()})
            continue

        asst_msg = {"role": "assistant", "content": raw_response}
        if reasoning:
            asst_msg["reasoning"] = reasoning
        rc.messages.append(asst_msg)
        traj_step = {"role": "assistant", "content": raw_response}
        if reasoning:
            traj_step["reasoning"] = reasoning
        rc.ctx.trajectory.append(traj_step)

        tool_name, parsed_args = parse_react_output(raw_response)
        if not tool_name:
            rc.messages.append({"role": "user",
                                "content": f"Could not parse tool call. Output JSON like: "
                                           f"{{\"tool\": \"...\", \"args\": {{...}}}}. "
                                           f"{rc.allowed_tools_hint()}"})
            rc.ctx.trajectory.append({"role": "tool", "content": "(unparsed)"})
            continue

        parsed_args = parsed_args or {}
        ok, err, new_state = seq_validate(rc.state, _to_tool_calls(tool_name, parsed_args))
        if not ok:
            rc.messages.append({"role": "user", "content": f"REJECTED: {err}"})
            rc.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
            continue
        rc.state = new_state

        # sync the decompose projection onto ctx so dispatch sees the fact structure
        rc.ctx.fact_ids = list(rc.state.fact_ids)
        rc.ctx.fact_texts = dict(rc.state.fact_texts)
        rc.ctx._model_anchor = rc.state.anchor or ""
        if tool_name == "decompose":
            # resolve the anchor (entities[0]) → ctx.anchor_idx, used by _do_seq_decompose
            # to ground fact_1. Per-fact anchor selection for later hops happens inside
            # resolve_fact (the model picks anchor_entities each turn).
            from kgqa.agent.loop import _resolve_anchor
            _resolve_anchor(rc.ctx)

        try:
            result_str = await ST.dispatch(tool_name, parsed_args, rc.ctx, session)
        except Exception as e:
            result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

        rc.messages.append({"role": "user",
                            "content": f"Tool result ({tool_name}): {result_str}"})
        rc.ctx.trajectory.append({"role": "tool", "name": tool_name,
                                  "content": result_str})

        if rc.state.state == "DONE":
            ans_entities = (parsed_args.get("entities") if tool_name == "answer" else None) or []
            pool = list(getattr(rc.ctx, "all_candidates", []) or [])
            if (tool_name == "answer" and not ans_entities
                    and not rc._empty_answer_retried and pool):
                rc._empty_answer_retried = True
                rc.state.state = "RETRIEVE"   # roll back so `answer` is legal again
                rc.messages.append({"role": "user", "content":
                    "Your answer was empty — an empty answer scores 0. Pick the entity (or "
                    "entities) MOST likely to answer the question from the evidence you have "
                    f"and call `answer` again. Candidate pool: {pool[:40]}."})
                continue
            rc.done = True
            break
    else:
        rc.failed = True
        rc.failure_reason = f"max_iters ({max_rounds}) reached at state {rc.state.state}"

    result = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
    result["decomposition_method"] = "seq_per_fact"
    return result
