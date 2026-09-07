#!/usr/bin/env bash
# =============================================================================
# SEQ offline-GRPO trainer — per-turn advantage (responsibility decomposition).
# Consumes the SEQ trainer-ready JSONL (kgqa/rl/seq_advantage.py reallocate).
# LoRA r=64 (same as SAPS), 2×GPU ZeRO-2, limer scalar-GRPO loss backend.
#
# VERIFIED config (2026-08-12): max_len=14336 → 98.7% retention (7878/7984),
# peak mem 35.7GB/40GB (fla fast path ON), ~68-87s/step, conv1d stable under ZeRO-2.
# max_len=8192 retains only 84% — DO NOT go below 14336.
#
# Smoke:  MAX_STEPS=4 bash scripts/run_seq_train.sh
# Full:   bash scripts/run_seq_train.sh
# =============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# conda env qwen35: torch 2.11+cu130, transformers 5.14.1, fla 0.5.2,
# causal-conv1d 1.6.2 → Qwen3.5 linear-attn fast path available (verified True).
export LD_LIBRARY_PATH="/usr/local/cuda-13.1/compat:${LD_LIBRARY_PATH:-}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export NCCL_IB_DISABLE=1 NCCL_DEBUG=WARN

DATASET="${DATASET:-/tmp/seq_train_v4.jsonl}"
MODEL="${MODEL:-/zhaoshu/llm/Qwen3.5-9B}"
OUTPUT="${OUTPUT:-checkpoint/seq_grpo_v1}"
MAX_LENGTH="${MAX_LENGTH:-14336}"      # 14336 → 98.7% retention; 8192 only 84%
EPOCHS="${EPOCHS:-1}"
BATCH="${BATCH:-2}"                    # 2/GPU × 2 GPU × 4 accum = eff 16
GRAD_ACCUM="${GRAD_ACCUM:-4}"
LR="${LR:-1e-5}"
MAX_STEPS="${MAX_STEPS:--1}"
WARMUP="${WARMUP:-0.03}"
CONFIG="${CONFIG:-configs/zero2_lora.yaml}"

LOG="/tmp/seq_train_$(date +%Y%m%d_%H%M%S).log"
echo "[seq] dataset=$DATASET output=$OUTPUT batch=$BATCH/GPU eff=$((BATCH*2*GRAD_ACCUM)) lr=$LR max_len=$MAX_LENGTH"
echo "[seq] log→$LOG"

ACCELERATE=/root/miniconda3/envs/qwen35/bin/accelerate

$ACCELERATE launch \
    --config_file "$CONFIG" --num_processes 2 \
    "${PROJECT_ROOT}/kgqa/rl/seq_train_grpo.py" \
        --dataset "$DATASET" --model "$MODEL" --output "$OUTPUT" \
        --max-length "$MAX_LENGTH" --epochs "$EPOCHS" \
        --batch-size "$BATCH" --grad-accum "$GRAD_ACCUM" \
        --lr "$LR" --warmup-ratio "$WARMUP" --max-steps "$MAX_STEPS" \
    2>&1 | tee "$LOG"
echo "[seq] done. checkpoint at $OUTPUT, log at $LOG"
