#!/usr/bin/env bash
# =============================================================================
# ROUTED scalar-GRPO — a/b/c routing baked offline into (train_stages, advantage).
# All examples use SCALAR advantage → LigerFusedLinearGRPOLoss (no logits
# materialized) → memory headroom for batch=2/GPU (~2x throughput vs batch=1).
#
# Dataset: data/offline_grpo/full3k_split/routed_train.jsonl
#   (route_cases.py → build_routed_dataset.py)
#
# Smoke:  MAX_STEPS=4 OUTPUT=checkpoint/routed_smoke bash scripts/run_routed.sh
# Full:   bash scripts/run_routed.sh
# =============================================================================
set -euo pipefail
export LD_LIBRARY_PATH="/root/miniconda3/lib/python3.10/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export NCCL_IB_DISABLE=1 NCCL_DEBUG=WARN
cd /zhaoshu/subgraph

DATASET="${DATASET:-data/offline_grpo/full3k_split/routed_train.jsonl}"
MODEL="/zhaoshu/llm/Qwen3.5-9B"
OUTPUT="${OUTPUT:-checkpoint/routed_256}"
MAX_LENGTH="${MAX_LENGTH:-14336}"
EPOCHS="${EPOCHS:-1}"
BATCH="${BATCH:-2}"                 # limer (no logits) → batch=2/GPU fits
GRAD_ACCUM="${GRAD_ACCUM:-4}"       # eff batch = 2 × 2 GPU × 4 = 16
MAX_STEPS="${MAX_STEPS:--1}"
RESUME="${RESUME:-}"               # checkpoint dir to resume from (e.g. checkpoint/routed_256/checkpoint-200)
RESUME_FLAG=""; [ -n "$RESUME" ] && RESUME_FLAG="--resume $RESUME"
SFT_W_START="${SFT_W_START:-1.0}"; SFT_W_END="${SFT_W_END:-0.2}"
CONFIG="${CONFIG:-configs/zero2_lora.yaml}"   # set CONFIG=configs/zero3_lora.yaml to shard base params
# ZeRO-3 needs reentrant grad-checkpointing (non-reentrant's recompute-match
# check fails when params are gathered/partitioned → CheckpointError in backward).
GC_FLAG=""
[[ "$CONFIG" == *zero3* ]] && GC_FLAG="--gc-reentrant"

LOG="/tmp/routed_$(date +%Y%m%d_%H%M%S).log"
echo "[routed] config=$CONFIG batch=$BATCH/GPU eff_batch=$((BATCH*2*GRAD_ACCUM)) max_length=$MAX_LENGTH λ:$SFT_W_START→$SFT_W_END log→$LOG"

accelerate launch \
    --config_file "$CONFIG" --num_processes 2 \
    scripts/train_offline_grpo.py \
        --dataset "$DATASET" --model "$MODEL" --output "$OUTPUT" \
        --routed \
        --max-length "$MAX_LENGTH" --epochs "$EPOCHS" \
        --batch-size "$BATCH" --grad-accum "$GRAD_ACCUM" --max-steps "$MAX_STEPS" \
        $RESUME_FLAG $GC_FLAG \
        --sft-weight-start "$SFT_W_START" --sft-weight-end "$SFT_W_END" \
    2>&1 | tee "$LOG"
echo "[routed] done. checkpoint at $OUTPUT, log at $LOG"
