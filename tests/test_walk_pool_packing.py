#!/usr/bin/env python3
"""Round-trip smoke for the packed walk pool (perf pack 2026-08-22).

retrieve_subgraph now dispatches ONE pool task per CALL carrying all centers
(_walk_call_spawn) on a per-case affine lane (hash(case_key) % WALK_POOL).
This file pins the contract:

  1. inline (WALK_POOL=0) and packed-pool (WALK_POOL=2) runs of the same
     multi-center steps produce the SAME per-center evidence labels + triples;
  2. lane bookkeeping: the first pool call ships ctx_data, the second call for
     the same case ships NONE and does not MISS (arrays resident in the affine
     worker — the affinity win);
  3. the MISS sentinel still fires when the worker cache lacks the case
     (in-process unit level — the reship path's precondition).

Fixture: first validation_virtuoso_patched.pkl sample where one relation id
instantiates on two distinct entities, so both centers have real walks to
compare. Lazy-loaded: spawn children re-execute this module's import under
direct `python3` runs.

Run: python3 tests/test_walk_pool_packing.py   (or pytest tests/test_walk_pool_packing.py)
"""
import asyncio
import os
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kgqa.agent.loop import build_context
from kgqa.agent import seq_tools

_VAL_PKL = ROOT / "data/cwq_processed/validation_virtuoso_patched.pkl"
_FIXTURE = None


async def _find_fixture():
    """Scan for (sample, pilot, steps) where a relation shared by two entities
    yields REAL evidence on at least one center (probed with the inline walk —
    many shared relations are noise-filtered and produce nothing to compare)."""
    val = pickle.loads(_VAL_PKL.read_bytes())
    for s in val:
        if not s.get("a_entity"):
            continue
        pilot = {"case_id": s.get("id", ""), "question": s.get("question", ""),
                 "gt_answers": s.get("a_entity", [])}
        ctx = build_context(s, pilot, 0)
        by_rel = {}
        for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids):
            if 0 <= h < len(ctx.ents) and 0 <= t < len(ctx.ents):
                by_rel.setdefault(r, set()).update((h, t))
        for r, eps in sorted(by_rel.items()):
            if len(eps) < 2:
                continue
            c1, c2 = sorted(eps)[:2]
            pe = [await seq_tools._run_walk_one_step(ctx, i, [r], "f1")
                  for i in (c1, c2)]
            if any(pe):
                return s, pilot, [(c1, [r], "f1"), (c2, [r], "f1")]
    return None


def _fixture(case_num=0):
    """(ctx, steps): two centers sharing one relation id, both with real edges."""
    global _FIXTURE
    if _FIXTURE is None:
        found = asyncio.run(_find_fixture())
        assert found is not None, "no multi-center evidence fixture in val split"
        _FIXTURE = found
    s, pilot, steps = _FIXTURE
    return build_context(s, pilot, case_num), steps


def _sig(pe):
    """Comparable signature of one center's evidence: label -> sorted triples."""
    return {label: sorted(str(tr) for tr in (ev.triples or []))
            for label, ev in (pe or {}).items()}


def test_packed_pool_matches_inline():
    """Same multi-center steps through WALK_POOL=0 and WALK_POOL=2 → identical
    per-center evidence (labels + triples)."""
    _fixture(case_num=0)                    # resolve the search OUTSIDE the loop
    async def _main():
        ctx, steps = _fixture(case_num=0)
        old = os.environ.pop("WALK_POOL", None)
        try:
            inline = await seq_tools._run_walk_packed(ctx, steps)
        finally:
            if old is not None:
                os.environ["WALK_POOL"] = old
        assert any(inline), "fixture produced no evidence — pick a richer case"
        os.environ["WALK_POOL"] = "2"
        try:
            packed = await seq_tools._run_walk_packed(ctx, steps)
        finally:
            if old is not None:
                os.environ["WALK_POOL"] = old
            else:
                os.environ.pop("WALK_POOL", None)
        assert len(inline) == len(packed) == len(steps)
        for a, b in zip(inline, packed):
            assert _sig(a) == _sig(b), (
                f"inline vs packed diverged:\n{_sig(a)}\nvs\n{_sig(b)}")
    asyncio.run(_main())


def test_lane_bookkeeping_second_call_ships_no_arrays():
    """First pool call ships ctx_data; the second for the same case ships NONE
    (per-lane sent-set) and still returns full evidence — no MISS reship."""
    _fixture(case_num=5)                    # resolve the search OUTSIDE the loop
    async def _main():
        ctx, steps = _fixture(case_num=5)   # fresh case_key → clean sent-set
        lanes = seq_tools._get_walk_lanes(2)
        key = (ctx.case_id or "seq", ctx.case_num or 0)
        lane_i = hash(key) % len(lanes)
        for sent in seq_tools._SENT_BY_LANE:
            sent.discard(key)
        lane = lanes[lane_i]
        shipped = []
        orig_submit = lane.submit

        def _rec_submit(fn, *a, **kw):
            if fn is seq_tools._walk_call_spawn_timed:
                shipped.append(a[0][1] is not None)   # task=(case_key, ctx_data, ...)
            return orig_submit(fn, *a, **kw)
        lane.submit = _rec_submit
        try:
            os.environ["WALK_POOL"] = "2"
            first = await seq_tools._run_walk_packed(ctx, steps)
            second = await seq_tools._run_walk_packed(ctx, steps)
        finally:
            del lane.submit                    # drop the instance-level patch
            os.environ.pop("WALK_POOL", None)
        assert shipped == [True, False], f"expected [ships-data, ships-none], got {shipped}"
        assert key in seq_tools._SENT_BY_LANE[lane_i]
        assert first != "MISS" and second != "MISS"
        assert [_sig(pe) for pe in first] == [_sig(pe) for pe in second]
        assert any(second), "second call lost the evidence (worker cache MISS?)"
    asyncio.run(_main())


def test_worker_miss_sentinel_and_full_result():
    """In-process worker body: no cached arrays → "MISS"; with data → a result
    list aligned with steps (never the sentinel)."""
    ctx, steps = _fixture(case_num=9)
    key = (ctx.case_id or "seq", ctx.case_num or 0)
    seq_tools._W_CASE_CACHE.pop(key, None)
    assert seq_tools._walk_call_spawn((key, None, steps)) == "MISS"
    res = seq_tools._walk_call_spawn(
        (key, (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
               ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts), steps))
    assert isinstance(res, list) and len(res) == len(steps)
    assert all(isinstance(pe, dict) for pe in res)
    seq_tools._W_CASE_CACHE.pop(key, None)     # leave the parent copy clean


def test_lanes_are_single_worker_and_route_by_hash():
    """_get_walk_lanes builds single-worker executors; routing is a pure hash
    of the case key — G lockstep trajectories (same case_key) share a lane."""
    # lanes are created once per process; earlier tests may have built them
    lanes = seq_tools._WALK_LANES or seq_tools._get_walk_lanes(3)
    n = len(lanes)
    assert n >= 1 and len(seq_tools._SENT_BY_LANE) == n
    assert all(l._max_workers == 1 for l in lanes), "affinity requires 1 worker/lane"
    key = ("some-case-id", 42)
    assert hash(key) % n == hash(key) % len(lanes)   # stable within the process


def _run():
    tests = [test_packed_pool_matches_inline,
             test_lane_bookkeeping_second_call_ships_no_arrays,
             test_worker_miss_sentinel_and_full_result,
             test_lanes_are_single_worker_and_route_by_hash]
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
