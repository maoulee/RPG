"""Profile GT (gold) vs SPARQL structure across the FULL 3531 test set.

Re-validates pilot-only conclusions (99-case gold-cardinality x SPARQL-filter
cross-tab, exclusive/accumulative framework) at scale, and adds:
  - which SPARQL features predict |gold|=1 vs |gold|>1
  - GT answer-type profile (entity vs literal) + cardinality distribution
  - exclusive vs accumulative relation cardinality distributions
  - gold cardinality vs constraint-richness correlation

Read-only analysis. Reuses filter logic from scan_relation_framework.py and
answer-relation regex from scan_relation_slots.py.

ASSUMPTIONS (flagged inline):
  - 'answer relation' = triple where ?x is subject or object.
  - filter = date-FILTER OR title-FILTER OR LIMIT (same defn as pilot script).
  - GT 'literal' = a gold item that is a pure year/number/date/numeric string;
    everything else is an 'entity' (named topic). Heuristic — see note.
  - exclusive/accumulative relation sets are keyword-defined then validated
    empirically against the observed cardinality distribution.
"""
import json, re, os, pickle
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = json.load(open(os.path.join(ROOT, 'data/cwq_sparql/test.json')))
PKL = pickle.load(open(os.path.join(ROOT,
    'data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl'), 'rb'))
GOLD = {x['id']: x for x in PKL}
N = len(SP)

def answer_rels(s):
    s = s or ''
    return (re.findall(r'ns:([\w.]+)\s+\?x\s*[\.;\}]', s)
            + re.findall(r'\?x\s+ns:([\w.]+)\s+', s))

def years_in(q):
    return set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', q or ''))

# ---- filter detection (mirrors scan_relation_framework.analyze_sparql) ----
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

# ---- GT answer type (heuristic) ----
def is_literal(a):
    """A gold item is 'literal' if it is a pure number, year, date, or numeric
    string. ASSUMPTION: named topics like '2014 World Series' are entities, NOT
    literals — only bare numerics/years/dates count as literal."""
    a = str(a).strip()
    if not a:
        return False
    if re.fullmatch(r'-?\d+(\.\d+)?', a):            # pure number
        return True
    if re.fullmatch(r'\d{4}s?', a):                  # year or '1990s'
        return True
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}.*', a):      # date
        return True
    if re.fullmatch(r'\$[\d,.]+( USD)?', a):         # currency amount
        return True
    return False

# ---- exclusive vs accumulative relation keyword sets ----
EXCLUSIVE_KW = [   # time-bounded CVT: typically few concurrent holders
    'government_position_held', 'government_positions_held',
    'sports_team_coach', 'coach_tenure', 'pro_athlete',
    'marriage', 'employment_tenure', 'sports_team_championship_season',
    'team_roster', 'candidate', 'election', 'office_holder',
]
ACCUMULATIVE_KW = [  # full set, no time bound
    'location.location.contains', 'containedby', 'languages_spoken',
    'countries_spoken_in', 'currency_used', 'form_of_government',
    'common.topic.notable_types', 'notable_for', 'education.institution',
    'film.director.film', 'film.producer.film', 'film.writer.film',
    'film.actor.film', 'religion_percentage', 'time_zones', 'influenced_by',
    'adjoining_relationship.adjoins', 'imports_and_exports',
]

# ---- build per-case feature rows ----
rows = []
for x in SP:
    s = x.get('sparql') or ''
    q = x.get('question') or ''
    cid = x['ID']
    rels = answer_rels(s)
    fl = filters(s)
    g = GOLD.get(cid, {})
    gold = g.get('a_entity') or []
    gold = [a for a in gold if str(a).strip()]
    gold_n = len(gold)
    # constraint richness: count of named-entity bindings (ns:m.) excluding the
    # bare ?c seed that some SPARQL use as the topic var
    m_count = len(re.findall(r'ns:m\.\w+', s))
    triple_count = len(re.findall(r'ns:[\w.]+\s+ns:[\w.]+\b', s))  # rough
    # relation category
    is_excl = any(any(k in r for k in EXCLUSIVE_KW) for r in rels)
    is_acc = any(any(k in r for k in ACCUMULATIVE_KW) for r in rels)
    # GT type
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
    rows.append(dict(id=cid, q=q, rels=rels, gold=gold, gold_n=gold_n,
                     cat=cat, filtered=filtered, fl=fl, m_count=m_count,
                     triple_count=triple_count, is_excl=is_excl, is_acc=is_acc,
                     gt_type=gt_type, primary_rel=(rels[0] if rels else '')))

def line(c='='): print(c * 78)

line()
print(f"GT vs SPARQL STRUCTURE PROFILE  (full CWQ test set, N = {N})")
line()

# =========================================================================
# [1] gold cardinality x SPARQL-filter cross-tab (large-scale)
# =========================================================================
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
print(f"\n  pilot (99) was: single no-filt 56 / filt 19 ; list no-filt 23 / filt 1")
print(f"  3531 rates: single={100*tot_single/N:.1f}%  list={100*tot_list/N:.1f}%  "
      f"none={100*tot_none/N:.1f}%")
print(f"             filtered={100*col_ff/N:.1f}%  no-filter={100*col_nf/N:.1f}%")
list_filt = ct.get(('list', 'FILTERED'), 0)
single_filt = ct.get(('single', 'FILTERED'), 0)
print(f"  among FILTERED: {100*single_filt/col_ff:.0f}% single, "
      f"{100*list_filt/col_ff:.0f}% list")
print(f"  among no-filter: {100*ct.get(('single','no-filter'),0)/col_nf:.0f}% single, "
      f"{100*ct.get(('list','no-filter'),0)/col_nf:.0f}% list")

# =========================================================================
# [2] features predicting single vs multi
# =========================================================================
print("\n[2] SPARQL FEATURES predicting |gold|=1 (single) vs |gold|>1 (list)")
print("-" * 78)
def rate(feature_rows, label):
    n = len(feature_rows)
    if n == 0:
        return
    s = sum(1 for r in feature_rows if r['cat'] == 'single')
    l = sum(1 for r in feature_rows if r['cat'] == 'list')
    print(f"  {label:38} n={n:>5}  single {100*s/n:>5.0f}%  list {100*l/n:>5.0f}%")

print("  --- feature PRESENCE -> cardinality ---")
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
for lo, hi, lab in [(0, 1, '1 entity '), (2, 2, '2 entities'),
                    (3, 3, '3 entities'), (4, 99, '4+ entities')]:
    sub = [r for r in rows if lo <= r['m_count'] <= hi]
    rate(sub, f'm_count {lab}')

print("\n  --- top answer-relations: single-rate ---")
rel_cat = defaultdict(lambda: [0, 0])  # [single, list]
for r in rows:
    for rel in set(r['rels']):
        if r['cat'] == 'single': rel_cat[rel][0] += 1
        elif r['cat'] == 'list': rel_cat[rel][1] += 1
print(f"  {'relation':40} {'n':>5} {'single%':>8}")
for rel, (s, l) in sorted(rel_cat.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:18]:
    tot = s + l
    if tot >= 15:
        print(f"  {rel:40} {tot:>5} {100*s/tot:>7.0f}%")

# =========================================================================
# [3] GT answer-type profile + cardinality distribution
# =========================================================================
print("\n[3] GT ANSWER-TYPE PROFILE + CARDINALITY DISTRIBUTION")
print("-" * 78)
tc = Counter(r['gt_type'] for r in rows)
for t, c in tc.most_common():
    print(f"  {t:10} {c:>5}  ({100*c/N:.1f}%)")
print("\n  gold cardinality distribution:")
gc = Counter(r['gold_n'] for r in rows)
for k in sorted(gc.keys())[:15]:
    print(f"    |G|={k:<3} {gc[k]:>5}  ({100*gc[k]/N:.1f}%)")
big = [gc[k] for k in gc if k > 15]
if big:
    print(f"    |G|>15  {sum(big):>5}  ({100*sum(big)/N:.1f}%)")
multi = [r for r in rows if r['gold_n'] > 1]
print(f"\n  among list cases (|G|>1, n={len(multi)}): "
      f"mean |G|={sum(r['gold_n'] for r in multi)/len(multi):.1f}, "
      f"median={sorted(r['gold_n'] for r in multi)[len(multi)//2]}")
print(f"  top |G| values among list cases:")
gc2 = Counter(r['gold_n'] for r in multi)
for k, c in gc2.most_common(8):
    print(f"    |G|={k:<3} {c:>5}")

# =========================================================================
# [4] framework revalidation: exclusive vs accumulative cardinality dist
# =========================================================================
print("\n[4] EXCLUSIVE vs ACCUMULATIVE framework revalidation")
print("-" * 78)
def card_dist(sub, label):
    if not sub:
        print(f"  {label:24} (none)")
        return
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
print("\n  data-driven check: relations with >=20 cases, ranked by single-rate")
print(f"  {'relation':40} {'n':>4} {'single%':>7} {'filt%':>6} {'mean|G|':>7}")
rel_stats = []
for rel, (s, l) in rel_cat.items():
    tot = s + l
    if tot >= 20:
        sub = [r for r in rows if rel in r['rels']]
        filt = sum(1 for r in sub if r['filtered'])
        mean = sum(r['gold_n'] for r in sub) / len(sub)
        rel_stats.append((rel, tot, 100*s/tot, 100*filt/tot, mean))
for rel, tot, sp, fp, mean in sorted(rel_stats, key=lambda x: -x[2])[:14]:
    print(f"  {rel:40} {tot:>4} {sp:>6.0f}% {fp:>5.0f}% {mean:>7.1f}")
print("  ... (most accumulative / list-heavy) ...")
for rel, tot, sp, fp, mean in sorted(rel_stats, key=lambda x: x[2])[:8]:
    print(f"  {rel:40} {tot:>4} {sp:>6.0f}% {fp:>5.0f}% {mean:>7.1f}")

# =========================================================================
# [5] constraint-richness vs cardinality correlation + revalidate ambiguity
# =========================================================================
print("\n[5] CONSTRAINT-RICHNESS vs CARDINALITY  +  ambiguity revalidation")
print("-" * 78)
# correlation: more ns:m. entities -> ?
buckets = defaultdict(lambda: [0, 0, 0])  # mc -> [n, single, list]
for r in rows:
    b = min(r['m_count'], 6)
    buckets[b][0] += 1
    if r['cat'] == 'single': buckets[b][1] += 1
    elif r['cat'] == 'list': buckets[b][2] += 1
print("  m_count(entities bound)  n     single%  list%")
for mc in sorted(buckets):
    n, s, l = buckets[mc]
    lab = f'{mc}' if mc < 6 else '6+'
    print(f"    {lab:<22}    {n:>5}  {100*s/n:>5.0f}%  {100*l/n:>5.0f}%")

# revalidate previous ambiguity numbers via this script's overlap with the
# multi-slot / hidden-criterion flags
amb = json.load(open(os.path.join(ROOT, 'reports/ambiguity_cases.json')))
amb_ids = set(amb.get('all_ambiguity_ids', []))
hard_ids = set(amb.get('hard_ambiguity_ids', []))
irred_ids = set(amb.get('hard_irreducible_ids', []))
ht_ids = set(amb.get('hidden_time_ids', []))
print(f"\n  previous ambiguity screen: union {len(amb_ids)} ({100*len(amb_ids)/N:.1f}%), "
      f"hard {len(hard_ids)} ({100*len(hard_ids)/N:.1f}%), "
      f"irreducible {len(irred_ids)} ({100*len(irred_ids)/N:.1f}%)")
# does ambiguity concentrate in list vs single?
amb_rows = [r for r in rows if r['id'] in amb_ids]
asg = sum(1 for r in amb_rows if r['cat'] == 'single')
alg = sum(1 for r in amb_rows if r['cat'] == 'list')
print(f"  ambiguity cases: {100*asg/len(amb_rows):.0f}% single, "
      f"{100*alg/len(amb_rows):.0f}% list  (mostly {'single' if asg>alg else 'list'})")
# cross-tab ambiguity x filtered
af = sum(1 for r in amb_rows if r['filtered'])
print(f"  ambiguity cases with a SPARQL filter: {af} ({100*af/len(amb_rows):.0f}%)")

# =========================================================================
# [6] NEW patterns only visible at scale
# =========================================================================
print("\n[6] PATTERNS only visible at scale (3531)")
print("-" * 78)
# (a) COUNT cases: how many, and is gold a number?
cnt_rows = [r for r in rows if r['fl']['count']]
print(f"  COUNT queries: {len(cnt_rows)} ({100*len(cnt_rows)/N:.1f}%)")
if cnt_rows:
    cnl = Counter(r['gt_type'] for r in cnt_rows)
    print(f"    their GT type: {dict(cnl)}")
    print(f"    sample: {cnt_rows[0]['q'][:60]} -> {cnt_rows[0]['gold']}")
# (b) ORDER BY (superlatives) without LIMIT
ob_rows = [r for r in rows if r['fl']['orderby']]
print(f"  ORDER-BY queries: {len(ob_rows)} ({100*len(ob_rows)/N:.1f}%)")
# (c) empty-gold cases (|G|=0)
empty = [r for r in rows if r['gold_n'] == 0]
print(f"  EMPTY gold (|G|=0): {len(empty)} ({100*len(empty)/N:.1f}%)")
# (d) very large gold sets
huge = sorted([r for r in rows if r['gold_n'] >= 15], key=lambda r: -r['gold_n'])
print(f"  |G|>=15: {len(huge)} cases; top relations:")
hrel = Counter()
for r in huge:
    for rel in r['rels']: hrel[rel] += 1
for rel, c in hrel.most_common(6):
    print(f"    {rel:40} x{c}")

# dump per-case features for reuse
os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
dump = [dict(id=r['id'], gold_n=r['gold_n'], cat=r['cat'],
             filtered=r['filtered'], gt_type=r['gt_type'],
             m_count=r['m_count'], is_excl=r['is_excl'], is_acc=r['is_acc'],
             primary_rel=r['primary_rel'],
             fl={k: v for k, v in r['fl'].items()}) for r in rows]
with open(os.path.join(ROOT, 'reports/gold_sparql_profile.json'), 'w') as f:
    json.dump(dump, f, indent=2)
print(f"\n[dumped reports/gold_sparql_profile.json — per-case features]")
