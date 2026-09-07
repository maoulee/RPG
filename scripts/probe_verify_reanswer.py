#!/usr/bin/env python3
"""Self-verify re-answer probe (user proposal, 2026-08-22): if a wrong case
is ANSWER-LAYER variance (evidence holds gold, binding went wrong), can the
model DETECT its own wrong answer and re-answer correctly when shown the
answer + a verification prompt? Control arm: does the same prompt wrongly
flip CORRECT answers (false-positive cost)?

Prefix = system(SEQ_AGENTS.md) + trajectory messages UP TO AND INCLUDING the
final answer tool result. Append ONE user turn asking verification; generate
one action. Parse the new answer (tool: answer entities / FINAL_BINDINGS).

Usage: python scripts/probe_verify_reanswer.py [N_WRONG] [N_CONTROL]
Output: tmp/verify_reanswer.json + stdout summary.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path("/zhaoshu/subgraph")
sys.path.insert(0, str(ROOT))

VERIFY_TURN = (
    "VERIFY your last answer against the QUESTION and the retrieved "
    "evidence. Check: (1) does every submitted entity satisfy ALL the "
    "question's constraints; (2) is any gold-binding visible in the evidence "
    "but missing from your answer; (3) is any submitted entity NOT justified "
    "by the evidence. If your answer was wrong or incomplete, call `answer` "
    "again NOW with the corrected entity set. If it was correct, re-state "
    "the same answer with `answer`. One decision, no further retrieval.")


def build_prefix(traj, question):
    msgs = []
    for s in traj:
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
    if not msgs or msgs[0].get("role") != "user":
        msgs.insert(0, {"role": "user",
                        "content": f"Answer the knowledge-graph question: {question}"})
    msgs.append({"role": "user", "content": VERIFY_TURN})
    return msgs


def parse_entities(text):
    """entities from a flat `tool: answer` block or a JSON list."""
    m = re.search(r"tool:\s*answer\s*\nentities:\s*(.+)", text or "")
    if m:
        val = m.group(1).strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                j = json.loads(val)
                if isinstance(j, list):
                    return [str(x) for x in j]
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in re.split(r"\s*\|\s*", val) if x.strip()]
    m = re.search(r'"entities"\s*:\s*\[(.*?)\]', text or "", re.S)
    if m:
        try:
            return [str(x) for x in json.loads(f"[{m.group(1)}]")]
        except Exception:
            return []
    m = re.search(r"FINAL_BINDINGS:\s*(.+)", text or "")
    if m:
        return [x.strip() for x in re.split(r"\s*\|\s*", m.group(1)) if x.strip()]
    return []


def f1(pred, gold):
    from kgqa.core.utils import normalize as nz
    from difflib import SequenceMatcher
    def _m(a, b):
        a, b = nz(a), nz(b)
        if a == b or b in a or a in b:
            return True
        return len(a) >= 8 and len(b) >= 8 and SequenceMatcher(None, a, b).ratio() >= 0.95
    P = set(range(len(pred))); G = set(range(len(gold)))
    if not P or not G:
        return 0.0
    tp = sum(1 for i in P if any(_m(pred[i], g) for g in gold))
    fp = len(P) - tp
    matched_g = sum(1 for j in G if any(_m(p, gold[j]) for p in pred))
    prec = tp / len(P); rec = matched_g / len(G)
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


async def main():
    n_w = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    n_c = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    run = json.loads((ROOT / "reports/regress267_ladderstack.json").read_text())
    sys_new = (ROOT / "kgqa/agent/SEQ_AGENTS.md").read_text()

    wrong, ctrl = [], []
    for r in run:
        gold = r.get("gold") or []
        ev = r.get("evidence_entities") or []
        from difflib import SequenceMatcher
        from kgqa.core.utils import normalize as nz
        def _m(a, b):
            a, b = nz(a), nz(b)
            if a == b or b in a or a in b: return True
            return len(a) >= 8 and len(b) >= 8 and SequenceMatcher(None, a, b).ratio() >= 0.95
        cov = gold and ev and sum(any(_m(p, nz(g)) for p in ev if p) for g in gold) / len(gold)
        if (r.get("f1") or 0) < 0.999 and cov and cov >= 0.999:
            wrong.append(r)
        elif (r.get("f1") or 0) >= 0.999:
            ctrl.append(r)
    wrong, ctrl = wrong[:n_w], ctrl[:n_c]
    print(f"targets(answer-layer wrong): {len(wrong)}  controls(EM): {len(ctrl)}", flush=True)

    jobs, meta = [], []
    for tag, cohort in (("wrong", wrong), ("ctrl", ctrl)):
        for r in cohort:
            # cut at the final answer tool RESULT (inclusive)
            ans_idx = max((i for i, s in enumerate(r["trajectory"])
                           if s.get("role") == "tool" and s.get("name") == "answer"),
                          default=None)
            if ans_idx is None:
                continue
            jobs.append([{"role": "system", "content": sys_new}] +
                        build_prefix(r["trajectory"][:ans_idx + 1], r["question"]))
            meta.append({"arm": tag, "case_id": r["case_id"], "question": r["question"],
                         "gold": r.get("gold") or [], "orig_f1": r.get("f1") or 0,
                         "orig_answer": r.get("answer") or ""})
    from kgqa.llm.offline_vllm import OfflineVLLM
    llm = OfflineVLLM(max_num_seqs=64)
    results = llm.chat_batch(jobs, thinking_budget=1000, temperature=0.3,
                             top_p=0.8, top_k=20, presence_penalty=1.5)
    out = []
    from collections import Counter
    arm_stat = Counter()
    for m, res in zip(meta, results):
        gen = getattr(res, "text", "") or ""
        ents = parse_entities(gen)
        new_f1 = f1(ents, m["gold"]) if ents else 0.0
        delta = new_f1 - m["orig_f1"]
        if m["arm"] == "wrong":
            k = ("corrected→EM" if new_f1 >= 0.999 else
                 "improved" if delta > 0.05 else
                 "unchanged" if abs(delta) <= 0.05 else "worsened")
        else:
            k = ("FALSE-FLIP→broken" if new_f1 < 0.999 else
                 "kept" if abs(delta) <= 0.05 else "changed-but-EM")
        arm_stat[f"{m['arm']}/{k}"] += 1
        out.append({**m, "new_entities": ents[:30], "new_f1": round(new_f1, 4),
                    "verdict": k, "gen_head": gen[:300]})
    (ROOT / "tmp/verify_reanswer.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print("\n".join(f"{k}: {v}" for k, v in sorted(arm_stat.items())))
    print("-> tmp/verify_reanswer.json")


if __name__ == "__main__":
    asyncio.run(main())
