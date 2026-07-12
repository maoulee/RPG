#!/usr/bin/env python3
"""Offline SFT training for the 6-tool RPG agent.

Uses trl SFTTrainer with prompt-completion data (from build_offline_dataset.py
--mode sft_expand). The prompt-completion format + completion_only_loss=True
applies a POSITION-based loss mask (prompt tokens → -100), so it does NOT need
the chat_template {% generation %} block. Every assistant turn in the trajectory
becomes a trainable completion.

Minimal test first (few samples, 1-2 steps) to validate the pipeline before a
full run.

Usage:
    # minimal smoke test
    python scripts/train_sft.py \
        --dataset data/offline_grpo/sft_expand_smoke.jsonl \
        --model /zhaoshu/llm/Qwen3.5-9B \
        --output checkpoint/sft_smoke --max-steps 2

    # full run
    python scripts/train_sft.py \
        --dataset data/offline_grpo/sft_expand_cwq.jsonl \
        --model /zhaoshu/llm/Qwen3.5-9B \
        --output checkpoint/sft_cwq --epochs 2 --lr 1e-5 --batch-size 1 --grad-accum 8
"""
from __future__ import annotations

import argparse
import os

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def _patch_apply_chat_template(tokenizer):
    """Fix trl 0.25.1 × transformers 5.8 incompatibility.

    transformers 5.8's ``apply_chat_template(tokenize=True)`` returns a
    ``BatchEncoding`` (len == n_keys), but trl 0.25.1 expects ``list[int]`` and
    does ``prompt_ids[0] if isinstance(prompt_ids[0], list) else prompt_ids``,
    which mis-handles BatchEncoding (its [0] is an Encoding, not a list) →
    completion_mask ends up almost-all-1 (prompt not masked).

    Wrap apply_chat_template so that, when ``tokenize=True`` without
    ``return_dict=True``, it returns the plain ``list[int]`` of input_ids.
    """
    if getattr(tokenizer, "_rl_patch_applied", False):
        return
    orig = tokenizer.apply_chat_template

    def patched(messages=None, tokenize=False, return_dict=False, return_assistant_tokens_mask=False, **kw):
        if tokenize and not return_dict:
            out = orig(messages, tokenize=True, return_dict=False, **kw)
            # BatchEncoding / dict → take input_ids; nested list → flatten
            if hasattr(out, "get") or isinstance(out, dict):
                ids = out["input_ids"]
                return ids[0] if isinstance(ids, list) and ids and isinstance(ids[0], list) else ids
            return out
        return orig(messages, tokenize=tokenize, return_dict=return_dict,
                    return_assistant_tokens_mask=return_assistant_tokens_mask, **kw)

    tokenizer.apply_chat_template = patched
    tokenizer._rl_patch_applied = True


def main():
    p = argparse.ArgumentParser(description="Offline SFT for 6-tool RPG agent")
    p.add_argument("--dataset", required=True)
    p.add_argument("--model", default="/zhaoshu/llm/Qwen3.5-9B")
    p.add_argument("--output", required=True)
    p.add_argument("--max-length", type=int, default=8192)
    p.add_argument("--max-steps", type=int, default=-1, help="-1 = full epochs")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lora-rank", type=int, default=64)
    p.add_argument("--lora-alpha", type=int, default=128)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--log-steps", type=int, default=5)
    args = p.parse_args()

    print(f"Loading dataset: {args.dataset}")
    ds = load_dataset("json", data_files=args.dataset, split="train")
    print(f"  {len(ds)} samples")

    print(f"Loading model: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    _patch_apply_chat_template(tokenizer)  # fix trl×transformers5.8 BatchEncoding bug
    # Load via Liger-Kernel's loader for fused ops (lower activation memory).
    from liger_kernel.transformers import AutoLigerKernelForCausalLM
    model = AutoLigerKernelForCausalLM.from_pretrained(
        args.model,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    print("  Model loaded with Liger-Kernel fused ops")

    peft_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    sft_config = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        max_length=args.max_length,
        # prompt-completion format → position-based completion mask, no {% generation %} needed
        completion_only_loss=True,
        assistant_only_loss=False,
        logging_steps=args.log_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="tensorboard",
        packing=False,
        dataset_num_proc=4,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=ds,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    print(f"\n=== Training: {len(ds)} samples, "
          f"epochs={args.epochs if args.max_steps < 0 else 'max_steps=' + str(args.max_steps)} ===")
    trainer.train()

    print(f"\n=== Saving to {args.output} ===")
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print("Done.")


if __name__ == "__main__":
    main()
