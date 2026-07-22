"""Tool-call ORDER state machine for the agent.

Enforces the strict sequence:
    INIT  → only `decompose`        (stores facts[], anchor, endpoints; runs GTE)
    RETRIEVE → optional `retrieve`  (fallback to re-fetch a fact's candidates)
    SELECT_RELATIONS → only `select_relations`  (picks relations + traverses)
    EXPAND → `expand_branches` (0-N) or `answer`
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
RETRIEVE = "RETRIEVE"          # optional fallback (re-retrieve with new hint)
SELECT_RELATIONS = "SELECT_RELATIONS"  # select relations + traverse (merged)
EXPAND = "EXPAND"
ANSWER = "ANSWER"
DONE = "DONE"

# Order, for the "allowed next" hint
_ORDER = [INIT, RETRIEVE, SELECT_RELATIONS, EXPAND, ANSWER]

# Safety-net caps on model-driven rewrites. The MODEL decides when a choice was
# wrong and re-submits; these only intercept abuse (the system is a guardrail,
# not a decision-maker). Tool-internal errors (structural pruning, traversal
# reach) are fixed in the tool, NOT compensated by rewrites.
MAX_SELECTS = 2   # select_relations: 1 original + 1 model-driven rewrite
MAX_EXPANDS = 6   # expand_branches: loop-guard against meaningless repeated expands
# retrieve: 1 rewrite per fact (tracked per-fact in state.retrieved)


@dataclass
class AgentState:
    """Mutable order-enforcement state for one case."""
    state: str = INIT
    fact_ids: list = field(default_factory=list)       # all fact ids from decompose
    fact_texts: dict = field(default_factory=dict)     # id -> text (for guidance)
    fact_satisfies: dict = field(default_factory=dict)  # id -> constraint text (if fact materializes a condition)
    fact_start_types: dict = field(default_factory=dict)  # id -> start_type (anchor name for f1, type noun for f2+)
    fact_start_entities: dict = field(default_factory=dict)  # id -> start_entity (only for multi-anchor chain roots)
    fact_steps: list = field(default_factory=list)      # ordered step groups (each=[fid] seq, or [fid,...] a `con` conjunctive layer)
    chains: list = field(default_factory=list)          # parsed question_chains: [{anchor (name), fact_steps ([groups])}, ...]; one entry per independent anchor (multi-anchor). Single-chain = 1 entry.
    anchor: Optional[str] = None                       # model-chosen anchor entity name
    endpoints: list = field(default_factory=list)      # model-chosen endpoint entity names (constraints)
    retrieved: list = field(default_factory=list)      # fact_ids already retrieved (via fallback retrieve)
    n_selects: int = 0
    n_expands: int = 0
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
                    "non-empty `facts` array (each fact has id, text, subquestion).",
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
        # Parse question_chains[].steps into ordered step groups. facts ARE the
        # sub-question decomposition; chains only organize them (multi-question /
        # conjunctive). Each step element is a fact id (a sequential step) or
        # {"con":[ids]} (conjunctive: those facts constrain the SAME entity, so
        # their relations are unioned at one layer, not chained). OMIT
        # question_chains for a single sequential question → facts in order are
        # the implicit chain. Every fact referenced in a step MUST be declared
        # in facts[] — a dangling reference (the old qs↔facts divergence bug,
        # where the model planned a chain in `qs` but emitted fewer facts) is
        # rejected so the model re-emits a coherent decomposition.
        declared = set(unique_ids)
        chains_raw = args.get("question_chains") or []

        def _parse_steps(steps):
            # Parse one chain's steps into ordered groups. Each element is a
            # fact id (sequential step -> [fid]) or {"con":[ids]} (conjunctive:
            # those facts constrain the SAME entity, relations unioned at one
            # layer, not chained -> [fid,...]). Returns (groups, err).
            groups = []
            for el in (steps or []):
                if isinstance(el, str):
                    fid = el.strip()
                    if not fid:
                        continue
                    if fid not in declared:
                        return None, (f"step references fact '{fid}' but it is not "
                                      "declared in facts[]. Declare it or fix the reference.")
                    groups.append([fid])
                elif isinstance(el, dict):
                    con_ids = el.get("con") or []
                    if isinstance(con_ids, str):
                        con_ids = [con_ids]
                    grp = []
                    for fid in con_ids:
                        fid = str(fid).strip()
                        if not fid:
                            continue
                        if fid not in declared:
                            return None, (f"con group references fact '{fid}' but it "
                                          "is not declared in facts[]. Declare it or fix the reference.")
                        grp.append(fid)
                    if grp:
                        groups.append(grp)
            return groups, None

        # Parse ALL chains (multi-anchor: each entry = one independent subgraph
        # retrieval with its own anchor). Previously only chains[0] was parsed,
        # silently dropping multi-anchor chains.
        parsed_chains = []
        if isinstance(chains_raw, list) and chains_raw and isinstance(chains_raw[0], dict):
            for ch in chains_raw:
                ch_anchor = str(ch.get("anchor") or "").strip()
                groups, err = _parse_steps(ch.get("steps") or [])
                if err:
                    return (False, err, state)
                if groups:
                    parsed_chains.append({"anchor": ch_anchor, "fact_steps": groups})
        if not parsed_chains:
            # No question_chains (or empty steps) → single implicit chain, facts
            # in order are the sequential chain.
            parsed_chains = [{"anchor": "", "fact_steps": [[f] for f in unique_ids]}]
        state.fact_start_types = start_types
        state.fact_start_entities = start_entities
        state.chains = parsed_chains
        # Backward compat: fact_steps = first chain's steps (single-chain path).
        state.fact_steps = parsed_chains[0]["fact_steps"]
        # Model-chosen anchor and endpoints (LLM ambiguity analysis). The
        # system resolves these to graph idx in loop.py after validate().
        state.anchor = args.get("anchor") or chain0.get("anchor")
        eps = args.get("endpoints")
        state.endpoints = list(eps) if isinstance(eps, list) else ([eps] if eps else [])
        state.n_decomposes += 1
        # decompose now includes GTE candidates inline → skip RETRIEVE, go
        # straight to SELECT_RELATIONS. (retrieve remains available as a
        # fallback via the RETRIEVE state if the model re-enters it.)
        state.state = SELECT_RELATIONS
        return (True, "", state)

    # ── RETRIEVE: optional fallback (re-retrieve with a new hint) ──
    # Only reached if the model explicitly calls retrieve after decompose
    # (e.g. GTE candidates were structurally pruned to empty and the model
    # wants to retry with a different subquestion). In the normal flow,
    # decompose already returns GTE candidates and this state is skipped.
    if state.state == RETRIEVE:
        if name == "select_relations":
            state.state = EXPAND
            return (True, "", state)
        if name != "retrieve":
            return (False,
                    f"Wrong order: '{name}' during retrieve fallback. "
                    "Call `retrieve` to re-fetch a fact's candidates with a new "
                    "hint, or `select_relations` to proceed.",
                    state)
        fid = str(args.get("fact_id", ""))
        if not fid or fid not in state.fact_ids:
            return (False,
                    f"retrieve fact_id '{fid}' is unknown. Valid ids: {state.fact_ids}.",
                    state)
        if fid in state.retrieved:
            return (False,
                    f"retrieve limit reached for fact '{fid}' (1 rewrite per fact). "
                    "Proceed to `select_relations` with the current candidates, or "
                    "revise a different fact.",
                    state)
        state.retrieved.append(fid)
        return (True, "", state)

    # ── SELECT_RELATIONS: select relations + traverse (merged) ──
    # select_relations now ALSO runs the graph traversal (formerly the
    # separate `select` tool) and returns the evidence tree inline. So
    # after select_relations the model goes straight to EXPAND.
    if state.state == SELECT_RELATIONS:
        if name == "retrieve":
            # Allow retrieve as a fallback even here (1 rewrite per fact)
            fid = str(args.get("fact_id", ""))
            if not fid or fid not in state.fact_ids:
                return (False,
                        f"retrieve fact_id '{fid}' is unknown. Valid ids: {state.fact_ids}.",
                        state)
            if fid in state.retrieved:
                return (False,
                        f"retrieve limit reached for fact '{fid}' (1 rewrite per fact). "
                        "Proceed with `select_relations`.",
                        state)
            state.retrieved.append(fid)
            return (True, "", state)
        if name != "select_relations":
            return (False,
                    f"Wrong order: '{name}' called before select_relations. "
                    "Call `select_relations` once to pick the relation chain "
                    "from each fact's candidates. The system will traverse "
                    "automatically and return the evidence tree.",
                    state)
        # select_relations now also runs traverse → go straight to EXPAND
        state.n_selects += 1
        state.state = EXPAND
        return (True, "", state)

    # ── EXPAND: expand_branches (batch, 0-N calls), 1 backward select rewrite, or answer ──
    if state.state == EXPAND:
        # Backward rewrite: model may re-issue select_relations ONCE if it judges
        # the traversal overview wrong (safety-net cap; the MODEL decides when).
        # Dispatch re-runs the traverse and returns a fresh overview; stay in EXPAND.
        if name == "select_relations":
            if state.n_selects < MAX_SELECTS:
                state.n_selects += 1
                return (True, "", state)
            return (False,
                    "select_relations rewrite limit reached (1 rewrite). Work "
                    "with the current evidence: call `expand_branches` or `answer`.",
                    state)
        if name == "expand_branches":
            bids = args.get("branch_ids")
            if not bids:
                return (False,
                        "expand_branches missing `branch_ids`. Pass a list of "
                        "branch numbers from the tree overview, e.g. ['1','2'].",
                        state)
            state.n_expands += 1
            if state.n_expands > MAX_EXPANDS:
                return (False,
                        f"expand_branches loop limit reached ({MAX_EXPANDS} calls). "
                        "Stop expanding and call `answer` with the best evidence so far.",
                        state)
            return (True, "", state)  # accept; loop executes
        if name == "answer":
            state.state = DONE
            return (True, "", state)
        return (False,
                f"Wrong order: '{name}' during expand phase. "
                "Call `expand_branches(['1','2',...])`, re-issue `select_relations` "
                "(once, if the overview looks wrong), or `answer`.",
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
        return "`retrieve` (fallback) or `select_relations`"
    if state.state == SELECT_RELATIONS:
        return "`select_relations` (picks relations + traverses the graph)"
    if state.state == EXPAND:
        return "`expand_branches(['1','2'])`, `select_relations` (1 rewrite if the overview is wrong), or `answer`"
    if state.state == ANSWER:
        return "`answer`"
    return "(done)"
