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

# =============================================================================
# Training runs in a DEDICATED venv at /zhaoshu/venvs/qwen35-train, isolated
# from the conda base (which is the vLLM/rollout env on torch 2.11+cu130 but
# WITHOUT fla/causal-conv1d and with transformers 4.57.3 — too old for qwen3_5).
# This venv has the SAME torch wheel (2.11.0+cu130) PLUS:
#   transformers 5.14.1 (adds Qwen3.5), fla 0.5.2 (chunk_gated_delta_rule),
#   causal-conv1d 1.6.2.post1 (causal_conv1d_fn) — both built from source with
#   CUDA_HOME=/usr/local/cuda-13.3. Together they give `Qwen3.5 fast path: True`.
# Rollout/eval still uses the conda env (vLLM :8000, GTE :8003) — DO NOT
# activate this venv there.
# =============================================================================
VENV_DIR="/zhaoshu/venvs/qwen35-train"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "[routed] FATAL: training venv missing at ${VENV_DIR}" >&2
    exit 1
fi
export PATH="${VENV_DIR}/bin:${PATH}"
unset CONDA_PREFIX          # venv takes precedence over (base) conda
VENV_NVIDIA_LIB="${VENV_DIR}/lib/python3.10/site-packages/nvidia"
export LD_LIBRARY_PATH="${VENV_NVIDIA_LIB}/cu13/lib:${VENV_NVIDIA_LIB}/cudnn/lib:${VENV_NVIDIA_LIB}/nccl/lib:${VENV_NVIDIA_LIB}/cusparselt/lib:${VENV_NVIDIA_LIB}/nvshmem/lib:${LD_LIBRARY_PATH:-}"
# Sanity: refuse to launch if Qwen3.5 fast path isn't available in this venv.
python - <<'PY' || { echo "[routed] FATAL: Qwen3.5 fast path not available in ${VENV_DIR}" >&2; exit 1; }
from transformers.models.qwen3_5 import modeling_qwen3_5 as m
assert getattr(m, "is_fast_path_available", False), "is_fast_path_available is False"
PY
echo "[routed] using venv ${VENV_DIR} (Qwen3.5 fast path: True)"

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
INIT_LORA="${INIT_LORA:-}"         # iterative self-training: continue from a previous adapter (no merge)
INIT_LORA_FLAG=""; [ -n "$INIT_LORA" ] && INIT_LORA_FLAG="--init-lora $INIT_LORA"
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
        $RESUME_FLAG $INIT_LORA_FLAG $GC_FLAG \
        --sft-weight-start "$SFT_W_START" --sft-weight-end "$SFT_W_END" \
    2>&1 | tee "$LOG"
echo "[routed] done. checkpoint at $OUTPUT, log at $LOG"
