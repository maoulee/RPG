"""Smoke test for the agent _do_select + _do_expand_branch CVT expansion fix.

Builds a synthetic Ohio-governor CVT subgraph (the case the spec §1 root-cause
analysis uses) and asserts that:
  - _do_select produces branches whose candidates contain the CVT-expanded
    office_holder NAMES (Kasich, Strickland), not bare CVT node IDs. (Blocker A)
  - the overview is a TREE with right-side #N markers. (Blocker B)
  - _do_expand_branch returns full triples + a rendered tree. (Blocker C)

Run: python tests/test_agent_select_expand_smoke.py
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio
import json

from kgqa.agent.loop import CaseContext
from kgqa.agent import tools as T


def _build_ohio_case() -> CaseContext:
    """Synthetic subgraph mirroring the Ohio-governor CVT case from spec §1.

    Topology (Freebase-style CVT mediator):
        Ohio --[government.governmental_jurisdiction.governing_officials]--> CVT_1
        CVT_1 --[government.government_office_held.office_holder]--> John Kasich
        CVT_1 --[government.government_office_held.from]------------- 2011
        CVT_1 --[government.government_office_held.to]--------------- 2019
        Ohio --[government.governmental_jurisdiction.governing_officials]--> CVT_2
        CVT_2 --[government.government_office_held.office_holder]--> Ted Strickland
        CVT_2 --[government.government_office_held.from]------------- 2007
        CVT_2 --[government.government_office_held.to]--------------- 2011
        Ohio --[location.location.contains]--> Columbus            # a distractor
    """
    ents = [
        "Ohio",            # 0  anchor
        "m.cvt_gov_1",     # 1  CVT (Kasich term)
        "John Kasich",     # 2
        "2011",            # 3
        "2019",            # 4
        "m.cvt_gov_2",     # 5  CVT (Strickland term)
        "Ted Strickland",  # 6
        "2007",            # 7
        "Columbus",        # 8  distractor
    ]
    rels = [
        "government.governmental_jurisdiction.governing_officials",   # 0
        "government.government_office_held.office_holder",            # 1
        "government.government_office_held.from",                     # 2
        "government.government_office_held.to",                       # 3
        "location.location.contains",                                 # 4
    ]
    # Triples as (h_id, r_id, t_id)
    edges = [
        (0, 0, 1),  # Ohio -> CVT_1
        (1, 1, 2),  # CVT_1 -> Kasich   (office_holder)
        (1, 2, 3),  # CVT_1 -> 2011     (from)
        (1, 3, 4),  # CVT_1 -> 2019     (to)
        (0, 0, 5),  # Ohio -> CVT_2
        (5, 1, 6),  # CVT_2 -> Strickland
        (5, 2, 7),  # CVT_2 -> 2007     (from)
        (5, 3, 3),  # CVT_2 -> 2011     (to)
        (0, 4, 8),  # Ohio -> Columbus  (distractor)
    ]
    h_ids = [e[0] for e in edges]
    r_ids = [e[1] for e in edges]
    t_ids = [e[2] for e in edges]

    ctx = CaseContext(
        case_id="smoke_ohio",
        case_num=0,
        question="Who governed Ohio?",
        gt_answers=["John Kasich", "Ted Strickland"],
        ents=ents,
        rels=rels,
        rel_texts=list(rels),
        h_ids=h_ids,
        r_ids=r_ids,
        t_ids=t_ids,
        anchor_idx=0,
        anchor_name="Ohio",
    )
    # Pretend decompose+retrieve already ran: one fact using the governing
    # relation (idx 0) and the contains relation (idx 4) as a distractor.
    ctx.fact_ids = ["f1"]
    ctx.fact_texts = {"f1": "the governor of Ohio"}
    ctx.fact_relations = {"f1": {0, 4}}  # let traversal explore both
    return ctx


def _run_select(ctx: CaseContext) -> dict:
    """Invoke _do_select synchronously (it is a coroutine)."""
    return asyncio.get_event_loop().run_until_complete(T._do_select(ctx))


def main():
    ctx = _build_ohio_case()
    print("=" * 70)
    print("SMOKE TEST: _do_select on synthetic Ohio-governor CVT case")
    print("=" * 70)

    result_raw = _run_select(ctx)
    result = json.loads(result_raw)
    print(f"\nn_patterns: {result.get('n_patterns')}")
    print(f"branches stored: {list(ctx.branches.keys())}")

    overview = result.get("overview", "")
    print("\n--- OVERVIEW (first 1500 chars) ---")
    print(overview[:1500])

    # ── Assertion 1 (Blocker A): candidates contain CVT-expanded NAMES ──
    all_branch_cands = []
    for bid, br in ctx.branches.items():
        all_branch_cands.extend(br.get("candidates", []))
    joined = " | ".join(all_branch_cands)
    has_kasich = "John Kasich" in joined
    has_strickland = "Ted Strickland" in joined
    print(f"\n[Blocker A] Kasich in candidates:  {has_kasich}")
    print(f"[Blocker A] Strickland in candidates: {has_strickland}")
    # No bare CVT id should leak as a "candidate"
    cvt_leak = any(c.startswith("m.cvt") for c in all_branch_cands)
    print(f"[Blocker A] bare CVT id leaked into candidates: {cvt_leak}")

    # ── Assertion 2 (Blocker B): overview is a tree with #N markers ──
    has_hash_markers = "#1" in overview or "#2" in overview
    tree_like = overview.count("\n") > 3  # multi-line, not flat
    print(f"\n[Blocker B] overview has #N right markers: {has_hash_markers}")
    print(f"[Blocker B] overview is multi-line (tree-like): {tree_like}")

    # ── Test expand_branch (Blocker C) ──
    print("\n" + "=" * 70)
    print("SMOKE TEST: _do_expand_branch on branch 1")
    print("=" * 70)
    if ctx.branches:
        exp_raw = T._do_expand_branch({"branch_id": "1"}, ctx)
        exp = json.loads(exp_raw)
        print(f"\nbranch_id: {exp.get('branch_id')}")
        print(f"readable:  {exp.get('readable')}")
        print(f"n_candidates: {exp.get('n_candidates')} -> {exp.get('candidates')}")
        print(f"n_triples: {exp.get('n_triples')}")
        triples = exp.get("triples", [])
        print("triples (first 6):")
        for t in triples[:6]:
            print(f"  {t}")
        tree = exp.get("tree", "")
        if tree:
            print("--- rendered tree ---")
            print(tree[:800])

        has_triples = len(triples) > 0
        has_tree = bool(tree)
        print(f"\n[Blocker C] expand returned triples: {has_triples}")
        print(f"[Blocker C] expand returned rendered tree: {has_tree}")
    else:
        print("SKIP: no branches stored — select produced nothing")
        has_triples = False
        has_tree = False

    # ── Verdict ──
    print("\n" + "=" * 70)
    ok = has_kasich and has_strickland and not cvt_leak and has_hash_markers and has_triples
    print(f"VERDICT: {'PASS ✅' if ok else 'FAIL ❌'}")
    print("  Blocker A (CVT-expanded candidates):",
          "FIXED" if (has_kasich and has_strickland and not cvt_leak) else "STILL BROKEN")
    print("  Blocker B (tree overview w/ #N):    ",
          "FIXED" if (has_hash_markers and tree_like) else "STILL BROKEN")
    print("  Blocker C (expand returns triples+tree):",
          "FIXED" if (has_triples and has_tree) else "STILL BROKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
