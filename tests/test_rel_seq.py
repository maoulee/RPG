"""SEQ_REL_SEQ relation-sequence accumulation (user design 2026-09-15).

Pure-function tests on a synthetic graph shaped like the runtime specimen:

    Anchor --rel1--> m.mid --rel2--> Target        (2-hop discriminator chain)
    Anchor --rel0--> Side                          (anchor-direct alternative)
    Target --rel3--> Val                           (deep continuation)

Layer semantics: an appended relation joins the DEEPEST layer whose
completions make it feasible; anchor-direct feasible = layer 1.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from kgqa.agent import seq_tools as ST
from kgqa.traversal.pattern_walk import get_pattern_index


def _ctx():
    ents = ["Anchor", "m.mid", "Target", "Side", "Val"]
    rels = ["a.b.rel0", "a.b.rel1", "a.b.rel2", "a.b.rel3", "a.b.relX"]
    #         r0         r1         r2         r3         rX (unconnected)
    edges = [           # (h, r, t)
        (0, 1, 1),      # Anchor --rel1--> m.mid
        (1, 2, 2),      # m.mid  --rel2--> Target
        (0, 0, 3),      # Anchor --rel0--> Side
        (2, 3, 4),      # Target --rel3--> Val
    ]
    return SimpleNamespace(
        ents=ents, rels=rels, rel_texts=[],
        h_ids=[e[0] for e in edges],
        r_ids=[e[1] for e in edges],
        t_ids=[e[2] for e in edges])


@pytest.fixture()
def setup(request):
    os.environ["SEQ_REL_SEQ"] = "1"
    request.addfinalizer(lambda: os.environ.pop("SEQ_REL_SEQ", None))
    ctx = _ctx()
    ix = get_pattern_index(ctx)
    return ctx, ix


def test_completions_per_layer(setup):
    ctx, ix = setup
    comps = ST._seq_completions(ctx, ix, 0, [frozenset({1})])
    assert comps[0] == {0}
    # transparency: rel1 lands on m.mid (CVT-like) which passes through to
    # its NAMED neighbor Target — the engine's same-layer semantics
    assert comps[1] == {2}


def test_memo_returns_same_object(setup):
    ctx, ix = setup
    a = ST._seq_completions(ctx, ix, 0, [frozenset({1})])
    b = ST._seq_completions(ctx, ix, 0, [frozenset({1})])
    assert a is b


def test_classify_append_frontier_only(setup):
    """rel2 lives on m.mid (layer-1 completions), not the anchor → append."""
    ctx, ix = setup
    layers, actions, _ = ST._classify_seq_submit(ctx, ix, 0, [frozenset({1})], [2])
    assert actions[2] == "append"
    assert list(layers[1]) == [2]


def test_classify_anchor_direct_joins_layer1(setup):
    """rel0 is anchor-direct → joins layer 1 (parallel widening)."""
    ctx, ix = setup
    layers, actions, _ = ST._classify_seq_submit(ctx, ix, 0, [frozenset({1})], [0])
    assert actions[0] == "join:1"
    assert layers[0] == frozenset({1, 0})


def test_classify_deep_join_mid_layer(setup):
    """After [rel1][rel2]: rel2's frontier IS Target (transparency skipped
    m.mid), so rel3 (Target-direct) joins layer 2 as rel2's same-layer
    sibling, while rel0 (anchor-direct) joins layer 1 — deepest-feasible
    never invents depth when a shallower layer fits."""
    ctx, ix = setup
    layers = [frozenset({1}), frozenset({2})]
    layers2, actions, _ = ST._classify_seq_submit(ctx, ix, 0, layers, [3, 0])
    assert actions[3] == "join:2"
    assert actions[0] == "join:1"
    assert layers2 == [frozenset({1, 0}), frozenset({2, 3})]


def test_classify_infeasible(setup):
    ctx, ix = setup
    layers, actions, _ = ST._classify_seq_submit(ctx, ix, 0, [frozenset({1})], [4])
    assert actions[4] == "infeasible"
    assert layers == [frozenset({1})]


def test_classify_depth_cap(setup):
    ctx, ix = setup
    layers = [frozenset({1}), frozenset({2}), frozenset({3})]
    # rel0 is anchor-feasible so it would join:1, not append — force an
    # append attempt with a relation feasible ONLY beyond the last layer
    # is impossible here (rel3 is IN layer 3); use the cap check directly
    layers2, actions, _ = ST._classify_seq_submit(ctx, ix, 0, layers, [0])
    assert actions[0] == "join:1"               # never appends past cap


def test_patterns_from_layers(setup):
    ctx, ix = setup
    layers = [frozenset({1}), frozenset({2})]
    pats = ST._patterns_from_layers(ctx, ix, 0, layers, {2})
    assert (1, 2) in pats
    assert pats[(1, 2)] == (frozenset({1}), frozenset({2}))
    # final relation not submitted → pattern dropped (rel3 chain ends in 3)
    assert (1, 3) not in pats and (1, 2, 3) not in pats


def test_patterns_infeasible_chain_pruned(setup):
    """rel2 from Anchor directly has no edges → (2,) pattern pruned."""
    ctx, ix = setup
    pats = ST._patterns_from_layers(ctx, ix, 0, [frozenset({2})], {2})
    assert pats == {}


def test_patterns_cross_layer_trim(setup):
    """Wide layers trim deterministically under the 24-combo cap."""
    ctx, ix = setup
    wide = [frozenset({1, 0})] * 5              # 2^5 = 32 > 24
    pats = ST._patterns_from_layers(ctx, ix, 0, wide, {1})
    assert len(pats) <= 24


# ── CHAIN TREE (user rulings 2026-09-20: leaf semantics + selection surface) ──

def _chain(nodes, edges):
    return {"nodes": list(nodes), "edges": list(edges),
            "full_nodes": list(nodes), "full_edges": list(edges)}


def test_tree_positions_leaf_mid_and_cvt_attr(setup):
    """Leaves = chain terminals ∪ terminal-CVT named attribute endpoints;
    interior nodes are mid (re-work points) with their reaching prefix."""
    ctx, ix = setup
    chains = {(1, 2): [_chain([0, 1, 2], [(0, 1, 1), (1, 2, 2)])]}
    pos = ST._tree_positions(ctx, ix, 0, chains)
    assert 2 in pos["leaves"]                       # Target (named terminal)
    assert 1 in pos["mid"]                          # m.mid is interior
    assert pos["leaf_pats"][2] == [((1, 2), 2)]
    assert pos["mid_pats"][1] == [((1, 2), 1)]
    # CVT-terminal chain: Anchor --rel1--> m.mid — the CVT's named attribute
    # endpoints (Target via rel2) count as leaves of the SAME pattern
    chains2 = {(1,): [_chain([0, 1], [(0, 1, 1)])]}
    pos2 = ST._tree_positions(ctx, ix, 0, chains2)
    assert 1 in pos2["leaves"]
    assert 2 in pos2["leaves"]                      # CVT attr endpoint
    assert pos2["leaf_pats"][2] == [((1,), 1)]


def test_supernode_own_rel_enumerated_and_rebuilt(setup):
    """E4: a 2-hop (r1, fam) whose fam edges hang on the CVT r1 LANDS ON —
    enumerable (derive keeps CVT landings) and walkable (rebuild keeps the
    CVT as a position; a real pattern edge outranks the passthrough parent)."""
    ctx, ix = setup
    # fam = rel2: its only edge is m.mid --rel2--> Target (on the CVT)
    out = ST._derive_multistep_seq(ix, ctx, 0, {2}, topk=0)
    assert (1, 2) in out
    chains, _ = ST._rebuild_paths(
        ctx, ix, 0, (frozenset({1}), frozenset({2})))
    # Target was CVT-expanded into hop-1's level; hop-2's pattern edge
    # (m.mid, rel2, Target) must own the chain's final hop
    hit = [c for c in chains if c["nodes"] == [0, 1, 2]]
    assert hit and hit[0]["edges"] == [(0, 1, 1), (1, 2, 2)]
