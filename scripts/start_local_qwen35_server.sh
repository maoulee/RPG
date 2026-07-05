#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Resolve interpreter / vllm binary: honor $VENV only when its vllm binary is
# actually present; otherwise fall back to the system PATH binaries (vLLM is
# installed in the base env after the post-reboot upgrade).
VENV="${VENV:-/root/.venv/subgraph}"
if [[ -n "${VENV}" && -x "${VENV}/bin/vllm" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-${VENV}/bin/python}"
  VLLM_BIN="${VLLM_BIN:-${VENV}/bin/vllm}"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
  VLLM_BIN="${VLLM_BIN:-$(command -v vllm)}"
fi

MODEL_PATH="${MODEL_PATH:-/zhaoshu/llm/Qwen3.5-9B}"
MODEL_ALIAS="${MODEL_ALIAS:-Qwen3.5-9B}"
VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_TP_SIZE="${VLLM_TP_SIZE:-2}"
# 65536 leaves headroom for long agent loops: a multi-hop case that runs the
# full decompose→retrieve×N→select→expand→answer sequence (each turn appends
# the tool result + candidate lists) can exceed 32k input tokens. At 32k the
# 1024-token completion budget tips the request over the limit (HTTP 400 on
# cases like "soviet union" / "knight rider" that hit 31745 input). fp8 KV
# cache keeps the larger window affordable.
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-65536}"
VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.90}"
# fp8 KV cache halves the KV-cache memory footprint (the 27B run used fp8 too),
# directly raising the number of concurrent sequences the batch endpoint can serve.
VLLM_KV_CACHE_DTYPE="${VLLM_KV_CACHE_DTYPE:-fp8}"
VLLM_LANGUAGE_MODEL_ONLY="${VLLM_LANGUAGE_MODEL_ONLY:-1}"
VLLM_SKIP_MM_PROFILING="${VLLM_SKIP_MM_PROFILING:-1}"
VLLM_REASONING_PARSER="${VLLM_REASONING_PARSER:-qwen3}"
# Explicit reasoning boundary config. vLLM docs: when --reasoning-parser is set
# WITHOUT --reasoning-config, vLLM "tries to auto-initialize" the boundary
# tokens from the parser. That auto-init is unreliable in tool-call mode
# (--tool-call-parser hermes + --reasoning-parser qwen3 both rewrite the output
# stream and occasionally interfere): the reasoning boundary goes undetected,
# thinking_token_budget's force-inject of reasoning_end_str never fires, and the
# model writes <think> until it hits max_tokens → empty tool_call → max_iters
# (the case 17/20/11 truncation root cause).
# Fix: pass --reasoning-config explicitly so vLLM does NOT rely on auto-init.
# reasoning_end_str carries a short transition phrase (per vLLM docs) so the
# budget cutoff feels natural — the model emits the phrase then </think> and
# proceeds cleanly to the tool_call, rather than a hard mid-thought cutoff.
VLLM_REASONING_CONFIG="${VLLM_REASONING_CONFIG:-{\"reasoning_start_str\":\"<think>\",\"reasoning_end_str\":\"I will now emit the tool call based on the reasoning above.</think>\"}}"
# Tool-calling (agent mode) requires auto-tool-choice + a parser. The Qwen3.5-9B
# chat template emits <tool_call><function=...><parameter=...></tool_call> — the
# standard hermes format — so tool_choice="required" works when these are set.
# Without them, vLLM rejects tool_choice="required" with HTTP 400
# ("requires --tool-call-parser to be set") and the agent loop never starts.
VLLM_ENABLE_AUTO_TOOL_CHOICE="${VLLM_ENABLE_AUTO_TOOL_CHOICE:-1}"
VLLM_TOOL_CALL_PARSER="${VLLM_TOOL_CALL_PARSER:-hermes}"
# Throughput-oriented extensions for the 9B batch deployment:
#  - prefix caching reuses the (large, shared) system prompt across requests
#  - max-num-seqs raises the continuous-batching concurrency ceiling
VLLM_ENABLE_PREFIX_CACHING="${VLLM_ENABLE_PREFIX_CACHING:-1}"
VLLM_MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-256}"
VLLM_USE_MODELSCOPE="${VLLM_USE_MODELSCOPE:-false}"
# Dynamic LoRA: set VLLM_ENABLE_LORA=1 to serve LoRA adapters on top of the
# base model WITHOUT merging (saves ~18GB disk vs merge_and_unload). When
# enabled, clients pass the adapter path as the request "model" field and vLLM
# hot-loads it. max_lora_rank MUST match/exceed the trained rank (we use r=64).
# Default off so normal base-model serving is unaffected.
VLLM_ENABLE_LORA="${VLLM_ENABLE_LORA:-0}"
VLLM_MAX_LORA_RANK="${VLLM_MAX_LORA_RANK:-64}"
VLLM_MAX_LORAS="${VLLM_MAX_LORAS:-2}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"

# Local serving does not need outbound proxy settings.
unset http_proxy https_proxy all_proxy no_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY

# Offline env: the box has no route to huggingface.co, and vLLM's
# maybe_override_with_speculators otherwise tries to resolve a relative
# MODEL_PATH as a HF repo id and crashes on DNS failure. Force local-only.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_USE_MODELSCOPE=false

export CUDA_VISIBLE_DEVICES
export VLLM_USE_MODELSCOPE
export PATH="${VENV}/bin:${PATH}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${VLLM_BIN}" serve "${MODEL_PATH}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  --served-model-name "${MODEL_ALIAS}" \
  --tensor-parallel-size "${VLLM_TP_SIZE}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${VLLM_MAX_MODEL_LEN}" \
  --max-num-seqs "${VLLM_MAX_NUM_SEQS}" \
  --kv-cache-dtype "${VLLM_KV_CACHE_DTYPE}" \
  --reasoning-parser "${VLLM_REASONING_PARSER}" \
  --reasoning-config "${VLLM_REASONING_CONFIG}" \
  --dtype auto \
  --trust-remote-code \
  $( [[ "${VLLM_LANGUAGE_MODEL_ONLY}" == "1" ]] && printf '%s' '--language-model-only' ) \
  $( [[ "${VLLM_SKIP_MM_PROFILING}" == "1" ]] && printf '%s' '--skip-mm-profiling' ) \
  $( [[ "${VLLM_ENABLE_PREFIX_CACHING}" == "1" ]] && printf '%s' '--enable-prefix-caching' ) \
  $( [[ "${VLLM_ENABLE_AUTO_TOOL_CHOICE}" == "1" ]] && printf '%s' "--enable-auto-tool-choice --tool-call-parser ${VLLM_TOOL_CALL_PARSER}" ) \
  $( [[ "${VLLM_ENABLE_LORA}" == "1" ]] && printf '%s' "--enable-lora --max-lora-rank ${VLLM_MAX_LORA_RANK} --max-loras ${VLLM_MAX_LORAS}" ) \
  "$@"
