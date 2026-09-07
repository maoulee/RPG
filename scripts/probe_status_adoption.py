#!/usr/bin/env python3
"""Adoption prediction for the four-state EVIDENCE_STATUS design (Codex audit,
2026-08-22): BEFORE touching the production prompt, inject a draft §1.5
(mandatory per-retrieval status classification) into the probe system prompt
and re-generate at decision points. Measures:
  1. adoption — does the model emit EVIDENCE_STATUS lines at all?
  2. discrimination — error-arm vs healthy-arm status distribution
     (healthy trajectories should mostly classify SUPPORTED);
  3. action mapping — does the classified status lead to its mandated action
     (RELATION_MISMATCH→relation move, PLAN_MISMATCH→plan, SUPPORTED→ckpt)?

Arms: ERROR = fixstack2 wrong cases cut at first mid-course detection;
      HEALTHY = EM cases cut at their first post-evidence assistant turn.

Usage: python scripts/probe_status_adoption.py [N_ERR] [N_HEALTHY]  (30/30)
Output: tmp/status_adoption.json + stdout summary.
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

DRAFT_15 = """
# 1.5 Evidence Diagnosis — the philosophy of correcting your own exploration

Error PERCEPTION is worthless without error LOCALIZATION: you will often see
that retrieved evidence is not what the fact needed — the whole skill of a
strong agent is naming WHICH layer failed, because the layer determines the
cheapest correct repair. Repair the wrong layer and you either keep a broken
fact (too passive) or throw away good evidence (too aggressive). So after
every retrieve_subgraph, NAME the layer:

EVIDENCE_STATUS: SUPPORTED | PARTIAL | RELATION_MISMATCH | PLAN_MISMATCH
REASON: one line

The status GUIDES the natural repair — it is judgment made explicit, not a
bureaucracy. When genuinely torn between two statuses, prefer the CHEAPER
repair (relation-level before plan-level).

* SUPPORTED — the structure answers the fact. Natural move: checkpoint
  `[fid ✓] ?var = [...]`, next open fact.
* PARTIAL — direction right, some evidence in, a discriminator missing.
  Natural move: keep the bindings; optionally top-up relations for THIS
  fact; else close it — the answer rules handle PARTIAL/UNKNOWN. Never
  restart on PARTIAL.
* RELATION_MISMATCH — the fact is right but the selected relations did not
  instantiate it. Natural move: re-call retrieve_subgraph with OTHER
  candidate relations you were shown; if none fits, reword the
  retrieve_relations question (the SAME wording returns the SAME list).
  Fact, head, and tail unchanged.
* PLAN_MISMATCH — the planned fact itself asks for the wrong evidence
  (wrong target type, wrong direction, a missing entity link, an attribute
  planned as the answer entity, two independent constraints chained into
  one). Natural move: declare it — the system discards this attempt ONCE
  and you re-plan the original question carrying the diagnosis. Do NOT
  declare it for missed relations, weak ranking, missing dates, many
  candidates, non-unique answers, or mere uncertainty.

Two failure scenes, diagnosed:

```text
# scene 1 — the fact asked for the governor, the relations returned offices
EVIDENCE_STATUS: RELATION_MISMATCH
REASON: returned office titles never instantiate the requested governor edge

tool: retrieve_subgraph
center: Arizona
relations: government.governmental_jurisdiction.governing_officials
sg: sg1
```

```text
# scene 2 — the fact itself retrieves a date, but the question needs the
# position entity constrained by that date; no relation choice can fix this
EVIDENCE_STATUS: PLAN_MISMATCH
REASON: f2's target ?date is an attribute; the question requires the
position entity selected by that date

(declare it and re-plan the original question once)
```

Retries consume the per-fact budget. A large candidate set, multiple
candidates, or an uncertain final answer are NOT mismatches.
"""


def build_prefix(traj, cut, question):
    msgs = []
    for s in traj[:cut]:
        role, c = s.get("role"), s.get("content") or ""
        if role == "assistant":
            r = (s.get("reasoning") or "").strip()
            msgs.append({"role": "assistant",
                         "content": (f"<think>\n{r}\n</think>\n{c}" if r else c)})
        elif role == "tool":
            n = s.get("name")
            msgs.append({"role": "user",
                         "content": (f"Tool result ({n}): {c}" if n else c)})
        else:
            msgs.append({"role": role, "content": c})
    if not msgs or msgs[0].get("role") != "user":
        msgs.insert(0, {"role": "user",
                        "content": f"Answer the knowledge-graph question: {question}"})
    return msgs


def first_action(text):
    for ln in (text or "").splitlines():
        ls = ln.strip()
        if ls.startswith("tool:") or ls.startswith("["):
            return ls
    return ""


def parse_status(text):
    m = re.search(r"EVIDENCE_STATUS:\s*(SUPPORTED|PARTIAL|RELATION_MISMATCH|PLAN_MISMATCH)",
                  text or "", re.I)
    return m.group(1).upper() if m else None


async def main():
    n_e = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    n_h = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    base = json.loads((ROOT / "reports/regress267_fixstack2.json").read_text())
    sys_txt = (ROOT / "kgqa/agent/SEQ_AGENTS.md").read_text()
    # swap §1.5 with the draft (keep everything else identical)
    sys_new = re.sub(r"# 1\.5 .*?\n---\n", DRAFT_15 + "\n---\n", sys_txt, count=1, flags=re.S)
    assert "EVIDENCE_STATUS: SUPPORTED" in sys_new, "draft swap failed"
    # EXAMPLE INTEGRATION (answer_type lesson: the model copies EXAMPLES over
    # prose — a format absent from examples adopts at ~20%). Two injections:
    # (a) a mismatch demonstration inside §1.5
    sys_new = sys_new.replace(
        "Retries consume the per-fact budget. A large candidate set, multiple\ncandidates, or an uncertain final answer are NOT mismatches.",
        "Retries consume the per-fact budget. A large candidate set, multiple\n"
        "candidates, or an uncertain final answer are NOT mismatches.\n\n"
        "Example of the diagnosis line in use:\n\n"
        "```text\nEVIDENCE_STATUS: RELATION_MISMATCH\n"
        "REASON: the selected relations returned offices, not the requested\n"
        "governor instantiation\n\n"
        "tool: retrieve_subgraph\ncenter: Arizona\n"
        "relations: government.governmental_jurisdiction.governing_officials\n"
        "sg: sg1\n```")
    # (b) Example 1's checkpoint block starts with the status line
    sys_new = sys_new.replace(
        "### Checkpoint\n\n```text\n[sg1.f1 ✓]",
        "### Checkpoint\n\n```text\nEVIDENCE_STATUS: SUPPORTED\n"
        "REASON: the founder relations instantiated the fact\n\n[sg1.f1 ✓]", 1)

    err, healthy = [], []
    for r in base:
        first_sg = next((i for i, s in enumerate(r["trajectory"])
                         if s.get("role") == "tool" and s.get("name") == "retrieve_subgraph"), None)
        if first_sg is None:
            continue
        if (r.get("f1") or 0) < 0.999:
            cut = next((i for i, s in enumerate(r["trajectory"])
                        if i > first_sg and s.get("role") == "assistant"
                        and DETECT.search(s.get("reasoning") or "")), None)
            if cut is not None:
                err.append((r, cut))
        else:
            cut = next((i for i, s in enumerate(r["trajectory"])
                        if i > first_sg and s.get("role") == "assistant"), None)
            if cut is not None:
                healthy.append((r, cut))
    err, healthy = err[:n_e], healthy[:n_h]
    print(f"probes: error={len(err)} healthy={len(healthy)}", flush=True)

    jobs, meta = [], []
    for tag, cohort in (("error", err), ("healthy", healthy)):
        for r, cut in cohort:
            msgs = build_prefix(r["trajectory"], cut, r["question"])
            # (b) objective-emptiness hint on the last sg result before cut —
            # simulating what the production harness would attach
            last_sg = max((i for i, s in enumerate(r["trajectory"][:cut])
                           if s.get("role") == "tool"
                           and s.get("name") == "retrieve_subgraph"), default=None)
            hinted = False
            if last_sg is not None:
                res = r["trajectory"][last_sg].get("content") or ""
                if ("(empty)" in res or "reached nothing" in res
                        or res.lstrip().startswith("error:") or '"error"' in res[:60]):
                    key = res[:80]
                    k = next((j for j, m in enumerate(msgs)
                              if m["role"] == "user"
                              and m["content"].startswith(
                                  "Tool result (retrieve_subgraph):")
                              and key in m["content"]), None)
                    if k is not None:
                        msgs[k]["content"] += (
                            "\n[diagnosis hint] none of the selected relations "
                            "instantiated this fact — this is RELATION_MISMATCH "
                            "unless the fact itself asks for the wrong thing.")
                        hinted = True
            jobs.append([{"role": "system", "content": sys_new}] + msgs)
            meta.append({"arm": tag, "case_id": r["case_id"],
                         "question": r["question"], "cut": cut, "hinted": hinted,
                         "orig_action": first_action(r["trajectory"][cut].get("content"))})
    from kgqa.llm.offline_vllm import OfflineVLLM
    llm = OfflineVLLM(max_num_seqs=64)
    results = llm.chat_batch(jobs, thinking_budget=1000, temperature=0.3,
                             top_p=0.8, top_k=20, presence_penalty=1.5)
    from collections import Counter
    stat = Counter(); mapping = Counter(); out = []
    for m, res in zip(meta, results):
        gen = getattr(res, "text", "") or ""
        st = parse_status(gen)
        act = first_action(gen)
        stat[f"{m['arm']}/{'adopted:' + st if st else 'NO-STATUS'}"] += 1
        if st:
            a0 = act.split(":")[0]
            if st == "SUPPORTED": want = "checkpoint"
            elif st == "RELATION_MISMATCH": want = "relation-move"
            elif st == "PLAN_MISMATCH": want = "plan"
            else: want = "any"
            got = ("checkpoint" if act.startswith("[") and "✓" in act else
                   "plan" if act.startswith("tool: plan") else
                   "relation-move" if act.startswith(("tool: retrieve_subgraph",
                                                      "tool: retrieve_relations")) else
                   "other")
            mapping[f"{st}→{got}{'✓' if (want in ('any', got)) else '✗'}"] += 1
        out.append({**m, "status": st, "action": act, "gen_head": gen[:400]})
    (ROOT / "tmp/status_adoption.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print("\n== 采用与分类分布:")
    for k, v in sorted(stat.items()):
        print(f"  {k}: {v}")
    print("\n== 状态→动作映射:")
    for k, v in sorted(mapping.items()):
        print(f"  {k}: {v}")
    print("-> tmp/status_adoption.json")


if __name__ == "__main__":
    asyncio.run(main())
