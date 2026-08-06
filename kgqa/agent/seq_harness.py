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


def _parse_subgraphs_decompose(args: dict) -> dict:
    """Parse the subgraphs decompose format (each named entity anchors a subgraph).
    Returns the same structure as _parse_triple_decompose so downstream code is unchanged."""
    subgraphs = args.get("subgraphs") or []
    entities = args.get("entities") or []
    if isinstance(entities, str):
        entities = [e.strip() for e in entities.split(",") if e.strip()]
    answer = str(args.get("answer") or "").strip()

    if not subgraphs:
        return {"error": "decompose must emit `subgraphs` (list of {id, anchor, facts})."}
    if not answer.startswith("?"):
        return {"error": "decompose `answer` must be a ?variable."}

    fact_ids, fact_texts, chains = [], {}, []
    for sg in subgraphs:
        if not isinstance(sg, dict):
            continue
        sg_anchor = str(sg.get("anchor") or "").strip()
        sg_facts = sg.get("facts") or []
        sg_fids = []
        for fact in sg_facts:
            if not isinstance(fact, (list, tuple)) or len(fact) < 3:
                continue
            head, rel, tail = str(fact[0]).strip(), str(fact[1]).strip(), str(fact[2]).strip()
            if not head or not rel:
                continue
            fid = f"f{len(fact_ids) + 1}"
            fact_ids.append(fid)
            fact_texts[fid] = f"({head} | {rel} | {tail})"
            sg_fids.append(fid)
        if sg_fids:
            chains.append({"anchor": sg_anchor, "fact_steps": [[f] for f in sg_fids]})

    if not fact_ids:
        return {"error": "subgraphs contained no valid facts. Each fact: [head, sub-question, tail]."}
    if not entities:
        return {"error": "`entities` is empty. List every named entity.", "entities_missing": True}

    first_anchor = chains[0].get("anchor", "") if chains else ""
    return {"fact_ids": fact_ids, "fact_texts": fact_texts, "chains": chains,
            "anchor": first_anchor, "entities": entities, "answer": answer}


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
            return (False, "Call `decompose` first.", state)
        # parse: subgraphs (new format) or flow (old fallback)
        if "subgraphs" in args:
            tri = _parse_subgraphs_decompose(args)
        else:
            tri = _parse_triple_decompose(args)
        if tri is None:
            return (False, "decompose must emit `subgraphs` (or `flow`) + entities + answer.", state)
        if "error" in tri:
            err = tri["error"]
            if "could not trace" in err:
                err += (" — every named ENTITY must have its own chain TO the answer ?variable. "
                        "If an entity is a CONSTRAINT, declare its chain FROM the constraint TO the answer "
                        "(e.g., [constraint_entity, 'which X are in this place', ?answer]), "
                        "not FROM the answer TO the constraint.")
            return (False, err, state)
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
