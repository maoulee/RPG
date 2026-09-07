#!/usr/bin/env python3
"""Decision-point prefix replay: does the §1.5 error-correction ladder make
the model choose a DIFFERENT (corrective) action at the moment it originally
detected an error and walked through it?

Design (user ruling, 2026-08-22): NOT a full-case rerun. For each error case
in the fixstack2 baseline, cut the trajectory at the FIRST detection point
(first assistant thinking that matches the DETECT markers), rebuild the chat
prefix with the NEW system prompt (SEQ_AGENTS.md incl. §1.5 ladder), generate
ONE next action, and compare it with the ORIGINAL next action:
  corrective  = different relation set / borrowed center / rephrased query /
                ✗ mismatch closure / otherwise-new direction
  same        = the original (locked-in) action repeated.

Usage: python scripts/probe_ladder_replay.py [A_LIMIT] [C_LIMIT]   (default 20/30)
Output: tmp/ladder_replay.json + stdout summary.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path("/zhaoshu/subgraph")
sys.path.insert(0, str(ROOT))

DETECT = re.compile(
    r"(doesn'?t|does not|not) (match|what I|align|seem right|help)"
    r"|wrong (relation|entity|plan|direction|approach|subgraph|choice)"
    r"|off-?target|reconsider"
    r"|this suggests the graph doesn'?t"
    r"|doesn'?t (contain|show|yield|provide) (the |any |this )?(evidence|information|answer|location)"
    r"|no (relevant |matching |useful )?(evidence|information|results)"
    r"|I don'?t see (any|the)|none of (these|the (relations|candidates))"
    r"|missing|absent|empty", re.I)
BLOCK = re.compile(
    r"cannot re-?plan|can't re-?plan|plan is (frozen|immutable|locked)"
    r"|unable to (adjust|modify|change|restructure)"
    r"|stuck with (what I have|the plan|this)"
    r"|work with what I have|proceed with what", re.I)


def build_prefix(traj, cut, question):
    msgs = []
    for s in traj[:cut]:
        role = s.get("role")
        c = s.get("content") or ""
        if role == "assistant":
            r = (s.get("reasoning") or "").strip()
            msgs.append({"role": "assistant",
                         "content": (f"<think>\n{r}\n</think>\n{c}" if r else c)})
        elif role == "tool":
            name = s.get("name")
            msgs.append({"role": "user",
                         "content": (f"Tool result ({name}): {c}" if name else c)})
        else:
            msgs.append({"role": role, "content": c})
    # Qwen chat template REQUIRES a leading user turn; very early cuts may
    # start with the assistant plan — synthesize the opening user turn.
    if not msgs or msgs[0].get("role") != "user":
        msgs.insert(0, {"role": "user",
                        "content": f"Answer the knowledge-graph question: {question}"})
    return msgs


def first_action(text):
    for ln in (text or "").splitlines():
        ls = ln.strip()
        if ls.startswith("tool:") or ls.startswith("["):
            return ls
    return (text or "").strip().splitlines()[0] if text else ""


def classify_action(new_a, orig_a):
    if not new_a:
        return "empty"
    if "✗" in new_a and "✗" not in (orig_a or ""):
        return "corrective:诊断关闭(✗ mismatch)"
    n_tool = new_a.split(":")[0] if new_a.startswith("tool:") else ""
    o_tool = (orig_a or "").split(":")[0] if (orig_a or "").startswith("tool:") else ""
    if n_tool and n_tool == o_tool:
        return "same-tool"          # same tool: needs arg diff below, caller refines
    if n_tool and o_tool and n_tool != o_tool:
        return "corrective:换了工具/方向"
    if new_a.startswith("[") and not (orig_a or "").startswith("["):
        return "corrective:先检查点后行动"
    return "unclear"


async def main():
    a_lim = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    c_lim = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    base = json.loads((ROOT / "reports/regress267_fixstack2.json").read_text())
    sys_new = (ROOT / "kgqa/agent/SEQ_AGENTS.md").read_text()

    cohorts = {"A_locked": [], "C_passive": []}
    for r in base:
        if (r.get("f1") or 0) >= 0.999:
            continue
        thinking = "\n".join(s.get("reasoning") or "" for s in r["trajectory"]
                             if s.get("role") == "assistant")
        if not thinking or not DETECT.search(thinking):
            continue
        cut = None
        first_sg_result = next(
            (i for i, s in enumerate(r["trajectory"])
             if s.get("role") == "tool" and s.get("name") == "retrieve_subgraph"), None)
        if first_sg_result is not None:
            cut = next(
                (i for i, s in enumerate(r["trajectory"])
                 if i > first_sg_result and s.get("role") == "assistant"
                 and DETECT.search(s.get("reasoning") or "")), None)
        if cut is None:
            continue   # no mid-course detection: not this experiment's target
        entry = (r["case_id"], r["question"], cut, r["trajectory"])
        (cohorts["A_locked"] if BLOCK.search(thinking) else cohorts["C_passive"]).append(entry)

    picks = {k: v[:lim] for k, lim, v in
             (("A_locked", a_lim, cohorts["A_locked"]),
              ("C_passive", c_lim, cohorts["C_passive"]))}
    jobs, meta = [], []
    for tag, entries in picks.items():
        for cid, q, cut, traj in entries:
            msgs = [{"role": "system", "content": sys_new}] + build_prefix(traj, cut, q)
            jobs.append(msgs)
            orig = traj[cut]["content"]
            meta.append({"cohort": tag, "case_id": cid, "question": q,
                         "cut": cut, "orig_action": first_action(orig),
                         "orig_full": orig})
    print(f"probes: {len(jobs)} (A={len(picks['A_locked'])} C={len(picks['C_passive'])})",
          flush=True)

    from kgqa.llm.offline_vllm import OfflineVLLM
    llm = OfflineVLLM(max_num_seqs=64)
    results = llm.chat_batch(jobs, thinking_budget=1000, temperature=0.3,
                             top_p=0.8, top_k=20, presence_penalty=1.5)
    out = []
    from collections import Counter
    verdicts = Counter()
    for m, res in zip(meta, results):
        gen = getattr(res, "text", "") or ""
        reason = getattr(res, "reasoning", "") or ""
        new_a = first_action(gen)
        v = classify_action(new_a, m["orig_action"])
        if v == "same-tool":
            # same tool — corrective only if arguments differ
            na, oa = new_a, m["orig_action"]
            v = "same-action" if na.strip() == oa.strip() else "corrective:同工具换参数"
        verdicts[v] += 1
        out.append({**m, "new_action": new_a, "verdict": v,
                    "new_reasoning": str(reason)[:600], "new_full": str(gen)})
    (ROOT / "tmp/ladder_replay.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print("\n".join(f"{k}: {v}" for k, v in verdicts.most_common()))
    print("-> tmp/ladder_replay.json")


if __name__ == "__main__":
    asyncio.run(main())
