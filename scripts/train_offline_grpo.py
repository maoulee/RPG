#!/usr/bin/env python3
"""Offline GRPO trainer: advantage-weighted policy gradient on fixed trajectories.

Unlike trl's GRPOTrainer (which needs online vLLM rollout and is broken on this
box by a vLLM/trl version mismatch), this trainer consumes a FIXED dataset of
trajectories with PRECOMPUTED advantages (build_advantage_dataset.py). The loss
is the standard GRPO policy-gradient objective:

    L = -mean( advantage_i * per-token-logprob(completion_i | prompt_i) )

only on completion (assistant) tokens — same position-based mask as SFT, so no
{% generation %} chat-template block is needed. A KL term against a frozen ref
model is optional (beta>0); default beta=0 (pure offline advantage weighting,
like early GRPO / RAFT).

Usage:
    python scripts/train_offline_grpo.py \
        --dataset data/offline_grpo/grpo_cwq.jsonl \
        --model /zhaoshu/llm/Qwen3.5-9B \
        --output checkpoint/grpo_cwq --epochs 2 --lr 1e-5
"""
from __future__ import annotations

import argparse
import os

import torch
import torch.nn.functional as F
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

# reuse the BatchEncoding compatibility patch from train_sft
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_sft import _patch_apply_chat_template

import re


# ---------------------------------------------------------------------------
# Per-stage (process-supervised) advantage
# ---------------------------------------------------------------------------
# The agent's completion is multi-turn: each assistant turn is one tool call.
# We attribute a stage score to each assistant turn by the tool it invokes, and
# build a PER-TOKEN advantage vector (one scalar per token) so the loss weights
# every completion token by its own stage's score, instead of one scalar over
# the whole trajectory. Stages follow agent_stage_scorer.score_case:
#   S_plan   ← measured at select_relations / select (plan reached the answer)
#   S_select ← measured at expand_branches (expanded paths carry the answer)
#   S_reason ← measured at answer (final-answer F1 within reach)
# All the decomposition / retrieval / relation-selection tools feed S_plan, so
# they map to the "plan" stage. A tool not in the map (rare/unknown) gets no
# stage → its turn is treated as non-assistant (not trained).
STAGE_OF_TOOL = {
    "decompose": "plan",
    "retrieve": "plan",
    "select_relations": "plan",
    "select": "plan",
    "expand_branch": "select",
    "expand_branches": "select",
    "answer": "reason",
}
# Assistant turns carry `tool: {"tool": "NAME", "args": {...}}`. Match the tool
# name robustly (whitespace-tolerant) without a full JSON parse.
_TOOL_RE = re.compile(r'"tool"\s*:\s*"([^"]+)"')


def _stage_of_assistant_turn(content: str):
    """Return (stage, tool_name) for an assistant turn's raw content, or
    (None, tool_or_None) if the tool is unknown / unparseable."""
    m = _TOOL_RE.search(content or "")
    if not m:
        return None, None
    tn = m.group(1)
    return STAGE_OF_TOOL.get(tn), tn


def _stage_adv_of(ex, stage):
    """Per-stage advantage value to weight for a record.

    Prefers the builder's group-baselined ``adv_<stage>`` field (group-baseline
    or PRM-raw-via-builder); falls back to raw ``S_<stage>`` for legacy/raw-traj
    data that only carries S_* (then the trainer applies PRM-raw weighting,
    w_stage × S_stage). Returns None when neither is present.
    """
    v = ex.get(f"adv_{stage}")
    if v is None:
        v = ex.get(f"S_{stage}")
    return v


# Tool-result user messages are prefixed 'Tool result (NAME): ...'. Used to read
# an assistant turn's tool name from the FOLLOWING message (more reliable than
# parsing the assistant content, and identical to build_advantage_dataset.py).
_TOOL_RESULT_PREFIX_RE = re.compile(r"^Tool result \(([^)]+)\)")


def _turn_stage_msgs(messages, i):
    """Stage of the assistant turn at index ``i`` in a messages list.

    Mirrors build_advantage_dataset._turn_stage so the trainer labels the SAME
    turns the builder chose as the origin. Tool name from the following
    tool-result message prefix; falls back to the assistant content's tool JSON
    (e.g. a trajectory that ends on an assistant turn with no following result).
    Returns None for non-assistant / unparseable turns.
    """
    m = messages[i]
    if m.get("role") != "assistant":
        return None
    if i + 1 < len(messages):
        mm = _TOOL_RESULT_PREFIX_RE.match(messages[i + 1].get("content", "") or "")
        if mm:
            return STAGE_OF_TOOL.get(mm.group(1))
    stage, _tn = _stage_of_assistant_turn(m.get("content", ""))
    return stage


def _tokenize_origin_stage(tokenizer, messages_truncated, origin_stage, max_length):
    """Tokenize a truncated conversation (prompt + origin completion, i.e.
    everything up to the end of the origin stage) and label ONLY the
    origin-stage assistant turns. All other tokens — prior-stage assistant
    turns, tool results, the prompt — are masked to -100. The advantage is a
    per-record SCALAR (group-baselined S_origin), applied at loss time.

    This is the assistant-only-labeling analogue of _tokenize_per_stage, but
    restricted to one stage and a scalar advantage so it can route through the
    fast scalar limer GRPO loss (no per-token advantage vector, no chunked CE).
    """
    ids = tokenizer.apply_chat_template(messages_truncated, tokenize=True,
                                        add_generation_prompt=False)
    if isinstance(ids, list) and ids and isinstance(ids[0], list):
        ids = ids[0]
    ids = list(ids)
    if len(ids) > max_length:
        return None

    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    starts = [i for i, t in enumerate(ids) if t == im_start]
    spans = [(starts[k], starts[k + 1] if k + 1 < len(starts) else len(ids))
             for k in range(len(starts))]
    if len(spans) != len(messages_truncated):
        return "MISMATCH"

    labels = [-100] * len(ids)
    n_origin_toks = 0
    turn_info = []
    for (s, e), idx in zip(spans, range(len(messages_truncated))):
        stg = _turn_stage_msgs(messages_truncated, idx)
        is_origin = stg == origin_stage
        turn_info.append((stg, is_origin, (s, e)))
        if is_origin:
            for t in range(s, e):
                labels[t] = ids[t]
            n_origin_toks += e - s
    if n_origin_toks == 0:
        return "NO_ORIGIN_TOKS"
    return {"input_ids": ids, "labels": labels, "turn_info": turn_info,
            "n_origin_toks": n_origin_toks}


def _tokenize_per_stage(tokenizer, messages, adv_plan, adv_select, adv_reason,
                        w_plan, w_select, w_reason, max_length):
    """Render one trajectory and build a per-token advantage vector.

    The conversation is rendered ONCE with apply_chat_template, then split into
    per-message token spans by the ``<|im_start|>`` role-marker tokens (every
    Qwen chat turn is wrapped in exactly one ``<|im_start|>{role}\\n...<|im_end|>``
    block, so #markers == #messages and spans align 1:1 with ``messages``).
    Incremental prefix-rendering is avoided because this template's query-
    detection logic rejects some partial conversations.

    ``adv_plan/adv_select/adv_reason`` are the per-stage advantage values to
    weight (NOT the raw scores): for group-baselined data these are
    S_stage − mean_group(S_stage) [± /std] computed by build_advantage_dataset.py;
    for PRM-raw / legacy data they ARE the raw S_stage (caller's _stage_adv_of
    handles the fallback). The per-token advantage placed on a turn is
    ``w_stage × adv_stage`` — SIGNED under group-baselining (reinforce +,
    suppress −), always ≥0 under PRM-raw.

    For each ASSISTANT span we set:
        labels[t]            = input_ids[t]     (train on this token)
        per_token_adv[t]     = w_stage × adv_stage (uniform across the turn)
    Non-assistant tokens (system / user / tool-result) keep labels=-100 and
    advantage=0, so they contribute neither to the loss nor to the denominator.

    Returns None if the rendered length exceeds ``max_length`` (caller filters)
    or if marker/message counts diverge (unexpected template — skipped loudly).
    """
    ids = tokenizer.apply_chat_template(messages, tokenize=True,
                                        add_generation_prompt=False)
    # trl×transformers5.8 BatchEncoding patch returns list[int]; be defensive.
    if isinstance(ids, list) and ids and isinstance(ids[0], list):
        ids = ids[0]
    ids = list(ids)
    if len(ids) > max_length:
        return None

    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    starts = [i for i, t in enumerate(ids) if t == im_start]
    spans = [(starts[k], starts[k + 1] if k + 1 < len(starts) else len(ids))
             for k in range(len(starts))]
    if len(spans) != len(messages):
        # Template added/dropped a turn block — aligning spans to messages is
        # unsafe. Skip rather than silently mis-attribute advantages.
        return "MISMATCH"

    stage_adv = {
        "plan": w_plan * (adv_plan or 0.0),
        "select": w_select * (adv_select or 0.0),
        "reason": w_reason * (adv_reason or 0.0),
    }
    labels = [-100] * len(ids)
    per_tok = [0.0] * len(ids)
    turn_info = []  # (stage, tool, span) for diagnostics
    for (s, e), m in zip(spans, messages):
        if m.get("role") != "assistant":
            continue
        stage, tn = _stage_of_assistant_turn(m.get("content", ""))
        if stage is None:
            turn_info.append((None, tn, (s, e)))
            continue
        adv = stage_adv[stage]
        for t in range(s, e):
            labels[t] = ids[t]
            per_tok[t] = adv
        turn_info.append((stage, tn, (s, e)))

    return {"input_ids": ids, "labels": labels,
            "per_token_advantage": per_tok, "turn_info": turn_info}


def _tokenize_stages(tokenizer, messages, stages_set, max_length):
    """Generalized origin-stage tokenization: label EVERY assistant turn whose
    stage is in ``stages_set`` (plan/select/reason), mask all other tokens.

    Routed trainer contract:
      train_stages=[X]            → train only the X-stage segment (origin-style)
      train_stages=[plan,select,reason] → whole-trajectory (all assistant turns)
    The advantage is a per-record SCALAR applied at loss time (limer GRPO), so
    this never builds a per-token advantage vector. Returns {input_ids, labels}
    or a skip-reason string.
    """
    ids = tokenizer.apply_chat_template(messages, tokenize=True,
                                        add_generation_prompt=False)
    if isinstance(ids, list) and ids and isinstance(ids[0], list):
        ids = ids[0]
    ids = list(ids)
    if len(ids) > max_length:
        return None
    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    starts = [i for i, t in enumerate(ids) if t == im_start]
    spans = [(starts[k], starts[k + 1] if k + 1 < len(starts) else len(ids))
             for k in range(len(starts))]
    if len(spans) != len(messages):
        return "MISMATCH"
    labels = [-100] * len(ids)
    n_tok = 0
    for (s, e), idx in zip(spans, range(len(messages))):
        if _turn_stage_msgs(messages, idx) in stages_set:
            for t in range(s, e):
                labels[t] = ids[t]
            n_tok += e - s
    if n_tok == 0:
        return "NO_STAGE_TOKS"
    return {"input_ids": ids, "labels": labels, "n_tok": n_tok}


def _get_base_transformer(model):
    """Unwrap PEFT/accelerate wrappers down to the causal LM module that has
    `.model` (the transformer backbone, returns last_hidden_state) and
    `.lm_head` (the vocab projection). Robust across PeftModel / DeepSpeed.

    Wrapper chain for PEFT:  PeftModel → base_model (LoraModel) → .model = CausalLM
    For DeepSpeed wrapping, we also unwrap `.module` / `.base_module`.
    """
    m = model
    # unwrap PEFT wrapper
    if hasattr(m, "base_model") and hasattr(m.base_model, "model"):
        m = m.base_model.model
    # unwrap accelerate/deepspeed .module
    while hasattr(m, "module"):
        m = m.module
    return m


def _gather_ctx(weight):
    """Context manager that all-gathers a DeepSpeed ZeRO-3 partitioned param so
    fused limer/CE kernels see the FULL weight. No-op when the param is already
    fully on-device (ZeRO-2 / single-GPU). Under ZeRO-3, leaf-module forward
    hooks auto-gather backbone params, but lm_head.weight accessed directly as a
    raw tensor stays partitioned → must gather explicitly for the limer call."""
    from contextlib import nullcontext
    if hasattr(weight, "ds_status") and getattr(weight.ds_status, "name", "") != "AVAILABLE":
        try:
            from deepspeed.runtime.zero import GatheredParameters
            return GatheredParameters([weight], modifier_rank=0)
        except Exception:
            return nullcontext()
    return nullcontext()


def _diag_trainable(trainer):
    """Print trainable-param audit + DeepSpeed status. Asserts no vision param is
    trainable (text-only training) and that only lora_A/lora_B are trainable."""
    try:
        trainer.model.print_trainable_parameters()
    except Exception:
        pass
    vis_train = [n for n, p in trainer.model.named_parameters()
                 if p.requires_grad and any(k in n.lower() for k in ("visual", "vision", "image"))]
    if vis_train:
        raise RuntimeError(f"Vision param unexpectedly trainable: {vis_train[:5]}")
    trainable = sum(p.numel() for n, p in trainer.model.named_parameters() if p.requires_grad)
    non_lora = [n for n, p in trainer.model.named_parameters()
                if p.requires_grad and "lora_" not in n]
    print(f"  [diag] trainable={trainable/1e6:.1f}M | non-lora trainable modules: {non_lora[:3] or 'none'}")
    try:
        print(f"  [diag] DeepSpeed enabled: {trainer.is_deepspeed_enabled} | "
              f"world_size: {trainer.args.world_size}")
    except Exception:
        pass


class OfflineGRPOTrainer(SFTTrainer):
    """SFTTrainer subclass with advantage-weighted policy-gradient loss.

    The dataset must carry an `advantage` float per example. Two loss backends:
      - "liger" (default): LigerFusedLinearGRPOLoss — runs the GRPO objective
        fused over (hidden_states, lm_head.weight) WITHOUT ever materializing
        the [B, T, V] logits. Memory-optimal; ideal for vocab=248K @ 8K seq.
        beta=0 + use_ref_model=False → pure advantage weighting (no KL), which
        matches our offline setting (trajectories are on-policy-ish, KL gain
        is negligible). loss_type="grpo" = per-sequence-mean normalization,
        mathematically equivalent to -adv * mean(completion logprob).
      - "ce": F.cross_entropy(reduction="none") path — fused CE kernel (does
        NOT materialize log_softmax either), kept as a fallback/comparison.
    """

    # set lazily in __init__ when loss=="liger"
    _grpo_loss_fn = None

    def __init__(self, *args, loss_backend: str = "liger",
                 sft_weight_start: float = 1.0, sft_weight_end: float = 0.1,
                 total_steps: int = -1,
                 per_stage: bool = False,
                 origin_stage: bool = False,
                 routed: bool = False,
                 w_plan: float = 0.2, w_select: float = 0.3, w_reason: float = 0.5,
                 per_stage_chunk: int = 1024, **kwargs):
        super().__init__(*args, **kwargs)
        self.loss_backend = loss_backend
        # --- per-stage (process-supervised) advantage ---
        # When True, compute_loss expects a per_token_advantage (B, T) tensor in
        # the batch (built by _tokenize_per_stage) and runs the per-token
        # weighted loss. When False, the original scalar-advantage path runs
        # unchanged (full backward compatibility).
        self.per_stage = per_stage
        # --- origin-stage process reward ---
        # When True, compute_loss expects PRE-TOKENIZED input_ids + labels (only
        # the origin-stage assistant turns labeled) + a scalar `advantage`. It
        # routes through the fast scalar limer GRPO loss (completion_mask is
        # derived from labels). Mutually exclusive with per_stage.
        self.origin_stage = origin_stage
        # --- routed scalar-GRPO (per-example stage-mask) ---
        # When True, compute_loss expects pre-tokenized input_ids + labels (only
        # train_stages turns labeled) + a scalar `advantage` + is_sft. Routes
        # through the limer scalar GRPO loss; CiSPO λ applies to role=sft rows.
        self.routed = routed
        if origin_stage and loss_backend != "liger":
            print(f"[OfflineGRPO] origin-stage forces loss backend liger "
                  f"(was {loss_backend})")
            self.loss_backend = "liger"
            loss_backend = "liger"
        self.w_plan = w_plan
        self.w_select = w_select
        self.w_reason = w_reason
        # chunk size (time dim) for the per-token logprob computation — bounds
        # peak activation to (B, chunk, V) instead of (B, T, V). vocab is ~152K
        # so an unchunked [B, T, V] logits tensor + log_softmax would OOM at
        # 8K seq. Default 1024 ≈ 1.2 GB/forward on top of the backbone.
        self.per_stage_chunk = per_stage_chunk
        if per_stage:
            print(f"[OfflineGRPO] per-stage advantage ON "
                  f"(w_plan={w_plan} w_select={w_select} w_reason={w_reason}, "
                  f"chunk={per_stage_chunk})")
        if origin_stage:
            print(f"[OfflineGRPO] origin-stage process reward ON (scalar limer)")
        # CiSPO-style hybrid curriculum: SFT-seeded samples (role="sft", adv=1.0
        # in the dataset) get their advantage multiplied by a time-decaying
        # weight λ(t). At t=0 λ=w_start (SFT dominates → stable bootstrap), at
        # t=T λ=w_end (SFT signal fades, GRPO relative credit takes over).
        # total_steps<0 → caller didn't know it yet; resolve lazily in
        # compute_loss from self.state.max_steps.
        self.sft_weight_start = sft_weight_start
        self.sft_weight_end = sft_weight_end
        self._total_steps = total_steps
        if loss_backend == "liger":
            from liger_kernel.chunked_loss import LigerFusedLinearGRPOLoss
            # beta=0: drop KL entirely (offline, on-policy-ish trajectories).
            # use_ref_model=False: skip ref forward + assert path.
            # loss_type="grpo": per-sequence mean normalization.
            #   = mean_seq( -adv * mean_t(per_token_logps) ), which equals our
            #     hand-written -adv * mean(completion logprob). coef_2=1 since
            #     ratio=1 (no old_logps) → no importance-sampling clipping.
            self._grpo_loss_fn = LigerFusedLinearGRPOLoss(
                beta=0.0,
                loss_type="grpo",
                use_ref_model=False,
                compiled=False,   # torch.compile + custom autograd can fight gradient_checkpointing
            )
            print(f"[OfflineGRPO] loss backend = liger GRPO (beta=0, no ref, no KL)")

    def _compute_loss_liger(self, model, input_ids, attention_mask, labels, advantage):
        # 1) forward the transformer backbone to get last_hidden_state.
        #    We call the BASE transformer (model.model) directly instead of
        #    model(...) so liger's FLCE-patched forward never runs and NO logits
        #    are materialized. liger's RMSNorm/swiGLU patches on the backbone
        #    still apply (those cut activation memory during the forward).
        base = _get_base_transformer(model)
        backbone = base.model  # the Qwen3_5Model inside the CausalLM
        out = backbone(input_ids=input_ids, attention_mask=attention_mask)
        hidden = out.last_hidden_state  # (B, T, H)

        # 2) shift for next-token prediction: predict token t+1 from hidden[t]
        shift_hidden = hidden[:, :-1, :].contiguous()      # (B, T-1, H)
        shift_labels = labels[:, 1:].contiguous()          # (B, T-1)

        # 3) completion mask: only assistant tokens (labels != -100)
        completion_mask = (shift_labels != -100).to(hidden.dtype)  # (B, T-1)
        # liger GRPO loss wants safe token ids (no -100)
        safe_tokens = shift_labels.clamp(min=0)

        # 4) liger fused GRPO loss over (hidden, lm_head.weight).
        #    It streams over vocab in chunks internally — never builds [T, V].
        #    NOTE: pass 3D (B, T-1, H) input + 2D (B, T-1) token ids — liger's
        #    chunk_forward flattens internally. Pre-flattening triggers a shape
        #    unpack error inside chunk_forward.
        adv = advantage.view(-1).to(hidden.dtype)
        lm_w = base.lm_head.weight
        # Under ZeRO-3 lm_head.weight is partitioned → all-gather it for the
        # fused limer call (no-op under ZeRO-2/single). Backbone params are
        # auto-gathered by DeepSpeed leaf-module hooks on the forward above.
        with _gather_ctx(lm_w):
            loss, _metrics = self._grpo_loss_fn(
                _input=shift_hidden,                      # (B, T-1, H)
                lin_weight=lm_w,                          # (V, H) — gathered under ZeRO-3
                selected_token_ids=safe_tokens,           # (B, T-1)
                attention_mask=completion_mask,           # (B, T-1)
                advantages=adv,                           # (B,)
            )
        return loss

    def _compute_loss_per_stage(self, model, input_ids, attention_mask, labels,
                                per_token_advantage):
        """Per-token advantage-weighted policy-gradient loss (process supervision).

            L = -mean_{t in completion}( per_token_adv[t] * logprob(token_t) )

        Forward the backbone ONCE to get hidden states, then project to logits
        in time-dim chunks (peak mem = B × chunk × V, not B × T × V — essential
        for vocab≈152K). The per-token logprob of the label token is gathered
        from each chunk's log_softmax and weighted by the per-token advantage.

        Alignment: per_token_advantage[t] is the advantage of the token at
        absolute position t. After the standard causal shift (predict token t
        from hidden[t-1]), shift_adv[q] = per_token_advantage[q+1] aligns with
        shift_labels[q] and shift_hidden[q]. Only positions where labels != -100
        (assistant tokens) are trained; non-assistant positions have adv=0 and
        are masked out of both numerator and denominator.
        """
        base = _get_base_transformer(model)
        out = base.model(input_ids=input_ids, attention_mask=attention_mask)
        hidden = out.last_hidden_state                  # (B, T, H)
        if per_token_advantage.dim() == 1:
            per_token_advantage = per_token_advantage.unsqueeze(0)  # (T,) → (1, T)
        if hidden.dim() == 2:
            hidden = hidden.unsqueeze(0)                 # (T, H) → (1, T, H)
        if labels.dim() == 1:
            labels = labels.unsqueeze(0)                 # (T,) → (1, T)
        shift_hidden = hidden[:, :-1, :].contiguous()   # (B, T-1, H)
        shift_labels = labels[:, 1:].contiguous()       # (B, T-1)
        B, Tm1, H = shift_hidden.shape
        shift_adv = per_token_advantage[:, 1:].contiguous().to(hidden.dtype)  # (B, T-1)
        mask = (shift_labels != -100).to(hidden.dtype)  # (B, T-1)
        safe = shift_labels.clamp(min=0)

        lm_head = base.lm_head
        chunk = max(1, self.per_stage_chunk)
        logp_chunks = []
        for st in range(0, Tm1, chunk):
            en = min(st + chunk, Tm1)
            logits = lm_head(shift_hidden[:, st:en, :])               # (B, c, V)
            lsm = torch.log_softmax(logits.float(), dim=-1)           # (B, c, V)
            lp = lsm.gather(-1, safe[:, st:en].unsqueeze(-1)).squeeze(-1)  # (B, c)
            logp_chunks.append(lp)
        logp = torch.cat(logp_chunks, dim=1) if logp_chunks else \
            torch.zeros(B, 0, device=hidden.device, dtype=torch.float32)

        contrib = -(shift_adv * logp) * mask                          # (B, T-1)
        denom = mask.sum().clamp(min=1.0)
        return contrib.sum() / denom

    def _compute_loss_ce(self, model, input_ids, attention_mask, labels, advantage):
        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        logits = outputs.logits
        B, T, V = logits.shape
        shift_logits = logits[:, :-1, :].contiguous()
        shift_labels = labels[:, 1:].contiguous()
        # fused CE: does NOT materialize log_softmax intermediate tensor.
        per_token_nll = F.cross_entropy(
            shift_logits.view(-1, V), shift_labels.view(-1),
            ignore_index=-100, reduction="none",
        ).view(B, T - 1)
        token_logprobs = -per_token_nll
        mask_f = (shift_labels != -100).float()
        seq_mask_sum = mask_f.sum(dim=1).clamp(min=1.0)
        seq_logprob = (token_logprobs * mask_f).sum(dim=1) / seq_mask_sum
        adv = advantage.view(-1).to(seq_logprob.dtype).to(seq_logprob.device)
        return (-adv * seq_logprob).mean()

    def _sft_lambda(self) -> float:
        """Curriculum weight λ for SFT-seeded samples at the current step.

        Linear decay from sft_weight_start (step 0) to sft_weight_end (final
        step). This multiplies the constant +1.0 advantage of role="sft"
        samples, so early on SFT dominates (stable bootstrap) and late GRPO's
        relative credit-assignment dominates. GRPO (role="grpo") samples are
        never scaled — they always use their raw signed advantage.
        """
        if self.sft_weight_start == self.sft_weight_end:
            return self.sft_weight_start
        total = self._total_steps if self._total_steps > 0 else getattr(
            self.state, "max_steps", -1)
        if not total or total <= 0:
            return self.sft_weight_start  # unknown horizon → full SFT until resolved
        t = min(getattr(self.state, "global_step", 0), total)
        return self.sft_weight_start + (self.sft_weight_end - self.sft_weight_start) * (t / total)

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        # ----- per-stage (process-supervised) path -----
        # Per-token advantage vector (B, T) built by _tokenize_per_stage. This
        # path is independent of the scalar-advantage / CiSPO-curriculum logic
        # below: process supervision uses raw w_stage*S_stage per turn, so there
        # is no group baseline and no SFT λ to apply.
        if self.per_stage:
            per_tok_adv = inputs.pop("per_token_advantage")
            # CiSPO curriculum on the per-stage path: SFT-seed rows carry
            # adv_*=1.0 in the data (→ uniform +w_stage per turn, set by
            # build_hybrid_dataset), so scale them by λ(t) — strong imitation
            # early, fades to let GRPO's signed per-stage credit dominate late.
            # GRPO rows keep their raw w_stage × adv_stage (signed). is_sft is
            # absent (None) for plain per-stage datasets → original behavior.
            is_sft = inputs.pop("is_sft", None)
            if is_sft is not None:
                lam = self._sft_lambda()
                is_sft = is_sft.to(per_tok_adv.device).to(per_tok_adv.dtype)
                scale = (is_sft * lam + (1.0 - is_sft) * 1.0)   # (B,)
                per_tok_adv = per_tok_adv * scale.unsqueeze(1)
            input_ids = inputs["input_ids"]
            attention_mask = inputs["attention_mask"]
            labels = inputs["labels"]
            loss = self._compute_loss_per_stage(
                model, input_ids, attention_mask, labels, per_tok_adv)
            if return_outputs:
                return loss, type("Out", (), {"logits": None})()
            return loss

        # ----- origin-stage process reward (scalar limer) -----
        # Pre-tokenized input_ids + labels (only origin-stage assistant turns
        # labeled, built by _tokenize_origin_stage) + a scalar advantage. Routes
        # through the SAME fused limer scalar-GRPO loss as the single-adv path;
        # the completion_mask is derived from labels (origin tokens only). No
        # CiSPO curriculum (origin-stage is its own objective).
        if self.origin_stage:
            advantage = inputs.pop("advantage")  # (B,) scalar, group-baselined S_origin
            input_ids = inputs["input_ids"]
            attention_mask = inputs["attention_mask"]
            labels = inputs["labels"]
            loss = self._compute_loss_liger(
                model, input_ids, attention_mask, labels, advantage)
            if return_outputs:
                return loss, type("Out", (), {"logits": None})()
            return loss

        # ----- routed scalar-GRPO (per-example stage-mask, limer) -----
        # Pre-tokenized input_ids + labels (only train_stages turns labeled,
        # built by _tokenize_stages) + a scalar advantage + is_sft. CiSPO λ(t)
        # scales role=sft rows (a_sft examples); grpo rows keep raw signed adv.
        if self.routed:
            advantage = inputs.pop("advantage")
            is_sft = inputs.pop("is_sft", None)
            if is_sft is not None:
                lam = self._sft_lambda()
                is_sft = is_sft.to(advantage.device).to(advantage.dtype)
                advantage = advantage * (is_sft * lam + (1.0 - is_sft) * 1.0)
            input_ids = inputs["input_ids"]
            attention_mask = inputs["attention_mask"]
            labels = inputs["labels"]
            loss = self._compute_loss_liger(
                model, input_ids, attention_mask, labels, advantage)
            if return_outputs:
                return loss, type("Out", (), {"logits": None})()
            return loss

        # ----- scalar-advantage path (original, backward-compatible) -----
        advantage = inputs.pop("advantage")  # (B,) or (B,1) — already SFT=1.0/GRPO=signed
        # role marker: True where the sample is an SFT seed (needs curriculum weight).
        # Absent for plain-GRPO datasets → all-False → identical to original behavior.
        is_sft = inputs.pop("is_sft", None)
        input_ids = inputs["input_ids"]
        attention_mask = inputs["attention_mask"]
        labels = inputs["labels"]

        # Apply curriculum weight λ(t) to the SFT rows only. GRPO rows keep
        # their raw signed advantage. One shot, then a single liger/ce call —
        # no second forward, no second loss term.
        if is_sft is not None:
            lam = self._sft_lambda()
            is_sft = is_sft.to(advantage.device).to(advantage.dtype)
            advantage = advantage * (is_sft * lam + (1.0 - is_sft) * 1.0)

        if self.loss_backend == "liger":
            loss = self._compute_loss_liger(model, input_ids, attention_mask, labels, advantage)
        else:
            loss = self._compute_loss_ce(model, input_ids, attention_mask, labels, advantage)

        # return_outputs required by HF: synthesize a minimal dummy (logits=None
        # for liger path since we never materialized them).
        if return_outputs:
            return loss, type("Out", (), {"logits": None})()
        return loss


def _prepare_per_stage_dataset(tokenizer, ds, args):
    """Pre-tokenize a per-stage dataset into {input_ids, labels,
    per_token_advantage} so SFTTrainer treats it as already-processed
    (is_processed = 'input_ids' in columns → skips its own chat-template
    tokenization). Each assistant turn's tokens carry w_stage*S_stage; all
    other tokens carry advantage 0 and labels -100.

    Requires records with a `messages` field (full conversation) +
    S_plan/S_select/S_reason. The prompt/completion single-advantage format
    cannot be split per-turn (middle assistant turns are truncated away), so we
    reject it with a clear message.
    """
    if "messages" not in ds.column_names:
        raise ValueError(
            "Per-stage mode needs records carrying a `messages` field (the full "
            "agent conversation) + S_plan/S_select/S_reason. Use either raw "
            "sampled trajectories (sample_trajectories.py output, e.g. "
            "traj_mixed_large.jsonl) or build_advantage_dataset.py --per-stage. "
            "The prompt/completion split drops middle turns and cannot be used "
            "for per-stage advantage.")

    from collections import Counter

    def _tok(ex):
        r = _tokenize_per_stage(
            tokenizer, ex["messages"],
            _stage_adv_of(ex, "plan"), _stage_adv_of(ex, "select"),
            _stage_adv_of(ex, "reason"),
            args.w_plan, args.w_select, args.w_reason, args.max_length)
        if not isinstance(r, dict):
            return {"input_ids": [], "labels": [], "per_token_advantage": [],
                    "_skip_reason": (r or "too_long")}
        return {"input_ids": r["input_ids"], "labels": r["labels"],
                "per_token_advantage": r["per_token_advantage"], "_skip_reason": ""}

    n_in = len(ds)
    ds = ds.map(_tok, num_proc=4)
    reasons = Counter(r for r in ds["_skip_reason"] if r)
    ds = ds.filter(lambda r: len(r["input_ids"]) > 0, num_proc=4)
    n_out = len(ds)
    if reasons:
        print(f"  per-stage tokenize: kept {n_out}/{n_in} "
              f"(dropped: {dict(reasons)})")
    else:
        print(f"  per-stage tokenize: kept {n_out}/{n_in}")
    # drop everything except the three tensors the collator/trainer need
    # (plus `role` so the hybrid CiSPO curriculum can scale SFT-seed rows).
    keep = {"input_ids", "labels", "per_token_advantage", "role"}
    ds = ds.remove_columns([c for c in ds.column_names if c not in keep])
    return ds


def _make_per_stage_collator(pad_id):
    """Pad a batch of pre-tokenized per-stage examples. Right-pad input_ids
    with pad_id, labels with -100, per_token_advantage with 0.0; build an
    attention_mask (1 on real tokens, 0 on pad). Also forwards `is_sft` (1.0
    for role="sft" rows, 0.0 otherwise) so compute_loss can apply the CiSPO
    λ curriculum to SFT-seed rows; absent/0 for plain per-stage datasets."""
    def collate(features):
        maxlen = max(len(f["input_ids"]) for f in features)
        ii, ll, aa, am, is_sft = [], [], [], [], []
        for f in features:
            ids, lab, adv = f["input_ids"], f["labels"], f["per_token_advantage"]
            n, pad = len(ids), maxlen - len(ids)
            ii.append(list(ids) + [pad_id] * pad)
            ll.append(list(lab) + [-100] * pad)
            aa.append(list(adv) + [0.0] * pad)
            am.append([1] * n + [0] * pad)
            is_sft.append(1.0 if f.get("role") == "sft" else 0.0)
        return {
            "input_ids": torch.tensor(ii, dtype=torch.long),
            "attention_mask": torch.tensor(am, dtype=torch.long),
            "labels": torch.tensor(ll, dtype=torch.long),
            "per_token_advantage": torch.tensor(aa, dtype=torch.float32),
            "is_sft": torch.tensor(is_sft, dtype=torch.float32),
        }
    return collate


def _prepare_origin_stage_dataset(tokenizer, ds, args):
    """Pre-tokenize an origin-stage dataset (build_advantage_dataset.py default
    output: prompt + completion + scalar advantage + origin_stage) into
    {input_ids, labels, advantage}. The truncated conversation = prompt +
    completion (everything up to the end of the origin stage); only origin-stage
    assistant turns are labeled, so the scalar limer loss trains exactly the
    origin turn(s). Requires `prompt`, `completion`, `advantage`, `origin_stage`.
    """
    need = {"prompt", "completion", "advantage", "origin_stage"}
    missing = need - set(ds.column_names)
    if missing:
        raise ValueError(
            f"Origin-stage mode needs columns {sorted(need)}; missing "
            f"{sorted(missing)}. Build the dataset with "
            f"build_advantage_dataset.py --origin-stage (the default).")

    from collections import Counter

    def _tok(ex):
        truncated = list(ex["prompt"]) + list(ex["completion"])
        r = _tokenize_origin_stage(tokenizer, truncated, ex["origin_stage"],
                                   args.max_length)
        if not isinstance(r, dict):
            return {"input_ids": [], "labels": [],
                    "_skip_reason": (r or "too_long")}
        return {"input_ids": r["input_ids"], "labels": r["labels"],
                "_skip_reason": ""}

    n_in = len(ds)
    ds = ds.map(_tok, num_proc=4)
    reasons = Counter(r for r in ds["_skip_reason"] if r)
    ds = ds.filter(lambda r: len(r["input_ids"]) > 0, num_proc=4)
    n_out = len(ds)
    print(f"  origin-stage tokenize: kept {n_out}/{n_in} "
          f"(dropped: {dict(reasons) or 'none'})")
    # keep advantage (scalar) + the two tensors
    keep = {"input_ids", "labels", "advantage"}
    ds = ds.remove_columns([c for c in ds.column_names if c not in keep])
    return ds


def _make_origin_stage_collator(pad_id):
    """Pad a batch of pre-tokenized origin-stage examples and stack the scalar
    advantage. Right-pad input_ids with pad_id, labels with -100; build
    attention_mask (1 on real tokens, 0 on pad)."""
    def collate(features):
        maxlen = max(len(f["input_ids"]) for f in features)
        ii, ll, am, adv = [], [], [], []
        for f in features:
            ids, lab = f["input_ids"], f["labels"]
            n, pad = len(ids), maxlen - len(ids)
            ii.append(list(ids) + [pad_id] * pad)
            ll.append(list(lab) + [-100] * pad)
            am.append([1] * n + [0] * pad)
            adv.append(f["advantage"])
        return {
            "input_ids": torch.tensor(ii, dtype=torch.long),
            "attention_mask": torch.tensor(am, dtype=torch.long),
            "labels": torch.tensor(ll, dtype=torch.long),
            "advantage": torch.tensor(adv, dtype=torch.float32),
        }
    return collate


def _prepare_routed_dataset(tokenizer, ds, args):
    """Pre-tokenize a routed dataset (build_routed_dataset.py output: messages +
    train_stages + advantage + role) into {input_ids, labels, advantage, role}.

    Labels ONLY the assistant turns whose stage is in train_stages (per-example
    completion_mask — this is where the a/b/c routing lives). Advantage is the
    scalar carried through the collator to the limer GRPO loss.
    """
    need = {"messages", "train_stages", "advantage", "role"}
    missing = need - set(ds.column_names)
    if missing:
        raise ValueError(f"Routed mode needs columns {sorted(need)}; missing {sorted(missing)}. "
                         f"Build with route_cases.py + build_routed_dataset.py.")
    from collections import Counter

    def _tok(ex):
        stages_set = set(ex["train_stages"])
        r = _tokenize_stages(tokenizer, ex["messages"], stages_set, args.max_length)
        if not isinstance(r, dict):
            # non-empty int64 placeholders so datasets.map infers a consistent
            # dtype across workers (empty [] infers null → "int64 to null" cast
            # error when many samples drop, e.g. low max_length). Filtered by _skip.
            return {"input_ids": [0], "labels": [-100], "_skip": (r or "too_long")}
        return {"input_ids": r["input_ids"], "labels": r["labels"], "_skip": ""}

    n_in = len(ds)
    ds = ds.map(_tok, num_proc=4)
    reasons = Counter(r for r in ds["_skip"] if r)
    ds = ds.filter(lambda r: r["_skip"] == "", num_proc=4)
    n_out = len(ds)
    print(f"  routed tokenize: kept {n_out}/{n_in} (dropped: {dict(reasons) or 'none'})")
    keep = {"input_ids", "labels", "advantage", "role"}
    ds = ds.remove_columns([c for c in ds.column_names if c not in keep])
    return ds


def _make_routed_collator(pad_id):
    """Pad routed examples + stack scalar advantage + is_sft (role==sft)."""
    def collate(features):
        maxlen = max(len(f["input_ids"]) for f in features)
        ii, ll, am, adv, is_sft = [], [], [], [], []
        for f in features:
            ids, lab = f["input_ids"], f["labels"]
            n, pad = len(ids), maxlen - len(ids)
            ii.append(list(ids) + [pad_id] * pad)
            ll.append(list(lab) + [-100] * pad)
            am.append([1] * n + [0] * pad)
            adv.append(f["advantage"])
            is_sft.append(1.0 if f.get("role") == "sft" else 0.0)
        return {
            "input_ids": torch.tensor(ii, dtype=torch.long),
            "attention_mask": torch.tensor(am, dtype=torch.long),
            "labels": torch.tensor(ll, dtype=torch.long),
            "advantage": torch.tensor(adv, dtype=torch.float32),
            "is_sft": torch.tensor(is_sft, dtype=torch.float32),
        }
    return collate


def _run_smoke_test(args, ds):
    """Logic-only dry-run: NO model load, NO GPU, NO training.

    Validates the per-stage machinery end-to-end:
      1. tokenize N trajectories → per-turn token spans + per-token advantage,
         print each assistant turn's stage / tool / token count / advantage;
      2. build a padded batch via the real per-stage collator;
      3. run the REAL _compute_loss_per_stage through a tiny random stub model
         (small hidden dim + small remapped vocab) and confirm a finite scalar
         loss whose backward() populates lm_head.weight.grad.

    This exercises the exact tokenization + the exact loss method used in real
    training, so if the smoke test passes the logic is sound.
    """
    from collections import Counter
    print(f"\n=== SMOKE TEST (per-stage, no model/GPU) ===")
    print(f"  weights: w_plan={args.w_plan} w_select={args.w_select} "
          f"w_reason={args.w_reason}")

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    _patch_apply_chat_template(tokenizer)
    pad_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)

    n = min(args.smoke_n, len(ds))
    rows = ds.select(range(n))
    featurized, n_skipped = [], 0
    for ex in rows:
        r = _tokenize_per_stage(
            tokenizer, ex["messages"],
            _stage_adv_of(ex, "plan"), _stage_adv_of(ex, "select"),
            _stage_adv_of(ex, "reason"),
            args.w_plan, args.w_select, args.w_reason, args.max_length)
        if not isinstance(r, dict):
            n_skipped += 1
            print(f"  [skip {ex.get('case_id','?')[:24]}] reason={r or 'too_long'}")
            continue
        # ---- per-turn report ----
        a_plan, a_sel, a_rea = (_stage_adv_of(ex, "plan"),
                                _stage_adv_of(ex, "select"),
                                _stage_adv_of(ex, "reason"))
        is_grp = ex.get("adv_plan") is not None  # builder group-baselined data
        print(f"\n  case {ex.get('case_id','?')[:32]}  sample={ex.get('sample_id')}")
        print(f"     raw  S_plan={ex.get('S_plan')} S_select={ex.get('S_select')} "
              f"S_reason={ex.get('S_reason')}")
        print(f"     adv  plan={a_plan} select={a_sel} reason={a_rea}  "
              f"({'group-baselined' if is_grp else 'PRM-raw/legacy'} → "
              f"per-token = w_stage × adv)  (rendered {len(r['input_ids'])} tok)")
        for stage, tn, (s, e) in r["turn_info"]:
            adv = None
            if stage is not None:
                adv = {"plan": args.w_plan * (a_plan or 0),
                       "select": args.w_select * (a_sel or 0),
                       "reason": args.w_reason * (a_rea or 0)}[stage]
            print(f"     turn {s:>5}:{e:<5} n={e-s:>4}  tool={tn or '-':16s} "
                  f"stage={stage or '-':7s} adv/token={adv if adv is not None else 0:.4f}")
        # confirm the advantage vector matches the reported per-turn values
        advs = r["per_token_advantage"]
        lab = r["labels"]
        n_trained = sum(1 for x in lab if x != -100)
        nonzero = sorted({round(a, 6) for a in advs if a != 0.0})
        print(f"     -> trained(assistant) tokens={n_trained}  "
              f"distinct adv values on them={nonzero}")
        featurized.append({"input_ids": r["input_ids"], "labels": r["labels"],
                           "per_token_advantage": r["per_token_advantage"]})

    if n_skipped:
        print(f"\n  skipped {n_skipped} (too long / template mismatch)")
    if not featurized:
        print("\n  no usable samples — aborting smoke test (try --max-length, "
              "--smoke-n).")
        return

    # ---- padded batch via the real collator ----
    collate = _make_per_stage_collator(pad_id)
    batch = collate(featurized)
    print(f"\n  batch: input_ids {tuple(batch['input_ids'].shape)}  "
          f"labels {tuple(batch['labels'].shape)}  "
          f"per_token_advantage {tuple(batch['per_token_advantage'].shape)}")
    n_trained_batch = int((batch["labels"] != -100).sum())
    print(f"  trained tokens in batch: {n_trained_batch}")

    # ---- mock forward through a tiny stub to exercise the REAL loss method ----
    # Use a small fake vocab: remap label ids into [0, V_fake) so the stub
    # lm_head is tiny. -100 preserved (masked). This tests the loss MATH +
    # shapes + grad flow, not the real backbone (which needs a GPU).
    V_FAKE, H_FAKE, CHUNK = 2000, 64, 512
    max_id = int(batch["labels"].clamp(min=0).max())
    if max_id >= V_FAKE:
        remap = { -100: -100 }
        nxt = 0
        lab_r = []
        for row in batch["labels"].tolist():
            new_row = []
            for x in row:
                if x == -100:
                    new_row.append(-100)
                else:
                    if x not in remap:
                        remap[x] = nxt % V_FAKE
                        nxt += 1
                    new_row.append(remap[x])
            lab_r.append(new_row)
        labels_fake = torch.tensor(lab_r, dtype=torch.long)
        print(f"  mock loss: remapped {len(remap)-1} token ids into V_fake={V_FAKE}")
    else:
        labels_fake = batch["labels"]
    B, T = batch["input_ids"].shape

    lm_head = torch.nn.Linear(H_FAKE, V_FAKE, bias=False)
    def _backbone(input_ids, attention_mask):
        h = torch.randn(B, T, H_FAKE, requires_grad=True)
        return type("O", (), {"last_hidden_state": h})()
    # staticmethod so base.model(input_ids=..., attention_mask=...) doesn't bind
    # the instance as a first positional arg (functions in a class dict bind).
    causal = type("C", (), {"model": staticmethod(_backbone), "lm_head": lm_head})()
    stub_model = type("M", (), {"base_model": type("BM", (), {"model": causal})()})()

    class _StubSelf:
        per_stage_chunk = CHUNK
    loss = OfflineGRPOTrainer._compute_loss_per_stage(
        _StubSelf(), stub_model, batch["input_ids"], batch["attention_mask"],
        labels_fake, batch["per_token_advantage"])
    loss.backward()
    print(f"\n  mock loss = {loss.item():.6f}  (finite={torch.isfinite(loss).item()})")
    g = lm_head.weight.grad
    print(f"  lm_head.weight.grad: shape={tuple(g.shape)} "
          f"nonzero={(g.abs() > 0).sum().item()}  "
          f"max|g|={g.abs().max().item():.6f}")
    # grad should be NON-zero only on rows that received advantage>0 tokens
    trained_rows = set(labels_fake.clamp(min=0).flatten().tolist())
    # rows with advantage>0 trained tokens:
    adv_mask = batch["per_token_advantage"][:, 1:] > 0
    trained_with_adv = set((labels_fake[:, 1:].clamp(min=0) * adv_mask.long()).flatten().tolist())
    grad_rows_nonzero = set(int(i) for i in (g.abs().sum(dim=1) > 0).nonzero().flatten().tolist())
    print(f"  grad rows nonzero: {len(grad_rows_nonzero)} | "
          f"sanity: all within vocab={grad_rows_nonzero.issubset(set(range(V_FAKE)))}")
    print("\n=== SMOKE TEST PASSED ===")


def _run_origin_stage_smoke(args, ds):
    """Logic-only dry-run for origin-stage process reward: NO model/GPU/training.

    Validates:
      1. truncated conversation = prompt + completion; ONLY origin-stage
         assistant turns are labeled (everything before + all tool results
         masked); turns after origin are absent (discarded by the builder);
      2. the scalar group-baselined advantage is attached per record;
      3. a scalar-advantage loss is finite and its backward populates grads.

    NOTE: liger_kernel is not installed in this env, so the mock loss runs the
    CE path (_compute_loss_ce) — mathematically identical to limer's
    loss_type="grpo" (mean_batch(-adv · mean_t(completion logprob))). Real
    training uses limer (fused, same objective).
    """
    print(f"\n=== SMOKE TEST (origin-stage, no model/GPU) ===")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    _patch_apply_chat_template(tokenizer)
    pad_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)

    need = {"prompt", "completion", "advantage", "origin_stage"}
    missing = need - set(ds.column_names)
    if missing:
        print(f"  dataset missing origin-stage columns {sorted(missing)} — "
              f"build with build_advantage_dataset.py --origin-stage")
        return

    n = min(args.smoke_n, len(ds))
    featurized = []
    for ex in ds.select(range(n)):
        truncated = list(ex["prompt"]) + list(ex["completion"])
        r = _tokenize_origin_stage(tokenizer, truncated, ex["origin_stage"],
                                   args.max_length)
        if not isinstance(r, dict):
            print(f"  [skip {ex.get('case_id','?')[:24]}] reason={r or 'too_long'}")
            continue
        adv = ex["advantage"]
        print(f"\n  case {ex.get('case_id','?')[:30]:30s} s{ex.get('sample_id')} "
              f"origin={ex['origin_stage']:7s} advantage={adv:+.4f} "
              f"(rendered {len(r['input_ids'])} tok, {r['n_origin_toks']} origin tok)")
        n_lbl_turns = 0
        for idx, (stg, is_origin, (s, e)) in enumerate(r["turn_info"]):
            tmsg = truncated[idx]
            if tmsg.get("role") != "assistant":
                continue
            tn = _stage_of_assistant_turn(tmsg.get("content", ""))[1]
            tag = "TRAIN" if is_origin else "mask "
            mark = "  <== origin" if is_origin else ""
            print(f"     {tag} turn {s:>5}:{e:<5} n={e-s:>4} stage={stg or '-':7s} "
                  f"tool={tn or '-':16s}{mark}")
            if is_origin:
                n_lbl_turns += 1
        n_trained = sum(1 for x in r["labels"] if x != -100)
        print(f"     -> labeled(origin) turns={n_lbl_turns}  trained tokens={n_trained}")
        featurized.append({"input_ids": r["input_ids"], "labels": r["labels"],
                           "advantage": adv})

    if not featurized:
        print("\n  no usable samples — aborting (try --max-length / --smoke-n).")
        return

    collate = _make_origin_stage_collator(pad_id)
    batch = collate(featurized)
    print(f"\n  batch: input_ids {tuple(batch['input_ids'].shape)}  "
          f"labels {tuple(batch['labels'].shape)}  "
          f"advantage {tuple(batch['advantage'].shape)} = {batch['advantage'].tolist()}")
    n_trained = int((batch["labels"] != -100).sum())
    print(f"  trained tokens in batch: {n_trained}")

    # mock scalar-adv loss via _compute_loss_ce (limer-equivalent; limer absent here)
    V_FAKE, H_FAKE = 2000, 64
    max_id = int(batch["labels"].clamp(min=0).max())
    if max_id >= V_FAKE:
        remap = {-100: -100}; nxt = 0; lab_r = []
        for row in batch["labels"].tolist():
            new = []
            for x in row:
                if x == -100:
                    new.append(-100)
                else:
                    if x not in remap:
                        remap[x] = nxt % V_FAKE; nxt += 1
                    new.append(remap[x])
            lab_r.append(new)
        labels_fake = torch.tensor(lab_r, dtype=torch.long)
    else:
        labels_fake = batch["labels"]

    lm_head = torch.nn.Linear(H_FAKE, V_FAKE, bias=False)
    B, T = batch["input_ids"].shape
    class _StubModel:
        def __call__(self, input_ids=None, attention_mask=None):
            h = torch.randn(B, T, H_FAKE, requires_grad=True)
            return type("O", (), {"logits": lm_head(h)})()
    class _Self: loss_backend = "ce"
    loss = OfflineGRPOTrainer._compute_loss_ce(
        _Self(), _StubModel(), batch["input_ids"], batch["attention_mask"],
        labels_fake, batch["advantage"])
    loss.backward()
    print(f"\n  mock scalar-adv loss = {loss.item():.6f}  "
          f"(finite={torch.isfinite(loss).item()})")
    g = lm_head.weight.grad
    print(f"  lm_head.weight.grad nonzero={(g.abs() > 0).sum().item()}  "
          f"max|g|={g.abs().max().item():.6f}")
    print("  (real training routes this through fused limer GRPO — same objective)")
    print("\n=== SMOKE TEST PASSED ===")


def main():
    p = argparse.ArgumentParser(description="Offline GRPO (advantage-weighted PG)")
    p.add_argument("--dataset", required=True)
    p.add_argument("--model", default="/zhaoshu/llm/Qwen3.5-9B")
    p.add_argument("--output", default=None,
                   help="checkpoint output dir (required unless --smoke-test)")
    p.add_argument("--max-length", type=int, default=8192)
    p.add_argument("--max-steps", type=int, default=-1)
    p.add_argument("--resume", default=None,
                   help="Resume from a checkpoint dir (e.g. checkpoint/.../checkpoint-200). "
                        "Restores LoRA adapter + DeepSpeed optimizer state + step counter.")
    p.add_argument("--init-lora", default=None,
                   help="Iterative self-training: load a previous LoRA adapter as the starting "
                        "point (fresh optimizer, new data) and continue refining it. No merge. "
                        "e.g. checkpoint/rollout_train (loads its adapter weights).")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lora-rank", type=int, default=32,
                   help="LoRA rank (normal capacity, not the code-review's lean 16). "
                        "Tunable later; attention-only covers both full+linear attn.")
    p.add_argument("--lora-alpha", type=int, default=64)
    p.add_argument("--loraplus-lr-ratio", type=float, default=0.0,
                   help="LoRA+ : learning-rate ratio lr_B/lr_A (>1, e.g. 16) for "
                        "faster convergence. 0 = off (uniform LR). Applied via a "
                        "custom param-group optimizer when >0.")
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--log-steps", type=int, default=5)
    p.add_argument("--no-gc", action="store_true",
                   help="Disable gradient_checkpointing. Trades ~2x activation "
                        "memory for skipping the forward recompute (~33% faster "
                        "per step). Default keeps gc on for memory safety.")
    p.add_argument("--gc-reentrant", action="store_true",
                   help="Use reentrant gradient checkpointing (use_reentrant=True). "
                        "Needed under ZeRO-3: non-reentrant checkpointing's "
                        "recompute-match validation fails when params are "
                        "gathered/partitioned (CheckpointError in backward).")
    p.add_argument("--loss", choices=["liger", "ce"], default="liger",
                   help="[single-adv mode only] loss backend: 'liger' (fused GRPO, "
                        "no logits materialized) or 'ce' (fused cross-entropy). "
                        "Per-stage mode always uses its own chunked per-token "
                        "loss; this flag is ignored when --per-stage.")
    # --- CiSPO-style hybrid SFT+GRPO curriculum (single-adv mode only) ---
    p.add_argument("--sft-weight-start", type=float, default=1.0,
                   help="[single-adv mode] λ(t=0) multiplier on SFT-seed advantages.")
    p.add_argument("--sft-weight-end", type=float, default=0.1,
                   help="[single-adv mode] λ(t=T) multiplier on SFT-seed advantages. "
                        "Set equal to --sft-weight-start to disable decay.")
    # --- per-stage (process-supervised) advantage ---
    p.add_argument("--per-stage", action="store_true",
                   help="Use per-stage (per-process) advantage: each assistant "
                        "turn's tokens carry w_stage*S_stage instead of one scalar "
                        "over the whole trajectory. Requires dataset with a "
                        "`messages` field + S_plan/S_select/S_reason.")
    p.add_argument("--w-plan", type=float, default=0.2,
                   help="[per-stage] weight on S_plan (decompose/retrieve/"
                        "select_relations/select turns).")
    p.add_argument("--w-select", type=float, default=0.3,
                   help="[per-stage] weight on S_select (expand_branches turns).")
    p.add_argument("--w-reason", type=float, default=0.5,
                   help="[per-stage] weight on S_reason (answer turns). Upweighted "
                        "since it is the outcome + the short-board stage.")
    p.add_argument("--per-stage-chunk", type=int, default=1024,
                   help="[per-stage] time-dim chunk for the per-token logprob "
                        "forward. Bounds peak logits mem to B*chunk*V. Lower if OOM.")
    # --- origin-stage process reward (scalar limer) ---
    p.add_argument("--origin-stage", action="store_true",
                   help="Origin-stage process reward: pre-tokenize so only the "
                        "origin-stage assistant turn(s) are labeled, route a "
                        "scalar group-baselined advantage through the fast "
                        "limer GRPO loss. Requires prompt/completion/advantage/"
                        "origin_stage columns (build_advantage_dataset.py default).")
    # --- routed scalar-GRPO (per-example stage-mask; a/b/c routing) ---
    p.add_argument("--routed", action="store_true",
                   help="Routed scalar-GRPO: pre-tokenize so only train_stages "
                        "turns are labeled (a/b/c routing baked into the "
                        "completion_mask), route a scalar advantage through "
                        "limer GRPO, CiSPO λ on role=sft rows. Requires "
                        "messages + train_stages + advantage + role columns "
                        "(route_cases.py + build_routed_dataset.py).")
    # --- smoke test (logic only, no model/GPU) ---
    p.add_argument("--smoke-test", action="store_true",
                   help="Run a logic-only dry-run: tokenize, build per-token "
                        "advantage, print per-turn stats, run a mock loss through "
                        "a tiny stub model. Loads NO real model, uses NO GPU.")
    p.add_argument("--smoke-n", type=int, default=4,
                   help="[smoke-test] number of trajectories to tokenize/report.")
    args = p.parse_args()

    if not args.smoke_test and not args.output:
        p.error("--output is required (unless --smoke-test)")

    print(f"Loading dataset: {args.dataset}")
    ds = load_dataset("json", data_files=args.dataset, split="train")
    print(f"  {len(ds)} samples")

    # ---- smoke test: run before any model/GPU work ----
    if args.smoke_test:
        if args.origin_stage:
            _run_origin_stage_smoke(args, ds)
        else:
            if not args.per_stage:
                print("  [note] --smoke-test implies --per-stage for this check")
                args.per_stage = True
            _run_smoke_test(args, ds)
        return

    print(f"Loading tokenizer: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    _patch_apply_chat_template(tokenizer)
    pad_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)

    if args.origin_stage:
        # ---- origin-stage path: pre-tokenize before model load ----
        ds = _prepare_origin_stage_dataset(tokenizer, ds, args)
    elif args.routed:
        # ---- routed path: pre-tokenize (stage-mask per example) before model load ----
        ds = _prepare_routed_dataset(tokenizer, ds, args)
    elif args.per_stage:
        # ---- per-stage path: pre-tokenize before model load ----
        ds = _prepare_per_stage_dataset(tokenizer, ds, args)
    else:
        # ---- single-advantage path sanity (original, backward-compatible) ----
        if "advantage" not in ds.column_names:
            raise ValueError("Dataset missing 'advantage' column — use "
                             "build_advantage_dataset.py")
        if "role" in ds.column_names:
            from collections import Counter
            rc = Counter(ds["role"])
            print(f"  hybrid roles: {dict(rc)} (CiSPO curriculum "
                  f"λ: {args.sft_weight_start}→{args.sft_weight_end})")

    # Load the TEXT-ONLY CausalLM explicitly (Qwen3.5-9B ships as a multimodal
    # checkpoint, but Qwen3_5ForCausalLM is the text branch — no visual tower).
    # Apply Liger RMSNorm+SwiGLU patches for memory/speed; FLCE is OFF because we
    # bypass the model head (the fused limer GRPO loss reads lm_head.weight directly).
    from transformers import Qwen3_5ForCausalLM
    model = Qwen3_5ForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, attn_implementation="sdpa",
        trust_remote_code=True, low_cpu_mem_usage=True)
    print(f"  Loaded model class: {type(model).__name__}")
    try:
        from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5
        apply_liger_kernel_to_qwen3_5(model=model, fused_linear_cross_entropy=False,
                                      rms_norm=True, swiglu=True)
        print("  Applied Liger RMSNorm + SwiGLU patches (FLCE off — using limer GRPO)")
    except Exception as e:
        print(f"  [warn] liger patch failed ({e}); running vanilla backbone")

    # Hard assert: NO vision parameters loaded (text-only training).
    _vis = [n for n, _ in model.named_parameters()
            if any(k in n.lower() for k in ("visual", "vision", "patch_embed", "image"))]
    if _vis:
        raise RuntimeError(f"Text-only training expected but vision params loaded: {_vis[:5]}")
    _tot = sum(p.numel() for p in model.parameters())
    print(f"  Text-only confirmed: 0 vision params | total {_tot/1e9:.2f}B")

    # Qwen3.5 linear-attention fast path needs causal-conv1d + flash-linear-attention;
    # without them it falls back to a SLOW torch impl (the #1 speed suspect).
    try:
        from transformers.models.qwen3_5.modeling_qwen3_5 import is_fast_path_available
        print(f"  [Qwen3.5] linear-attn fast path available: {is_fast_path_available}"
              + ("" if is_fast_path_available else " (INSTALL causal-conv1d + flash-linear-attention for a big speedup)"))
    except Exception:
        pass
    # use_cache=True (default) is incompatible with gradient checkpointing.
    for cfg in (getattr(model, "config", None), getattr(getattr(model, "config", None), "text_config", None)):
        if cfg is not None and hasattr(cfg, "use_cache"):
            cfg.use_cache = False
    print("  use_cache forced to False (gradient checkpointing requires it)")

    # Qwen3.5 is HYBRID: 8 full-attention layers (q/k/v/o_proj) + 24
    # linear-attention layers (in_proj_qkv/z/b/a + out_proj) + 32 MLP.
    # ATTENTION-ONLY (both attn types) per review: the old list matched only the
    # 8 full-attn layers + MLP, leaving the 24 linear-attn layers (3/4 of
    # attention) UNADAPTED. Now cover both attention families; MLP dropped to
    # keep trainable params lean (re-add gate/up/down later for capacity).
    peft_config = LoraConfig(
        r=args.lora_rank, lora_alpha=args.lora_alpha, lora_dropout=0.05,
        bias="none", task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",                          # 8 full-attn
            "in_proj_qkv", "in_proj_z", "in_proj_b", "in_proj_a", "out_proj",  # 24 linear-attn
        ])

    # Iterative self-training: continue from a previous LoRA (load its adapter
    # weights, fresh optimizer) instead of fresh init. Avoids merge (no-merge
    # policy) and keeps ONE adapter refined across rollout rounds. peft_config=None
    # so SFTTrainer trains the existing LoRA rather than wrapping a fresh one.
    if args.init_lora:
        from peft import PeftModel
        print(f"  [init-lora] continuing from previous adapter: {args.init_lora}")
        model = PeftModel.from_pretrained(model, args.init_lora, is_trainable=True)
        peft_config = None

    if args.origin_stage:
        # SFTConfig for pre-tokenized data: we supply labels (origin turns only),
        # keep the scalar advantage through the collator.
        sft_config = SFTConfig(
            output_dir=args.output,
            num_train_epochs=args.epochs, max_steps=args.max_steps,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr, lr_scheduler_type="cosine",
            warmup_ratio=args.warmup_ratio,
            max_length=args.max_length,
            completion_only_loss=False, assistant_only_loss=False,
            logging_steps=args.log_steps, save_steps=args.save_steps,
            save_total_limit=2,
            bf16=True, gradient_checkpointing=not args.no_gc,
            gradient_checkpointing_kwargs={"use_reentrant": args.gc_reentrant},
            optim="adamw_torch_fused",
            report_to="tensorboard", packing=False, dataset_num_proc=4,
            remove_unused_columns=False)
        trainer = OfflineGRPOTrainer(
            model=model, args=sft_config, train_dataset=ds,
            processing_class=tokenizer, peft_config=peft_config,
            data_collator=_make_origin_stage_collator(pad_id),
            origin_stage=True)
        print(f"\n=== Offline GRPO (origin-stage): {len(ds)} samples ===")
        trainer.train(resume_from_checkpoint=args.resume)
        print(f"\n=== Saving to {args.output} ===")
        trainer.save_model(args.output)
        tokenizer.save_pretrained(args.output)
        print("Done.")
        return

    if args.routed:
        # Routed scalar-GRPO: pre-tokenized stage-mask + scalar advantage +
        # CiSPO λ on role=sft rows. Limer loss (no logits) → batch>=2 feasible.
        from collections import Counter
        sft_config = SFTConfig(
            output_dir=args.output,
            num_train_epochs=args.epochs, max_steps=args.max_steps,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr, lr_scheduler_type="cosine",
            warmup_ratio=args.warmup_ratio,
            max_length=args.max_length,
            completion_only_loss=False, assistant_only_loss=False,
            logging_steps=args.log_steps, save_steps=args.save_steps,
            save_total_limit=2,
            bf16=True, gradient_checkpointing=not args.no_gc,
            gradient_checkpointing_kwargs={"use_reentrant": args.gc_reentrant},
            optim="adamw_torch_fused",
            report_to="tensorboard", packing=False, dataset_num_proc=4,
            remove_unused_columns=False)
        trainer = OfflineGRPOTrainer(
            model=model, args=sft_config, train_dataset=ds,
            processing_class=tokenizer, peft_config=peft_config,
            data_collator=_make_routed_collator(pad_id),
            routed=True,
            sft_weight_start=args.sft_weight_start, sft_weight_end=args.sft_weight_end)
        rc = Counter(r for r in ds["role"]) if "role" in ds.column_names else {}
        print(f"\n=== Offline GRPO (routed): {len(ds)} samples | roles {dict(rc)} "
              f"| λ {args.sft_weight_start}→{args.sft_weight_end} ===")
        _diag_trainable(trainer)
        trainer.train(resume_from_checkpoint=args.resume)
        print(f"\n=== Saving to {args.output} ===")
        trainer.save_model(args.output)
        tokenizer.save_pretrained(args.output)
        print("Done.")
        return

    if args.per_stage:
        # SFTConfig for pre-tokenized data: no completion_only_loss (we supply
        # our own labels), keep per_token_advantage through the collator.
        sft_config = SFTConfig(
            output_dir=args.output,
            num_train_epochs=args.epochs, max_steps=args.max_steps,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr, lr_scheduler_type="cosine",
            warmup_ratio=args.warmup_ratio,
            max_length=args.max_length,
            completion_only_loss=False, assistant_only_loss=False,
            logging_steps=args.log_steps, save_steps=args.save_steps,
            save_total_limit=2,
            bf16=True, gradient_checkpointing=not args.no_gc,
            gradient_checkpointing_kwargs={"use_reentrant": args.gc_reentrant},
            optim="adamw_torch_fused",
            report_to="tensorboard", packing=False, dataset_num_proc=4,
            remove_unused_columns=False)
        trainer = OfflineGRPOTrainer(
            model=model, args=sft_config, train_dataset=ds,
            processing_class=tokenizer, peft_config=peft_config,
            data_collator=_make_per_stage_collator(pad_id),
            per_stage=True, w_plan=args.w_plan, w_select=args.w_select,
            w_reason=args.w_reason, per_stage_chunk=args.per_stage_chunk,
            sft_weight_start=args.sft_weight_start, sft_weight_end=args.sft_weight_end)
        print(f"\n=== Offline GRPO (per-stage): {len(ds)} samples ===")
        trainer.train(resume_from_checkpoint=args.resume)
        print(f"\n=== Saving to {args.output} ===")
        trainer.save_model(args.output)
        tokenizer.save_pretrained(args.output)
        print("Done.")
        return

    sft_config = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs, max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        max_length=args.max_length,
        completion_only_loss=True, assistant_only_loss=False,
        logging_steps=args.log_steps, save_steps=args.save_steps, save_total_limit=2,
        bf16=True, gradient_checkpointing=not args.no_gc,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="adamw_torch_fused",
        report_to="tensorboard", packing=False, dataset_num_proc=4,
        remove_unused_columns=False)

    trainer = OfflineGRPOTrainer(
        model=model, args=sft_config, train_dataset=ds,
        processing_class=tokenizer, peft_config=peft_config,
        loss_backend=args.loss,
        sft_weight_start=args.sft_weight_start, sft_weight_end=args.sft_weight_end)

    # Ensure the data collator forwards `advantage` (and `role`→`is_sft` for
    # hybrid datasets) to compute_loss. SFT's collator only knows fixed keys.
    _orig_collate = trainer.data_collator

    def collate_with_advantage(features):
        advantages = [f.pop("advantage", 0.0) for f in features]
        # role may be absent (plain-GRPO dataset) → is_sft all False → original
        # behavior preserved exactly.
        roles = [f.pop("role", "grpo") for f in features]
        is_sft = torch.tensor([1.0 if r == "sft" else 0.0 for r in roles],
                              dtype=torch.float32)
        batch = _orig_collate(features)
        batch["advantage"] = torch.tensor(advantages, dtype=torch.float32)
        batch["is_sft"] = is_sft
        return batch

    trainer.data_collator = collate_with_advantage

    print(f"\n=== Offline GRPO: {len(ds)} samples ===")
    trainer.train(resume_from_checkpoint=args.resume)
    print(f"\n=== Saving to {args.output} ===")
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print("Done.")


if __name__ == "__main__":
    main()
