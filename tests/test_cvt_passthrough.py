#!/usr/bin/env python3
"""TDD: a CVT-mediated fact must traverse through the CVT to the answer.

Bug: build_mode_level_logical_paths._hit_paths matches a target relation at hop1
and `continue`s, so when the hop1 target lands on a CVT mediator, the CVT's
target out-edge (also selected) is never walked -> the answer behind the CVT is
lost.

Fixture: David Duke (WebQTrn-1907, GT=Louisiana State University). Gold path =
Duke -[people.person.education]-> education CVT -[education.education.institution]
-> LSU, with BOTH relations selected into one fact. The traversal must reach LSU.

Run: python3 tests/test_cvt_passthrough.py
"""
import importlib.util
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from kgqa.agent.loop import build_context
from kgqa.traversal.logical_paths import build_mode_level_logical_paths
from kgqa.core.utils import normalize
from diagnose_plan_failures import answer_idxs

_VAL = pickle.loads((ROOT / "data/cwq_processed/val.pkl").read_bytes())


def _find_david_duke():
    for s in _VAL:
        if "David Duke attend" in (s.get("question") or ""):
            return s
    return None


def _recall_pool(sample, step_rels, gt):
    ctx = build_context(sample, {"case_id": sample.get("id", ""),
                                 "question": sample.get("question", ""),
                                 "gt_answers": gt}, 0)
    a_idxs = answer_idxs(ctx, gt)
    assert a_idxs, f"gold answer {gt} not located in subgraph"
    lp = build_mode_level_logical_paths(
        ctx.anchor_idx, step_rels, ctx.h_ids, ctx.r_ids, ctx.t_ids,
        ctx.ents, ctx.rels, set(), beam_width=80, max_hops_per_step=2,
        relation_list=ctx.rels)
    raw_nodes = set()
    for p in lp:
        for rp in p.get("raw_paths", []):
            raw_nodes.update(rp.get("nodes") or [])
        for n in ((p.get("best_raw_path") or {}).get("nodes") or []):
            raw_nodes.add(n)
    return ctx, a_idxs, raw_nodes, lp


def _model_selection(record):
    """Parse the model's actual decompose anchor + per-fact selected relations."""
    import json as _json
    dec = sel = None
    for m in record.get("messages", []):
        c = m.get("content", "")
        if not isinstance(c, str):
            continue
        if c.startswith("Tool result (decompose):"):
            try:
                dec = _json.loads(c[len("Tool result (decompose):"):])
            except Exception:
                dec = None
        elif c.startswith("Tool result (select_relations):"):
            try:
                sel = _json.loads(c[len("Tool result (select_relations):"):])
            except Exception:
                sel = None
    sd = {}
    if sel and isinstance(sel.get("selected"), dict):
        for fid, rels in sel["selected"].items():
            sd[str(fid)] = [str(r) for r in rels] if isinstance(rels, list) else []
    return list(sd.values())


def _dd_record():
    import json as _json
    p = ROOT / "reports/samp_val_pool/rescored.jsonl"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        try:
            r = _json.loads(line)
        except Exception:
            continue
        if "David Duke attend" in (r.get("question") or "") and (r.get("S_plan") or 0) == 0:
            return r
    return None


def test_cvt_fact_reaches_answer():
    sample = _find_david_duke()
    assert sample is not None, "David Duke case not in val.pkl"
    rec = _dd_record()
    assert rec is not None, "David Duke S_plan=0 record not in rescored.jsonl"
    gt = ["Louisiana State University"]
    ctx = build_context(sample, {"case_id": sample.get("id", ""),
                                 "question": sample.get("question", ""),
                                 "gt_answers": gt}, 0)
    a_idxs = answer_idxs(ctx, gt)
    assert a_idxs, f"gold answer {gt} not located in subgraph"
    ridx = {r: i for i, r in enumerate(ctx.rels)}
    step_rels = [{ridx[x] for x in rels if x in ridx} for rels in _model_selection(rec)]
    step_rels = [s for s in step_rels if s]
    assert step_rels, "no selected relations parsed"
    lp = build_mode_level_logical_paths(
        ctx.anchor_idx, step_rels, ctx.h_ids, ctx.r_ids, ctx.t_ids,
        ctx.ents, ctx.rels, set(), beam_width=80, max_hops_per_step=2,
        relation_list=ctx.rels)
    raw_nodes = set()
    for p in lp:
        for rp in p.get("raw_paths", []):
            raw_nodes.update(rp.get("nodes") or [])
        for n in ((p.get("best_raw_path") or {}).get("nodes") or []):
            raw_nodes.add(n)
    gold_idx = a_idxs[0]
    assert gold_idx in raw_nodes, (
        f"CVT-mediated fact did not reach gold '{gt[0]}' (idx {gold_idx}); "
        f"raw_paths had {len(raw_nodes)} nodes but not the answer. "
        f"patterns={len(lp)}, step_rels={step_rels}")


def _run():
    tests = [test_cvt_fact_reaches_answer]
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
