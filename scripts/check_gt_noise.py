#!/usr/bin/env python3
"""Detect and mark noisy GT answers in WebQSP.

Two-stage:
  1. REGEX (zero-cost, full 1639): flags CVT-id leak, duplicates, date-vs-year
     format, foreign-script, and superlong answers. Also SCREENS
     temporal/superlative-constraint questions (year/first/last/before/after in
     question + >=3 GT) as candidates for LLM judging.
  2. LLM (only on temporal candidates): asks the local model whether each GT
     answer violates the question's time/ordinal constraint.

Output: data/cwq_processed/mask_gt_noise_ids.json (id list, same format as the
existing mask_wrong_type_ids.json, loaded by run_agent/run_pipeline to skip).

This is a DATA-QUALITY task — it does not touch the agent/traversal pipeline.
GT is only MARKED, never rewritten.

Usage:
    python scripts/check_gt_noise.py                     # regex only
    python scripts/check_gt_noise.py --llm-judge         # + LLM temporal judging
    python scripts/check_gt_noise.py --dry-run           # print stats, no write
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kgqa.core.config import DEFAULT_PILOT, DEFAULT_CWQ, MASK_WRONG_TYPE
from kgqa.core.utils import normalize

MASK_OUT = ROOT / "data" / "cwq_processed" / "mask_gt_noise_ids.json"

YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ID_RE = re.compile(r"^[mg]\.[a-z0-9_]+$", re.I)
SUPER_Q_RE = re.compile(r"\b(first|last|current|former|before|after|since|during)\b", re.I)


def _load_cases(pilot_path):
    pilot = json.loads(Path(pilot_path).read_text())
    samples = {s.get("id"): s for s in pickle.loads(DEFAULT_CWQ.read_bytes())}
    cases = []
    for p in pilot:
        cid = p["case_id"]
        s = samples.get(cid.split("_")[0], {})
        gt = p.get("gt_answers") or p.get("gt") or []
        cases.append({"case_id": cid, "question": p.get("question", ""), "gt": gt, "sample": s})
    return cases


# ---------------------------------------------------------------------------
# Stage 1: regex noise detection
# ---------------------------------------------------------------------------

def regex_mark(cases):
    """Return (noise_ids:set, candidates_for_llm:list, breakdown:dict)."""
    noise = set()
    breakdown = {"cvt_id": 0, "duplicate": 0, "date_vs_year": 0,
                 "superlong": 0, "empty_gt": 0}
    llm_candidates = []

    for c in cases:
        cid, q, gt = c["case_id"], c["question"], c["gt"]
        if not gt:
            noise.add(cid); breakdown["empty_gt"] += 1
            continue

        flagged = False
        # CVT-id leak: GT is a bare Freebase node id (m.xxx / g.xxx).
        if any(ID_RE.match(g) for g in gt):
            noise.add(cid); breakdown["cvt_id"] += 1; flagged = True
        # Duplicate GT (same normalized entity listed twice).
        norms = [normalize(g) for g in gt]
        if len(norms) != len(set(norms)):
            noise.add(cid); breakdown["duplicate"] += 1; flagged = True
        # Date-vs-year: "what year" but GT is a full ISO date.
        if re.search(r"what year|which year", q, re.I) and any(DATE_RE.search(g) for g in gt):
            noise.add(cid); breakdown["date_vs_year"] += 1; flagged = True
        # Superlong GT (>80 chars — edition/publisher suffix noise).
        if any(len(g) > 80 for g in gt):
            noise.add(cid); breakdown["superlong"] += 1; flagged = True

        # Temporal/ordinal-constraint screening for LLM: question mentions a
        # year or first/last/before/after, AND has >=3 GT (a single clean GT
        # is unlikely to violate; multiple answers risk mixing eras).
        has_year = bool(YEAR_RE.search(q))
        has_super = bool(SUPER_Q_RE.search(q))
        if (has_year or has_super) and len(gt) >= 3 and not flagged:
            llm_candidates.append(c)

    return noise, llm_candidates, breakdown


# ---------------------------------------------------------------------------
# Stage 2: LLM temporal-constraint judging
# ---------------------------------------------------------------------------

LLM_PROMPT = """You are checking a QA dataset for annotation errors. The question has a TIME or ORDER constraint (a specific year, or "first/last/before/after"). Some gold answers VIOLATE that constraint — they belong to a different time period.

Question: {question}
Gold Answer(s): {answers}

Task: for EACH answer, decide if it could plausibly satisfy the question's time/order constraint. If ANY answer clearly violates the constraint (wrong era, different time period), the case is NOISY.

Respond in EXACTLY this format:
<judgment>
noisy: yes or no
violating: [list the answers that violate the constraint, or "none"]
reason: [one sentence]
</judgment>"""


async def llm_judge(candidates, args):
    """Ask the local model whether each candidate's GT violates its constraint."""
    import aiohttp
    from kgqa.llm.batch import batch_call_llm

    prompts = []
    for c in candidates:
        msgs = [{"role": "user", "content": LLM_PROMPT.format(
            question=c["question"], answers=", ".join(c["gt"][:10]))}]
        prompts.append(msgs)

    print(f"  LLM judging {len(prompts)} temporal candidates...")
    async with aiohttp.ClientSession() as session:
        responses = await batch_call_llm(session, prompts, max_tokens=200)

    noisy_ids = set()
    for c, resp in zip(candidates, responses):
        if not resp:
            continue
        m = re.search(r"noisy:\s*(yes|no)", resp, re.I)
        if m and m.group(1).lower() == "yes":
            noisy_ids.add(c["case_id"])
    return noisy_ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    ap = argparse.ArgumentParser(description="Mark noisy GT answers in WebQSP")
    ap.add_argument("--pilot", default=str(DEFAULT_PILOT),
                    help="pilot results.json (default: small 50-case; pass the full webqsp pilot for all)")
    ap.add_argument("--llm-judge", action="store_true",
                    help="Also LLM-judge temporal-constraint candidates")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print stats only, do not write mask file")
    args = ap.parse_args()

    cases = _load_cases(args.pilot)
    print(f"Loaded {len(cases)} cases")

    noise, candidates, breakdown = regex_mark(cases)
    print(f"\n=== Stage 1: regex noise ===")
    for k, v in breakdown.items():
        print(f"  {k:15s}: {v}")
    print(f"  regex-flagged cases: {len(noise)}")
    print(f"  temporal candidates for LLM: {len(candidates)}")

    if args.llm_judge and candidates:
        llm_noise = await llm_judge(candidates, args)
        print(f"\n=== Stage 2: LLM temporal judging ===")
        print(f"  LLM-flagged noisy: {len(llm_noise)}")
        noise |= llm_noise

    # Merge with existing wrong-type mask (don't double-count, just union).
    existing = set()
    if MASK_WRONG_TYPE.exists():
        existing = set(json.loads(MASK_WRONG_TYPE.read_text()))
    overlap = noise & existing
    print(f"\n=== Summary ===")
    print(f"  new noise ids: {len(noise)}")
    print(f"  overlap with existing wrong-type mask: {len(overlap)}")
    print(f"  total unique noise (new ∪ existing): {len(noise | existing)}")

    if not args.dry_run:
        MASK_OUT.parent.mkdir(parents=True, exist_ok=True)
        # Write ONLY the new GT-noise ids (separate from wrong-type, so each
        # mask stays independently auditable). Loaders union them at runtime.
        MASK_OUT.write_text(json.dumps(sorted(noise), ensure_ascii=False, indent=2))
        print(f"\n  wrote {MASK_OUT} ({len(noise)} ids)")
        print(f"  to use: union this with MASK_WRONG_TYPE in run_agent/run_pipeline")
    else:
        print(f"\n  (dry-run, no file written)")


if __name__ == "__main__":
    asyncio.run(main())
