#!/usr/bin/env python3
"""COMMIT-WIDENING pack (2026-08-22) — unit simulation + structural smoke.

Covers the 8-item pack that widens the EVIDENCE COMMIT trigger from
`state.all_retrieved` to the READY predicate:
  * ready_to_commit truth table (all-closed / tail==ans / head==ans overshoot /
    shared-covers alias escape / irrelevant-open / unbound / SEQ_WIDE_COMMIT fuse)
  * fact_key_map three-namespace normalization (f1 / sg1 / sg1.f2)
  * closures (✗) counting into completion
  * loop mechanics: STAGE GATE intercept, repeat rejection, purity detector
    reachability (the historical dead-code regression), pre-gate commit on an
    answer-on-READY turn, EXTEND flag reset, RESTART flag reset,
    early-answer reminder limited to blocking facts / silent when READY,
    guessed answer var emits no SUPPORT matrix.

GPU-free: ST.dispatch is faked; no LLM, no GTE.

Run: /root/miniconda3/envs/qwen35/bin/python -m pytest tests/test_commit_widening.py -v
"""
import ast
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from kgqa.agent import seq_react_loop as L
from kgqa.agent.seq_harness import (
    SeqAgentState, _parse_subgraphs_decompose, blocking_facts, commit_due,
    norm_fact_key, ready_to_commit, validate,
)

# ── fixtures ────────────────────────────────────────────────────────────────

# Plan A: f1 tail==?founder (answer), f2 head==?founder (discriminator walk),
# f3 irrelevant (own requirement R3). R4 left UNPLANNED for the EXTEND test.
PLAN_A = {
    "subgraphs": [
        {"id": "sg1", "anchor": "OrgAlpha", "covers": {"f1": "R1", "f2": "R2"},
         "facts": [["OrgAlpha", "who founded this organization", "?founder"],
                   ["?founder", "which country is this person in", "?country"]]},
        {"id": "sg2", "anchor": "OrgAlpha", "covers": {"f1": "R3"},
         "facts": [["OrgAlpha", "headquarters city", "?city"]]},
    ],
    "entities": ["OrgAlpha"], "answer": "?founder", "answer_type": "person",
    "requirements": {"R1": {"kind": "structural", "text": "founder of the org"},
                     "R2": {"kind": "filter", "text": "country of the founder"},
                     "R3": {"kind": "structural", "text": "headquarters city"},
                     "R4": {"kind": "structural", "text": "airport near the org"}},
}

# Plan B (multi-anchor): f2 tail==ans from a second anchor, f3 shares R2 with
# f2 (alias escape), f4 head==ans (overshoot), f5 fully irrelevant.
PLAN_B = {
    "subgraphs": [
        {"id": "sg1", "anchor": "OrgAlpha", "covers": {"f1": "R1"},
         "facts": [["OrgAlpha", "founded by", "?founder"]]},
        {"id": "sg2", "anchor": "Nijmegen", "covers": {"f1": "R2", "f2": "R2"},
         "facts": [["Nijmegen", "airport serving this city", "?founder"],
                   ["Nijmegen", "which country contains it", "?country"]]},
        {"id": "sg3", "anchor": "OrgAlpha", "covers": {"f1": "R3"},
         "facts": [["?founder", "birth year", "?year"]]},
        {"id": "sg4", "anchor": "OrgAlpha", "covers": {"f1": "R4"},
         "facts": [["OrgAlpha", "current CEO", "?ceo"]]},
    ],
    "entities": ["OrgAlpha", "Nijmegen"], "answer": "?founder", "answer_type": "person",
    "requirements": {"R1": {"kind": "structural", "text": "founder"},
                     "R2": {"kind": "structural", "text": "airport city"},
                     "R3": {"kind": "filter", "text": "birth year"},
                     "R4": {"kind": "filter", "text": "ceo"}},
}


def build_state(plan: dict) -> SeqAgentState:
    tri = _parse_subgraphs_decompose(plan)
    assert "error" not in tri, tri.get("error")
    st = SeqAgentState()
    st.fact_ids = tri["fact_ids"]
    st.fact_texts = tri["fact_texts"]
    st.chains = tri["chains"]
    st.requirements = tri["requirements"]
    st.fact_covers = tri["fact_covers"]
    st.anchor = tri["anchor"]
    st.entities = tri["entities"]
    st.sg_plan = tri["sg_info"]
    st.sg_facts = tri["sg_facts"]
    st.fact_key_map = tri["fact_key_map"]
    st.fact_edges = tri["fact_edges"]
    st.answer_var = tri["answer_var"]
    st.state = "RETRIEVE"
    return st


def plan_a() -> SeqAgentState:
    return build_state(PLAN_A)


def plan_b() -> SeqAgentState:
    return build_state(PLAN_B)


# ── ready_to_commit truth table ─────────────────────────────────────────────

def test_ready_all_closed_true():
    st = plan_b()
    st.retrieved_fids = ["f1", "f2", "f4"]
    st.closed_fids = {"f3"}            # closure counts as done
    st.declared_fids = {"f5"}
    assert ready_to_commit(st, {}, {"f1": ["Alice"]}, {}) is True


def test_ready_open_tail_eq_answer_false():
    # answer bound via f1, but f2 (second anchor) still open with tail==?founder
    st = plan_b()
    st.retrieved_fids = ["f1"]
    st.closed_fids = {"f3", "f4", "f5"}    # isolate: only f2 open
    fb = {"sg1.f1": ["Alice"]}
    assert ready_to_commit(st, {}, fb, {}) is False
    assert blocking_facts(st, {}, fb, {}) == ["f2"]


def test_ready_open_head_eq_answer_false():
    # overshoot guard: f4 (head==?founder discriminator walk) still open
    st = plan_b()
    st.retrieved_fids = ["f1", "f2"]
    st.closed_fids = {"f3"}
    st.declared_fids = {"f5"}
    fb = {"sg1.f1": ["Alice"]}
    assert ready_to_commit(st, {}, fb, {}) is False
    assert blocking_facts(st, {}, fb, {}) == ["f4"]


def test_ready_shared_covers_alias_escape_false():
    # f3 tail==?country but shares R2 with f2 (a tail==?founder fact): completing
    # it can still eliminate candidates — must block
    st = plan_b()
    st.retrieved_fids = ["f1", "f2", "f4"]
    st.declared_fids = {"f5"}
    fb = {"sg1.f1": ["Alice"]}
    assert ready_to_commit(st, {}, fb, {}) is False
    assert blocking_facts(st, {}, fb, {}) == ["f3"]


def test_ready_only_irrelevant_open_true():
    st = plan_b()
    st.retrieved_fids = ["f1", "f2", "f3", "f4"]
    fb = {"sg1.f1": ["Alice"]}
    assert ready_to_commit(st, {}, fb, {}) is True
    assert blocking_facts(st, {}, fb, {}) == []


def test_ready_irrelevant_open_plan_a_true():
    st = plan_a()
    st.retrieved_fids = ["f1", "f2"]
    fb = {"sg1.f1": ["Alice"]}
    assert ready_to_commit(st, {}, fb, {}) is True


def test_ready_answer_unbound_false():
    st = plan_b()
    st.retrieved_fids = ["f1", "f2"]
    assert ready_to_commit(st, {}, {}, {}) is False
    # unbound ⇒ every open fact is listed as blocking
    assert set(blocking_facts(st, {}, {}, {})) == {"f3", "f4", "f5"}


def test_ready_join_binding_counts():
    # answer bound via a non-empty join intersection, no direct fact binding
    st = plan_b()
    st.retrieved_fids = ["f1", "f2", "f4"]
    st.closed_fids = {"f3"}
    joins = {"?founder": (("f1", "f2"), ("Alice",))}
    assert ready_to_commit(st, {}, {"f5": ["Bob"]}, joins) is True


def test_commit_due_seq_wide_off_falls_back(monkeypatch):
    st = plan_a()
    st.retrieved_fids = ["f1", "f2"]
    fb = {"f1": ["Alice"]}
    monkeypatch.delenv("SEQ_WIDE_COMMIT", raising=False)
    assert commit_due(st, {}, fb, {}) is True          # READY (wide default on)
    monkeypatch.setenv("SEQ_WIDE_COMMIT", "off")
    assert ready_to_commit(st, {}, fb, {}) is True     # predicate still READY
    assert commit_due(st, {}, fb, {}) is False         # fuse → legacy all_retrieved


# ── fact_key_map: three namespaces → one canonical key ─────────────────────

def test_key_map_namespaces():
    st = plan_a()
    assert st.fact_ids == ["f1", "f2", "f3"]
    assert norm_fact_key(st, "f1") == "f1"
    assert norm_fact_key(st, "sg1.f2") == "f2"
    assert norm_fact_key(st, "sg2.f1") == "f3"
    # pure sgN resolves to the group's first unfinished fact (sequential flow)
    assert norm_fact_key(st, "sg1") == "f1"
    st.retrieved_fids.append(norm_fact_key(st, "sg1"))
    st.declared_fids.add("f1")
    assert norm_fact_key(st, "sg1") == "f2"
    # all group facts finished → last fact (idempotent append)
    st.retrieved_fids += ["f2"]
    st.closed_fids.add("f2")
    assert norm_fact_key(st, "sg1") == "f2"


def test_closures_count_into_completion():
    st = plan_a()
    st.retrieved_fids = ["f1", "f2"]
    assert st.all_retrieved is False
    # ctx-side closure in sg-namespace normalizes into the done set
    assert ready_to_commit(st, {"sg2.f1": "empty"}, {"f1": ["Alice"]}, {}) is True
    assert st.all_retrieved is False      # state-only view still lacks the closure
    st.closed_fids = {norm_fact_key(st, k) for k in ("sg2.f1",)}
    assert st.all_retrieved is True       # once synced, the legacy path agrees


def _call(name: str, args: dict) -> list:
    # OpenAI tool_call shape — what _tool_name/_tool_args (harness.py) read
    return [{"function": {"name": name, "arguments": args}}]


def test_validate_retrieve_subgraph_appends_canonical_key():
    st = plan_a()
    ok, err, _ = validate(st, _call("retrieve_subgraph",
                                    {"center": ["OrgAlpha"], "relations": ["r"], "sg": "sg1.f2"}))
    assert ok, err
    assert st.retrieved_fids == ["f2"]


def test_validate_budget_counts_base_sg():
    st = plan_a()
    st.sg_plan["sg1"] = 1                 # budget = 3 calls
    for sg_arg in ("sg1", "sg1.f2", "sg1", "sg1.f2", "sg1"):
        validate(st, _call("retrieve_subgraph",
                           {"center": ["OrgAlpha"], "relations": ["r"], "sg": sg_arg}))
    assert st.sg_calls["sg1"] == 5        # both namespaces hit the same budget
    assert "sg1" in st.sg_done            # 5 > 3 → budget-intercepted


def test_validate_early_answer_reminder_gates():
    st = plan_a()
    st.retrieved_fids = ["f1"]
    # READY ⇒ no reminder at all, answer accepted
    ok, err, st2 = validate(st, _call("answer", {"entities": ["Alice"]}), ready=True)
    assert ok and err == "" and st2.state == "DONE"
    # not READY ⇒ reminder lists ONLY the blocking fact (f2, head==ans), not f3
    st = plan_a()
    st.retrieved_fids = ["f1"]
    ok, err, st2 = validate(st, _call("answer", {"entities": ["Alice"]}),
                            ready=False, missing_facts=["f2"])
    assert not ok and "['f2']" in err and "f3" not in err.split("missing")[1]


# ── loop-level structural smoke + mechanics ────────────────────────────────

async def _fake_dispatch(tool_name, args, ctx, session):
    return json.dumps({"ok": True, "fact_id": args.get("sg", ""),
                       "candidates": ["Alice"]})


PLAN_TURN = """tool: plan
entities: OrgAlpha
answer: ?founder
answer_type: person
R1.kind: structural
R1.text: founder of the organization
R2.kind: filter
R2.text: country of the founder
R3.kind: structural
R3.text: headquarters city
R4.kind: structural
R4.text: airport near the org
sg1.anchor: OrgAlpha
sg1.f1: OrgAlpha | who founded this organization | ?founder
sg1.f1.covers: R1
sg1.f2: ?founder | which country is this person in | ?country
sg1.f2.covers: R2
sg2.anchor: OrgAlpha
sg2.f1: OrgAlpha | headquarters city | ?city
sg2.f1.covers: R3
"""


def make_case(monkeypatch):
    monkeypatch.setattr(L.ST, "dispatch", _fake_dispatch)
    rc = L.SeqReactCase({}, {}, 0)
    return rc


def turn(rc, content):
    return asyncio.run(rc.process_turn(None, content, None))


def _process_turn_depth1():
    """Depth-1 statements of the turn flow — the guard against the historical
    indentation-dead-code regression. Since the perf-4 three-phase split
    (2026-08-23) process_turn is the sequential composition of
    _parse_prepare (A) → _execute_tool (B) → _finalize (C); the guard now
    covers the three method bodies that ARE the main flow."""
    tree = ast.parse(Path(L.__file__).read_text())
    bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and \
                node.name in ("process_turn", "_parse_prepare", "_finalize"):
            bodies[node.name] = [ast.unparse(s) for s in node.body]
    assert "process_turn" in bodies, "process_turn not found"
    assert "_parse_prepare" in bodies and "_finalize" in bodies, \
        "three-phase split incomplete"
    return bodies


def test_structural_smoke_blocks_in_main_flow():
    bodies = _process_turn_depth1()
    joined = "\n".join(s for b in bodies.values() for s in b)
    # every guard must sit at depth 1 of a main-flow method body (not nested
    # after a return)
    for marker in ("REJECTED (repeat)", "STAGE GATE: evidence is committed",
                   "purity-loop reminder", "seq_validate(",
                   "_maybe_inject_evidence_commit()"):
        assert marker in joined, f"dead-code regression: {marker} not in main flow"
    assert joined.count("_maybe_inject_evidence_commit()") >= 2  # pre-gate + post-dispatch
    # the composition itself: process_turn drives A → B → C in order
    pt = "\n".join(bodies["process_turn"])
    assert "_parse_prepare" in pt and "_execute_tool" in pt and "_finalize" in pt
    assert pt.index("_parse_prepare") < pt.index("_execute_tool") < pt.index("_finalize")


def test_plan_turn_fills_ready_state(monkeypatch):
    rc = make_case(monkeypatch)
    assert turn(rc, PLAN_TURN) == "continue"
    st = rc.state
    assert st.state == "RETRIEVE"
    assert st.fact_ids == ["f1", "f2", "f3"]
    assert st.answer_var == ["?founder"]
    assert st.fact_edges["f1"] == ("OrgAlpha", "?founder")
    assert st.fact_edges["f2"] == ("?founder", "?country")
    assert st.fact_key_map["sg2.f1"] == "f3"
    assert st.sg_facts == {"sg1": ["f1", "f2"], "sg2": ["f3"]}


def test_stage_gate_intercepts_first_answer(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.ctx._analysis_pending = True
    out = turn(rc, "tool: answer\nentities: Alice")
    assert out == "continue"
    assert any("STAGE GATE" in (m.get("content") or "") for m in rc.messages)
    assert rc.ctx._analysis_pending is False      # one-shot consumed
    assert rc.state.state == "RETRIEVE"           # answer NOT accepted


def test_repeat_tool_rejected_second_time(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    call = "tool: retrieve_relations\ncenter: OrgAlpha\nquestion: who founded this organization"
    assert turn(rc, call) == "continue"
    assert turn(rc, call) == "continue"           # identical repeat
    traj = [s.get("content") or "" for s in rc.ctx.trajectory]
    assert any(t.startswith("REJECTED (repeat)") for t in traj)


def test_purity_detector_reachable(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    qs = ["which films did she direct",
          "which films has she directed",
          "what films did she direct"]
    for q in qs:
        out = turn(rc, f"tool: retrieve_relations\ncenter: OrgAlpha\nquestion: {q}")
        assert out == "continue"
    assert len(getattr(rc.ctx, "_qsim_hist", {}).get("orgalpha", [])) == 3
    assert any("3rd similarly-worded query" in (m.get("content") or "")
               for m in rc.messages)


def test_refusal_phrase_routes_ladder(monkeypatch):
    """Refusal routing (user ruling 2026-08-25): FIRST refusal keeps the
    model's go-back right (re-select ladder — never forced to answer);
    SECOND refusal (re-selection produced nothing new) → answer from current
    support with bindings shown."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]
    rc.ctx.fact_vars = {"f1": "?founder"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    turn(rc, "tool: answer\nentities: [Unable to determine — date evidence unavailable]")
    msgs = [m.get("content") or "" for m in rc.messages]
    assert any("fall back ONE level" in m for m in msgs)   # go-back right kept
    assert not any("answer NOW" in m for m in msgs)        # never forced on 1st
    assert rc.state.state == "RETRIEVE"
    out = turn(rc, "tool: answer\nentities: None")
    msgs = [m.get("content") or "" for m in rc.messages]
    sec = next(m for m in msgs if "Second refusal" in m)
    assert "?founder=['Alice']" in sec                     # bindings as basis
    assert rc.state.state == "RETRIEVE"


def test_none_answer_routes_ladder(monkeypatch):
    """Literal `entities: None` with EMPTY evidence → the re-select ladder;
    after restart → converts to explicit empty and accepts."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]
    rc.ctx.all_candidates = []          # no bindings, no pool → re-select arm
    rc.ctx.fact_vars = {}
    rc.ctx.fact_bindings = {}
    out = turn(rc, "tool: answer\nentities: None")
    msgs = [m.get("content") or "" for m in rc.messages]
    assert any("fall back ONE level" in m for m in msgs)
    assert rc.state.state == "RETRIEVE"           # not accepted, not dispatched
    # second attempt after restart: explicit-empty contract
    rc.ctx.restarted = True
    out = turn(rc, "tool: answer\nentities: None")
    assert rc.done is True                         # accepted as empty


def test_sg_var_status_in_checkpoint_ack(monkeypatch):
    """Checkpoint-only turns carry same-subgraph variable binding status
    (information, never enforcement)."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)          # sg1.f1 (?founder), sg1.f2 (?country), sg2.f1
    rc.state.retrieved_fids = ["f1"]
    rc.ctx.fact_vars = {"f1": "?founder", "f2": "?country"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}       # f2 unbound
    out = turn(rc, "[sg1.f1 ✓] ?founder = [Alice]")
    msgs = [m.get("content") or "" for m in rc.messages]
    ack = next(m for m in msgs if "Checkpoints recorded" in m)
    assert "?founder=bound(1)" in ack


def test_var_mismatch_intercept(monkeypatch):
    """Stalin specimen: answer entities entirely from ANOTHER var's bindings
    while the plan's answer var has its own bindings → one-shot intercept;
    resubmit passes (justified override)."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)      # answer var ?founder (f1); f2 binds ?country
    rc.state.answer_var = ["?founder"]
    rc.ctx.fact_vars = {"f1": "?founder", "f2": "?country"}
    rc.ctx.fact_bindings = {"f1": ["Alice"], "f2": ["Germany"]}
    rc.state.retrieved_fids = ["f1", "f2"]
    out = turn(rc, "tool: answer\nentities: Germany")
    msgs = [m.get("content") or "" for m in rc.messages]
    assert any("MECHANICAL MISMATCH" in m for m in msgs)
    assert any("?country" in m for m in msgs)
    assert rc.state.state == "RETRIEVE"
    # resubmit passes the one-shot
    out2 = turn(rc, "tool: answer\nentities: Germany")
    assert not any("MECHANICAL MISMATCH" in (m.get("content") or "")
                   for m in rc.messages[-2:])


def test_self_analysis_same_turn_passes_gate(monkeypatch):
    """Self-analysis pass-through (user ruling 2026-08-24): a turn carrying a
    FULL ANSWER_ANALYSIS block ahead of the answer call satisfies the
    two-stage intent by itself — no redundant STAGE GATE re-analysis round."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]
    rc.ctx.fact_vars = {"f1": "?founder"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    rc.ctx._analysis_pending = True
    final = ("ANSWER_ANALYSIS\nBASE_CANDIDATES:\nAlice\n"
             "REQUIREMENT_CHECK:\nAlice: R1 = SUPPORTED\n"
             "PROVISIONAL_FINAL:\nAlice\nREASON: support\n"
             "tool: answer\nentities: Alice")
    turn(rc, final)
    msgs = [m.get("content") or "" for m in rc.messages]
    assert not any("STAGE GATE" in m for m in msgs)
    assert rc.ctx._analysis_done is True
    assert rc.state.state == "DONE"            # answer accepted directly


def test_answer_on_ready_routes_through_commit_and_analysis(monkeypatch):
    """The 42% bypass family: answer while READY must NOT be accepted directly —
    the ledger commits, the STAGE GATE forces ANSWER_ANALYSIS, then the answer."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]        # f3 open but irrelevant
    rc.ctx.fact_vars = {"f1": "?founder"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    out = turn(rc, "tool: answer\nentities: Alice")
    assert out == "continue"
    msgs = [m.get("content") or "" for m in rc.messages]
    # ledger injected with the DECLARED answer var; STAGE GATE (not the reminder)
    assert rc.ctx._ledger_injected is True
    assert any("EVIDENCE COMMIT" in m and "CANDIDATES (?founder)" in m for m in msgs)
    assert any("STAGE GATE" in m for m in msgs)
    assert not any("You answered before retrieving" in m for m in msgs)
    assert rc.state.state == "RETRIEVE"
    # analysis turn → ANSWER_READY
    assert turn(rc, "ANSWER_ANALYSIS\nBASE_CANDIDATES:\nAlice\nREASON: R1 supported.") == "continue"
    assert rc.ctx._analysis_done is True
    # final answer accepted
    assert turn(rc, "tool: answer\nentities: Alice") == "done"
    assert rc.state.state == "DONE"


def test_support_matrix_from_declared_var(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]
    rc.ctx.fact_vars = {"f1": "?founder"}         # fid-namespace declaration
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    turn(rc, "tool: answer\nentities: Alice")
    msgs = [m.get("content") or "" for m in rc.messages]
    led = next(m for m in msgs if "EVIDENCE COMMIT" in m)
    assert "CANDIDATES (?founder): [Alice]" in led
    assert "SUPPORT R1" in led                     # covers map aligns on fid keys


def test_guessed_answer_var_no_support_lines(monkeypatch):
    """Plan declares ?founder but the checkpoint bound it under an alias var —
    the READY edge check still sees the binding; the ledger falls back to the
    alias var for display and SUPPRESSES the (wrong) support matrix."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2"]
    rc.ctx.fact_vars = {"f1": "?founder_alias"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    turn(rc, "tool: answer\nentities: Alice")
    msgs = [m.get("content") or "" for m in rc.messages]
    led = next(m for m in msgs if "EVIDENCE COMMIT" in m)
    assert "CANDIDATES (?founder_alias)" in led   # heuristic display fallback
    assert "SUPPORT" not in led                   # but NO wrong support matrix


def test_early_answer_reminder_lists_only_blocking(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1"]
    rc.ctx.closed_facts = {"sg2.f1": "empty"}      # f3 closed (sg-namespace key)
    rc.ctx.fact_vars = {"f1": "?founder"}
    rc.ctx.fact_bindings = {"f1": ["Alice"]}
    out = turn(rc, "tool: answer\nentities: Alice")
    assert out == "continue"
    msgs = [m.get("content") or "" for m in rc.messages]
    rem = next(m for m in msgs if "You answered before retrieving" in m)
    assert "['f2']" in rem and "f3" not in rem.split("missing")[1]
    # second answer passes the one-shot reminder (budget escape)
    assert turn(rc, "tool: answer\nentities: Alice") == "done"


def test_plan_extend_resets_ledger_and_registers_facts(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.ctx._ledger_injected = True
    rc.ctx._analysis_pending = True
    rc.ctx._analysis_done = True
    out = turn(rc, "[PLAN EXTEND]\ncovers: R4\n\nsg3.anchor: OrgAlpha\n"
                   "sg3.f1: OrgAlpha | airport near the org | ?airport\n")
    assert out == "continue"
    assert rc.ctx._ledger_injected is False
    assert rc.ctx._analysis_pending is False
    assert rc.ctx._analysis_done is False
    st = rc.state
    assert st.fact_ids == ["f1", "f2", "f3", "f4"]
    assert st.fact_edges["f4"] == ("OrgAlpha", "?airport")
    assert st.fact_key_map["sg3.f1"] == "f4"
    assert st.sg_facts["sg3"] == ["f4"]
    assert st.sg_plan["sg3"] == 1


def test_closure_only_completion_fires_commit(monkeypatch):
    """Audit defect ③ e2e: completion via ✗ closures (not retrievals) must fire
    EVIDENCE COMMIT. f1 ✓-declared, f3 retrieved, f2 closed `[sg1.f2 ✗ moot]`
    in the same turn as the answer attempt — all three namespaces in play."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    # turn 1: declare f1's checkpoint + retrieve sg2.f1 (pure sg namespace)
    out = turn(rc, "[sg1.f1 ✓] ?founder = [Alice]\n\n"
                   "tool: retrieve_subgraph\ncenter: OrgAlpha\nrelations: rel.hq\nsg: sg2")
    assert out == "continue"
    assert rc.state.retrieved_fids == ["f3"]
    assert rc.state.declared_fids == {"f1"}
    assert not getattr(rc.ctx, "_ledger_injected", False)   # f2 still open (head==ans)
    # turn 2: close f2 as moot + answer → READY branch 1, commit, STAGE GATE
    out = turn(rc, "[sg1.f2 ✗ moot] the founder's country never needed walking\n\n"
                   "tool: answer\nentities: Alice")
    assert out == "continue"
    msgs = [m.get("content") or "" for m in rc.messages]
    assert rc.ctx._ledger_injected is True
    assert any("EVIDENCE COMMIT" in m and "CANDIDATES (?founder)" in m for m in msgs)
    assert any("STAGE GATE" in m for m in msgs)
    assert not any("You answered before retrieving" in m for m in msgs)
    assert rc.state.all_retrieved is True            # closures counted state-side


def test_restart_resets_two_stage_flags(monkeypatch):
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.ctx._ledger_injected = True
    rc.ctx._analysis_pending = True
    rc.ctx._analysis_done = True
    out = turn(rc, "[explore ✗ none] everything retrieved was irrelevant")
    assert out == "continue"
    assert rc.ctx._ledger_injected is False
    assert rc.ctx._analysis_pending is False
    assert rc.ctx._analysis_done is False
    assert any("RESTART" in (m.get("content") or "") for m in rc.messages)
    assert rc.state.state == "INIT"                # fresh state machine


# ── placeholder-fid canonicalization (2026-08-22 cohort audit: 22% of fuse-on
# trajectories declared checkpoints as the DOC PLACEHOLDER `[fid ✓]` — the
# declaration landed under a junk key, completion accounting missed the fact,
# and the EVIDENCE COMMIT never fired while the answer slipped through) ──────

def test_placeholder_fid_declaration_commits_and_gates(monkeypatch):
    """`[fid ✓] ?founder = [...]` + answer in ONE turn must resolve `fid` via the
    declared variable against fact_edges → canonical f-key → READY branch 1 →
    ledger injection; the same-turn ANSWER_ANALYSIS satisfies the two-stage
    intent (self-analysis pass-through, 2026-08-24) — no redundant re-gate."""
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.state.retrieved_fids = ["f1", "f2", "f3"]
    rc.state.n_subgraphs = 3
    rc.ctx.fact_key_map = dict(getattr(rc.state, "fact_key_map", None) or {})
    rc.ctx.fact_edges = dict(getattr(rc.state, "fact_edges", None) or {})
    final = ("[fid ✓] ?founder = [Alice]\n"
             "ANSWER_ANALYSIS\nBASE_CANDIDATES:\nAlice\n"
             "REQUIREMENT_CHECK:\nAlice: R1 = SUPPORTED\n"
             "PROVISIONAL_FINAL:\nAlice\nREASON: support\n"
             "tool: answer\nentities: Alice")
    turn(rc, final)
    msgs = [m.get("content") or "" for m in rc.messages]
    assert rc.ctx._ledger_injected is True
    # same-turn analysis passes the gate directly (user ruling 2026-08-24)
    assert not any("STAGE GATE" in m for m in msgs)
    assert rc.ctx._analysis_done is True
    assert rc.state.state == "DONE"
    # ALL downstream stores carry the canonical key, not the placeholder
    assert "f1" in (getattr(rc.ctx, "fact_bindings", None) or {})
    assert getattr(rc.ctx, "_fid_alias", {}).get("fid") in rc.state.fact_ids


def test_placeholder_fid_closure_canonical_single_fact(monkeypatch):
    """`[fid ✗ empty]` on a single-fact plan resolves to that fact (var-less ✗
    fallback); empty-binding closures keep the no-ledger early return (nothing
    to analyze) but the closure must land under the canonical key."""
    single = """tool: plan
entities: OrgAlpha
answer: ?founder
answer_type: person
R1.kind: structural
R1.text: founder of the organization
sg1.anchor: OrgAlpha
sg1.f1: OrgAlpha | who founded this organization | ?founder
sg1.f1.covers: R1
"""
    rc = make_case(monkeypatch)
    turn(rc, single)
    rc.ctx.fact_key_map = dict(getattr(rc.state, "fact_key_map", None) or {})
    rc.ctx.fact_edges = dict(getattr(rc.state, "fact_edges", None) or {})
    rc.state.retrieved_fids = ["f1"]
    turn(rc, "[fid ✗ empty] no advancing relation")
    assert getattr(rc.ctx, "closed_facts", {}).get("f1") == "empty"


def test_real_fids_unaffected_by_alias(monkeypatch):
    """Real ids pass through unchanged (memoized); an unknown non-placeholder id
    stays raw — no accidental remapping."""
    from kgqa.agent.seq_react_loop import _canonical_decl_fid
    rc = make_case(monkeypatch)
    turn(rc, PLAN_TURN)
    rc.ctx.fact_key_map = dict(getattr(rc.state, "fact_key_map", None) or {})
    rc.ctx.fact_edges = dict(getattr(rc.state, "fact_edges", None) or {})
    assert _canonical_decl_fid(rc.ctx, "sg1.f1", "?founder") == "f1"
    assert _canonical_decl_fid(rc.ctx, "f2", "?country") == "f2"
    assert _canonical_decl_fid(rc.ctx, "weird-id", "?founder") == "weird-id"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
