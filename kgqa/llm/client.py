"""Low-level LLM client functions for the KGQA pipeline.

Provides `call_llm()` for coalesced batch-optimized calls and
`_call_single_direct()` for single-shot requests.
"""
from __future__ import annotations

import asyncio
import os

import aiohttp

# ---------------------------------------------------------------------------
# Configuration — mirrors the constants in the monolith until kgqa.core.config
# is established.
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _completion_url(raw_url: str) -> str:
    url = raw_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


_RAW_LLM_API_URL = os.getenv("KGQA_LLM_API_URL", os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"))
LLM_API_URL = _completion_url(_RAW_LLM_API_URL)
LLM_MODEL = os.getenv("KGQA_MODEL_NAME", os.getenv("KGQA_LLM_MODEL", "Qwen3.5-9B"))
LLM_API_KEY = os.getenv("KGQA_LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_TIMEOUT_SEC = _env_float("KGQA_LLM_TIMEOUT_SEC", 120.0)
LLM_TEMPERATURE = _env_float("KGQA_LLM_TEMPERATURE", 0.3)
LLM_TOP_P = _env_float("KGQA_LLM_TOP_P", 0.8)

_LOCAL_API = any(host in LLM_API_URL for host in ("localhost", "127.0.0.1", "0.0.0.0"))
SEND_CHAT_TEMPLATE_KWARGS = _env_bool("KGQA_LLM_SEND_CHAT_TEMPLATE_KWARGS", _LOCAL_API)
ENABLE_THINKING = _env_bool("KGQA_ENABLE_THINKING", False)
USE_BATCH_ENDPOINT = _env_bool("KGQA_LLM_USE_BATCH_ENDPOINT", _LOCAL_API)


def batch_api_url() -> str:
    """Return the local vLLM-style batch endpoint for chat completions."""
    return LLM_API_URL.replace("/chat/completions", "/chat/completions/batch")


def request_headers() -> dict:
    """Headers for OpenAI-compatible services."""
    if LLM_API_KEY and LLM_API_KEY != "EMPTY":
        return {"Authorization": f"Bearer {LLM_API_KEY}"}
    return {}


def build_payload(messages, max_tokens: int, temperature: float | None = None,
                  top_p: float | None = None) -> dict:
    """Build a chat-completions payload shared by single and batch clients."""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        "top_p": LLM_TOP_P if top_p is None else top_p,
    }
    if SEND_CHAT_TEMPLATE_KWARGS:
        payload["chat_template_kwargs"] = {"enable_thinking": ENABLE_THINKING}
    return payload


async def _call_single_direct(
    session: aiohttp.ClientSession,
    messages: list,
    max_tokens: int = 500,
    temperature: float | None = None,
    top_p: float | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Direct single LLM call (no coalescing).

    Used by ``batch_call_llm`` for single-item fallback.
    """
    payload = build_payload(messages, max_tokens, temperature=temperature, top_p=top_p)
    async with session.post(
        LLM_API_URL,
        headers=request_headers(),
        json=payload,
        timeout=aiohttp.ClientTimeout(total=timeout_seconds or LLM_TIMEOUT_SEC),
    ) as resp:
        if resp.status >= 400:
            body = await resp.text()
            raise RuntimeError(f"LLM request failed with HTTP {resp.status}: {body[:500]}")
        data = await resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM response has no choices: {str(data)[:500]}")
    return data["choices"][0]["message"]["content"]


class _BatchCoalescer:
    """Coalesces concurrent call_llm requests into batch API calls.

    When multiple call_llm calls arrive within a short collection window,
    they are merged into a single /v1/chat/completions/batch request.
    This avoids GPU contention between independent LLM requests.
    """

    _BATCH_WINDOW = 0.05  # 50ms collection window
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._pending: list = []  # list of (messages, max_tokens, future)
        self._timer = None
        self._lock = asyncio.Lock()

    async def submit(self, session, messages, max_tokens=500, retries=3):
        """Submit a request. Returns response string."""
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        async with self._lock:
            self._pending.append((session, messages, max_tokens, retries, fut))
            if self._timer is None or self._timer.done():
                self._timer = asyncio.ensure_future(self._flush_after_window())
        return await fut

    async def _flush_after_window(self):
        await asyncio.sleep(self._BATCH_WINDOW)
        await self._flush()

    async def _flush(self):
        async with self._lock:
            batch = self._pending[:]
            self._pending.clear()

        if not batch:
            return

        # Group by (session, max_tokens) — same params can share a batch
        groups: dict = {}
        for session, messages, max_tokens, retries, fut in batch:
            key = (id(session), max_tokens)
            groups.setdefault(key, []).append((session, messages, max_tokens, retries, fut))

        for key, items in groups.items():
            session = items[0][0]
            max_tokens = items[0][2]
            retries = items[0][3]

            if len(items) == 1 or not USE_BATCH_ENDPOINT:
                # Single request — use normal endpoint
                async def _run_one(item):
                    _, messages, _, _, fut = item
                    try:
                        result = await self._call_single(session, messages, max_tokens, retries)
                        if not fut.done():
                            fut.set_result(result)
                    except Exception:
                        if not fut.done():
                            fut.set_result("")
                await asyncio.gather(*[_run_one(item) for item in items])
            else:
                # Multiple requests — use batch endpoint
                messages_list = [m for _, m, _, _, _ in items]
                futs = [f for _, _, _, _, f in items]
                try:
                    results = await self._call_batch(session, messages_list, max_tokens, retries)
                    for f, r in zip(futs, results):
                        if not f.done():
                            f.set_result(r)
                except Exception:
                    # Fallback: individual calls
                    async def _fallback_one(item):
                        _, messages, _, _, fut = item
                        if fut.done():
                            return
                        try:
                            r = await self._call_single(session, messages, max_tokens, retries)
                            fut.set_result(r)
                        except Exception:
                            fut.set_result("")
                    await asyncio.gather(*[_fallback_one(item) for item in items])

    @staticmethod
    async def _call_single(session, messages, max_tokens, retries):
        payload = build_payload(messages, max_tokens)
        for attempt in range(retries):
            try:
                async with session.post(
                    LLM_API_URL,
                    headers=request_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=LLM_TIMEOUT_SEC),
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"LLM request failed with HTTP {resp.status}: {body[:500]}")
                    data = await resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"LLM response has no choices: {str(data)[:500]}")
                return choices[0]["message"]["content"]
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise

    @staticmethod
    async def _call_batch(session, messages_list, max_tokens, retries):
        payload = build_payload(messages_list, max_tokens)
        for attempt in range(retries):
            try:
                async with session.post(
                    batch_api_url(),
                    headers=request_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=max(LLM_TIMEOUT_SEC, 120.0)),
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"LLM batch request failed with HTTP {resp.status}: {body[:500]}")
                    data = await resp.json()
                results = [None] * len(messages_list)
                for choice in data.get("choices", []):
                    idx = choice["index"]
                    if 0 <= idx < len(messages_list):
                        results[idx] = choice["message"]["content"]
                # Fill any missing results with individual calls
                for i, r in enumerate(results):
                    if r is None:
                        results[i] = await _BatchCoalescer._call_single(
                            session, messages_list[i], max_tokens, retries)
                return results
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise


async def call_llm(
    session: aiohttp.ClientSession,
    messages: list,
    max_tokens: int = 500,
    retries: int = 3,
) -> str:
    """LLM call with automatic request coalescing for batch optimization."""
    return await _BatchCoalescer.get().submit(session, messages, max_tokens, retries)
