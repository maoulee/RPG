"""Tool-call ORDER state machine for the native tool-calling agent.

Enforces the strict sequence:
    INIT  → only `decompose`        (stores facts[])
    RETRIEVE → only `retrieve`      (one fact_id per call; tracks coverage)
    SELECT → only `select`          (exactly once)
    ANSWER → only `answer`          (terminal)

Any out-of-order, skipped, or merged call is REJECTED with a guidance message.
The loop appends that guidance as a `tool` role message and re-prompts the model,
so the model can self-correct without losing the conversation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# State constants
INIT = "INIT"
RETRIEVE = "RETRIEVE"
SELECT_RELATIONS = "SELECT_RELATIONS"
SELECT = "SELECT"
EXPAND = "EXPAND"
ANSWER = "ANSWER"
DONE = "DONE"

# Order, for the "allowed next" hint
_ORDER = [INIT, RETRIEVE, SELECT_RELATIONS, SELECT, EXPAND, ANSWER]


@dataclass
class AgentState:
    """Mutable order-enforcement state for one case."""
    state: str = INIT
    fact_ids: list = field(default_factory=list)       # all fact ids from decompose
    fact_texts: dict = field(default_factory=dict)     # id -> text (for guidance)
    fact_satisfies: dict = field(default_factory=dict)  # id -> constraint text (if fact materializes a condition)
    fact_start_types: dict = field(default_factory=dict)  # id -> start_type (anchor name for f1, type noun for f2+)
    fact_start_entities: dict = field(default_factory=dict)  # id -> start_entity (only for multi-anchor chain roots)
    retrieved: list = field(default_factory=list)      # fact_ids already retrieved
    n_selects: int = 0
    n_decomposes: int = 0
    terminal_answer: Optional[str] = None              # set when answer accepted

    @property
    def pending_facts(self) -> list:
        return [f for f in self.fact_ids if f not in self.retrieved]


def _tool_name(tool_call: dict) -> str:
    """Extract the tool name from either an OpenAI tool_call dict or a plain dict."""
    if not isinstance(tool_call, dict):
        return ""
    fn = tool_call.get("function") or {}
    if isinstance(fn, dict):
        return fn.get("name", "") or tool_call.get("name", "")
    return tool_call.get("name", "")


def _tool_args(tool_call: dict) -> dict:
    """Extract parsed arguments dict from a tool_call."""
    if not isinstance(tool_call, dict):
        return {}
    fn = tool_call.get("function") or {}
    if isinstance(fn, dict):
        raw = fn.get("arguments", {})
    else:
        raw = tool_call.get("arguments", {})
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}
    return raw or {}


def validate(state: AgentState, tool_calls) -> tuple:
    """Validate a batch of tool_calls against the order state machine.

    Returns ``(ok: bool, error_msg: str, new_state: AgentState)``.
    ``new_state`` is the SAME object (mutated in place) when ok, unchanged on
    rejection. The model is expected to emit exactly one tool call per turn in
    this workflow; a multi-call turn is treated as an attempted merge/skip and
    rejected so the model issues them one at a time.

    On rejection, ``error_msg`` is guidance the loop relays to the model.
    """
    calls = tool_calls or []
    if not calls:
        return (False,
                "You emitted no tool call. Call the next tool in order: "
                f"{_allowed_hint(state)}.",
                state)

    if len(calls) > 1:
        names = ", ".join(_tool_name(c) or "?" for c in calls)
        return (False,
                f"You emitted multiple tool calls in one turn ({names}). "
                "Issue ONE tool call per turn, in the required order. "
                f"Next expected: {_allowed_hint(state)}.",
                state)

    call = calls[0]
    name = _tool_name(call)
    args = _tool_args(call)

    # ── expand_branch name/arg normalize (defensive) ──
    # The schema/tool family was pluralized to `expand_branches` (batch), but
    # a model under prompt pressure can still emit the legacy singular form
    # `expand_branch` + `branch_id`. Normalize it here so the rest of validate
    # and dispatch see the canonical plural form — never reject on name shape.
    # (This was the latent bug behind the select-rules 0.80→0.15 regression:
    # harness rejected singular while dispatch accepted it.)
    if name == "expand_branch":
        name = "expand_branches"
        if "branch_id" in args and "branch_ids" not in args:
            bid = args.pop("branch_id")
            args["branch_ids"] = [bid] if isinstance(bid, str) else (bid or [])

    # ── INIT: only decompose ──
    if state.state == INIT:
        if name != "decompose":
            return (False,
                    f"Wrong order: '{name}' called before decompose. "
                    "You MUST call `decompose` first to break the question into facts.",
                    state)
        facts = args.get("facts") or []
        if not isinstance(facts, list) or not facts:
            return (False,
                    "decompose returned no `facts` array. Re-call decompose with a "
                    "non-empty `facts` array (each fact has id, text, relation_hint).",
                    state)
        ids = []
        texts = {}
        satisfies = {}
        start_types = {}
        start_entities = {}
        for f in facts:
            if not isinstance(f, dict):
                continue
            fid = f.get("id") or f.get("fact_id")
            if fid is None:
                continue
            fid = str(fid)
            ids.append(fid)
            texts[fid] = f.get("text", "")
            sat = f.get("satisfies")
            if sat:
                satisfies[fid] = str(sat)
            st = f.get("start_type")
            if st:
                start_types[fid] = str(st)
            se = f.get("start_entity")
            if se:
                start_entities[fid] = str(se)
        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for fid in ids:
            if fid not in seen:
                seen.add(fid)
                unique_ids.append(fid)
        if not unique_ids:
            return (False,
                    "decompose facts had no usable ids. Give each fact a stable "
                    "id like 'f1', 'f2'.",
                    state)
        state.fact_ids = unique_ids
        state.fact_texts = texts
        state.fact_satisfies = satisfies
        state.fact_start_types = start_types
        state.fact_start_entities = start_entities
        state.n_decomposes += 1
        state.state = RETRIEVE
        return (True, "", state)

    # ── RETRIEVE: only retrieve, one fact_id per call ──
    if state.state == RETRIEVE:
        if name != "retrieve":
            return (False,
                    f"Wrong order: '{name}' called during retrieve phase. "
                    f"Still need to retrieve facts: {state.pending_facts or '(none)'}. "
                    "Call `retrieve` for each remaining fact before `select`.",
                    state)
        fid = args.get("fact_id")
        if fid is None:
            return (False,
                    "retrieve missing `fact_id`. Call retrieve with a single fact_id "
                    f"from: {state.pending_facts or state.fact_ids}.",
                    state)
        fid = str(fid)
        if fid not in state.fact_ids:
            return (False,
                    f"retrieve fact_id '{fid}' is unknown. Valid ids: {state.fact_ids}.",
                    state)
        if fid in state.retrieved:
            return (False,
                    f"fact_id '{fid}' already retrieved. Remaining: {state.pending_facts}. "
                    "Do not retrieve the same fact twice.",
                    state)
        # Accept this retrieve
        state.retrieved.append(fid)
        if not state.pending_facts:
            state.state = SELECT_RELATIONS
        return (True, "", state)

    # ── SELECT_RELATIONS: only select_relations, exactly once ──
    if state.state == SELECT_RELATIONS:
        if name != "select_relations":
            return (False,
                    f"Wrong order: '{name}' called before select_relations. "
                    "Call `select_relations` once to pick the relation chain "
                    "from each fact's candidates, then `select`.",
                    state)
        state.state = SELECT
        return (True, "", state)

    # ── SELECT: only select, exactly once ──
    if state.state == SELECT:
        if name != "select":
            return (False,
                    f"Wrong order: '{name}' called before select. "
                    "Call `select` once to materialise the evidence, then `answer`.",
                    state)
        state.n_selects += 1
        state.state = EXPAND
        return (True, "", state)

    # ── EXPAND: expand_branches (batch, 0-N calls) or answer directly ──
    if state.state == EXPAND:
        if name == "expand_branches":
            bids = args.get("branch_ids")
            if not bids:
                return (False,
                        "expand_branches missing `branch_ids`. Pass a list of "
                        "branch numbers from the tree overview, e.g. ['1','2'].",
                        state)
            return (True, "", state)  # accept; loop executes
        if name == "answer":
            state.state = DONE
            return (True, "", state)
        return (False,
                f"Wrong order: '{name}' during expand phase. "
                "Call `expand_branches(['1','2',...])` to see the full evidence "
                "of relevant branches, or `answer` if you have enough evidence.",
                state)

    # ── ANSWER: only answer, terminal ──
    if state.state == ANSWER:
        if name != "answer":
            return (False,
                    f"Wrong order: '{name}' called during answer phase. "
                    "Call `answer` with the entities from the evidence.",
                    state)
        state.state = DONE
        return (True, "", state)

    # Already DONE
    return (False,
            f"Conversation already finished (state={state.state}). "
            "Stop calling tools.",
            state)


def _allowed_hint(state: AgentState) -> str:
    """Human-readable hint of what tool is expected next."""
    if state.state == INIT:
        return "`decompose`"
    if state.state == RETRIEVE:
        pend = state.pending_facts
        return f"`retrieve` for fact_id(s) {pend}" if pend else "`retrieve`"
    if state.state == SELECT:
        return "`select`"
    if state.state == EXPAND:
        return "`expand_branches(['1','2'])` or `answer`"
    if state.state == ANSWER:
        return "`answer`"
    return "(done)"
