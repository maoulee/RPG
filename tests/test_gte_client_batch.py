#!/usr/bin/env python3
"""Unit tests for the client-side round-level GTE request collector
(kgqa/stages/stage2_entity.py, perf phase 3, 2026-08-23).

  1. DETERMINISM (the ruling constraint): same (pool, query, top_k,
     instruct) → the SAME result object — in-flight dedup and the completed
     memo both hand back one shared list; callers treat rows as read-only.
  2. batching: a burst collects into ONE /retrieve_batch POST with results
     distributed back per request; a LONE request flushes after the FIRST
     slice only (no full-window tax); a second arrival within the slice
     extends to the full window.
  3. fallback: a missing /retrieve_batch (stale server, 404) degrades to
     the legacy per-request /retrieve path; a failed transport raises to
     every waiter (callers' retry loops own recovery).
  4. legacy mode (GTE_CLIENT_BATCH_WINDOW<=0) keeps the old per-request
     payload, byte-for-byte semantics.
  5. memo is bounded (LRU eviction) and keyed by the full request identity.

No HTTP: a fake aiohttp session records posts and answers deterministically.

Run: python3 tests/test_gte_client_batch.py   (or pytest tests/test_gte_client_batch.py)
"""
import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kgqa.stages.stage2_entity as m


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Deterministic GTE answers: rows ranked by md5(candidate+query), so
    every request's result is a pure function of its payload."""

    def __init__(self, batch_status=200, fail_batch=False):
        self.calls = []                     # (url, payload)
        self.batch_status = batch_status
        self.fail_batch = fail_batch

    def _rows(self, query, candidates, cand_texts, top_k):
        texts = cand_texts if cand_texts else candidates
        order = sorted(range(len(candidates)),
                       key=lambda i: hashlib.md5(
                           (candidates[i] + "#" + query).encode()).hexdigest())
        return [{"index": i, "candidate": candidates[i],
                 "text": texts[i], "score": 1.0 - j * 0.01}
                for j, i in enumerate(order[:min(top_k, len(candidates))])]

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if url.endswith("/retrieve_batch"):
            if self.fail_batch:
                raise ConnectionResetError("simulated reset")
            if self.batch_status != 200:
                return _FakeResp(self.batch_status, {"detail": "Not Found"})
            items = json["items"]
            return _FakeResp(200, {"results": [
                self._rows(it["query"], it["candidates"],
                           it.get("candidate_texts"), it["top_k"])
                for it in items]})
        p = json
        return _FakeResp(200, {"results": self._rows(
            p["query"], p["candidates"], p.get("candidate_texts"), p["top_k"])})

    def batch_items(self):
        return [len(p["items"]) for u, p in self.calls
                if u.endswith("/retrieve_batch")]

    def n_retrieve(self):
        return sum(1 for u, _ in self.calls if u.endswith("/retrieve"))


def _reset(**env):
    m._GTE_REQ_BATCH = None
    m._GTE_MEMO.clear()
    m._GTE_MEMO_MAX = 50000
    for k in list(m._GTE_BATCH_STATS):
        m._GTE_BATCH_STATS[k] = 0.0 if isinstance(m._GTE_BATCH_STATS[k], float) else 0
    saved = {k: os.environ.get(k) for k in
             ("GTE_CLIENT_BATCH_WINDOW", "GTE_CLIENT_BATCH_FIRST",
              "GTE_CLIENT_MEMO_MAX")}
    os.environ.update(env)
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


CANDS = ["people.person.place_of_birth", "location.location.containedby",
         "film.film.country"]


def test_same_key_concurrent_shares_one_object_and_one_item():
    """Two in-flight identical requests → ONE server item, SAME result list."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession()

        async def go():
            r1, r2 = await asyncio.gather(
                m.gte_retrieve(s, "born where", CANDS, top_k=2),
                m.gte_retrieve(s, "born where", list(CANDS), top_k=2))
            return r1, r2

        r1, r2 = asyncio.run(go())
        assert r1 is r2, "same-key concurrent requests must share one object"
        assert s.batch_items() == [1], f"expected one 1-item batch, got {s.calls}"
        assert m._GTE_BATCH_STATS["dedup"] == 1
    finally:
        _restore(saved)


def test_memo_repeat_returns_same_object_no_http():
    """Sequential repeat → memo hit, identical object, zero new posts."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession()
        r1 = asyncio.run(m.gte_retrieve(s, "born where", CANDS, top_k=2))
        n = len(s.calls)
        r2 = asyncio.run(m.gte_retrieve(s, "born where", CANDS, top_k=2))
        assert r1 is r2
        assert len(s.calls) == n, "memo hit must not POST"
        assert m._GTE_BATCH_STATS["memo_hits"] == 1
        # a reworded query (different key) is NOT served by that memo entry
        asyncio.run(m.gte_retrieve(s, "born where exactly", CANDS, top_k=2))
        assert len(s.calls) == n + 1
    finally:
        _restore(saved)


def test_distinct_requests_map_back_correctly():
    """Distinct queries in one flush get their OWN rows back (order-safe
    distribution)."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession()

        async def go():
            return await asyncio.gather(
                m.gte_retrieve(s, "q-alpha", CANDS, top_k=2),
                m.gte_retrieve(s, "q-beta", CANDS, top_k=3),
                m.gte_retrieve(s, "q-alpha", CANDS, top_k=2))

        ra, rb, ra3 = asyncio.run(go())
        assert s.batch_items() == [2]      # q-alpha×2 dedup + q-beta
        assert ra is ra3                   # same key → same object
        assert len(ra) == 2 and len(rb) == 3 and len(ra3) == 2
        # each result must be the pure function of ITS request payload
        exp_a = s._rows("q-alpha", CANDS, None, 2)
        exp_b = s._rows("q-beta", CANDS, None, 3)
        assert [r["candidate"] for r in ra] == [r["candidate"] for r in exp_a]
        assert [r["candidate"] for r in rb] == [r["candidate"] for r in exp_b]
    finally:
        _restore(saved)


def test_lone_request_flushes_after_first_slice_only():
    """A single request pays only the FIRST slice — not the full window."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5.0", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession()
        t0 = time.perf_counter()
        r = asyncio.run(m.gte_retrieve(s, "lone query", CANDS, top_k=2))
        dt = time.perf_counter() - t0
        assert len(r) == 2
        assert dt < 2.0, f"lone request waited {dt:.2f}s — full-window tax leaked"
        assert s.batch_items() == [1]
        assert m._GTE_BATCH_STATS["single"] == 1
    finally:
        _restore(saved)


def test_burst_extends_to_full_window():
    """A second arrival within the first slice extends the deadline: both
    land in ONE flush instead of two."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="1.0", GTE_CLIENT_BATCH_FIRST="0.2")
    try:
        s = _FakeSession()

        async def go():
            async def second():
                await asyncio.sleep(0.1)   # inside the 0.2s first slice
                return await m.gte_retrieve(s, "q-two", CANDS, top_k=1)
            return await asyncio.gather(
                m.gte_retrieve(s, "q-one", CANDS, top_k=1), second())

        r1, r2 = asyncio.run(go())
        assert len(r1) == 1 and len(r2) == 1
        assert s.batch_items() == [2], (
            f"burst did not coalesce: {[ (u, p) for u, p in s.calls ]}")
        assert m._GTE_BATCH_STATS["burst"] == 1
    finally:
        _restore(saved)


def test_pool_key_registration_then_key_only_share_pool():
    """The registering call and the key-only sibling land in one batch; the
    batch payload carries candidates only on the registering item."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession()

        async def go():
            return await asyncio.gather(
                m.gte_retrieve(s, "register", CANDS, top_k=2, pool_key="pk"),
                m.gte_retrieve(s, "reuse", [], top_k=2, pool_key="pk"))

        asyncio.run(go())
        items = s.calls[0][1]["items"]
        assert items[0]["candidates"] == CANDS and items[0]["pool_key"] == "pk"
        assert items[1]["candidates"] == [] and items[1]["pool_key"] == "pk"
    finally:
        _restore(saved)


def test_missing_endpoint_falls_back_to_per_request():
    """404 from /retrieve_batch (stale server) → legacy /retrieve per item."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        s = _FakeSession(batch_status=404)

        async def go():
            return await asyncio.gather(
                m.gte_retrieve(s, "q-a", CANDS, top_k=2),
                m.gte_retrieve(s, "q-b", CANDS, top_k=2))

        ra, rb = asyncio.run(go())
        assert s.n_retrieve() == 2         # every item re-sent per-request
        assert len(ra) == 2 and len(rb) == 2
        assert m._GTE_BATCH_STATS["fallback"] == 1
    finally:
        _restore(saved)


def test_transport_failure_raises_to_every_waiter():
    """A failed batch transport (non-404) also falls back per-request; if
    THAT fails too, every waiter sees the exception (caller retries own it)."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.05")
    try:
        class _Dead(_FakeSession):
            def post(self, url, json=None, timeout=None):
                self.calls.append((url, json))
                raise ConnectionResetError("server gone")

        s = _Dead()

        async def go():
            return await asyncio.gather(
                m.gte_retrieve(s, "q-a", CANDS, top_k=2),
                m.gte_retrieve(s, "q-b", CANDS, top_k=2),
                return_exceptions=True)

        res = asyncio.run(go())
        assert all(isinstance(r, ConnectionResetError) for r in res)
        assert not m._GTE_MEMO, "failed requests must not poison the memo"
    finally:
        _restore(saved)


def test_legacy_window_zero_keeps_per_request_path():
    """GTE_CLIENT_BATCH_WINDOW<=0 → the old direct POST, same payload shape."""
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="0")
    try:
        s = _FakeSession()
        r = asyncio.run(m.gte_retrieve(s, "legacy", CANDS,
                                       candidate_texts=["t"] * 3, top_k=2,
                                       pool_key="lpk"))
        assert s.calls[0][0].endswith("/retrieve")
        p = s.calls[0][1]
        assert p["query"] == "legacy" and p["candidates"] == CANDS
        assert p["candidate_texts"] == ["t"] * 3 and p["top_k"] == 2
        assert p["instruct"] == m.GTE_INSTRUCT
        assert p["pool_key"] == "lpk" and len(p) == 6
        assert len(r) == 2
        # memo/dedup inactive on this path
        asyncio.run(m.gte_retrieve(s, "legacy", CANDS,
                                   candidate_texts=["t"] * 3, top_k=2,
                                   pool_key="lpk"))
        assert s.n_retrieve() == 2 and m._GTE_BATCH_STATS["reqs"] == 0
    finally:
        _restore(saved)


def test_memo_bounded_lru_evicts_oldest():
    saved = _reset(GTE_CLIENT_BATCH_WINDOW="5", GTE_CLIENT_BATCH_FIRST="0.02")
    try:
        m._GTE_MEMO_MAX = 2
        s = _FakeSession()
        asyncio.run(m.gte_retrieve(s, "q1", CANDS, top_k=1))
        asyncio.run(m.gte_retrieve(s, "q2", CANDS, top_k=1))
        asyncio.run(m.gte_retrieve(s, "q3", CANDS, top_k=1))   # evicts q1
        assert len(m._GTE_MEMO) == 2
        asyncio.run(m.gte_retrieve(s, "q1", CANDS, top_k=1))   # re-POSTs
        assert len(s.calls) == 4
        assert set(k[1] for k in m._GTE_MEMO) == {"q3", "q1"}
    finally:
        _restore(saved)


def _run():
    tests = [test_same_key_concurrent_shares_one_object_and_one_item,
             test_memo_repeat_returns_same_object_no_http,
             test_distinct_requests_map_back_correctly,
             test_lone_request_flushes_after_first_slice_only,
             test_burst_extends_to_full_window,
             test_pool_key_registration_then_key_only_share_pool,
             test_missing_endpoint_falls_back_to_per_request,
             test_transport_failure_raises_to_every_waiter,
             test_legacy_window_zero_keeps_per_request_path,
             test_memo_bounded_lru_evicts_oldest]
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
