"""Statistics: how many branches are available vs how many the model expands.

For each case:
  - n_avail : # distinct branches in the select_relations evidence-tree overview
  - n_expand: # branch_ids the model passed to expand_branches
  - ratio   : n_expand / n_avail
  - f1, llm_hit, gt_hit, list/single
Aggregate the distribution + correlate with F1 to see if under-expansion is a
systematic leak.
"""
import json, re, sys
from collections import Counter
from difflib import SequenceMatcher

def normalize(t):
    t=str(t).strip().lower(); t=re.sub(r"[^a-z0-9%.' ]+"," ",t); return re.sub(r"\s+"," ",t).strip()
def _m(c,t):
    if not c or not t: return False
    if c==t or t in c or c in t: return True
    if len(c)>=8 and len(t)>=8 and SequenceMatcher(None,c,t).ratio()>=0.95: return True
    return False

def main(path):
    d=json.load(open(path)); recs=d if isinstance(d,list) else d.get("results",d)
    rows=[]
    for r in recs:
        if not isinstance(r,dict): continue
        tj=r.get("agent_trajectory",[])
        n_avail=None; n_expand=None; expand_args=None; called_expand=False
        for i,t in enumerate(tj):
            if not isinstance(t,dict): continue
            c=t.get("content","")
            if t.get("role")=="assistant" and "select_relations" in c:
                res=tj[i+1].get("content","") if i+1<len(tj) else ""
                n_avail=len(set(re.findall(r"branch (\d+):", res)))
            if t.get("role")=="assistant" and "expand_branches" in c:
                called_expand=True
                mj=re.search(r'"branch_ids":\s*\[([^\]]*)\]', c)
                if mj:
                    ids=[x.strip().strip('"').strip("'") for x in mj.group(1).split(",") if x.strip()]
                    n_expand=len(ids); expand_args=ids
        # did the model skip expand and answer directly?
        if n_expand is None:
            n_expand=0
        rows.append(dict(case=r["case_id"], n_avail=n_avail, n_expand=n_expand,
                         ratio=(n_expand/n_avail if n_avail else None),
                         f1=r.get("llm_f1"), hit=r.get("llm_hit"), gt=r.get("gt_hit"),
                         gold=r.get("gt_answers"), pred=r.get("llm_answer"),
                         called=called_expand, q=r.get("question","")))

    n=len(rows)
    print(f"=== Branch usage across {n} cases ===")
    exp=Counter(r["n_expand"] for r in rows)
    print(f"{'n_expand':>9} {'cases':>6} {'%':>6}")
    for k in sorted(exp):
        print(f"{k:>9} {exp[k]:>6} {100*exp[k]/n:>5.1f}%")

    avail=Counter(r["n_avail"] for r in rows)
    print(f"\n{'n_avail':>9} {'cases':>6}")
    for k in sorted(avail, key=lambda x:(x is None,x)):
        print(f"{str(k):>9} {avail[k]:>6}")

    # how often did model expand < available?
    under=[r for r in rows if r["n_avail"] and r["n_expand"]<r["n_avail"]]
    same =[r for r in rows if r["n_avail"] and r["n_expand"]>=r["n_avail"]]
    print(f"\nexpanded ALL available : {len(same):>3} / {n}")
    print(f"expanded FEWER than avail: {len(under):>3} / {n}")

    # F1 of under-expand vs full-expand (among list questions, where it matters)
    def is_list(r):
        g=r["gold"] or []; return len([x for x in g if str(x).strip()])>1
    listrows=[r for r in rows if is_list(r)]
    def avg(rs): return sum(r["f1"] or 0 for r in rs)/len(rs) if rs else 0
    lu=[r for r in listrows if r["n_avail"] and r["n_expand"]<r["n_avail"]]
    lf=[r for r in listrows if r["n_avail"] and r["n_expand"]>=r["n_avail"]]
    print(f"\n--- LIST questions ({len(listrows)}) ---")
    print(f"under-expand ({len(lu)}): mean F1 = {avg(lu):.3f}")
    print(f"full-expand  ({len(lf)}): mean F1 = {avg(lf):.3f}")

    # detail of under-expand list cases
    print(f"\n--- under-expand LIST cases (n_expand < n_avail) ---")
    for r in sorted(lu, key=lambda x:x["f1"] or 0):
        cid=r["case"].split("_")[0]
        ng=len([g for g in (r["gold"] or []) if str(g).strip()])
        print(f"  F1={r['f1']:.2f}  avail={r['n_avail']} exp={r['n_expand']}  |G|={ng}  {cid}  Q={r['q'][:70]}")

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "reports/cwq_hit1_minimal_greedy/results.json")
