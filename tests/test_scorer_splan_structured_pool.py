#!/usr/bin/env python3
"""TDD tests: S_plan must be computed from the STRUCTURED candidate pool
(ctx.all_candidates / answer_candidates), NOT by regex-mining the rendered
overview text.

Bug (audited): _extract_plan_reachable regex-mines the overview. The grouped-node
render `node1: [Aristotle | ... | Thomas More]` (formatting.py:708) defeats both
regexes, so an answer that IS in the structured pool scores S_plan=0. This makes
the GRPO reward signal wrong and inflates the TRAVERSAL failure bucket.

Run: python3 tests/test_scorer_splan_structured_pool.py
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "agent_stage_scorer", ROOT / "scripts/agent_stage_scorer.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)
score_case = scorer.score_case


def _case(gt, answer_candidates, select_pool, overview):
    """Build a minimal case dict that exercise score_case -> parse_trajectory."""
    return {
        "case_id": "fixture",
        "question": "q",
        "gt_answers": list(gt),
        "answer_candidates": list(answer_candidates),
        "agent_trajectory": [
            {"role": "tool", "name": "select_relations", "content": json.dumps({
                "n_patterns": 1,
                "candidates": list(select_pool),          # the [:20] select_pool
                "selected": {"f1": ["influence.influence_node.influenced_by"]},
                "overview": overview,
            })},
            {"role": "tool", "name": "answer", "content": json.dumps({"entities": []})},
        ],
    }


# Overview rendering the gold as a pipe-separated grouped node — the exact format
# the current regex cannot parse (named-node char class excludes '['; bracket
# parser splits on ',' and requires '=').
GROUPED_OVERVIEW = (
    "EVIDENCE TREE:\n"
    "  branch 1: Pico --[influenced_by]--> influencers  -> 3 candidates\n"
    "    node0: Giovanni Pico della Mirandola    #1\n"
    "      influence.influence_node.influenced_by:    #1\n"
    "        node1: [Aristotle | Augustine of Hippo | Thomas More]    #1\n"
)

# A case where the gold IS in the structured pool but regex-invisible in the
# overview, and absent from the (capped) select_pool.
CASE_POOL_HAS_GOLD = _case(
    gt=["Thomas More"],
    answer_candidates=["Aristotle", "Augustine of Hippo", "Thomas More"],
    select_pool=["Aristotle", "Augustine of Hippo"],   # [:20] cap dropped Thomas More
    overview=GROUPED_OVERVIEW,
)

# Precision: gold genuinely absent from the structured pool -> must stay 0.
CASE_POOL_LACKS_GOLD = _case(
    gt=["Nobody Real"],
    answer_candidates=["Aristotle", "Augustine of Hippo"],
    select_pool=["Aristotle", "Augustine of Hippo"],
    overview=GROUPED_OVERVIEW,
)


def test_s_plan_uses_structured_pool_when_overview_regex_misses():
    """Gold in structured pool + regex-invisible in overview -> S_plan > 0."""
    labels = score_case(CASE_POOL_HAS_GOLD)
    assert labels["S_plan"] is not None, "S_plan should not be None"
    assert labels["S_plan"] > 0.0, (
        f"expected S_plan>0 (gold is in the structured pool), got {labels['S_plan']}")


def test_s_plan_zero_when_gold_absent_from_pool():
    """Gold absent from structured pool -> S_plan == 0 (no false reach)."""
    labels = score_case(CASE_POOL_LACKS_GOLD)
    assert labels["S_plan"] == 0.0, (
        f"expected S_plan=0 (gold absent from pool), got {labels['S_plan']}")


def test_s_plan_bounded_by_pool_recall_not_inflated():
    """Multi-gold case: S_plan = fraction of gold in the structured pool."""
    case = _case(
        gt=["Thomas More", "Averroes", "Missing Guy"],
        answer_candidates=["Aristotle", "Thomas More", "Averroes"],  # 2 of 3 gold
        select_pool=["Aristotle"],
        overview=GROUPED_OVERVIEW,
    )
    labels = score_case(case)
    # scorer rounds S_plan to 4 decimals (round(S_plan, 4)) -> 0.6667
    assert abs(labels["S_plan"] - (2 / 3)) < 1e-3, (
        f"expected S_plan~=2/3 (2 of 3 gold in pool), got {labels['S_plan']}")


def _run():
    tests = [
        test_s_plan_uses_structured_pool_when_overview_regex_misses,
        test_s_plan_zero_when_gold_absent_from_pool,
        test_s_plan_bounded_by_pool_recall_not_inflated,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _run()
