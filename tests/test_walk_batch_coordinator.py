#!/usr/bin/env python3
"""Round-level walk coordinator (perf2 2026-08-23) — contract tests.

The rollout is round-synchronized; _run_walk_packed now collects a burst of
retrieve_subgraph calls in an ADAPTIVE window (first slice, extended to the
full window only on a second arrival — GTE _collect_batch pattern), dedups
identical (case_key, center, rels) steps, and gives each affine lane ONE
packed multi-case task. This file pins:

  1. DETERMINISM (the ruling constraint): a memo HIT returns the same
     evidence as a fresh execution — memo/dedup may not change results.
  2. multi-case lane task == per-case task: batching cases into one
     _walk_batch_spawn does not perturb per-case walks.
  3. coordinator == legacy lane path == inline path for the same steps
     (WALK_BATCH_WINDOW>0 vs <=0 vs WALK_POOL=0).
  4. same-batch dedup: two concurrent identical requests share one execution
     (worker call count == 1) and get identical results.
  5. adaptive window: a lone request flushes after the FIRST slice only
     (measured wait << full window); a burst extends to the full window.
  6. lane balancing keeps every case's slots together on ONE lane.

Fixture: same validation split as test_walk_pool_packing (lazy-loaded).
Run: python3 tests/test_walk_batch_coordinator.py
"""
import asyncio
import os
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kgqa.agent.loop import build_context
from kgqa.agent import seq_tools

_VAL_PKL = ROOT / "data/cwq_processed/validation_virtuoso_patched.pkl"
_FIXTURE = None


async def _find_fixture():
    """First val sample whose anchor's 1-hop relation yields real evidence —
    plus a SECOND case for the multi-case lane task."""
    val = pickle.loads(_VAL_PKL.read_bytes())
    found = []
    for s in val:
        if not s.get("a_entity"):
            continue
        pilot = {"case_id": s.get("id", ""), "question": s.get("question", ""),
                 "gt_answers": s.get("a_entity", [])}
        ctx = build_context(s, pilot, 0)
        if ctx.anchor_idx is None:
            continue
        rels = {r for h, r, t in zip(ctx.h_ids, ctx.r_ids, ctx.t_ids)
                if h == ctx.anchor_idx or t == ctx.anchor_idx}
        for r in sorted(rels):
            pe = await seq_tools._run_walk_one_step(ctx, ctx.anchor_idx, [r], "f1")
            if pe:
                found.append((s, pilot, (ctx.anchor_idx, [r], "f1")))
                break
        if len(found) == 2:
            break
    return found


def _fixture(idx, case_num):
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = asyncio.run(_find_fixture())
        assert len(_FIXTURE) == 2, "need two single-center fixtures"
    s, pilot, step = _FIXTURE[idx]
    return build_context(s, pilot, case_num), step


def _sig(pe):
    """Deep-comparable signature: label -> (triples, candidates, readable)."""
    return {label: (sorted(str(tr) for tr in (ev.triples or [])),
                    sorted(ev.candidates or []),
                    getattr(ev, "readable", ""))
            for label, ev in (pe or {}).items()}


def _cleanup():
    seq_tools._WALK_BATCH = None
    seq_tools._WALK_CASE_LANE.clear()
    seq_tools._WALK_MEMO.clear()
    for s in seq_tools._SENT_BY_LANE:
        s.clear()
    seq_tools._W_CASE_CACHE.clear()
    for k, v in seq_tools._WALK_BATCH_STATS.items():
        seq_tools._WALK_BATCH_STATS[k] = 0.0 if isinstance(v, float) else 0


def test_memo_hit_matches_fresh_execution():
    """Cross-batch memo: the second call for the same (case, center, rels)
    returns the memoized evidence — identical to a fresh (memo-cleared)
    execution. Deterministic reuse must not change results."""
    _cleanup()
    _fixture(0, case_num=21)          # resolve the search OUTSIDE the loop

    async def _main():
        ctx, step = _fixture(0, case_num=21)
        os.environ.update(WALK_POOL="2", WALK_BATCH_WINDOW="2.0",
                          WALK_BATCH_FIRST="0.05")
        try:
            first = await seq_tools._run_walk_packed(ctx, [step])
            seq_tools._WALK_MEMO.clear()          # force a fresh execution
            fresh = await seq_tools._run_walk_packed(ctx, [step])
            memoed = await seq_tools._run_walk_packed(ctx, [step])  # memo hit
        finally:
            os.environ.pop("WALK_BATCH_WINDOW", None)
            os.environ.pop("WALK_BATCH_FIRST", None)
            os.environ.pop("WALK_POOL", None)
        assert _sig(first[0]) == _sig(fresh[0]) == _sig(memoed[0]), \
            "memo hit diverged from a fresh execution"
        st = seq_tools._WALK_BATCH_STATS
        assert st["memo_hits"] >= 1
    asyncio.run(_main())


def test_batch_spawn_equals_per_case_spawn():
    """The multi-case lane task (_walk_batch_spawn) returns exactly what the
    per-case task (_walk_call_spawn) returns for each case — batching cases
    into one worker task does not perturb the walks."""
    _cleanup()
    ctx_a, step_a = _fixture(0, case_num=22)
    ctx_b, step_b = _fixture(1, case_num=23)
    data_a = (ctx_a.sample, ctx_a.pilot_row, ctx_a.ents, ctx_a.rels,
              ctx_a.h_ids, ctx_a.r_ids, ctx_a.t_ids, ctx_a.rel_texts)
    data_b = (ctx_b.sample, ctx_b.pilot_row, ctx_b.ents, ctx_b.rels,
              ctx_b.h_ids, ctx_b.r_ids, ctx_b.t_ids, ctx_b.rel_texts)
    solo_a = seq_tools._walk_call_spawn(((ctx_a.case_id, 22), data_a, [step_a]))
    solo_b = seq_tools._walk_call_spawn(((ctx_b.case_id, 23), data_b, [step_b]))
    batched = seq_tools._walk_batch_spawn([
        ((ctx_a.case_id, 22), data_a, [step_a]),
        ((ctx_b.case_id, 23), data_b, [step_b])])
    assert _sig(solo_a[0]) == _sig(batched[0][0])
    assert _sig(solo_b[0]) == _sig(batched[1][0])
    seq_tools._W_CASE_CACHE.clear()


def test_coordinator_matches_legacy_paths():
    """Same steps through all three dispatch modes → identical evidence."""
    _cleanup()

    async def _main():
        ctx, step = _fixture(0, case_num=24)
        os.environ["WALK_POOL"] = "0"
        inline = await seq_tools._run_walk_packed(ctx, [step])
        os.environ["WALK_POOL"] = "2"
        os.environ["WALK_BATCH_WINDOW"] = "0"      # legacy lane path
        legacy = await seq_tools._run_walk_packed(ctx, [step])
        os.environ["WALK_BATCH_WINDOW"] = "2.0"
        os.environ["WALK_BATCH_FIRST"] = "0.05"
        coord = await seq_tools._run_walk_packed(ctx, [step])
        os.environ.pop("WALK_BATCH_WINDOW", None)
        os.environ.pop("WALK_BATCH_FIRST", None)
        os.environ.pop("WALK_POOL", None)
        assert _sig(inline[0]) == _sig(legacy[0]) == _sig(coord[0])
    asyncio.run(_main())


def test_same_batch_dedup_shares_one_execution():
    """Two concurrent identical requests → ONE worker call, identical
    results, and the stats count the share."""
    _cleanup()

    async def _main():
        ctx, step = _fixture(0, case_num=25)
        # duplicate the ctx so the two requests are independent objects (as
        # lockstep trajectories are) — same case_key, same arrays
        ctx2 = build_context(ctx.sample, ctx.pilot_row, 25)
        os.environ.update(WALK_POOL="2", WALK_BATCH_WINDOW="2.0",
                          WALK_BATCH_FIRST="0.05")
        lanes = seq_tools._get_walk_lanes(2)
        calls = []

        async def _call(c):
            return await seq_tools._run_walk_packed(c, [step])

        orig_submit = lanes[0].submit

        def _rec(fn, *a, **kw):
            calls.append(fn.__name__)
            return orig_submit(fn, *a, **kw)
        for ln in lanes:
            ln.submit = _rec
        try:
            ra, rb = await asyncio.gather(_call(ctx), _call(ctx2))
        finally:
            for ln in lanes:
                del ln.submit
            os.environ.pop("WALK_BATCH_WINDOW", None)
            os.environ.pop("WALK_BATCH_FIRST", None)
            os.environ.pop("WALK_POOL", None)
        assert _sig(ra[0]) == _sig(rb[0])
        n_spawn = sum(1 for c in calls if c == "_walk_batch_spawn_timed")
        assert n_spawn == 1, f"expected 1 lane task for identical requests, got {n_spawn}"
        st = seq_tools._WALK_BATCH_STATS
        assert st["dedup_shares"] >= 1
    asyncio.run(_main())


def test_adaptive_window_lone_request_no_full_tax():
    """A LONE request must flush after the FIRST slice — its wait must stay
    far below the full window (no fixed full-window delay)."""
    _cleanup()

    async def _main():
        ctx, step = _fixture(0, case_num=26)
        os.environ.update(WALK_POOL="2", WALK_BATCH_WINDOW="5.0",
                          WALK_BATCH_FIRST="0.05")
        try:
            t0 = time.perf_counter()
            await seq_tools._run_walk_packed(ctx, [step])
            dt = time.perf_counter() - t0
        finally:
            os.environ.pop("WALK_BATCH_WINDOW", None)
            os.environ.pop("WALK_BATCH_FIRST", None)
            os.environ.pop("WALK_POOL", None)
        st = seq_tools._WALK_BATCH_STATS
        assert st["batches"] == 1 and st["single"] == 1
        assert dt < 2.0, f"lone request waited {dt:.2f}s — full-window tax leaked"
    asyncio.run(_main())


def test_burst_extends_window_and_keeps_cases_whole():
    """A second arrival within the first slice extends the flush to the full
    window (both requests land in ONE flush), and every case's slots go to
    exactly ONE lane (whole-case packing)."""
    _cleanup()

    async def _main():
        ctx_a, step_a = _fixture(0, case_num=27)
        ctx_b, step_b = _fixture(1, case_num=28)
        os.environ.update(WALK_POOL="2", WALK_BATCH_WINDOW="1.0",
                          WALK_BATCH_FIRST="0.2")

        async def _delayed(c, step, delay):
            await asyncio.sleep(delay)
            return await seq_tools._run_walk_packed(c, [step])

        try:
            ra, rb = await asyncio.gather(
                _delayed(ctx_a, step_a, 0.0),
                _delayed(ctx_b, step_b, 0.05))   # inside the first slice
        finally:
            os.environ.pop("WALK_BATCH_WINDOW", None)
            os.environ.pop("WALK_BATCH_FIRST", None)
            os.environ.pop("WALK_POOL", None)
        st = seq_tools._WALK_BATCH_STATS
        assert st["batches"] == 1 and st["burst"] == 1, \
            f"expected one burst flush, got batches={st['batches']}"
        assert _sig(ra[0]) and _sig(rb[0])       # both produced evidence
        # each case's slots on exactly one lane: case lane map is single-valued
        for ck, lane in seq_tools._WALK_CASE_LANE.items():
            assert isinstance(lane, int) and 0 <= lane < 2
        lanes_used = set(seq_tools._WALK_CASE_LANE.values())
        assert len(lanes_used) <= 2
    asyncio.run(_main())


def test_memo_only_request_skips_lane_task():
    """Once the memo holds a request's every step, a repeat call must issue
    NO lane task (pure in-process resolve) and still return identical
    evidence — the memo-skip perf path (492 memo hits re-executed in the
    first perf2 A/B before this)."""
    _cleanup()
    _fixture(0, case_num=29)          # resolve the search OUTSIDE the loop

    async def _main():
        ctx, step = _fixture(0, case_num=29)
        os.environ.update(WALK_POOL="2", WALK_BATCH_WINDOW="2.0",
                          WALK_BATCH_FIRST="0.05")
        lanes = seq_tools._get_walk_lanes(2)
        submits = []
        orig = {i: lanes[i].submit for i in range(len(lanes))}

        def _patch(li):
            def _sub(fn, *a, **kw):
                submits.append((li, fn.__name__))
                return orig[li](fn, *a, **kw)
            lanes[li].submit = _sub
        try:
            for i in range(len(lanes)):
                _patch(i)
            first = await seq_tools._run_walk_packed(ctx, [step])
            n_after_first = len(submits)
            again = await seq_tools._run_walk_packed(ctx, [step])   # all-memo
        finally:
            for i in range(len(lanes)):
                del lanes[i].submit
            os.environ.pop("WALK_BATCH_WINDOW", None)
            os.environ.pop("WALK_BATCH_FIRST", None)
            os.environ.pop("WALK_POOL", None)
        assert n_after_first >= 1, "first call must submit a lane task"
        assert len(submits) == n_after_first, \
            f"memo-only call submitted {len(submits) - n_after_first} lane tasks"
        assert _sig(first[0]) == _sig(again[0])
    asyncio.run(_main())


def _run():
    tests = [test_memo_hit_matches_fresh_execution,
             test_batch_spawn_equals_per_case_spawn,
             test_coordinator_matches_legacy_paths,
             test_same_batch_dedup_shares_one_execution,
             test_adaptive_window_lone_request_no_full_tax,
             test_burst_extends_window_and_keeps_cases_whole,
             test_memo_only_request_skips_lane_task]
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
