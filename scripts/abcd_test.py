#!/usr/bin/env python3
"""ABCD prompt test: inject 4 answer-section variants into AGENTS.md, run 100-case each, compare.

A = original baseline (git 6a27056: FROM->WHERE->SELECT)
B = audit v4 rewrite (default-keep-all spine, three pick-one triggers enumerated)
C = minimal one-paragraph v4
D = self-question v4

B/C/D share a v4-aligned Thinking bullet + expand nudge (cross-section held constant).
"""
import subprocess, json, shutil, re, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "kgqa/agent/AGENTS.md"
BACKUP = ROOT / "kgqa/agent/AGENTS.md.abcd_backup"
sys.path.insert(0, str(ROOT))

# ---------- shared v4 cross-section patches (for B/C/D) ----------
V4_THINK_ANSWER = ("- **answer**: keep all branch entities by default; apply the question's "
                   "explicit filters; pick one ONLY on a one-at-a-time-current / superlative / "
                   "unique-attribute trigger; else keep all — graph evidence only, never world knowledge.")
V4_EXPAND_NUDGE = """may skip directly to `answer` for a plain list-all ("what championships / languages
   border X"). Expand first when you need the start/end dates on each candidate to pick a specific
   holder — i.e. the question asks for the current or dated holder of something held one-at-a-time
   (a leader / coach / spouse), or states a date / official / quantity, or uses a superlative or a
   unique attribute. The overview shows candidate names only; the per-candidate dates live in the
   expanded evidence."""

# ---------- variant answer sections ----------
B_ANSWER = """## Answer reasoning

Once you've expanded the branch whose relation chain answers the question, **every entity on that branch is a candidate — keep all of them by default. Narrowing is the exception, not the rule.** Do not decide the count up front.

Apply the question's **explicit** filters directly — only what it actually states: a stated date, a stated type ("what country / person / language"), "official / main", or a stated quantity. Anything the question does NOT state is not a filter; do not invent one.

Then make the one judgment that decides one-vs-all — **does THIS question want only a single answer?** It wants one only when one of these is true:
- **One-at-a-time fact, asked for the current or a specific moment** — a role only one entity holds at a time (a position, a leader, a coach, a spouse, the team a player plays for, a place's capital), phrased "who is / currently / the" or pinned to a date. Pick the single entity the graph points to: the current holder (the one whose end date is open / `to=(incumbent)`), the most recent, or the one matching the stated date — use the start/end dates shown on each candidate.
- **Superlative** — "first / last / largest / oldest / most". Pick the single entity that ranks on that attribute (not by date).
- **Unique attribute** — the question pins exactly one by a distinguishing attribute: "the capital of X", "the female X", "the official language". Pick the one matching it.

Hit any one of these → return that single entity. Hit none → keep every candidate on the branch.

Keep-all is correct and common for facts that coexist: all championships won, all languages spoken, all team members, all films, all the deities a people worship — keep them all, **even if the question reads as grammatically singular** ("their God" → all the deities; "what championships" → all of them). A date sitting on such a relation is just a record — it does not pick one, and you should not invent one.

Only remove an entity when both the question states a constraint AND the graph evidence shows it fails; if you are unsure or the graph lacks the attribute to check, keep it.

Use only the graph as evidence — never outside knowledge (fame, prominence, dates from memory) to fabricate a filter. If the graph shows 17 championships and the question states no time/singular constraint, output all 17.

Output the kept entities verbatim as the graph named them — the complete entity ("2014 World Series", "United States of America"), never a bare year, number, or ID; no bridge/intermediate nodes. Put the one you are most certain of first (top-1 / Hit@1); the rest follow in any order.
"""

C_ANSWER = """## Answer reasoning

Every entity on the branch you expanded is a candidate — **keep all of them by default; narrowing is the exception.** First apply only the filters the question explicitly states (a date, a type like "what country", "official", a quantity); never invent one. Then decide one-vs-all: the question wants a single answer only when it asks for the current/specific holder of something one entity holds at a time (a position, leader, coach, spouse, the team a player plays for, a capital), OR uses a superlative (first/last/largest/most), OR pins one by a unique attribute ("the capital", "the female X") — in those cases pick the one the graph evidence identifies (the incumbent / most-recent date / ranked / attribute-matching); otherwise return every candidate. Facts that coexist (championships, languages, members, deities) are all kept even if the question reads singular — a date on them is just a record, not a filter. When unsure, keep. Use graph evidence only, never world knowledge. Output entities verbatim (complete names, no bare years/IDs), most-certain first (top-1 / Hit@1).
"""

D_ANSWER = """## Answer reasoning

After expanding the branch, ask yourself first: **does this question want only ONE answer, or all that apply?** Don't presuppose the count.

Default to keeping every entity on the branch. Apply the question's explicit filters directly (stated date, type "what country", "official", quantity) — drop only what fails one of these; never invent a filter.

The question wants ONE answer only if you answer "yes" to any of: is it asking for the current or dated holder of something held one-at-a-time (a position, leader, coach, spouse, a player's team, a capital)? Does it use a superlative (first/last/largest/most)? Does it pin one by a unique attribute ("the capital", "the female X")? If yes to any, pick that single entity with graph evidence (the incumbent `to=(incumbent)`, most-recent date, ranked, or attribute-matching). If no to all, keep every candidate.

Coexisting facts (championships, languages, deities, members) stay all, even when the question reads singular ("their God" → all deities); a date on them is bookkeeping. When unsure, keep. Graph evidence only, never world knowledge. Output entities verbatim (complete names, no bare years/IDs), most-certain first (top-1 / Hit@1).
"""


def patch_cross_section(text):
    """Apply v4 Thinking bullet + expand nudge to a v4-variant AGENTS.md text."""
    # Thinking answer bullet
    text = re.sub(r"- \*\*answer\*\*:.*?(?=\n- |\n\n|\Z)", V4_THINK_ANSWER, text, count=1, flags=re.DOTALL)
    # expand nudge: replace the "may skip directly ... expanded evidence." block
    text = re.sub(r"   may skip directly to `answer`.*?expanded evidence\.",
                  "   " + V4_EXPAND_NUDGE.strip(), text, count=1, flags=re.DOTALL)
    return text


def build_variant(base_text, answer_section):
    """Replace the answer section (## Answer reasoning .. ## Decision rules) + patch cross-section."""
    pre, rest = re.split(r"\n## Answer reasoning\b", base_text, maxsplit=1)
    _ans, post = re.split(r"\n## Decision rules\b", rest, maxsplit=1)
    out = pre + "\n" + answer_section.rstrip() + "\n\n## Decision rules" + post
    return patch_cross_section(out)


def get_baseline_A():
    return subprocess.check_output(["git", "show", "6a27056:kgqa/agent/AGENTS.md"], cwd=ROOT).decode()


def run_eval(name):
    out = ROOT / f"reports/abcd_{name}/results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["python3", "scripts/run_agent_batch.py", "--start", "0", "--end", "100",
           "--output", str(out), "--parallel", "16"]
    print(f"\n>>> running variant {name} ...", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ERROR variant {name}: {r.stderr[-500:]}", flush=True)
        return None
    return out


def metrics(path):
    from kgqa.core.utils import normalize as _norm
    d = json.load(open(path))
    recs = d if isinstance(d, list) else d.get("results", d)
    recs = [r for r in recs if isinstance(r, dict)]
    n = len(recs)
    if not n:
        return None
    gt = sum(1 for r in recs if r.get("gt_hit"))
    lh = sum(1 for r in recs if r.get("llm_hit"))
    f1 = sum(r.get("llm_f1", 0) for r in recs) / n

    def _h1(r):
        ans = r.get("llm_answer", "") or ""
        preds = [p.strip() for p in ans.split(" | ") if p.strip()]
        if not preds:
            return False
        g = r.get("gt_answers") or []
        if not g:
            return False
        p1 = _norm(preds[0])
        return any(p1 in _norm(x) or _norm(x) in p1 for x in g)
    h1 = sum(1 for r in recs if _h1(r))
    return dict(n=n, gt=gt / n * 100, llm_hit=lh / n * 100, hit1=h1 / n * 100, f1=f1)


def main():
    current = AGENTS.read_text()
    shutil.copy(AGENTS, BACKUP)
    variants = {
        "A": ("baseline (git 6a27056)", get_baseline_A()),
        "B": ("audit v4 rewrite", build_variant(current, B_ANSWER)),
        "C": ("minimal v4", build_variant(current, C_ANSWER)),
        "D": ("self-question v4", build_variant(current, D_ANSWER)),
    }
    results = {}
    for name, (desc, text) in variants.items():
        AGENTS.write_text(text)
        # loader uses lru_cache per-process; run_agent_batch is a fresh process each time
        p = run_eval(name)
        if p and p.exists():
            results[name] = (desc, metrics(p))
            print(f"  {name} ({desc}): {results[name][1]}", flush=True)
    # restore
    shutil.copy(BACKUP, AGENTS)
    BACKUP.unlink()
    print("\n" + "=" * 70)
    print("ABCD RESULTS (100-case greedy)")
    print("=" * 70)
    print(f"{'variant':8} {'description':22} {'GT':>6} {'llm_hit':>8} {'Hit@1':>7} {'F1':>7}")
    for name, (desc, m) in results.items():
        if m:
            print(f"{name:8} {desc:22} {m['gt']:5.1f}% {m['llm_hit']:7.1f}% {m['hit1']:6.1f}% {m['f1']:7.4f}")
    print("baseline reference: cwq_hit1_minimal GT=90.9 llm_hit=85.9 Hit@1=79.8 F1=0.7822")


if __name__ == "__main__":
    main()
