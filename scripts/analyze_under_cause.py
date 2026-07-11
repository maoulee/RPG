"""For each list-partial (UNDER/OVER/MIXED) case, decide WHY cardinality split failed:
  - REASONING    : expand_branches showed ALL gold, but model emitted fewer/different
  - EXPAND-TRUNC : gold is in full pool but expand_branches did NOT surface it
  - SUBGRAPH-MISS: gold not even in the candidate pool (retrieval)
"""
import json, re, sys
from difflib import SequenceMatcher

def normalize(t):
    t=str(t).strip().lower(); t=re.sub(r"[^a-z0-9%.' ]+"," ",t); return re.sub(r"\s+"," ",t).strip()
def _m(c,t):
    if not c or not t: return False
    if c==t or t in c or c in t: return True
    if len(c)>=8 and len(t)>=8 and SequenceMatcher(None,c,t).ratio()>=0.95: return True
    return False

def is_list_partial(r):
    gold=r.get("gt_answers") or []
    preds=[p.strip() for p in (r.get("llm_answer") or "").split(" | ") if p.strip()]
    ng=[normalize(g) for g in gold if str(g).strip()]
    np_=[normalize(p) for p in preds if p.strip()]
    if len(ng)<2: return False
    mg=sum(1 for t in ng if any(_m(c,t) for c in np_))
    mp=sum(1 for c in np_ if any(_m(c,t) for t in ng))
    if mg==0: return False
    return not (mg==len(ng) and mp==len(np_))

def main(path):
    d=json.load(open(path)); recs=d if isinstance(d,list) else d.get("results",d)
    print(f"{'case':16} {'|G|':>4} {'pool':>5} {'exp':>4} {'g_in_exp':>8} {'|P|':>4}  verdict")
    print("-"*95)
    for r in recs:
        if not is_list_partial(r): continue
        tj=r.get("agent_trajectory",[]); exp_cands=[]
        for i,turn in enumerate(tj):
            if isinstance(turn,dict) and turn.get("role")=="assistant" and "expand_branches" in turn.get("content",""):
                res=tj[i+1].get("content","") if i+1<len(tj) else ""
                try:
                    j=json.loads(res); exp_cands=j.get("candidates",[])
                except Exception: exp_cands=[]
                break
        pool=r.get("answer_candidates") or []
        gold=r.get("gt_answers") or []
        ng=[normalize(g) for g in gold]
        gip=sum(1 for t in ng if any(_m(normalize(c),t) for c in pool))
        gie=sum(1 for t in ng if any(_m(normalize(c),t) for c in exp_cands))
        if gie==len(ng):
            v="REASONING (gold all shown, model narrowed)"
        elif gip==len(ng):
            v=f"EXPAND-TRUNC (pool {gip}/{len(ng)}, expand showed {gie}/{len(ng)})"
        else:
            v=f"SUBGRAPH-MISS (pool {gip}/{len(ng)})"
        cid=r["case_id"].split("_")[0]
        nP=len([p for p in (r.get("llm_answer") or "").split(" | ") if p.strip()])
        print(f"{cid:16} {len(ng):>4} {gip:>5} {len(exp_cands):>4} {gie:>8} {nP:>4}  {v}")

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "reports/cwq_hit1_minimal_greedy/results.json")
