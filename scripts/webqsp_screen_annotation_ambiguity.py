"""Screen annotation ambiguity across the WebQSP test set (1639 cases).

Mirrors scripts/screen_annotation_ambiguity.py (CWQ). Same multi-slot concept
definitions and hidden-criterion logic (Freebase-wide). WebQSP adaptation:
SPARQL from Parses[0]['Sparql'], question = ProcessedQuestion.

ASSUMPTIONS (same as CWQ):
  - 'answer relation' = ?x subject/object triple, deduped per case.
  - disambiguation keyword lists reused from CWQ (curated on CWQ samples; may
    be slightly miscalibrated for WebQSP phrasing — flagged).
  - hard ambiguity = no slot keyword; irreducible = minority-slot + no keyword.
"""
import json, re, os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WQ = json.load(open(os.path.join(ROOT, 'data/webqsp/WebQSP.test.json')))
QS = WQ['Questions']
N = len(QS)

def get_sparql(q):
    return q['Parses'][0].get('Sparql', '') if q.get('Parses') else ''
def get_qtext(q):
    return q.get('ProcessedQuestion') or q.get('RawQuestion') or ''

def answer_rels(s):
    s = s or ''
    rels = (re.findall(r'ns:([\w.]+)\s+\?x\s*[\.;\}]', s)
            + re.findall(r'\?x\s+ns:([\w.]+)\s+', s))
    seen = []
    for r in rels:
        if r not in seen:
            seen.append(r)
    return seen

CONCEPTS = {
    'LANGUAGE': {
        'slots': {
            'official_language':  (['official_language'], ['official']),
            'languages_spoken':   (['languages_spoken'],
                                   ['all language', 'languages are', 'languages spoken',
                                    'languages do', 'language do', 'language are']),
        },
        'ambiguity_note': 'official vs all; generic singular "language spoken"',
    },
    'CURRENCY': {
        'slots': {
            'currency_used':          (['country.currency_used'],
                                       ['current', 'today', 'present', 'now use',
                                        'currency of', "currency is", 'what currency',
                                        'what money', 'uses the']),
            'currency_formerly_used': (['currency_formerly_used'],
                                       ['before', 'former', 'formerly', 'previous',
                                        'prior', 'used to', 'was the', 'old', 'past',
                                        'earlier', 'used before', 'pre-euro', 'adapted']),
        },
        'ambiguity_note': 'current vs former; former keyworded, current is default',
    },
    'RELIGION': {
        'slots': {
            'religion_percentage': (['religion_percentage.religion'],
                                    ['predominant', 'main religion', 'majority',
                                     'biggest', 'largest', 'most common',
                                     'major religion', 'primary', 'practic',
                                     'religion is', 'religions are']),
            'deities':             (['religion.religion.deities'],
                                    ['deity', 'deities', 'god', 'gods', 'goddess',
                                     'worship', 'diety']),
            'texts':               (['religion.religion.texts'],
                                    ['text', 'book', 'scripture', 'holy book',
                                     'sacred text', 'bible']),
            'person_religion':     (['people.person.religion'],
                                    ['who', 'person', 'man', 'woman']),
        },
        'ambiguity_note': 'predominant% vs person vs deities vs texts',
    },
    'BORDER_CONTAIN': {
        'slots': {
            'contains':         (['location.location.contains'],
                                 ['contain', 'include', 'consist of', 'made up',
                                  'has', 'have', 'with', 'composed of', 'made of',
                                  'are in the location']),
            'containedby':      (['location.location.containedby'],
                                 ['inside', 'within', 'located', 'part of', 'where is',
                                  'a part of', 'what part', 'situated in', 'located in',
                                  'is in']),
            'adjoins':          (['adjoining_relationship.adjoins'],
                                 ['border', 'next to', 'neighbor', 'neighboring',
                                  'sharing', 'shares a', 'adjacent', 'adjoin']),
            'partially_contained': (['partially_contain'],
                                    ['partial', 'partly', 'bisect', 'divid', 'cross',
                                     'through']),
        },
        'ambiguity_note': 'directional parent/child + partial + adjoin',
    },
    'GOVT_FORM_HOLDER': {
        'slots': {
            'form_of_government': (['form_of_government'],
                                   ['form of government', 'type of government',
                                    'government type', 'governmental type',
                                    'kind of government', 'system of government',
                                    'political system', 'governent', 'government is',
                                    'run by', 'what type', 'form of gov']),
            'office_holder':      (['government_position_held.office_holder',
                                   'politician.government_positions_held'],
                                   ['who', 'leader', 'governor', 'president',
                                    'prime minister', 'minister', 'man', 'woman',
                                    'brother', 'holds', 'held', 'head of', 'ruler',
                                    'king', 'queen', 'chairman', 'chairperson']),
        },
        'ambiguity_note': 'system-of-govt vs leader',
    },
}

def hidden_time(s, q):
    d = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s or '')
    if not d:
        return False
    date_years = set(dd[:4] for dd in d)
    q_years = set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', q or ''))
    has_word = any(k in (q or '').lower() for k in
                   ('current', ' now', 'latest', 'last ', 'most recent', 'recent',
                    'currently'))
    return not (date_years & q_years) and not has_word

def has_not_exists(s):
    U = (s or '').upper()
    return 'NOT EXISTS' in U or 'not exists' in (s or '')

rows = []
for q in QS:
    s = get_sparql(q)
    qtext = get_qtext(q)
    cid = q['QuestionId']
    rels = answer_rels(s)
    rec = dict(id=cid, q=qtext, rels=rels, multi_slot={}, hidden={})
    for cname, cdef in CONCEPTS.items():
        picked = None
        for slot, (kws, _) in cdef['slots'].items():
            if any(any(k in r for k in kws) for r in rels):
                picked = slot
                break
        if picked is None:
            continue
        n_slots = len(cdef['slots'])
        if n_slots < 2:
            continue
        ql = qtext.lower()
        picked_kws = cdef['slots'][picked][1]
        picked_signal = any(d in ql for d in picked_kws)
        other_kws = []
        for slot, (_, disambig) in cdef['slots'].items():
            if slot != picked:
                other_kws += disambig
        other_signal = any(d in ql for d in other_kws)
        if picked_signal:
            grade = 'disambig'
        elif other_signal:
            grade = 'soft'
        else:
            grade = 'hard'
        rec['multi_slot'][cname] = dict(slot=picked, grade=grade,
            hard=(grade == 'hard'), has_soft=(grade == 'soft'),
            has_strong=(grade == 'disambig'))
    if hidden_time(s, qtext):
        rec['hidden']['hidden_time'] = True
    if has_not_exists(s):
        rec['hidden']['not_exists'] = True
    rows.append(rec)

def line(c='='): print(c * 78)

line()
print(f"WebQSP ANNOTATION-AMBIGUITY SCREEN  (N = {N})")
line()

print("\n[A] MULTI-SLOT CONCEPT AMBIGUITY  (per concept)")
print("-" * 92)
print(f"{'concept':16} {'slots':>5} {'cases':>6} {'hard':>5} {'soft':>5} {'disamb':>6} "
      f"{'maj%':>6} | {'hard->min':>9} {'hard->maj':>9}")
print(f"{'':16} {'':>5} {'':>6} {'amb':>5} {'amb':>5} {'':>6} "
      f"{'':>6} | {'(irred.)':>9} {'(default)':>9}")
print("-" * 92)

concept_summary = []
amb_case_ids = set()
hard_amb_ids = set()
soft_amb_ids = set()
hard_irred_ids = set()
hard_default_ids = set()
for cname, cdef in CONCEPTS.items():
    cases = [r for r in rows if cname in r['multi_slot']]
    if not cases:
        continue
    slot_dist = Counter(r['multi_slot'][cname]['slot'] for r in cases)
    n_slots = len(cdef['slots'])
    majority_slot, majority_n = slot_dist.most_common(1)[0]
    majority_pct = 100 * majority_n / len(cases)
    hard = [r for r in cases if r['multi_slot'][cname]['hard']]
    soft = [r for r in cases if r['multi_slot'][cname]['has_soft']
            and not r['multi_slot'][cname]['has_strong']]
    disambig = [r for r in cases if r['multi_slot'][cname]['has_strong']]
    hard_min = [r for r in hard if r['multi_slot'][cname]['slot'] != majority_slot]
    hard_maj = [r for r in hard if r['multi_slot'][cname]['slot'] == majority_slot]
    print(f"{cname:16} {n_slots:>5} {len(cases):>6} {len(hard):>5} {len(soft):>5} "
          f"{len(disambig):>6} {majority_pct:>5.0f}% | {len(hard_min):>9} "
          f"{len(hard_maj):>9}")
    for slot, c in slot_dist.most_common():
        tag = ' (MAJ)' if slot == majority_slot else ''
        print(f"    {' ':12}   slot {slot:26} x{c}{tag}")
    concept_summary.append(dict(concept=cname, n_slots=n_slots, cases=len(cases),
        hard=len(hard), soft=len(soft), disambig=len(disambig),
        hard_minority=len(hard_min), hard_majority=len(hard_maj),
        majority_slot=majority_slot, majority_pct=majority_pct,
        slot_dist=dict(slot_dist)))
    for r in hard:
        hard_amb_ids.add(r['id']); amb_case_ids.add(r['id'])
        if r['multi_slot'][cname]['slot'] != majority_slot:
            hard_irred_ids.add(r['id'])
        else:
            hard_default_ids.add(r['id'])
    for r in soft:
        soft_amb_ids.add(r['id']); amb_case_ids.add(r['id'])

print("\n[B] HIDDEN-CRITERION AMBIGUITY")
print("-" * 78)
ht_ids = {r['id'] for r in rows if r['hidden'].get('hidden_time')}
ne_ids = {r['id'] for r in rows if r['hidden'].get('not_exists')}
print(f"  hidden-time  : {len(ht_ids):>5}  ({100*len(ht_ids)/N:.1f}%)")
print(f"  NOT-EXISTS   : {len(ne_ids):>5}  ({100*len(ne_ids)/N:.1f}%)")
hidden_ids = ht_ids | ne_ids

line()
print("[C] TOTALS")
line()
all_amb_ids = amb_case_ids | hidden_ids
hard_total = hard_amb_ids | ht_ids | ne_ids
soft_total = soft_amb_ids
print(f"  multi-slot ambiguity (hard or soft): {len(amb_case_ids):>5}  "
      f"({100*len(amb_case_ids)/N:.1f}%)")
print(f"     - hard                          : {len(hard_amb_ids):>5}  "
      f"({100*len(hard_amb_ids)/N:.1f}%)")
print(f"     - soft                           : {len(soft_amb_ids):>5}  "
      f"({100*len(soft_amb_ids)/N:.1f}%)")
print(f"  hidden-criterion                    : {len(hidden_ids):>5}  "
      f"({100*len(hidden_ids)/N:.1f}%)")
print(f"  UNION (all potential ambiguity)     : {len(all_amb_ids):>5}  "
      f"({100*len(all_amb_ids)/N:.1f}%)")
print(f"  HARD grade                          : {len(hard_total):>5}  "
      f"({100*len(hard_total)/N:.1f}%)")
genuine_irred = hard_irred_ids | ht_ids
print(f"  TRUE irreducible (hard-min U hidden-time): {len(genuine_irred):>5}  "
      f"({100*len(genuine_irred)/N:.1f}%)")
print(f"     - multi-slot minority-surprise   : {len(hard_irred_ids):>5}")
print(f"     - hidden-time                    : {len(ht_ids):>5}")
print(f"  defaultable (majority-slot)         : {len(hard_default_ids):>5}  "
      f"({100*len(hard_default_ids)/N:.1f}%)")

print("\n[D] CWQ vs WebQSP ambiguity comparison")
print("-" * 78)
cwq_path = os.path.join(ROOT, 'reports/ambiguity_cases.json')
if os.path.exists(cwq_path):
    cwq = json.load(open(cwq_path))
    ct = cwq['totals']
    print(f"  {'metric':32} {'CWQ(3531)':>12} {'WebQSP(1639)':>14}")
    print(f"  {'-'*60}")
    print(f"  {'union ambiguity %':32} {100*ct['union']/3531:>11.1f}% {100*len(all_amb_ids)/N:>13.1f}%")
    print(f"  {'hard %':32} {100*ct['multi_slot_hard']/3531:>11.1f}% {100*len(hard_amb_ids)/N:>13.1f}%")
    print(f"  {'irreducible %':32} {100*ct['genuine_irreducible']/3531:>11.1f}% {100*len(genuine_irred)/N:>13.1f}%")
    print(f"  {'hidden-time %':32} {100*ct['hidden_time']/3531:>11.1f}% {100*len(ht_ids)/N:>13.1f}%")
    print(f"  {'NOT-EXISTS %':32} {100*ct['not_exists']/3531:>11.1f}% {100*len(ne_ids)/N:>13.1f}%")

out = dict(N=N, concept_summary=concept_summary,
           hard_ambiguity_ids=sorted(hard_amb_ids),
           hard_irreducible_ids=sorted(hard_irred_ids),
           hard_defaultable_ids=sorted(hard_default_ids),
           hidden_time_ids=sorted(ht_ids),
           not_exists_ids=sorted(ne_ids),
           all_ambiguity_ids=sorted(all_amb_ids),
           totals=dict(
               multi_slot_hard=len(hard_amb_ids),
               multi_slot_soft=len(soft_amb_ids),
               multi_slot_hard_irreducible=len(hard_irred_ids),
               multi_slot_hard_defaultable=len(hard_default_ids),
               hidden_time=len(ht_ids),
               not_exists=len(ne_ids),
               hidden=len(hidden_ids),
               union=len(all_amb_ids),
               hard_grade=len(hard_total),
               genuine_irreducible=len(genuine_irred)))
os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
with open(os.path.join(ROOT, 'reports/webqsp_ambiguity_cases.json'), 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n[dumped reports/webqsp_ambiguity_cases.json]")
