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
    entities_raw = args.get("entities")
    entities = entities_raw or []
    if isinstance(entities, str):
        entities = [e.strip() for e in entities.split(",") if e.strip()]
    answer = str(args.get("answer") or "").strip()

    if not subgraphs:
        return {"error": "plan must emit `subgraphs` (list of {id, anchor, facts})."}
    if not answer.startswith("?"):
        # internal repair: the answer field may be missing due to partial JSON parse
        # (reasoning-leak truncation). Infer from the last subgraph's last fact's tail.
        for sg in reversed(subgraphs):
            if isinstance(sg, dict):
                for fact in reversed(sg.get("facts") or []):
                    if isinstance(fact, (list, tuple)) and len(fact) >= 3:
                        tail = str(fact[-1]).strip()
                        if tail.startswith("?"):
                            answer = tail
                            break
                if answer.startswith("?"):
                    break
        if not answer.startswith("?"):
            return {"error": ("plan `answer` must be a ?variable (e.g. '?answer'). The answer "
                              "field was missing — if your JSON was truncated mid-write, re-emit "
                              "the plan as ONE complete `tool:` line with the full JSON.")}

    fact_ids, fact_texts, chains = [], {}, []
    sg_info = {}   # {sg_id → n_facts} for per-fact budget tracking
    for sg in subgraphs:
        if not isinstance(sg, dict):
            continue
        sg_id = str(sg.get("id") or f"sg{len(sg_info) + 1}")
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
            sg_info[sg_id] = len(sg_fids)

    if not fact_ids:
        return {"error": "subgraphs contained no valid facts. Each fact: [head, sub-question, tail]."}
    if not entities:
        if entities_raw is None:
            return {"error": ("The `entities` field was not found in the parsed JSON — the plan JSON "
                              "may have been partially parsed (truncated/corrupted). Re-emit the plan "
                              "as ONE complete `tool:` line with valid JSON including the `entities` list."),
                    "entities_missing": True}
        return {"error": "`entities` is empty. List every named entity in the question.", "entities_missing": True}

    first_anchor = chains[0].get("anchor", "") if chains else ""
    return {"fact_ids": fact_ids, "fact_texts": fact_texts, "chains": chains,
            "anchor": first_anchor, "entities": entities, "answer": answer,
            "sg_info": sg_info}


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

    # subgraph tracking (SEQ redesign — per-fact budget + deviation detection)
    sg_plan: dict = field(default_factory=dict)    # {sg_id → n_facts} from decompose
    sg_calls: dict = field(default_factory=dict)   # {sg_id → retrieve_subgraph call count}
    sg_done: set = field(default_factory=set)      # resolved/failed sg_ids

    def sg_budget(self, sg_id: str) -> int:
        """Max retrieve calls for this subgraph = 3 × n_facts (1 relations + 1 subgraph + 1 repair per fact)."""
        return 3 * self.sg_plan.get(sg_id, 1)

    @property
    def n_done(self) -> int:
        # count by fact_id when available, else by retrieve_subgraph calls
        return max(len(self.retrieved_fids), self.n_subgraphs)

    @property
    def all_retrieved(self) -> bool:
        # sg-based: all declared subgraphs resolved or failed — ONLY when sg_done is
        # fully populated (i.e., every sg was either completed or budget-intercepted).
        # Otherwise fall back to the call-count method (normal completion doesn't
        # explicitly mark sg_done — the model just moves on or answers).
        if self.sg_plan and len(self.sg_done) >= len(self.sg_plan):
            return all(sg in self.sg_done for sg in self.sg_plan)
        # fallback: call-count method
        return bool(self.fact_ids) and self.n_done >= len(self.fact_ids)


def _todo(state: SeqAgentState) -> str:
    done = set(state.retrieved_fids)
    marks = " ".join(f"{'✓' if f in done else '⬜'}{f}" for f in state.fact_ids) or "(no facts)"
    return f"{marks}  (retrieved {state.n_done}/{len(state.fact_ids)})"


def _allowed_hint(state: SeqAgentState) -> str:
    if state.state == INIT:
        return "`plan` (or `decompose`)"
    if state.state == RETRIEVE:
        todo = _todo(state)
        if state.all_retrieved:
            return (f"`retrieve_relations`/`retrieve_subgraph` (extra probes on seen entities) "
                    f"or `answer`. facts: {todo}")
        return (f"WORKFLOW ORDER per fact: `retrieve_relations` FIRST (returns candidate "
                f"relations), THEN `retrieve_subgraph` with the relations you picked. You CANNOT "
                f"call `retrieve_subgraph` before `retrieve_relations` — it has no relations to "
                f"walk. Next action: `retrieve_relations` for the next unresolved fact, or "
                f"`answer`. facts: {todo}")
    return "(done)"


def validate(state: SeqAgentState, tool_calls) -> tuple:
    """One tool per turn. Returns (ok, err_msg, new_state)."""
    if not tool_calls:
        return (False, "No tool call. " + _allowed_hint(state), state)
    if len(tool_calls) > 1:
        return (False, "ONE tool call per turn. " + _allowed_hint(state), state)

    name = _tool_name(tool_calls[0])
    args = _tool_args(tool_calls[0]) or {}

    # ── INIT: only decompose/plan ──
    if state.state == INIT:
        if name not in ("decompose", "plan"):
            return (False, "Call `plan` (or `decompose`) first.", state)
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
        state.sg_plan = tri.get("sg_info", {})       # {sg_id → n_facts} for per-fact budget
        state.n_decomposes += 1
        state.state = RETRIEVE
        return (True, "", state)

    # ── RETRIEVE: retrieve_relations / retrieve_subgraph / answer ──
    if state.state == RETRIEVE:
        if name == "retrieve_relations":
            return (True, "", state)                       # no state change
        if name == "retrieve_subgraph":
            state.n_subgraphs += 1
            sg = str(args.get("sg") or args.get("fact_id") or args.get("step") or "")
            if sg and sg not in state.retrieved_fids:
                state.retrieved_fids.append(sg)
            # per-fact budget deviation detection: each sg gets 3 × n_facts retrieve calls
            if sg and sg in state.sg_plan:
                state.sg_calls[sg] = state.sg_calls.get(sg, 0) + 1
                budget = state.sg_budget(sg)
                if state.sg_calls[sg] > budget:
                    state.sg_done.add(sg)
                    return (False, (f"Subgraph {sg} used {state.sg_calls[sg]} retrieval calls "
                                   f"(budget {budget} = 3×{state.sg_plan[sg]} facts). It appears stuck. "
                                   f"Mark {sg} done and proceed to the next subgraph, or answer from current evidence."),
                            state)
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
        return (False, "Wrong tool in the retrieve phase — and note the WORKFLOW ORDER: "
                       "`retrieve_relations` must come BEFORE `retrieve_subgraph` for each fact. "
                       + _allowed_hint(state), state)

    return (False, f"Conversation finished (state={state.state}).", state)
