#!/usr/bin/env python3
"""A/B test two compliance fixes on top of the C (v4) prompt. General rules only
(no case-specific examples → no overfit). Tested on the FULL 100-case.

baseline = C (v4 minimal)
A = C + tighten the Role world-knowledge loophole (general: world knowledge only
    for parsing text + typing the relation; NOT for entity facts/attributes/dates).
B = C + structured <think> template (FACTS graph-only → CONSTRAINTS question-only
    → ONE-ANSWER? → DECIDE). Forces graph-facts separate from reasoning.
"""
import subprocess, json, shutil, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import abcd_test as T

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "kgqa/agent/AGENTS.md"
BACKUP = ROOT / "kgqa/agent/AGENTS.md.ab_backup"

# --- patch A: tighten Role world-knowledge loophole (general, no case mentions) ---
ROLE_OLD = ("do **not** use outside world knowledge for facts — only for understanding the\n"
            "question and for typing the relation you need.")
ROLE_NEW = ("do **not** use outside world knowledge for ANY fact — not about entities, their\n"
            "attributes, dates, roles, tenure, or how they relate. Use world knowledge ONLY to\n"
            "(1) parse the question text and (2) pick which relation type to walk. Every entity,\n"
            "attribute, and date in your answer must come from the graph evidence the tools\n"
            "returned; if the graph does not show it, you do not know it.")

def patch_role(text):
    return text.replace(ROLE_OLD, ROLE_NEW)

# --- patch B: structured <think> template (general, no case mentions) ---
TEMPLATE = (
    "## Answer reasoning\n\n"
    "In `<think>`, work the answer in this fixed order before emitting the `answer` call:\n"
    "- **FACTS (graph only)** — the candidates the expanded branch returned. List them; do NOT mix in anything the graph does not show.\n"
    "- **CONSTRAINTS (question text only)** — the explicit filters the question states (a date / a type like \"what country\" / \"official\" / a quantity). Write `none` if it states none.\n"
    "- **ONE-ANSWER?** — `yes` ONLY if the question wants a single answer: a one-at-a-time role (a position, leader, coach, spouse, a player's team, a capital) asked in present or dated tense, a superlative (first/last/largest/most), or a unique attribute (\"the capital\", \"the female X\"); otherwise `no`.\n"
    "- **DECIDE** — `no` → return every candidate on the branch; `yes` → pick the one the graph evidence identifies (incumbent / most-recent date / ranked / attribute-matching).\n\n"
)

def add_structured(text):
    return text.replace("## Answer reasoning\n\n", TEMPLATE, 1)


def main():
    current = AGENTS.read_text()
    shutil.copy(AGENTS, BACKUP)
    base_C = T.build_variant(current, T.C_ANSWER)          # v4 minimal (shared base)
    variants = {
        "C":  ("baseline v4 (C)",            base_C),
        "A":  ("C + tighten Role loophole",  patch_role(base_C)),
        "B":  ("C + structured <think>",     add_structured(base_C)),
    }
    results = {}
    for name, (desc, text) in variants.items():
        # sanity: confirm the patch took
        if name == "A":
            assert "for ANY fact" in text, "A patch failed"
        if name == "B":
            assert "**FACTS (graph only)**" in text, "B patch failed"
        AGENTS.write_text(text)
        p = T.run_eval(name)
        if p and p.exists():
            results[name] = (desc, T.metrics(p))
            print(f"  {name} ({desc}): {results[name][1]}", flush=True)
    shutil.copy(BACKUP, AGENTS); BACKUP.unlink()
    print("\n" + "=" * 72)
    print("A/B COMPLIANCE TEST (100-case greedy, 9B, on top of C)")
    print("=" * 72)
    print(f"{'variant':6} {'description':30} {'GT':>6} {'llm_hit':>8} {'Hit@1':>7} {'F1':>7}")
    for name, (desc, m) in results.items():
        if m:
            print(f"{name:6} {desc:30} {m['gt']:5.1f}% {m['llm_hit']:7.1f}% {m['hit1']:6.1f}% {m['f1']:7.4f}")


if __name__ == "__main__":
    main()
