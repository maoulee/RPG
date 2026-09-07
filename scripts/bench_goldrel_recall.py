#!/usr/bin/env python3
"""Gold-relation recall benchmark (user-directed validation, 2026-08-21).

For N train cases: take the case's GOLD answer entity, find the gold edge
(the edge touching it — the relation the final hop needs), and check whether
retrieve_relations-style GTE ranking surfaces that relation in top-15 —
across MANY cases (single-case tuning overfits; the Iraq specimen taught
that). Variants (all embedding-native, no class filters):
  A current pipeline format: candidates "head | <last2 ns labeling> | ?" + V0 instruct
  B proposed:               candidates "head | <last1 labeling> | ?"     + V2 instruct

Output: tmp/goldrel_recall.json + stdout summary.
Usage: python scripts/bench_goldrel_recall.py [N_CASES]
"""
import asyncio
import json
import pickle
import random
import sys
from pathlib import Path

sys.path.insert(0, "/zhaoshu/subgraph")
import aiohttp
from kgqa.agent.seq_tools import _seq_pool_relids
from kgqa.agent.tools import _rel_last2

ROOT = Path("/zhaoshu/subgraph")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
random.seed(7)

V0 = ("Retrieve the triple-format question (head, relation, tail) that is "
      "semantically consistent with the natural-language query question — "
      "both ask about the same thing")
V2 = ("Given a natural-language question about the head entity, retrieve "
      "the specific knowledge-graph relation that carries the answer as its "
      "tail. The relation must be informative about the question's topic.")
# V3 (2026-08-22, user ruling: 本质是关系语义是否与问题相符合 — no case words, no
# "topic" coupling): semantic-match essence, keeps V2's answer-bearing core.
V3 = ("Given a natural-language question about the head entity, retrieve "
      "the knowledge-graph relation whose semantics match what the question "
      "asks — the relation must connect the head entity to the answer.")

TOPK = 15


def last1(r):
    return str(r).rsplit(".", 1)[-1].replace("_", " ")


def load_cases():
    samples = pickle.loads((ROOT / "data/cwq_processed/train_v4_repaired.pkl").read_bytes())
    pool = [s for s in samples if s.get("a_entity") and s.get("text_entity_list")]
    random.shuffle(pool)
    return pool[:N]


def gold_edge(s):
    """(center_idx, gold_rel_id) — an edge touching a gold answer entity;
    center = the OTHER endpoint. Prefer centers that are q_entity."""
    ents, gold = s["text_entity_list"], set(s["a_entity"])
    qe = set(s.get("q_entity") or [])
    best = None
    for k in range(len(s["r_id_list"])):
        h, r, t = s["h_id_list"][k], s["r_id_list"][k], s["t_id_list"][k]
        if not (0 <= r < len(s["relation_list"])):
            continue
        h_in = 0 <= h < len(ents) and ents[h] in gold
        t_in = 0 <= t < len(ents) and ents[t] in gold
        if h_in == t_in:
            continue
        center, gold_ent = (t, ents[h]) if h_in else (h, ents[t])
        if not (0 <= center < len(ents)) or not ents[center]:
            continue
        is_qe = ents[center] in qe
        cand = (1 if is_qe else 0, k, center, s["relation_list"][r])
        if best is None or cand[0] > best[0]:
            best = cand
    return best  # (is_qe, edge_k, center_idx, gold_rel)


async def main():
    cases = load_cases()
    print(f"benchmark cases: {len(cases)}", flush=True)
    results = []
    sem = asyncio.Semaphore(8)

    async with aiohttp.ClientSession() as session:
        async def one(s, ci):
            g = gold_edge(s)
            if g is None:
                return None
            _, _, center_idx, gold_rel = g
            class Ctx:
                pass
            ctx = Ctx()
            ctx.ents = s["text_entity_list"]; ctx.rels = s["relation_list"]
            ctx.h_ids, ctx.r_ids, ctx.t_ids = s["h_id_list"], s["r_id_list"], s["t_id_list"]
            try:
                pool = sorted(_seq_pool_relids(ctx, {center_idx}))
            except Exception:
                return None
            head = ctx.ents[center_idx]
            rec = {"id": s["id"], "head": head, "gold_rel": gold_rel,
                   "pool_n": len(pool), "in_pool": gold_rel in {ctx.rels[i] for i in pool}}
            q = s["question"]
            for tag, cands, ins in (
                ("A_current", [f"{head} | {_rel_last2(ctx.rels[i])} | ?" for i in pool], V0),
                ("B_last1v2", [f"{head} | {last1(ctx.rels[i])} | ?" for i in pool], V2),
                # instruct-only cells on the PRODUCTION format (last2+head):
                ("C_l2_v2", [f"{head} | {_rel_last2(ctx.rels[i])} | ?" for i in pool], V2),
                ("D_l2_v3", [f"{head} | {_rel_last2(ctx.rels[i])} | ?" for i in pool], V3),
            ):
                try:
                    async with sem:
                        async with session.post(
                            "http://127.0.0.1:8003/retrieve",
                            json={"query": q, "candidates": cands,
                                  "candidate_texts": cands,
                                  "top_k": min(TOPK, len(cands)), "instruct": ins},
                            timeout=aiohttp.ClientTimeout(total=120),
                        ) as resp:
                            rows = (await resp.json())["results"]
                    # match by the gold relation's labeled text
                    if tag.startswith("A") or tag.startswith("C") or tag.startswith("D"):
                        labeled_gold = f"{head} | {_rel_last2(gold_rel)} | ?"
                    else:
                        labeled_gold = f"{head} | {last1(gold_rel)} | ?"
                    pos = next((n for n, r in enumerate(rows, 1)
                                if r["candidate"] == labeled_gold), 99)
                    rec[tag] = pos
                except Exception as e:
                    rec[tag] = f"ERR:{type(e).__name__}"
            return rec

        recs = await asyncio.gather(*[one(s, i) for i, s in enumerate(cases)])
    results = [r for r in recs if r]
    out = ROOT / "tmp/goldrel_recall.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))

    valid = [r for r in results if isinstance(r.get("A_current"), int) and isinstance(r.get("B_last1v2"), int)]
    in_pool = [r for r in valid if r["in_pool"]]
    def recall(key, sub):
        return sum(1 for r in sub if r[key] <= TOPK) / len(sub) * 100 if sub else 0
    print(f"usable: {len(valid)} | gold-in-pool: {len(in_pool)} ({len(in_pool)/len(valid)*100:.0f}%)")
    print(f"recall@15 (gold-in-pool subset, n={len(in_pool)}):")
    print(f"  A current (last2+V0): {recall('A_current', in_pool):.1f}%")
    print(f"  B last1+V2:           {recall('B_last1v2', in_pool):.1f}%")
    both = [r for r in in_pool]
    a_win = sum(1 for r in both if r["A_current"] < r["B_last1v2"])
    b_win = sum(1 for r in both if r["B_last1v2"] < r["A_current"])
    print(f"  pair: A better {a_win} | B better {b_win} | tie {len(both)-a_win-b_win}")
    # A fails but B saves — the cases that matter
    saved = [r for r in in_pool if r["A_current"] > TOPK and r["B_last1v2"] <= TOPK]
    lost = [r for r in in_pool if r["B_last1v2"] > TOPK and r["A_current"] <= TOPK]
    print(f"  B rescues (A>15, B<=15): {len(saved)} | B loses (B>15, A<=15): {len(lost)}")
    for r in saved[:5]:
        print(f"    rescued: [{r['head'][:20]}] gold={r['gold_rel'].rsplit('.',1)[-1]} q含gold词")
    for r in lost[:5]:
        print(f"    lost:    [{r['head'][:20]}] gold={r['gold_rel'].rsplit('.',1)[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
