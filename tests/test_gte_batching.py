#!/usr/bin/env python3
"""Unit tests for the GTE server's dynamic-batching layer (perf pack 2026-08-22).

  - _collect_batch: the ADAPTIVE two-stage window — empty queue starts
    computing after the short FIRST_SLICE (no full-window tax); an arrival
    within the slice extends the deadline to the full window (cluster
    coalescing intact); EARLY-CLOSE caps merged texts; window<=0 drains
    without waiting (and without consulting the clock);
  - _merge_jobs: same-(batch_size,max_length) jobs coalesce into ONE _encode
    call with correctly sliced results — the grouping /retrieve's query path
    (bs=32, ml=MAX_QUERY_LEN) now relies on.

No model is touched: _encode is swapped for a recorder; the real inference
worker thread stays idle on its empty queue.

Run: python3 tests/test_gte_batching.py   (or pytest tests/test_gte_batching.py)
"""
import queue
import sys
from concurrent.futures import Future
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gte_api_server as srv


class _Clock:
    """Scripted monotonic clock; repeats the last tick once the script runs out
    (a repeated past-deadline tick keeps the collector in break territory)."""

    def __init__(self, *ticks):
        self._ticks = list(ticks)
        self.calls = 0

    def __call__(self):
        v = self._ticks[min(self.calls, len(self._ticks) - 1)]
        self.calls += 1
        return v


def _mk(texts, bs, ml):
    return (list(texts), bs, ml, Future(), 0.0)   # t_submit=0 (stats attribution)


def test_collect_batch_empty_queue_starts_immediately():
    """No arrival within the first slice → single-job batch, no full-window wait."""
    q = queue.Queue()
    q.put(_mk(["a"], 32, 256))
    clk = _Clock(0.0, 0.006)                       # probe at 6ms > 5ms slice
    jobs = srv._collect_batch(q, window_s=0.015, first_s=0.005, early_n=256,
                              clock=clk)
    assert len(jobs) == 1 and jobs[0][0] == ["a"]


def test_collect_batch_arrival_extends_to_full_window():
    """An arrival within the first slice extends the deadline to the full
    window (from the first job) — later arrivals up to 15ms still coalesce."""
    q = queue.Queue()
    q.put(_mk(["a"], 32, 256))
    q.put(_mk(["b"], 32, 256))
    q.put(_mk(["c"], 32, 256))
    q.put(_mk(["late"], 32, 256))                  # queued but past full window
    clk = _Clock(0.0, 0.002, 0.010, 0.020)
    jobs = srv._collect_batch(q, window_s=0.015, first_s=0.005, early_n=256,
                              clock=clk)
    assert [j[0] for j in jobs] == [["a"], ["b"], ["c"]]


def test_collect_batch_early_close():
    """EARLY-CLOSE: a first job already at/over the text cap skips collection."""
    q = queue.Queue()
    q.put(_mk(["t"] * 300, 32, 256))
    q.put(_mk(["more"], 32, 256))
    jobs = srv._collect_batch(q, window_s=0.015, first_s=0.005, early_n=256,
                              clock=_Clock(0.0))
    assert len(jobs) == 1 and len(jobs[0][0]) == 300


def test_collect_batch_window_zero_drains_nowait():
    """window_s<=0 disables waiting entirely (legacy drain) — and never reads
    the clock."""
    q = queue.Queue()
    for t in ("a", "b", "c"):
        q.put(_mk([t], 32, 256))
    clk = _Clock()
    jobs = srv._collect_batch(q, window_s=0.0, first_s=0.005, early_n=256,
                              clock=clk)
    assert [j[0] for j in jobs] == [["a"], ["b"], ["c"]]
    assert clk.calls == 0


def test_merge_jobs_coalesces_same_params_and_slices():
    """Same-(bs,ml) jobs flatten into ONE _encode call; results slice back to
    each future; different (bs,ml) groups stay separate encodes."""
    calls = []

    def _fake_encode(texts, batch_size=64, max_length=128):
        calls.append((list(texts), batch_size, max_length))
        return np.arange(len(texts) * 4, dtype=np.float32).reshape(len(texts), 4)

    orig = srv._encode
    srv._encode = _fake_encode
    try:
        jq1 = _mk(["q1", "q2"], 32, 256)           # the /retrieve query group
        jq2 = _mk(["q3"], 32, 256)
        jc = _mk(["c1", "c2", "c3"], 64, 128)      # the candidate group
        srv._merge_jobs([jq1, jq2, jc])
    finally:
        srv._encode = orig
    assert len(calls) == 2, f"expected one encode per param group, got {len(calls)}"
    by_params = {(bs, ml): texts for texts, bs, ml in calls}
    assert by_params[(32, 256)] == ["q1", "q2", "q3"]
    assert by_params[(64, 128)] == ["c1", "c2", "c3"]
    # slice distribution: query group flattened in submission order
    assert jq1[3].result().shape == (2, 4)
    assert jq2[3].result().shape == (1, 4)
    np.testing.assert_array_equal(jq1[3].result(), np.arange(8).reshape(2, 4))
    np.testing.assert_array_equal(jq2[3].result()[0], np.arange(8, 12))
    assert jc[3].result().shape == (3, 4)


def _run():
    tests = [test_collect_batch_empty_queue_starts_immediately,
             test_collect_batch_arrival_extends_to_full_window,
             test_collect_batch_early_close,
             test_collect_batch_window_zero_drains_nowait,
             test_merge_jobs_coalesces_same_params_and_slices]
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
