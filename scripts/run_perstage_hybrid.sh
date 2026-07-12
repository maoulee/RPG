#!/usr/bin/env bash
# =============================================================================
# PER-STAGE HYBRID SFT+GRPO — CiSPO curriculum on the per-stage (process-
# supervised) path. Trains ALL assistant turns:
#   - role="sft"  rows: adv_*=1.0 in data → uniform +w_stage per turn (whole
#                  good trajectory imitated, downstream practice RETAINED),
#                  scaled by λ(t) = sft_weight_start → sft_weight_end.
#   - role="grpo" rows: per-stage signed advantage w_stage × adv_stage
#                  (group-baselined S_stage − mean_group). Saturated stages
#                  get ~0 gradient (natural protection).
#
# Dataset: data/offline_grpo/full3k_split/hybrid_per_stage.jsonl
#   (build via: build_train_msgs.py → build_advantage_dataset --per-stage
#    → build_hybrid_dataset --sft-per-case top1)
#
# Smoke first:   MAX_STEPS=4 bash scripts/run_perstage_hybrid.sh
# Full run:      bash scripts/run_perstage_hybrid.sh
# =============================================================================
set -euo pipefail

export LD_LIBRARY_PATH="/root/miniconda3/lib/python3.10/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export NCCL_IB_DISABLE=1
export NCCL_DEBUG=WARN

cd /zhaoshu/subgraph

DATASET="${DATASET:-data/offline_grpo/full3k_split/hybrid_per_stage_clean.jsonl}"
MODEL="/zhaoshu/llm/Qwen3.5-9B"
OUTPUT="${OUTPUT:-checkpoint/perstage_hybrid_258}"
# per-stage keeps the FULL trajectory (no truncation); p90~17K tokens. 14336
# keeps ~85% (the longest multi-candidate trajectories drop). batch=1 because
# two 14K+ trajectories per micro-batch would OOM; grad-accum keeps eff batch.
MAX_LENGTH="${MAX_LENGTH:-14336}"
EPOCHS="${EPOCHS:-1}"
BATCH=1
GRAD_ACCUM="${GRAD_ACCUM:-8}"          # eff batch = 1 × 2 GPU × 8 = 16
MAX_STEPS="${MAX_STEPS:--1}"           # -1 = full; 4 = smoke
W_PLAN="${W_PLAN:-0.2}"; W_SELECT="${W_SELECT:-0.3}"; W_REASON="${W_REASON:-0.5}"
SFT_W_START="${SFT_W_START:-1.0}"      # SFT seeds full-strength at step 0
SFT_W_END="${SFT_W_END:-0.2}"          # fade to 0.2 so good-practice anchors stay

LOG="/tmp/perstage_hybrid_$(date +%Y%m%d_%H%M%S).log"
echo "[perstage_hybrid] max_length=$MAX_LENGTH eff_batch=$((BATCH*2*GRAD_ACCUM)) λ:$SFT_W_START→$SFT_W_END w=$W_PLAN/$W_SELECT/$W_REASON  log→$LOG"

accelerate launch \
    --config_file configs/zero2_lora.yaml \
    --num_processes 2 \
    scripts/train_offline_grpo.py \
        --dataset "$DATASET" --model "$MODEL" --output "$OUTPUT" \
        --per-stage \
        --max-length "$MAX_LENGTH" --epochs "$EPOCHS" \
        --batch-size "$BATCH" --grad-accum "$GRAD_ACCUM" --max-steps "$MAX_STEPS" \
        --w-plan "$W_PLAN" --w-select "$W_SELECT" --w-reason "$W_REASON" \
        --sft-weight-start "$SFT_W_START" --sft-weight-end "$SFT_W_END" \
    2>&1 | tee "$LOG"

echo "[perstage_hybrid] done. checkpoint at $OUTPUT, log at $LOG"
