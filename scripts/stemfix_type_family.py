#!/usr/bin/env python3
"""Stem-only repair of the TYPE mismatch family (user ruling 2026-08-19).

For each two-pass-confirmed TYPE case: minimally reword the interrogative so
the question asks for exactly what the FIXED gold provides. Gold is never
touched. Two QC gates:
  1. programmatic: every numeric token of the original question must survive
     the rewrite (dates/counts are constraints, not type words);
  2. LLM verify (fresh context): reworded question + gold must judge MATCH.

Outputs:
  tmp/qa_stemfix_type.json   (per-case: id, old, new, qc flags)
  tmp/qa_stemfix_type.md     (review file)
  data/cwq_processed/test_v5_stemfix.pkl  (v4 copy with verified rewords)
Usage: /root/miniconda3/envs/qwen35/bin/python scripts/stemfix_type_family.py
"""
import json
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/zhaoshu/subgraph")

ROOT = Path("/zhaoshu/subgraph")
TEST_PKL = ROOT / "data/cwq_processed/test_v4_repaired.pkl"
OUT_PKL = ROOT / "data/cwq_processed/test_v5_stemfix.pkl"
OUT_JSON = ROOT / "tmp/qa_stemfix_type.json"
OUT_MD = ROOT / "tmp/qa_stemfix_type.md"

REWORD_PROMPT = """You are repairing the interrogative wording of a KGQA benchmark question. The GOLD ANSWERS below are FIXED and cannot change. An auditor judged that the question asks for the wrong answer TYPE (the gold entities are of a different kind than the question requests). Rewrite ONLY the type-demanding words so the question asks exactly for what the gold provides.

STRICT RULES:
- Keep every constraint entity, name, date, number, and the topic EXACTLY unchanged.
- Change as few words as possible — ideally only the interrogative phrase or the type noun (e.g. "what year ... win" -> "which championship ... win"; "what countries" -> "what countries or territories"; "who plays" -> "which actor plays" — whatever the gold's actual type demands).
- Do NOT add new constraints; do NOT remove constraints; do NOT answer the question inside the stem.
- The rewritten question must be answerable EXACTLY by the gold set (no more, no fewer).
- Keep the scaffolded tone; fix ONLY the type mismatch, not general grammar.
- If no faithful type-only rewording exists, output null.

Output STRICT JSON one line: {"new": "..."} or {"new": null}

Original question: {q}
Fixed gold answers: {gold}"""

VERIFY_PROMPT = """Judge whether the GOLD answer list below correctly and exactly answers the question (a KGQA benchmark case; the benchmark's world is the knowledge graph). Minor scaffold grammar is fine. Multiple golds for a plural question are fine; aliases of one entity are fine.

Output STRICT JSON one line: {"verdict": "MATCH"} or {"verdict": "NOMATCH"} or {"verdict": "UNSURE"}

Question: {q}
Gold answers: {gold}"""


def parse_json(text, key):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0)).get(key)
    except Exception:
        return None


def num_tokens(q):
    return set(re.findall(r"\d[\d,.:-]*", q))


def cap_tokens(q):
    words = re.findall(r"\b[A-Z][a-zA-Z']+\b", q)
    return [w for w in words[1:]] if len(words) > 1 else words  # skip sentence start


def main():
    p1 = {x["id"]: x for x in json.loads((ROOT / "tmp/qa_mismatch_llm.json").read_text())}
    p2 = {x["id"]: x for x in json.loads((ROOT / "tmp/qa_mismatch_llm_pass2.json").read_text())}
    samples = pickle.loads(TEST_PKL.read_bytes())
    by_id = {s["id"]: s for s in samples}
    ids = [i for i, x in p2.items()
           if x["verdict"] == "CONFIRMED" and p1[i]["type"] == "TYPE"]
    print(f"TYPE confirmed: {len(ids)}", flush=True)

    from kgqa.llm.offline_vllm import OfflineVLLM
    llm = OfflineVLLM(tp_size=2, max_num_seqs=128)

    # -- pass A: reword -----------------------------------------------------
    msgs = []
    for i in ids:
        s = by_id[i]
        msgs.append([{"role": "user", "content": REWORD_PROMPT
                      .replace("{q}", s["question"])
                      .replace("{gold}", " | ".join(s["a_entity"][:12]))}])
    rewords = llm.chat_batch(msgs, thinking_budget=700, temperature=0.0, max_tokens=1100)
    rows = []
    for i, r in zip(ids, rewords):
        s = by_id[i]
        new = parse_json(r.text, "new")
        if isinstance(new, str):
            new = new.strip()
        qc_num = None
        qc_num_ok = False
        if new:
            qc_num_ok = num_tokens(s["question"]) <= num_tokens(new)
        rows.append({"id": i, "old": s["question"], "gold": s["a_entity"],
                     "new": new, "num_kept": qc_num_ok})
    n_new = sum(1 for r in rows if r["new"])
    print(f"reworded: {n_new}/{len(rows)}  num-qc-pass: "
          f"{sum(1 for r in rows if r['new'] and r['num_kept'])}", flush=True)

    # -- pass B: verify (fresh context, only rewrites that passed gate 1) ---
    cand = [r for r in rows if r["new"] and r["num_kept"]]
    vmsgs = [[{"role": "user", "content": VERIFY_PROMPT
               .replace("{q}", r["new"]).replace("{gold}", " | ".join(r["gold"][:12]))}]
             for r in cand]
    verif = llm.chat_batch(vmsgs, thinking_budget=500, temperature=0.0, max_tokens=900)
    for r, v in zip(cand, verif):
        r["verify"] = (parse_json(v.text, "verdict") or "PARSE_FAIL")
    for r in rows:
        r.setdefault("verify", None)

    final = [r for r in rows if r.get("verify") == "MATCH"]
    print(f"verified MATCH: {len(final)}/{len(rows)}", flush=True)
    print("verify outcomes:", dict(Counter(r.get("verify") for r in cand)), flush=True)

    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=1))

    # -- build v5 pkl --------------------------------------------------------
    fixmap = {r["id"]: r["new"] for r in final}
    v5 = []
    for s in samples:
        t = dict(s)
        if s["id"] in fixmap:
            t["question"] = fixmap[s["id"]]
        v5.append(t)
    OUT_PKL.write_bytes(pickle.dumps(v5))
    print(f"wrote {OUT_PKL} ({len(fixmap)} questions reworded of {len(samples)})", flush=True)

    # -- review dump ---------------------------------------------------------
    wrong = {l.strip() for l in (ROOT / "tmp/test_wrong_set.txt").read_text().split() if l.strip()}
    d16 = json.loads((ROOT / "reports/v16_testwrong.json").read_text())
    recs16 = d16 if isinstance(d16, list) else d16["records"]
    f16 = {x.get("case_id", x.get("id")): x.get("f1", 0.0) for x in recs16}
    lines = ["# TYPE 家族题干修复（gold 未动）— 审阅清单",
             f"\n283 例确认 TYPE 错配 → 改写 {n_new} → 数字约束保真 "
             f"{len(cand)} → 验证 MATCH **{len(final)}**（已写入 test_v5_stemfix.pkl）",
             f"错误集内 {sum(1 for r in final if r['id'] in wrong)} 例。\n"]
    for n, r in enumerate(sorted(final, key=lambda r: r["id"] not in wrong), 1):
        err = " [E]" if r["id"] in wrong else ""
        f1v = f16.get(r["id"])
        f1s = f" | F1={f1v:.2f}" if f1v is not None else ""
        lines += [f"**{n}.{r['id']}{err}{f1s}**",
                  f"- 旧: {r['old']}",
                  f"- 新: {r['new']}",
                  f"- gold: {' | '.join(r['gold'][:10])}", ""]
    rejected = [r for r in rows if r not in final]
    lines += ["## 未通过 QC（保持原题）", ""]
    for r in rejected:
        why = ("改写为空" if not r["new"]
               else "数字约束丢失" if not r["num_kept"]
               else f"验证 {r.get('verify')}")
        lines += [f"- {r['id']}: {why} | 新题: {r.get('new')}", ""]
    OUT_MD.write_text("\n".join(lines))
    print(f"review dump: {OUT_MD}", flush=True)


if __name__ == "__main__":
    main()
