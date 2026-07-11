"""Profile GT (gold) vs SPARQL structure across the FULL WebQSP test set (1639).

Mirrors scripts/profile_gold_sparql_structure.py (CWQ) for cross-dataset
comparison. Adaptations for WebQSP dialect:
  - SPARQL read from WebQSP.test.json['Questions'][i]['Parses'][0]['Sparql']
    (one question may have multiple Parses; we take P0 = the primary parse).
  - question text = ProcessedQuestion (fallback RawQuestion).
  - answer-relation regex reused unchanged (?x subject/object triples); verified
    to also catch ?x inside nested sub-SELECTs (WebQSP has MANUAL SPARQL with
    sub-queries). Per-case relation list deduped.
  - filter/date/COUNT/title regexes verified: COUNT=0 (no false positives),
    same FILTER patterns as CWQ.

ASSUMPTIONS (flagged):
  - 'answer relation' = triple where ?x is subject or object; deduped per case.
  - filter = date-FILTER OR title-FILTER OR LIMIT (same defn as CWQ).
  - GT 'literal' heuristic identical to CWQ (pure number/year/date string).
  - exclusive/accumulative keyword sets reused from CWQ (Freebase-wide).
"""
import json, re, os, pickle
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WQ = json.load(open(os.path.join(ROOT, 'data/webqsp/WebQSP.test.json')))
QS = WQ['Questions']
PKL = pickle.load(open(os.path.join(ROOT,
    'data/webqsp/test_fixed_path_completed.pkl'), 'rb'))
GOLD = {x['id']: x for x in PKL}
N = len(QS)

def get_sparql(q):
    return q['Parses'][0].get('Sparql', '') if q.get('Parses') else ''

def get_qtext(q):
    return q.get('ProcessedQuestion') or q.get('RawQuestion') or ''

def answer_rels(s):
    s = s or ''
    rels = (re.findall(r'ns:([\w.]+)\s+\?x\s*[\.;\}]', s)
            + re.findall(r'\?x\s+ns:([\w.]+)\s+', s))
    # dedupe per case (a ?x may appear twice in nested MANUAL SPARQL)
    seen = []
    for r in rels:
        if r not in seen:
            seen.append(r)
    return seen

def filters(s):
    s = s or ''
    U = s.upper()
    has_datefilter = bool(re.search(
        r'FILTER\s*\([^)]*(datetime|\.from|\.to|\.date|start_date|end_date)', s, re.I))
    has_titlefilter = bool(re.search(
        r'(basic_title|office_position_or_title|position_held\.(title|basic_title))', s, re.I))
    has_limit = 'LIMIT' in U
    has_count = bool(re.search(r'\bCOUNT\s*\(', U))
    has_orderby = 'ORDER BY' in U
    has_not_exists = ('NOT EXISTS' in U) or ('not exists' in s)
    has_neg = bool(re.search(r'FILTER\s*\(\s*\?x\s*!=', s))
    return dict(date=has_datefilter, title=has_titlefilter, limit=has_limit,
                count=has_count, orderby=has_orderby, not_exists=has_not_exists,
                neg=has_neg)

def is_literal(a):
    a = str(a).strip()
    if not a:
        return False
    if re.fullmatch(r'-?\d+(\.\d+)?', a): return True
    if re.fullmatch(r'\d{4}s?', a): return True
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}.*', a): return True
    if re.fullmatch(r'\$[\d,.]+( USD)?', a): return True
    return False

def hidden_time(s, q):
    d = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s or '')
    if not d:
        return False
    date_years = set(dd[:4] for dd in d)
    q_years = set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', q or ''))
    has_word = any(k in (q or '').lower() for k in
                   ('current', ' now', 'latest', 'last ', 'most recent', 'recent', 'currently'))
    return not (date_years & q_years) and not has_word

EXCLUSIVE_KW = ['government_position_held', 'government_positions_held',
    'sports_team_coach', 'coach_tenure', 'pro_athlete', 'marriage',
    'employment_tenure', 'sports_team_championship_season', 'team_roster',
    'candidate', 'election', 'office_holder']
ACCUMULATIVE_KW = ['location.location.contains', 'containedby', 'languages_spoken',
    'countries_spoken_in', 'currency_used', 'form_of_government',
    'common.topic.notable_types', 'notable_for', 'education.institution',
    'film.director.film', 'film.producer.film', 'film.writer.film',
    'film.actor.film', 'religion_percentage', 'time_zones', 'influenced_by',
    'adjoining_relationship.adjoins', 'imports_and_exports']

rows = []
for q in QS:
    s = get_sparql(q)
    qtext = get_qtext(q)
    cid = q['QuestionId']
    rels = answer_rels(s)
    fl = filters(s)
    g = GOLD.get(cid, {})
    gold = [a for a in (g.get('a_entity') or []) if str(a).strip()]
    gold_n = len(gold)
    m_count = len(re.findall(r'ns:m\.\w+', s))
    is_excl = any(any(k in r for k in EXCLUSIVE_KW) for r in rels)
    is_acc = any(any(k in r for k in ACCUMULATIVE_KW) for r in rels)
    if gold_n == 0:
        gt_type = 'empty'
    elif all(is_literal(a) for a in gold):
        gt_type = 'literal'
    elif any(is_literal(a) for a in gold):
        gt_type = 'mixed'
    else:
        gt_type = 'entity'
    filtered = fl['date'] or fl['title'] or fl['limit']
    cat = 'single' if gold_n == 1 else ('list' if gold_n > 1 else 'none')
    rows.append(dict(id=cid, q=qtext, rels=rels, gold=gold, gold_n=gold_n,
                     cat=cat, filtered=filtered, fl=fl, m_count=m_count,
                     is_excl=is_excl, is_acc=is_acc, gt_type=gt_type,
                     primary_rel=(rels[0] if rels else ''), sparql=s))

def line(c='='): print(c * 78)

line()
print(f"WebQSP GT vs SPARQL STRUCTURE PROFILE  (N = {N})")
line()

# ---- [1] gold cardinality x SPARQL-filter ----
print("\n[1] GOLD CARDINALITY x SPARQL-FILTER  (filter = date OR title OR LIMIT)")
print("-" * 78)
ct = Counter()
for r in rows:
    f = 'FILTERED' if r['filtered'] else 'no-filter'
    ct[(r['cat'], f)] += 1
print(f"{'':16} {'no-filter':>12} {'FILTERED':>12} {'row%':>8}")
tot_single = ct.get(('single', 'no-filter'), 0) + ct.get(('single', 'FILTERED'), 0)
tot_list = ct.get(('list', 'no-filter'), 0) + ct.get(('list', 'FILTERED'), 0)
tot_none = ct.get(('none', 'no-filter'), 0) + ct.get(('none', 'FILTERED'), 0)
for cat, tot in [('single', tot_single), ('list', tot_list), ('none', tot_none)]:
    nf = ct.get((cat, 'no-filter'), 0); ff = ct.get((cat, 'FILTERED'), 0)
    print(f"{cat+' gold':16} {nf:>12} {ff:>12} {100*tot/N:>7.1f}%")
col_nf = sum(ct.get((c, 'no-filter'), 0) for c in ('single', 'list', 'none'))
col_ff = sum(ct.get((c, 'FILTERED'), 0) for c in ('single', 'list', 'none'))
print(f"{'col total':16} {col_nf:>12} {col_ff:>12} {100*(col_nf+col_ff)/N:>7.1f}%")
print(f"\n  rates: single={100*tot_single/N:.1f}%  list={100*tot_list/N:.1f}%  "
      f"none={100*tot_none/N:.1f}%  filtered={100*col_ff/N:.1f}%")
if col_ff:
    print(f"  among FILTERED: {100*ct.get(('single','FILTERED'),0)/col_ff:.0f}% single, "
          f"{100*ct.get(('list','FILTERED'),0)/col_ff:.0f}% list")
if col_nf:
    print(f"  among no-filter: {100*ct.get(('single','no-filter'),0)/col_nf:.0f}% single, "
          f"{100*ct.get(('list','no-filter'),0)/col_nf:.0f}% list")

# ---- [2] features predicting single vs multi ----
print("\n[2] SPARQL FEATURES predicting |gold|=1 (single) vs |gold|>1 (list)")
print("-" * 78)
def rate(sub, label):
    n = len(sub)
    if n == 0: return
    s = sum(1 for r in sub if r['cat'] == 'single')
    l = sum(1 for r in sub if r['cat'] == 'list')
    print(f"  {label:38} n={n:>5}  single {100*s/n:>5.0f}%  list {100*l/n:>5.0f}%")
for feat, lab in [
    (lambda r: r['fl']['date'], 'date-FILTER'),
    (lambda r: r['fl']['title'], 'title-FILTER'),
    (lambda r: r['fl']['limit'], 'LIMIT'),
    (lambda r: r['fl']['count'], 'COUNT'),
    (lambda r: r['fl']['not_exists'], 'NOT-EXISTS'),
    (lambda r: r['fl']['neg'], 'negation FILTER (?x!=)'),
    (lambda r: r['filtered'], 'ANY filter'),
    (lambda r: not r['filtered'], 'no filter'),
    (lambda r: r['is_excl'], 'exclusive relation (kw)'),
    (lambda r: r['is_acc'], 'accumulative relation (kw)'),
]:
    rate([r for r in rows if feat(r)], lab)
print("\n  --- constraint richness (ns:m. count) -> cardinality ---")
for lo, hi, lab in [(0, 1, '0-1 entity'), (2, 2, '2 entities'),
                    (3, 3, '3 entities'), (4, 99, '4+ entities')]:
    rate([r for r in rows if lo <= r['m_count'] <= hi], f'm_count {lab}')

# ---- [3] GT type + cardinality distribution ----
print("\n[3] GT ANSWER-TYPE PROFILE + CARDINALITY DISTRIBUTION")
print("-" * 78)
tc = Counter(r['gt_type'] for r in rows)
for t, c in tc.most_common():
    print(f"  {t:10} {c:>5}  ({100*c/N:.1f}%)")
print("\n  gold cardinality distribution:")
gc = Counter(r['gold_n'] for r in rows)
for k in sorted(gc.keys())[:14]:
    print(f"    |G|={k:<3} {gc[k]:>5}  ({100*gc[k]/N:.1f}%)")
big = [gc[k] for k in gc if k > 15]
if big:
    print(f"    |G|>15  {sum(big):>5}  ({100*sum(big)/N:.1f}%)")
multi = [r for r in rows if r['gold_n'] > 1]
if multi:
    print(f"\n  among list cases (|G|>1, n={len(multi)}): "
          f"mean |G|={sum(r['gold_n'] for r in multi)/len(multi):.1f}, "
          f"median={sorted(r['gold_n'] for r in multi)[len(multi)//2]}")
    gc2 = Counter(r['gold_n'] for r in multi)
    print(f"  top |G| values among list cases:")
    for k, c in gc2.most_common(8):
        print(f"    |G|={k:<3} {c:>5}")

# ---- [4] exclusive vs accumulative framework ----
print("\n[4] EXCLUSIVE vs ACCUMULATIVE framework")
print("-" * 78)
def card_dist(sub, label):
    if not sub:
        print(f"  {label:24} (none)"); return
    s = sum(1 for r in sub if r['cat'] == 'single')
    l = sum(1 for r in sub if r['cat'] == 'list')
    filt = sum(1 for r in sub if r['filtered'])
    mean = sum(r['gold_n'] for r in sub) / len(sub)
    med = sorted(r['gold_n'] for r in sub)[len(sub) // 2]
    print(f"  {label:24} n={len(sub):>5}  single {100*s/len(sub):>4.0f}%  "
          f"list {100*l/len(sub):>4.0f}%  filtered {100*filt/len(sub):>4.0f}%  "
          f"mean|G| {mean:>4.1f}  median {med}")
card_dist([r for r in rows if r['is_excl']], 'EXCLUSIVE (kw)')
card_dist([r for r in rows if r['is_acc']], 'ACCUMULATIVE (kw)')
card_dist([r for r in rows if r['is_excl'] and r['filtered']], '  exclusive+filtered')
card_dist([r for r in rows if r['is_acc'] and not r['filtered']], '  accumul.+no-filter')

# ---- [5] relation -> cardinality prior table ----
print("\n[5] RELATION -> CARDINALITY PRIOR  (relations with >=15 cases)")
print("-" * 78)
rel_cat = defaultdict(lambda: [0, 0])
for r in rows:
    for rel in set(r['rels']):
        if r['cat'] == 'single': rel_cat[rel][0] += 1
        elif r['cat'] == 'list': rel_cat[rel][1] += 1
rel_stats = []
for rel, (s, l) in rel_cat.items():
    tot = s + l
    if tot >= 15:
        sub = [r for r in rows if rel in r['rels']]
        filt = sum(1 for r in sub if r['filtered'])
        mean = sum(r['gold_n'] for r in sub) / len(sub)
        rel_stats.append((rel, tot, 100*s/tot, 100*filt/tot, mean))
print(f"  {'relation':46} {'n':>4} {'single%':>7} {'filt%':>6} {'mean|G|':>7}")
print("  --- most single-prone (top) ---")
for rel, tot, sp, fp, mean in sorted(rel_stats, key=lambda x: -x[2])[:12]:
    print(f"  {rel:46} {tot:>4} {sp:>6.0f}% {fp:>5.0f}% {mean:>7.1f}")
print("  --- most list-prone (bottom) ---")
for rel, tot, sp, fp, mean in sorted(rel_stats, key=lambda x: x[2])[:12]:
    print(f"  {rel:46} {tot:>4} {sp:>6.0f}% {fp:>5.0f}% {mean:>7.1f}")

# ---- [6] new patterns / list drivers ----
print("\n[6] LIST-DRIVER detail (WebQSP has higher multi-answer rate)")
print("-" * 78)
print(f"  ORDER-BY (superlative) queries: {sum(1 for r in rows if r['fl']['orderby'])}")
cnt_rows = [r for r in rows if r['fl']['count']]
print(f"  COUNT queries: {len(cnt_rows)}")
empty = [r for r in rows if r['gold_n'] == 0]
print(f"  EMPTY gold: {len(empty)} ({100*len(empty)/N:.1f}%)")
huge = sorted([r for r in rows if r['gold_n'] >= 10], key=lambda r: -r['gold_n'])
print(f"  |G|>=10: {len(huge)} cases; top list-driving relations:")
hrel = Counter()
for r in huge:
    for rel in r['rels']: hrel[rel] += 1
for rel, c in hrel.most_common(8):
    print(f"    {rel:46} x{c}")
# m_count vs cardinality
print("\n  constraint richness vs list-rate:")
buckets = defaultdict(lambda: [0, 0, 0])
for r in rows:
    b = min(r['m_count'], 6)
    buckets[b][0] += 1
    if r['cat'] == 'single': buckets[b][1] += 1
    elif r['cat'] == 'list': buckets[b][2] += 1
print("    m_count   n     single%  list%")
for mc in sorted(buckets):
    n, s, l = buckets[mc]
    lab = f'{mc}' if mc < 6 else '6+'
    print(f"    {lab:<8}  {n:>5}  {100*s/n:>5.0f}%  {100*l/n:>5.0f}%")

# ---- [7] CWQ vs WebQSP comparison ----
print("\n[7] CWQ vs WebQSP COMPARISON")
print("-" * 78)
cwq_path = os.path.join(ROOT, 'reports/gold_sparql_profile.json')
cwq_single = cwq_list = cwq_filt = cwq_n = None
if os.path.exists(cwq_path):
    cwq = json.load(open(cwq_path))
    cwq_n = len(cwq)
    cwq_single = 100 * sum(1 for r in cwq if r['cat'] == 'single') / cwq_n
    cwq_list = 100 * sum(1 for r in cwq if r['cat'] == 'list') / cwq_n
    cwq_filt = 100 * sum(1 for r in cwq if r['filtered']) / cwq_n
    cwq_excl = [r for r in cwq if r['is_excl']]
    cwq_acc = [r for r in cwq if r['is_acc']]
print(f"  {'metric':28} {'CWQ(3531)':>12} {'WebQSP(1639)':>14}")
print(f"  {'-'*56}")
print(f"  {'single gold %':28} {cwq_single:>11.1f}% {100*tot_single/N:>13.1f}%")
print(f"  {'list gold %':28} {cwq_list:>11.1f}% {100*tot_list/N:>13.1f}%")
print(f"  {'filtered %':28} {cwq_filt:>11.1f}% {100*col_ff/N:>13.1f}%")
if cwq_excl and cwq_acc:
    cwq_ex_s = 100*sum(1 for r in cwq_excl if r['cat']=='single')/len(cwq_excl)
    cwq_acc_s = 100*sum(1 for r in cwq_acc if r['cat']=='single')/len(cwq_acc)
    print(f"  {'exclusive single %':28} {cwq_ex_s:>11.0f}% {100*sum(1 for r in rows if r['is_excl'] and r['cat']=='single')/max(1,sum(1 for r in rows if r['is_excl'])):>13.0f}%")
    print(f"  {'accumulative single %':28} {cwq_acc_s:>11.0f}% {100*sum(1 for r in rows if r['is_acc'] and r['cat']=='single')/max(1,sum(1 for r in rows if r['is_acc'])):>13.0f}%")
# list mean |G|
if multi:
    print(f"  {'list mean |G|':28} {'4.7':>12} {sum(r['gold_n'] for r in multi)/len(multi):>13.1f}")

os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
dump = [dict(id=r['id'], gold_n=r['gold_n'], cat=r['cat'],
             filtered=r['filtered'], gt_type=r['gt_type'],
             m_count=r['m_count'], is_excl=r['is_excl'], is_acc=r['is_acc'],
             primary_rel=r['primary_rel'],
             fl={k: v for k, v in r['fl'].items()}) for r in rows]
with open(os.path.join(ROOT, 'reports/webqsp_gold_sparql_profile.json'), 'w') as f:
    json.dump(dump, f, indent=2)
print(f"\n[dumped reports/webqsp_gold_sparql_profile.json]")
