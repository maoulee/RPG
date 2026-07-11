"""Analyze answer-cardinality outcomes on a results.json.

Classify each case by how the model's answer-set cardinality aligns with gold:
  SINGLE*   : n_gold == 1
  LIST_*    : n_gold  > 1
    FULL      : recall=1 & precision=1  (F1=1, perfectly split)
    OVER      : recall=1 & precision<1  (over-emit junk — WHERE failed to filter)
    UNDER     : precision=1 & recall<1  (dropped valid answers)
    MIXED     : both miss gold AND include junk
    MISS      : no overlap

The user's focus: PARTIAL (OVER / UNDER / MIXED) — where the reasoning fails
to split the answer set exactly. Cross-tabs against GT-hit to separate
retrieval failure (gold not in pool) from reasoning failure (gold in pool
but model emitted wrong cardinality).
"""
from __future__ import annotations
import json, sys, re
from difflib import SequenceMatcher

def normalize(t):
    t = str(t).strip().lower()
    t = re.sub(r"[^a-z0-9%.' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _matches(c, t):
    if not c or not t:
        return False
    if c == t or t in c or c in t:
        return True
    if len(c) >= 8 and len(t) >= 8 and SequenceMatcher(None, c, t).ratio() >= 0.95:
        return True
    return False

def split_preds(ans):
    if not ans:
        return []
    parts = [p.strip() for p in ans.split(" | ") if p.strip()]
    return parts

def classify(rec):
    gold = rec.get("gt_answers") or []
    preds = split_preds(rec.get("llm_answer", ""))
    ng = [normalize(g) for g in gold if str(g).strip()]
    np_ = [normalize(p) for p in preds if p.strip()]
    n_gold = len(ng); n_pred = len(np_)
    matched_gold = sum(1 for t in ng if any(_matches(c, t) for c in np_))
    matched_pred = sum(1 for c in np_ if any(_matches(c, t) for t in ng))
    gt_hit = bool(rec.get("gt_hit"))

    if n_gold == 0:
        cat = "NO_GOLD"
    elif n_gold == 1:
        cat = "SINGLE_HIT" if matched_gold == 1 else "SINGLE_MISS"
    else:  # list question
        if matched_gold == 0:
            cat = "LIST_MISS"
        elif matched_gold == n_gold and matched_pred == n_pred:
            cat = "LIST_FULL"
        elif matched_gold == n_gold and matched_pred > n_pred:
            cat = "LIST_FULL"  # impossible branch, guard
        elif matched_gold == n_gold:
            cat = "LIST_OVER"   # recall=1, precision<1 (junk)
        elif matched_pred == n_pred:
            cat = "LIST_UNDER"  # precision=1, recall<1 (dropped)
        else:
            cat = "LIST_MIXED"  # both junk + dropped
    return dict(cat=cat, n_gold=n_gold, n_pred=n_pred,
                matched_gold=matched_gold, matched_pred=matched_pred,
                gt_hit=gt_hit, gold=gold, preds=preds,
                q=rec.get("question",""), case=rec.get("case_id",""),
                llm_f1=rec.get("llm_f1"))

def main(path):
    d = json.load(open(path))
    recs = d if isinstance(d, list) else d.get("results", d)
    rows = [classify(r) for r in recs if isinstance(r, dict)]

    from collections import Counter, defaultdict
    cnt = Counter(r["cat"] for r in rows)
    n = len(rows)

    order = ["SINGLE_HIT","SINGLE_MISS","LIST_FULL","LIST_OVER",
             "LIST_UNDER","LIST_MIXED","LIST_MISS","NO_GOLD"]
    print(f"=== Cardinality distribution ({n} cases) ===")
    print(f"{'category':14} {'count':>5} {'%':>6}  meaning")
    meanings = {
        "SINGLE_HIT":"single-answer correct",
        "SINGLE_MISS":"single-answer wrong",
        "LIST_FULL":"list, perfectly split (F1=1)",
        "LIST_OVER":"list, over-emit JUNK (recall=1, prec<1)",
        "LIST_UNDER":"list, DROPPED valid (prec=1, recall<1)",
        "LIST_MIXED":"list, BOTH junk + dropped",
        "LIST_MISS":"list, zero overlap",
        "NO_GOLD":"no gold answer",
    }
    for c in order:
        if cnt[c]:
            print(f"{c:14} {cnt[c]:>5} {100*cnt[c]/n:>5.1f}%  {meanings[c]}")

    partial = [r for r in rows if r["cat"] in ("LIST_OVER","LIST_UNDER","LIST_MIXED")]
    print(f"\n=== PARTIAL (the user's focus): {len(partial)} cases ===")
    # cross-tab with gt_hit
    gt = Counter(("gt_hit" if r["gt_hit"] else "gt_MISS") for r in partial)
    print(f"  of which gold-in-pool(gt_hit): {gt.get('gt_hit',0)}  | gold NOT in pool(gt_MISS): {gt.get('gt_MISS',0)}")
    print(f"  -> gt_MISS partial = retrieval problem (can't split what isn't there)")
    print(f"  -> gt_hit  partial = pure REASONING/cardinality problem (split failure)")

    for cat in ("LIST_OVER","LIST_UNDER","LIST_MIXED"):
        sub = [r for r in partial if r["cat"]==cat]
        if not sub: continue
        print(f"\n--- {cat} ({len(sub)} cases) ---")
        sub_sorted = sorted(sub, key=lambda r:(not r["gt_hit"], r["case"]))
        for r in sub_sorted:
            flag = "RETRIEVAL" if not r["gt_hit"] else "REASONING"
            print(f"\n  [{flag}] {r['case']}  |G|={r['n_gold']} |P|={r['n_pred']} "
                  f"mg={r['matched_gold']} mp={r['matched_pred']} f1={r['llm_f1']:.3f}")
            print(f"    Q: {r['q'][:110]}")
            print(f"    GOLD : {r['gold']}")
            print(f"    PRED : {r['preds']}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "reports/cwq_hit1_minimal_greedy/results.json")
