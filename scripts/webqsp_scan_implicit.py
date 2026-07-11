"""Scan WebQSP for cases whose answer needs an IMPLICIT constraint to decide
latest/current vs all (the Step-3 crux). Goal: derive a reliable rule.

Classify each case by:
  - answer relation type: EXCLUSIVE (role/position: gov_position, coach,
    marriage, office_holder, spouse) vs ACCUMULATIVE (set/event: championships,
    languages, deities, professions, members, films, containedby, currency)
  - explicit constraint in question: date / 'last'/latest/current / official / superlative
  - gold cardinality (|a_entity|)
  - present-tense singular cue ('is the X', 'who is')

Implicit-constraint cases (the crux):
  TYPE-LATEST: exclusive role + no explicit date + present/singular → needs implicit CURRENT (pick 1)
  TYPE-ALL:    accumulative + no explicit 'all' marker + gold>1 → needs implicit ALL (the model's trap)
Quantify each + measure how well 'relation type' predicts latest-vs-all.
"""
import json, re, pickle
from collections import Counter, defaultdict

sp = {q['QuestionId']: q for q in json.load(open('data/webqsp/WebQSP.test.json'))['Questions']}
test = pickle.load(open('data/webqsp/test_fixed_path_completed.pkl', 'rb'))
gold = {x['id']: x['a_entity'] for x in test}

EXCL_KW = ('government_position_held.office_holder', 'governmental_jurisdiction.governing_officials',
           'sports_team_coach.coach', 'sports.sports_team.coaches', 'people.marriage.spouse',
           'office_holders', 'president', 'vice_president', 'political_appointer.appointees')
ACCUM_KW = ('championships', 'languages_spoken', 'official_language', 'deities', 'profession',
            'notable_types', 'contains', 'containedby', 'currency_used', 'members', 'film',
            'genre', 'religion')

def ans_rels(s):
    return set(re.findall(r'ns:([\w.]+)\s+\?x\s*\.', s)) | set(re.findall(r'\?x\s+ns:([\w.]+)\s+', s))

def rel_type(rels):
    r = ' '.join(rels).lower()
    if any(k.lower() in r for k in EXCL_KW): return 'EXCL'
    if any(k.lower() in r for k in ACCUM_KW): return 'ACCUM'
    return 'OTHER'

def cues(q):
    ql = q.lower()
    return dict(
        date=bool(re.search(r'\b(1[6-9]\d{2}|20\d{2})\b', q)),
        last='last' in ql or 'latest' in ql or 'most recent' in ql or 'recent' in ql,
        current='current' in ql or ' now' in ql,
        official='official' in ql or 'main' in ql,
        present_singular=bool(re.search(r'\b(is|was)\s+(the|a|our|its)\s', ql)),
    )

rows = []
for qid, q in sp.items():
    pq = q.get('Parses', [{}])[0]
    sparql = pq.get('Sparql', '') or ''
    if not sparql: continue
    rels = ans_rels(sparql)
    if not rels: continue
    rt = rel_type(rels)
    if rt == 'OTHER': continue
    g = gold.get(qid, [])
    ng = len(g) if isinstance(g, list) else 1
    c = cues(q.get('ProcessedQuestion') or q.get('RawQuestion', ''))
    rows.append(dict(qid=qid, rt=rt, ng=ng, q=q.get('ProcessedQuestion', ''), c=c, rels=rels))

print(f"=== WebQSP answer-relation cases (EXCL/ACCUM): {len(rows)} ===")
print("by type:", Counter(r['rt'] for r in rows))
print()

# TYPE-LATEST: exclusive, present/singular, no explicit date/last
latest = [r for r in rows if r['rt'] == 'EXCL' and r['c']['present_singular']
          and not (r['c']['date'] or r['c']['last'])]
print(f"=== TYPE-LATEST (exclusive role + present/singular + no explicit date/last): {len(latest)} ===")
print(f"  gold|G| dist: {Counter(r['ng'] for r in latest).most_common(5)}")
g1 = sum(1 for r in latest if r['ng'] == 1)
print(f"  gold=1 (current/latest applied): {g1}/{len(latest)} = {100*g1/max(len(latest),1):.0f}%")
print("  samples:")
for r in latest[:5]:
    print(f"    |G|={r['ng']} {r['qid']} {r['q'][:65]}")

# TYPE-ALL: accumulative, gold>1 (the model's all-trap)
allset = [r for r in rows if r['rt'] == 'ACCUM' and r['ng'] > 1]
print(f"\n=== TYPE-ALL (accumulative + gold>1): {len(allset)} ===")
print(f"  with explicit 'last/current': {sum(1 for r in allset if r['c']['last'] or r['c']['current'])}")
print(f"  present/singular phrasing: {sum(1 for r in allset if r['c']['present_singular'])}")
print("  samples:")
for r in allset[:6]:
    print(f"    |G|={r['ng']} {r['qid']} {r['q'][:65]}")

# the real trap: accumulative + present/singular + gold>1 (model reads singular, should be all)
trap = [r for r in allset if r['c']['present_singular']]
print(f"\n=== THE TRAP (accumulative + present/singular + gold>1): {len(trap)} ===")
for r in trap[:8]:
    print(f"    |G|={r['ng']} {r['qid']} {r['q'][:70]}")

# rule reliability: does relation type predict cardinality?
print(f"\n=== RULE RELIABILITY: relation type → gold cardinality ===")
for rt in ('EXCL', 'ACCUM'):
    rs = [r for r in rows if r['rt'] == rt]
    g1 = sum(1 for r in rs if r['ng'] == 1)
    gm = sum(1 for r in rs if r['ng'] > 1)
    print(f"  {rt}: n={len(rs)} gold=1:{g1} ({100*g1/max(len(rs),1):.0f}%) gold>1:{gm} ({100*gm/max(len(rs),1):.0f}%)")
