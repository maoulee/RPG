#!/usr/bin/env python3
"""ABC test: move the reasoning into CONTENT as an evidence checklist (committed
solution trajectory), not <think>. Parser anchors on `tool:`, so the checklist
text before it is safe. Overrides the lean-content rule for the answer step only.

baseline = C (v4, lean content)  [reference]
A = per-candidate graph-EVIDENCE checklist (cite a graph triple to keep/drop each)
B = CONSTRAINT-forced checklist (state graph-supported constraints, then answer)
C = DECISION-forced table (KEEP/DROP + graph reason per candidate)

All general (no case-specific terms). Tested on the full 100-case.
"""
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import abcd_test as T

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "kgqa/agent/AGENTS.md"
BACKUP = ROOT / "kgqa/agent/AGENTS.md.cot_backup"

# Override the lean-content rule for the answer step. Insert right after the
# answer-section header, before the C prose.
PREFIX = ("## Answer reasoning\n\n"
          "**For the `answer` call ONLY, your CONTENT carries the reasoning as an "
          "evidence checklist — it is your committed solution trajectory here, NOT a "
          "lean status note (the lean-content rule is suspended for this one call). "
          "Cite ONLY graph triples you actually see; if you cannot cite a graph triple, "
          "you cannot drop the candidate. Then emit the `tool:` call.**\n\n")

A_FMT = (
    "Checklist format (in content, before `tool:`):\n"
    "```\n"
    "CANDIDATES: <entities on the answer branch>\n"
    "EVIDENCE (one graph triple per candidate — KEEP or DROP, with the triple):\n"
    "  - <candidate>: KEEP — <graph triple>   |   DROP — <graph triple>  (if no graph triple proves it fails, write KEEP — no graph evidence to drop)\n"
    "ANSWER: <the KEEP entities>\n"
    "tool: {\"tool\": \"answer\", \"args\": {\"entities\": [...]}}\n"
    "```\n\n"
)
B_FMT = (
    "Checklist format (in content, before `tool:`):\n"
    "```\n"
    "CANDIDATES: <entities on the answer branch>\n"
    "CONSTRAINTS the question STATES (and a graph triple supporting each; \"none\" if the question states none):\n"
    "  - <constraint>: <graph triple>  (or: none)\n"
    "ANSWER: <candidates the graph keeps after those constraints; if no constraint is stated and the question is not a one-at-a-time role in present/dated tense, return ALL candidates>\n"
    "tool: {\"tool\": \"answer\", \"args\": {\"entities\": [...]}}\n"
    "```\n\n"
)
C_FMT = (
    "Checklist format (in content, before `tool:`) — one line per candidate:\n"
    "```\n"
    "<candidate1>: KEEP — <graph reason>   (or  DROP — <graph reason>; a DROP needs a graph triple proving failure — \"I think\" / outside knowledge is NOT a graph reason)\n"
    "<candidate2>: ...\n"
    "ANSWER: <all KEEP candidates>\n"
    "tool: {\"tool\": \"answer\", \"args\": {\"entities\": [...]}}\n"
    "```\n\n"
)


def build_content_variant(base_C, fmt):
    import re
    text = base_C.replace("## Answer reasoning\n\n", PREFIX + fmt, 1)
    # relax the output-format lean reminder for the answer call (robust to indent)
    text = re.sub(
        r"Do your\s+detailed reasoning in `<think>` instead — content should stay lean\.",
        "Do your detailed reasoning in `<think>` for decompose/select/expand; "
        "for the `answer` call, content carries the evidence checklist (see Answer reasoning).",
        text, count=1)
    return text


def main():
    current = AGENTS.read_text()
    shutil.copy(AGENTS, BACKUP)
    base_C = T.build_variant(current, T.C_ANSWER)
    variants = {
        "C0": ("baseline v4 (lean content)",      base_C),
        "A":  ("content: per-candidate EVIDENCE", build_content_variant(base_C, A_FMT)),
        "B":  ("content: CONSTRAINT-forced",      build_content_variant(base_C, B_FMT)),
        "C":  ("content: DECISION table",         build_content_variant(base_C, C_FMT)),
    }
    results = {}
    for name, (desc, text) in variants.items():
        if name in ("A", "B", "C"):
            assert "evidence checklist" in text, f"{name} patch failed"
        AGENTS.write_text(text)
        p = T.run_eval(name if name != "C0" else "C0")
        if p and p.exists():
            results[name] = (desc, T.metrics(p))
            print(f"  {name} ({desc}): {results[name][1]}", flush=True)
    shutil.copy(BACKUP, AGENTS); BACKUP.unlink()
    print("\n" + "=" * 74)
    print("CONTENT-CHECKLIST ABC TEST (100-case, 9B, on top of C)")
    print("=" * 74)
    print(f"{'variant':6} {'description':32} {'GT':>6} {'llm_hit':>8} {'Hit@1':>7} {'F1':>7}")
    for name, (desc, m) in results.items():
        if m:
            print(f"{name:6} {desc:32} {m['gt']:5.1f}% {m['llm_hit']:7.1f}% {m['hit1']:6.1f}% {m['f1']:7.4f}")


if __name__ == "__main__":
    main()
