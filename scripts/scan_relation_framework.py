"""Validate the exclusive-vs-accumulative framework on the pilot.

Cross-tab: gold cardinality (single=1 / list>1) × SPARQL filter behavior
  (filter = date-FILTER or title-FILTER or LIMIT on the answer CVT).
Framework predicts:
  - accumulative relation, no filter  -> list, gold = full set
  - exclusive relation, has filter    -> single (or list-via-time-window)
Anomalies (framework doesn't cleanly cover):
  - list gold (>1) WITH a filter      -> exclusive relation but multiple (time-window?) OR noise
  - single gold (1) with NO filter    -> accumulative relation, cardinality happens to be 1 (data-driven)
  - single gold with COUNT            -> "how many" (number answer, separate type)
"""
import json, re
from collections import Counter, defaultdict

def analyze_sparql(s):
    s = s or ""
    U = s.upper()
    has_date = bool(re.search(r'government_position_held\.(from|to)|\.date|start_date|end_date|xsd:datetime', s, re.I))
    has_datefilter = bool(re.search(r'FILTER\s*\([^)]*(datetime|from|to|date)', s, re.I))
    has_titlefilter = bool(re.search(r'(basic_title|office_position_or_title|position_held\.(title|basic_title))', s, re.I))
    has_limit = 'LIMIT' in U
    has_count = bool(re.search(r'\bCOUNT\b', U))
    # extract the final answer relation(s): the triple with ?x as object
    ans_rels = re.findall(r'(\?[\w]+\s+ns:[\w.]+)\s+\?x\s*[\.\}]', s)
    return dict(date=has_datefilter, title=has_titlefilter, limit=has_limit,
                count=has_count, ans_rels=ans_rels, raw_date=has_date)

def main():
    sp = {x['ID']: x for x in json.load(open('data/cwq_sparql/test.json'))}
    d = json.load(open('reports/cwq_hit1_minimal_greedy/results.json'))
    recs = d if isinstance(d, list) else d.get('results', d)

    rows = []
    for r in recs:
        cid = r['case_id']
        gold = r.get('gt_answers') or []
        ng = len([g for g in gold if str(g).strip()])
        s = sp.get(cid, {})
        a = analyze_sparql(s.get('sparql', ''))
        filtered = a['date'] or a['title'] or a['limit']
        cat = 'single' if ng == 1 else ('list' if ng > 1 else 'none')
        rows.append(dict(cid=cid.split('_')[0], ng=ng, cat=cat, **a,
                         filtered=filtered, q=r.get('question', ''), gold=gold))

    n = len(rows)
    print(f"=== {n} pilot cases: gold-cardinality × SPARQL-filter ===\n")
    ct = Counter()
    for r in rows:
        f = 'FILTERED' if r['filtered'] else 'no-filter'
        ct[(r['cat'], f)] += 1
    print(f"{'':18} {'no-filter':>10} {'FILTERED':>10}")
    for cat in ('single', 'list'):
        nf = ct.get((cat, 'no-filter'), 0); ff = ct.get((cat, 'FILTERED'), 0)
        print(f"{cat+' gold':18} {nf:>10} {ff:>10}")

    # Framework-predicted vs anomalous
    print("\n=== framework fit ===")
    fit = [r for r in rows if (r['cat']=='list' and not r['filtered']) or (r['cat']=='single' and (r['filtered'] or r['ng']==1))]
    anom_list_filtered = [r for r in rows if r['cat']=='list' and r['filtered']]   # exclusive but multiple
    anom_single_nofilter = [r for r in rows if r['cat']=='single' and not r['filtered'] and not r['count']]
    print(f"list + no-filter (accumulative, clean): {sum(1 for r in rows if r['cat']=='list' and not r['filtered'])}")
    print(f"single + FILTERED    (exclusive, clean): {sum(1 for r in rows if r['cat']=='single' and r['filtered'])}")
    print(f"ANOMALY list+FILTER (exclusive-relation but gold>1 = time-window?): {len(anom_list_filtered)}")
    print(f"ANOMALY single+no-filter (accumulative but cardinality=1): {len(anom_single_nofilter)}")

    print("\n--- ANOMALY: list gold WITH filter (exclusive relation, multiple answers) ---")
    for r in anom_list_filtered:
        flags = [k for k in ('date','title','limit') if r[k]]
        print(f"  |G|={r['ng']:>2} [{','.join(flags):>10}] {r['cid']}  Q={r['q'][:75]}")
        print(f"        GOLD={r['gold']}")

    print("\n--- ANOMALY: single gold, NO filter, NOT count (accumulative, |G|=1) ---")
    for r in anom_single_nofilter[:15]:
        print(f"  |G|={r['ng']} {r['cid']}  Q={r['q'][:70]}  GOLD={r['gold']}")

if __name__ == '__main__':
    main()
