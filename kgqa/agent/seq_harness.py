"""SEQ harness — boundary-only state machine for iterative subgraph retrieval.

States: INIT → decompose → RETRIEVE → DONE (answer accepted).

The harness enforces ONLY boundaries — it never decides which relation, which center
entity, or when to answer. Those are the model's job. The boundaries:
  - order:  decompose first; answer last.
  - to-do:  track declared facts vs retrieved facts → progress hint + answer guard.
  - answer guard: if the model answers before every declared fact is retrieved, it is
            reminded ONCE (rejected with the missing list); a second answer is accepted.

The DATA boundary (next center ∈ accumulated subgraph) is enforced in the tool
(seq_tools.retrieve_subgraph), not here, because it needs ctx.

SAPS baseline (react_loop / harness.py / tools.py) is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from kgqa.agent.harness import _tool_name, _tool_args, _parse_triple_decompose

INIT = "INIT"
RETRIEVE = "RETRIEVE"   # retrieve_relations / retrieve_subgraph / answer
DONE = "DONE"


@dataclass
class SeqAgentState:
    state: str = INIT

    # decompose projection
    fact_ids: list = field(default_factory=list)        # declared fact ids, in flow order
    fact_texts: dict = field(default_factory=dict)
    chains: list = field(default_factory=list)
    anchor: Optional[str] = None
    entities: list = field(default_factory=list)

    # to-do / answer guard
    retrieved_fids: list = field(default_factory=list)  # fact ids retrieved (when the model passes fact_id)
    n_subgraphs: int = 0                                # retrieve_subgraph call count (robust fallback)
    reminded: bool = False                              # early-answer reminder fired once
    n_decomposes: int = 0

    @property
    def n_done(self) -> int:
        # count by fact_id when available, else by retrieve_subgraph calls
        return max(len(self.retrieved_fids), self.n_subgraphs)

    @property
    def all_retrieved(self) -> bool:
        return bool(self.fact_ids) and self.n_done >= len(self.fact_ids)


def _todo(state: SeqAgentState) -> str:
    done = set(state.retrieved_fids)
    marks = " ".join(f"{'✓' if f in done else '⬜'}{f}" for f in state.fact_ids) or "(no facts)"
    return f"{marks}  (retrieved {state.n_done}/{len(state.fact_ids)})"


def _allowed_hint(state: SeqAgentState) -> str:
    if state.state == INIT:
        return "`decompose`"
    if state.state == RETRIEVE:
        todo = _todo(state)
        if state.all_retrieved:
            return (f"`retrieve_relations`/`retrieve_subgraph` (extra probes on seen entities) "
                    f"or `answer`. facts: {todo}")
        return (f"`retrieve_relations` then `retrieve_subgraph` for the next fact, or `answer`. "
                f"facts: {todo}")
    return "(done)"


def validate(state: SeqAgentState, tool_calls) -> tuple:
    """One tool per turn. Returns (ok, err_msg, new_state)."""
    if not tool_calls:
        return (False, "No tool call. " + _allowed_hint(state), state)
    if len(tool_calls) > 1:
        return (False, "ONE tool call per turn. " + _allowed_hint(state), state)

    name = _tool_name(tool_calls[0])
    args = _tool_args(tool_calls[0]) or {}

    # ── INIT: only decompose ──
    if state.state == INIT:
        if name != "decompose":
            return (False, "Call `decompose` first to emit FLOW + entities + answer.", state)
        tri = _parse_triple_decompose(args)
        if tri is None:
            return (False, "decompose must emit the TRIPLE format: args.flow, args.entities, args.answer.", state)
        if "error" in tri:
            return (False, tri["error"], state)
        if tri.get("entities_missing") and state.n_decomposes == 0:
            state.n_decomposes += 1
            return (False, "decompose `entities` is empty. List EVERY named entity in the question.", state)
        state.fact_ids = tri["fact_ids"]
        state.fact_texts = tri["fact_texts"]
        state.chains = tri["chains"]
        state.anchor = tri["anchor"]
        state.entities = tri.get("entities") or []
        state.n_decomposes += 1
        state.state = RETRIEVE
        return (True, "", state)

    # ── RETRIEVE: retrieve_relations / retrieve_subgraph / answer ──
    if state.state == RETRIEVE:
        if name == "retrieve_relations":
            return (True, "", state)                       # no state change
        if name == "retrieve_subgraph":
            state.n_subgraphs += 1
            fid = str(args.get("fact_id") or args.get("step") or "")
            if fid and fid not in state.retrieved_fids:
                state.retrieved_fids.append(fid)
            return (True, "", state)
        if name == "answer":
            if not state.all_retrieved and not state.reminded:
                state.reminded = True
                missing = [f for f in state.fact_ids if f not in state.retrieved_fids]
                return (False, (f"You answered before retrieving every declared fact "
                                f"(missing: {missing}). Retrieve them first — or call `answer` "
                                f"again if you are certain the missing facts are unanswerable."), state)
            state.state = DONE
            return (True, "", state)
        return (False, "During retrieve: call `retrieve_relations`, `retrieve_subgraph`, or `answer`. "
                       + _allowed_hint(state), state)

    return (False, f"Conversation finished (state={state.state}).", state)
