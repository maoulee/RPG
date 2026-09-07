#!/usr/bin/env python3
"""Unit tests for the GTE server's /retrieve_batch + response cache
(perf phase 3, 2026-08-23).

  1. CONSISTENCY (the ruling constraint): /retrieve_batch returns EXACTLY
     what /retrieve returns for the same items — same pools (value-shipped
     and pool_key), same queries, same top_k/instruct.
  2. response cache: a repeat answers with zero new encodes; the cache is
     shared across both endpoints; different top_k never conflates.
  3. pool_key registration inside ONE batch: a key-only item may arrive in
     the same batch as (and after) its registering item.
  4. batch encode shape: the misses' unique queries go through ONE merged
     encode call; unique pools encode once regardless of request count.

No model is touched: _encode is swapped for a text-seeded deterministic
embedding; srv.model is stubbed only for .config.hidden_size. The real
inference worker thread runs the fake through the normal queue path.

Run: python3 tests/test_gte_batch_endpoint.py   (or pytest tests/test_gte_batch_endpoint.py)
"""
import asyncio
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gte_api_server as srv


DIM = 8


def _fake_encode(texts, batch_size=64, max_length=128):
    """Text-seeded deterministic unit vectors: same text → same vector,
    independent of batch composition (the consistency the real fp16 path
    gets from the embedding cache)."""
    srv._ENCODE_CALLS.append(list(texts))
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        seed = int(hashlib.md5(t.encode()).hexdigest()[:8], 16)
        out[i] = np.random.default_rng(seed).standard_normal(DIM)
    out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
    return out


def _reset():
    srv._ENCODE_CALLS = []
    srv._encode = _fake_encode
    srv.model = SimpleNamespace(config=SimpleNamespace(hidden_size=DIM))
    srv.emb_cache.clear()
    srv._pool_registry.clear()
    srv._RESP_CACHE.clear()
    with srv._SRV_STATS_LOCK:
        for k in srv._SRV_STATS:
            srv._SRV_STATS[k] = 0


def _batch(items):
    return asyncio.run(srv.retrieve_batch(
        srv.RetrieveBatchRequest(items=[srv.RetrieveRequest(**it) for it in items])))


def _one(item):
    return asyncio.run(srv.retrieve(srv.RetrieveRequest(**item)))


CANDS = ["people.person.place_of_birth", "people.person.nationality",
         "location.location.containedby", "film.film.country"]
TEXTS = ["person birth place", "person nationality", "place contained by", "movie country"]


def test_batch_equals_per_request_value_pool():
    """Same input → identical results, item by item (batch vs /retrieve)."""
    _reset()
    items = [
        {"query": q, "candidates": CANDS, "candidate_texts": TEXTS, "top_k": 3}
        for q in ("where was he born", "what country is it in", "where was he born")
    ]
    br = _batch(items).results
    for it, rows in zip(items, br):
        sr = _one(it).results            # resp cache cleared per _reset only;
        assert rows == sr, f"{it['query']}: batch != per-request"
    # the repeated query resolves identically (one unique query encode)
    assert br[0] == br[2]
    with srv._SRV_STATS_LOCK:
        assert srv._SRV_STATS["batch_calls"] == 1
        assert srv._SRV_STATS["batch_items"] == 3


def test_batch_equals_per_request_pool_key_mode():
    """pool_key mode: register + query-by-key in ONE batch, then a second
    batch with key-only items — all identical to /retrieve. The response
    cache is cleared before each /retrieve so the comparison exercises real
    recomputation, not a cache hit (this is what caught the label-mode bug:
    a key-only item's rows must carry the STORED-TEXT labels, exactly like
    /retrieve, not the registering item's candidates)."""
    _reset()
    b1 = _batch([
        {"query": "q1", "candidates": CANDS, "candidate_texts": TEXTS,
         "top_k": 2, "instruct": "custom instruct", "pool_key": "pk1"},
        {"query": "q2", "candidates": [], "top_k": 2,
         "instruct": "custom instruct", "pool_key": "pk1"},   # key-only sibling
    ]).results
    srv._RESP_CACHE.clear()                  # defeat the shared response cache
    one_reg = _one({"query": "q1", "candidates": CANDS, "candidate_texts": TEXTS,
                    "top_k": 2, "instruct": "custom instruct", "pool_key": "pk1"}).results
    assert b1[0] == one_reg, "registering item: batch != per-request"
    srv._RESP_CACHE.clear()
    one_key = _one({"query": "q2", "candidates": [], "top_k": 2,
                    "instruct": "custom instruct", "pool_key": "pk1"}).results
    assert b1[1] == one_key, "key-only item: batch != per-request"
    # the two modes label rows differently (pre-existing /retrieve semantics)
    assert [r["candidate"] for r in one_reg] != [r["candidate"] for r in one_key] \
        or CANDS == TEXTS
    # second batch: key-only, pool still registered — and now cache-hit parity
    srv._RESP_CACHE.clear()
    b2 = _batch([{"query": "q2", "candidates": [], "top_k": 2,
                  "instruct": "custom instruct", "pool_key": "pk1"}]).results
    assert b2[0] == one_key


def test_pool_registration_order_inside_batch():
    """A key-only item listed BEFORE its registering item still resolves
    (the registration pass runs first)."""
    _reset()
    rows = _batch([
        {"query": "q-key-only", "candidates": [], "top_k": 2, "pool_key": "pk2"},
        {"query": "q-register", "candidates": CANDS, "candidate_texts": TEXTS,
         "top_k": 2, "pool_key": "pk2"},
    ]).results
    assert len(rows[0]) == 2 and len(rows[1]) == 2
    assert all(r["text"] in TEXTS for r in rows[0] + rows[1])


def test_response_cache_zero_encode_on_hit():
    """Repeat (either endpoint) → zero new _encode calls."""
    _reset()
    item = {"query": "cache me", "candidates": CANDS, "candidate_texts": TEXTS, "top_k": 3}
    _one(item)
    n_after_first = len(srv._ENCODE_CALLS)
    assert n_after_first > 0
    _one(dict(item))                       # per-request repeat
    b = _batch([dict(item), {"query": "cache me too", "candidates": CANDS,
                             "candidate_texts": TEXTS, "top_k": 3}]).results
    assert len(srv._ENCODE_CALLS) == n_after_first + 1   # only the new query
    assert len(b[0]) == 3 and len(b[1]) == 3
    with srv._SRV_STATS_LOCK:
        hits = srv._SRV_STATS["resp_cache_hits"]
    assert hits == 2, f"expected 2 response-cache hits (retrieve+batch), got {hits}"


def test_response_cache_shared_across_endpoints():
    """Warm via /retrieve → /retrieve_batch hits (and vice versa)."""
    _reset()
    item = {"query": "shared", "candidates": CANDS, "candidate_texts": TEXTS, "top_k": 2}
    expect = _one(item).results
    n = len(srv._ENCODE_CALLS)
    got = _batch([dict(item)]).results
    assert got[0] == expect
    assert len(srv._ENCODE_CALLS) == n    # hit: nothing encoded
    # warm via batch → per-request hit
    item2 = {"query": "shared2", "candidates": CANDS, "candidate_texts": TEXTS, "top_k": 2}
    expect2 = _batch([dict(item2)]).results[0]
    n = len(srv._ENCODE_CALLS)
    assert _one(dict(item2)).results == expect2
    assert len(srv._ENCODE_CALLS) == n


def test_cache_never_conflates_top_k_or_instruct():
    """(pool, query) with different top_k/instruct are distinct cache keys."""
    _reset()
    base = {"query": "q", "candidates": CANDS, "candidate_texts": TEXTS}
    r2 = _one({**base, "top_k": 2}).results
    r3 = _one({**base, "top_k": 3}).results
    assert len(r2) == 2 and len(r3) == 3
    b = _batch([{**base, "top_k": 2}, {**base, "top_k": 3},
                {**base, "top_k": 2, "instruct": "other"}]).results
    assert b[0] == r2 and b[1] == r3 and len(b[2]) == 2
    assert b[2] == _one({**base, "top_k": 2, "instruct": "other"}).results


def test_batch_merged_query_encode():
    """All miss queries encode in ONE call; the pool encodes once per unique
    pool even when several items score it."""
    _reset()
    items = [{"query": f"query-{i}", "candidates": CANDS,
              "candidate_texts": TEXTS, "top_k": 2} for i in range(4)]
    _batch(items)
    query_calls = [c for c in srv._ENCODE_CALLS
                   if all(t.startswith("Instruct:") for t in c)]
    cand_calls = [c for c in srv._ENCODE_CALLS
                  if not all(t.startswith("Instruct:") for t in c)]
    assert len(query_calls) == 1 and len(query_calls[0]) == 4
    assert len(cand_calls) == 1 and cand_calls[0] == TEXTS   # pool dedup by sig


def test_value_pool_identity_keyed_by_candidates():
    """Same query/top_k but a DIFFERENT candidate list is a different pool —
    no cross-pool cache pollution."""
    _reset()
    short = ["a.b.c", "d.e.f"]
    r_full = _one({"query": "q", "candidates": CANDS, "top_k": 4}).results
    r_short = _one({"query": "q", "candidates": short, "top_k": 4}).results
    assert [r["candidate"] for r in r_full] != [r["candidate"] for r in r_short]
    b = _batch([{"query": "q", "candidates": short, "top_k": 4}]).results
    assert b[0] == r_short


def _run():
    tests = [test_batch_equals_per_request_value_pool,
             test_batch_equals_per_request_pool_key_mode,
             test_pool_registration_order_inside_batch,
             test_response_cache_zero_encode_on_hit,
             test_response_cache_shared_across_endpoints,
             test_cache_never_conflates_top_k_or_instruct,
             test_batch_merged_query_encode,
             test_value_pool_identity_keyed_by_candidates]
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
