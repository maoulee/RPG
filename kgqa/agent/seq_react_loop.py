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

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp

from kgqa.agent.loop import build_context, _ctx_to_result_dict
from kgqa.agent.seq_harness import (
    SeqAgentState, validate as seq_validate, _allowed_hint as seq_allowed_hint,
)
from kgqa.agent import seq_tools as ST
from kgqa.agent.seq_schemas import validate_args
from kgqa.agent.react_loop import parse_react_output, _to_tool_calls  # reuse verbatim

_AGENT_DIR = Path(__file__).resolve().parent

# Model checkpoint declaration: `[fid ✓] ?var = [v1 | v2 | ...]` (| -separated values,
# the same separator as the tree display — avoids comma-in-entity-name collisions).
# Later declarations override earlier ones (a fact may be re-resolved with tighter bindings).
_CKPT_RE = re.compile(r'\[[^\]]*?✓\]\s*(\?\w+)\s*=\s*\[([^\]]*)\]')


def _update_var_bindings(ctx, content: str) -> None:
    """Parse the model's checkpoint declarations and merge into ctx.var_bindings
    (?variable -> bound entity names). The model declares the curated binding for a
    variable after the retrieve_subgraph that resolves it; downstream tool calls that
    reference `?var` are expanded from this map (seq_tools._expand_entities)."""
    if not content:
        return
    vb = getattr(ctx, "var_bindings", None)
    if vb is None:
        ctx.var_bindings = vb = {}
    for m in _CKPT_RE.finditer(content):
        var, vals = m.group(1), m.group(2)
        parts = [p.strip() for p in re.split(r'\s*\|\s*', vals) if p.strip()]
        if parts:
            vb[var] = parts
            # Seed declared bindings into subgraph_entities. The model curated these from
            # a prior retrieve_subgraph (the checkpoint marks the fact resolved); they ARE
            # valid centers. Without seeding, the boundary check rejects bindings that
            # appeared in the dense tree but weren't accumulated into the subgraph set
            # (display/accumulate mismatch) — e.g. ?religion=[Catholicism|...] then
            # retrieve_relations(center:?religion) failed "not in retrieved subgraph".
            # Only seed bindings that resolve to a graph entity (hallucinated names stay out).
            se = getattr(ctx, "subgraph_entities", None)
            if se is not None and getattr(ctx, "ents", None):
                from kgqa.core.utils import normalize as _norm
                n2i = {_norm(e): i for i, e in enumerate(ctx.ents) if e}
                for p in parts:
                    idx = n2i.get(_norm(p))
                    if idx is not None:
                        se.add(idx)


def _parse_flat(content: str):
    """Parse a flat key:value tool-call format (no JSON braces/brackets).
    Each line is 'key: value'. Lists use '|'. Facts use 'head | sub-question | tail'.
    Subgraph fields: 'sgN.anchor: value', 'sgN.fM: head | sub-question | tail'.

    This is inherently more stable than JSON: no brace/bracket matching, each line
    is independent (robust to reasoning-leak corruption — a leaked line doesn't
    break the structure). The model outputs this format; the parser constructs the
    args dict, which is then validated by Pydantic."""
    lines = content.split('\n')
    tool_name = None
    kv: dict = {}
    sg_data: dict = {}   # {sg_id: {'anchor': str, 'facts': list}}

    for line in lines:
        line = line.strip().strip('`').strip()
        if not line or line.startswith('#') or line.startswith('```') or line.startswith('json'):
            continue
        if line.lower().startswith('tool:'):
            tool_name = line.split(':', 1)[1].strip()
            continue
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()

        # subgraph fields: sgN.anchor / sgN.fM
        if '.' in key and key.split('.')[0].lower().startswith('sg'):
            parts = key.split('.', 1)
            sg_id, field = parts[0], parts[1]
            sg = sg_data.setdefault(sg_id, {'anchor': '', 'facts': []})
            if field.lower() == 'anchor':
                sg['anchor'] = val
            elif field.lower().startswith('f'):   # fact: head | sub-question | tail
                fact = [p.strip() for p in val.split('|')]
                if len(fact) >= 3:
                    sg['facts'].append(fact[:3])
            continue

        # regular key:value — list fields accept pipe-separated, JSON-array syntax,
        # or a bare value. JSON-array handling is essential: the base model often
        # writes `center: ["Harvard Art Museum"]` or `entities: []` (JSON syntax)
        # inside the flat format. Without this, the value is stored as the literal
        # string '["Harvard Art Museum"]' (one entity named '["Harvard..."]') and
        # `entities: []` becomes ['[]'] (which the scorer's empty-normalization
        # bug then read as a perfect match for any gold).
        list_keys = ('entities', 'center', 'relations', 'candidates')
        if key.lower() in list_keys:
            if val.startswith('[') and val.endswith(']'):
                try:
                    parsed = json.loads(val)
                    kv[key] = [str(x).strip() for x in parsed if str(x).strip()] \
                        if isinstance(parsed, list) else val
                except json.JSONDecodeError:
                    kv[key] = val
            elif '|' in val:
                kv[key] = [v.strip() for v in val.split('|') if v.strip()]
            else:
                kv[key] = val
        else:
            kv[key] = val

    if not tool_name:
        return None, None

    # construct args dict based on tool_name
    def _as_list(v):
        return v if isinstance(v, list) else ([v] if v else [])

    if tool_name in ('plan', 'decompose'):
        subgraphs = [{'id': sg_id, 'anchor': sg['anchor'], 'facts': sg['facts']}
                     for sg_id, sg in sorted(sg_data.items())]
        return tool_name, {
            'subgraphs': subgraphs,
            'entities': _as_list(kv.get('entities')),
            'answer': kv.get('answer', ''),
        }
    if tool_name == 'retrieve_relations':
        return tool_name, {
            'center': _as_list(kv.get('center')),
            'question': kv.get('question', ''),
        }
    if tool_name == 'retrieve_subgraph':
        return tool_name, {
            'center': _as_list(kv.get('center')),
            'relations': _as_list(kv.get('relations')),
            'sg': kv.get('sg', ''),
        }
    if tool_name == 'answer':
        return tool_name, {'entities': _as_list(kv.get('entities'))}
    return tool_name, kv


def _parse_with_repair(content: str):
    """parse_react_output with conservative JSON repair + multi-tool retry.
    Layered:
      1. strict parse (whole content — parse_react_output does bracket-balance + ?var quoting).
      2. trailing-comma repair (whole content).
      3. multi-tool retry: the model's reasoning may LEAK mid-JSON (vLLM reasoning_end_str
         force-injected at thinking-budget exhaustion), corrupting the first `tool:` segment.
         The model often re-emits a CLEAN `tool:` line after the leak — scan ALL `tool:`
         occurrences, try each segment, return the first that yields a valid tool. This
         eliminates the ~52 decompose rejections caused by the reasoning-leak-on-long-payload.
      4. flat format: no JSON braces — each line is an independent key:value pair.
         Inherently stable (reasoning-leak corrupts one line, not the whole structure).
         The model may output flat format OR corrupted JSON — this catches both.
    SAPS parse_react_output is left untouched."""
    # 1. strict parse (whole content)
    tool, args = parse_react_output(content)
    if tool:
        return tool, args
    # 2. trailing-comma repair
    repaired = re.sub(r',(\s*[}\]])', r'\1', content)
    if repaired != content:
        tool, args = parse_react_output(repaired)
        if tool:
            return tool, args
    # 3. multi-tool retry: reasoning-leak may corrupt the first tool: JSON mid-write;
    #    the model often re-emits a clean version. Try each tool: occurrence.
    for m in re.finditer(r'tool:\s*\{', content):
        segment = content[m.start():]
        tool, args = parse_react_output(segment)
        if tool:
            return tool, args
        seg_repaired = re.sub(r',(\s*[}\]])', r'\1', segment)
        if seg_repaired != segment:
            tool, args = parse_react_output(seg_repaired)
            if tool:
                return tool, args
    # 4. flat format fallback: no JSON — each line is key:value (robust to leaks).
    tool, args = _parse_flat(content)
    if tool:
        return tool, args
    return None, None




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
        # anti-loop: track consecutive identical tool calls so a stuck model (re-issuing
        # the same retrieve_relations/subgraph) is nudged to converge instead of burning
        # the turn budget (root cause of 2209/1864 empty-FAILs).
        self._last_tool_sig = None
        self._tool_repeat = 0
        self._init_messages()

    def loop_nudge(self) -> str:
        tool = self._last_tool_sig[0] if self._last_tool_sig else "the tool"
        return (
            f"⚠ You already called `{tool}` with these EXACT arguments, and the result was already "
            f"returned to you — calling it again returns the same evidence and cannot advance the fact. "
            f"Act on the result you already have: either SELECT a structural relation from the "
            f"candidate_relations and call `retrieve_subgraph`, or declare your variable bindings and "
            f"call `answer`. Do not re-call `{tool}` with the same arguments.")

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

    async def process_turn(self, session, raw_response, reasoning) -> str:
        """Process ONE turn's LLM output: append → bind vars → parse → validate →
        dispatch → record. Shared by the per-call runner (run_seq_react_case) and
        the batch runner (run_seq_react_batch) so both follow identical semantics.

        Returns "done" when the case is complete (answer accepted / failed), else
        "continue". The LLM call itself is the caller's responsibility — this method
        only consumes (raw_response, reasoning)."""
        # empty response — nudge, keep going
        if not raw_response or not raw_response.strip():
            self.messages.append({"role": "assistant", "content": ""})
            self.messages.append({"role": "user", "content": self.allowed_tools_hint()})
            return "continue"

        asst_msg = {"role": "assistant", "content": raw_response}
        if reasoning:
            asst_msg["reasoning"] = reasoning
        self.messages.append(asst_msg)
        traj_step = {"role": "assistant", "content": raw_response}
        if reasoning:
            traj_step["reasoning"] = reasoning
        self.ctx.trajectory.append(traj_step)
        # merge any checkpoint variable-bindings the model just declared, so the
        # dispatch below (and later turns) can expand `?var` in tool `entities`.
        _update_var_bindings(self.ctx, raw_response)

        # quote unquoted ?variables — ONLY for JSON format (flat format breaks if
        # quoted: answer: ?x → answer: "?x" → Pydantic sees '"?x"' not '?x')
        if re.search(r'tool:\s*\{', raw_response):
            raw_response = re.sub(r'(?<=[,\[\s:])\?(\w+)(?=[,\]\s}])', r'"?\1"', raw_response)

        tool_name, parsed_args = _parse_with_repair(raw_response)
        if not tool_name:
            # DIAGNOSTIC: report the SPECIFIC JSON parse error so the model can fix it
            _diag = None
            for m in re.finditer(r'tool:\s*(\{)', raw_response):
                _seg = raw_response[m.start(1):]
                _depth, _end = 0, 0
                for _i, _c in enumerate(_seg):
                    if _c == '{': _depth += 1
                    elif _c == '}': _depth -= 1
                    if _depth == 0 and _i > 0:
                        _end = _i + 1; break
                _candidate = _seg[:_end] if _end else _seg
                try:
                    json.loads(_candidate)
                except json.JSONDecodeError as je:
                    _diag = (f"The `tool:` JSON has a syntax error: {je.msg} at char {je.pos}. "
                             f"Re-emit ONE clean `tool:` line with complete, valid JSON.")
                    break
                except Exception:
                    _diag = "The `tool:` JSON could not be parsed. Re-emit ONE clean `tool:` line."
                    break
            if _diag:
                fmt_nudge = _diag
            elif "CANDIDATES" in raw_response or "ANSWER:" in raw_response:
                fmt_nudge = ("Your content has an answer checklist but no valid `tool:` call was parsed. "
                             "Submit your answer with exactly ONE line:\n"
                             'tool: {"tool": "answer", "args": {"entities": ["..."]}}')
            else:
                fmt_nudge = (f"No `tool:` line found or it has no JSON. Emit ONE line starting with "
                             f"`tool:` followed by valid JSON:\n"
                             f'tool: {{"tool": "...", "args": {{...}}}}\n'
                             f"{self.allowed_tools_hint()}")
            self.messages.append({"role": "user", "content": fmt_nudge})
            self.ctx.trajectory.append({"role": "tool", "content": "(unparsed)"})
            self._last_tool_sig = None; self._tool_repeat = 0   # different action — reset anti-loop
            return "continue"

        parsed_args = parsed_args or {}
        validated_args, schema_err = validate_args(tool_name, parsed_args)
        if schema_err:
            self.messages.append({"role": "user", "content": f"REJECTED: {schema_err}"})
            self.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {schema_err}"})
            self._last_tool_sig = None; self._tool_repeat = 0
            return "continue"
        parsed_args = validated_args
        # anti-loop: consecutive IDENTICAL tool calls
        sig = (tool_name, json.dumps(parsed_args, sort_keys=True, ensure_ascii=False))
        if sig == self._last_tool_sig:
            self._tool_repeat += 1
        else:
            self._last_tool_sig = sig
            self._tool_repeat = 1
        ok, err, new_state = seq_validate(self.state, _to_tool_calls(tool_name, parsed_args))
        if not ok:
            self.messages.append({"role": "user", "content": f"REJECTED: {err}"})
            self.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
            return "continue"
        self.state = new_state

        # sync the decompose projection onto ctx so dispatch sees the fact structure
        self.ctx.fact_ids = list(self.state.fact_ids)
        self.ctx.fact_texts = dict(self.state.fact_texts)
        self.ctx._model_anchor = self.state.anchor or ""
        if tool_name in ("decompose", "plan"):
            from kgqa.agent.loop import _resolve_anchor
            _resolve_anchor(self.ctx)

        try:
            result_str = await ST.dispatch(tool_name, parsed_args, self.ctx, session)
        except Exception as e:
            result_str = json.dumps({"error": f"dispatch_{tool_name}: {e}"})

        self.messages.append({"role": "user",
                              "content": f"Tool result ({tool_name}): {result_str}"})
        self.ctx.trajectory.append({"role": "tool", "name": tool_name,
                                    "content": result_str})

        if self.state.state == "DONE":
            ans_entities = (parsed_args.get("entities") if tool_name == "answer" else None) or []
            pool = list(getattr(self.ctx, "all_candidates", []) or [])
            if (tool_name == "answer" and not ans_entities
                    and not self._empty_answer_retried and pool):
                self._empty_answer_retried = True
                self.state.state = "RETRIEVE"   # roll back so `answer` is legal again
                self.messages.append({"role": "user", "content":
                    "Your answer was empty — an empty answer scores 0. Pick the entity (or "
                    "entities) MOST likely to answer the question from the evidence you have "
                    f"and call `answer` again. Candidate pool: {pool[:40]}."})
                return "continue"
            self.done = True
            return "done"
        return "continue"


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
        hint = rc.allowed_tools_hint()
        if rc._tool_repeat >= 2:  # stuck on the same call — force convergence
            hint = rc.loop_nudge() + "\n" + hint
        msgs.append({"role": "user", "content": hint})

        try:
            raw_response, reasoning = await _call_single_with_reasoning(
                session, msgs, max_tokens=max_tokens)
        except Exception as e:
            rc.failed = True
            rc.failure_reason = f"call_llm error: {e}"
            break

        if await rc.process_turn(session, raw_response, reasoning) == "done":
            break
    else:
        rc.failed = True
        rc.failure_reason = f"max_iters ({max_rounds}) reached at state {rc.state.state}"

    result = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
    result["decomposition_method"] = "seq_per_fact"
    return result


async def run_seq_react_batch(cases_to_run, args):
    """Turn-synchronous SEQ batch runner — the production eval entry.

    Each round every active case advances exactly one turn: all cases' prompts are
    sent in ONE batched LLM call (``batch_call_llm_with_reasoning``, chunked to
    ``batch_chunk``), then each case's ``process_turn`` runs concurrently. This
    replaces the per-call path (``run_seq_react_case``) for evaluation: it is far
    faster (no per-turn HTTP round-trip per case) and avoids the per-call
    connection drops under concurrency that produced empty-answer regressions.

    ``cases_to_run``: list of ``(sample, pilot_row, idx)``. Returns
    ``[(sample, pilot_row, result_dict), ...]`` where result_dict carries
    ``agent_trajectory`` for dumping.
    """
    import time
    from kgqa.llm.client import THINKING_TOKEN_BUDGET as _tb
    from kgqa.llm.batch import batch_call_llm_with_reasoning

    total = len(cases_to_run)
    print(f"\n=== SEQ batch mode: {total} cases ===", flush=True)
    wall_start = time.perf_counter()

    react_cases = [SeqReactCase(s, pr, idx) for s, pr, idx in cases_to_run]
    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)
    batch_chunk = int(getattr(args, "batch_chunk", 25))

    async with aiohttp.ClientSession() as session:
        for round_num in range(max_rounds):
            active = [rc for rc in react_cases if rc.is_active]
            if not active:
                break

            # build prompts (append allowed-tools hint + anti-loop nudge) — mirrors
            # the per-call runner's prompt assembly exactly.
            prompts = []
            for rc in active:
                hint = rc.allowed_tools_hint()
                if rc._tool_repeat >= 2:
                    hint = rc.loop_nudge() + "\n" + hint
                msgs = list(rc.messages)
                msgs.append({"role": "user", "content": hint})
                prompts.append(msgs)

            # batched LLM call (chunked — batch endpoint scales poorly past ~25)
            try:
                if len(prompts) <= batch_chunk:
                    contents, reasoning = await batch_call_llm_with_reasoning(
                        session, prompts, max_tokens=max_tokens)
                    chunk_results = [(contents, reasoning)]
                else:
                    chunks = [prompts[i:i + batch_chunk]
                              for i in range(0, len(prompts), batch_chunk)]

                    async def _b(chunk):
                        return await batch_call_llm_with_reasoning(
                            session, chunk, max_tokens=max_tokens)
                    chunk_results = await asyncio.gather(*[_b(c) for c in chunks])
            except Exception as e:
                print(f"  batch call failed: {e}", flush=True)
                for rc in active:
                    rc.failed = True
                    rc.failure_reason = f"batch_call error: {e}"
                break

            responses, responses_reasoning = [], []
            for cr_c, cr_r in chunk_results:
                responses.extend(cr_c)
                responses_reasoning.extend(cr_r)

            # process each case concurrently (dispatch is cheap except retrieve_*,
            # which is bounded in-process)
            dispatch_sem = asyncio.Semaphore(16)

            async def _proc(rc, raw, rsn):
                async with dispatch_sem:
                    if not raw:
                        # batch endpoint returns None on a per-prompt failure — treat
                        # like the per-call empty-response path: nudge and keep going.
                        rc.messages.append({"role": "assistant", "content": ""})
                        rc.messages.append(
                            {"role": "user", "content": rc.allowed_tools_hint()})
                        return
                    await rc.process_turn(session, raw, rsn)

            await asyncio.gather(*[_proc(rc, raw, rsn)
                                   for rc, raw, rsn in
                                   zip(active, responses, responses_reasoning)])

            done = sum(1 for rc in react_cases if rc.done)
            failed = sum(1 for rc in react_cases if rc.failed)
            print(f"  round {round_num + 1}: {len(active)} active → "
                  f"done={done} failed={failed}", flush=True)

    dt = time.perf_counter() - wall_start
    print(f"SEQ batch done: {total} cases in {dt:.0f}s ({dt / total:.1f}s/case)", flush=True)

    results: List[Tuple[Any, Any, Dict[str, Any]]] = []
    for (s, pr, idx), rc in zip(cases_to_run, react_cases):
        r = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
        r["decomposition_method"] = "seq_per_fact"
        r["agent_trajectory"] = rc.ctx.trajectory
        results.append((s, pr, r))
    return results
