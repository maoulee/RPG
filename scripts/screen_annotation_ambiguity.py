"""Screen annotation ambiguity across the CWQ test set (3531 cases).

A case is a 'potential annotation ambiguity' when the English question phrasing
is generic (no disambiguation signal), but the gold SPARQL commits to a specific
relation slot / criterion. Such cases are not the model's fault: an equally
plausible alternative reading would be scored wrong.

Two ambiguity families:
  A. MULTI-SLOT concept ambiguity — same English concept maps to several Freebase
     relations of different breadth (e.g. language: official_language vs
     languages_spoken). Generic phrasing + specific slot chosen = ambiguity.
  B. HIDDEN-CRITERION ambiguity — SPARQL carries a filter/criterion that is not
     readable from the English text (hidden 'now' time, NOT-EXISTS completeness
     clause, hidden superlative).

Output: prints a structured report and dumps JSON to reports/ambiguity_cases.json.

ASSUMPTIONS (flagged inline):
  - 'answer relation' = triple where ?x (the SELECT var) is subject or object.
    Extracted via the two regexes reused from scan_relation_slots.py.
  - 'disambiguation keyword' lists are hand-curated from sampled questions;
    they are conservative (only count a case as disambiguated if a strong,
    slot-specific word is present). Misspellings in CWQ questions may cause a
    few false 'hard ambiguity' labels (flagged as a known limitation).
  - Hard ambiguity  = NO slot-specific keyword in the question.
    Soft ambiguity  = only a weak/tense cue (not enough to uniquely pick slot).
"""
import json, re, os, pickle
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = json.load(open(os.path.join(ROOT, 'data/cwq_sparql/test.json')))
PKL = pickle.load(open(os.path.join(ROOT,
    'data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl'), 'rb'))
GOLD = {x['id']: x for x in PKL}
N = len(SP)

# ---------------------------------------------------------------------------
# answer-relation extraction (reused from scan_relation_slots.py)
# ---------------------------------------------------------------------------
def answer_rels(s):
    s = s or ''
    return (re.findall(r'ns:([\w.]+)\s+\?x\s*[\.;\}]', s)
            + re.findall(r'\?x\s+ns:([\w.]+)\s+', s))

# ---------------------------------------------------------------------------
# MULTI-SLOT concept definitions
#   each concept: list of slots; each slot: (match_kw, disambig_keywords)
#   disambig_keywords = words that, if in the question, lock the slot.
# ---------------------------------------------------------------------------
# Disambiguation keywords are hand-curated from sampled questions of each slot.
# Conservative intent: a case is 'disambiguated' only when a strong slot-specific
# word is present, so the hard-ambiguity count is an honest upper bound.
CONCEPTS = {
    'LANGUAGE': {
        # official_language(48) vs languages_spoken(195) — different BREADTH.
        # Genuinely ambiguous: "what language is spoken in X" reads either way.
        'slots': {
            'official_language':  (['official_language'], ['official']),
            'languages_spoken':   (['languages_spoken'],
                                   ['all language', 'languages are', 'languages spoken',
                                    'languages do', 'language do', 'language are']),  # plural = all
        },
        'ambiguity_note': 'official vs all; generic singular "language spoken" is ~80% all',
    },
    'CURRENCY': {
        # currency_used(167) vs currency_formerly_used(9) — current vs former.
        # Former is keyworded; current is the strong default (95%).
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
        'ambiguity_note': 'current vs former; former keyworded, current is 95% default',
    },
    'RELIGION': {
        # religion_percentage(86) vs person.religion(6) vs deities(17)/texts(18)
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
                                    ['who', 'person', 'man', 'woman']),  # person-subject
        },
        'ambiguity_note': 'predominant% vs person vs deities vs texts',
    },
    'BORDER_CONTAIN': {
        # Mostly directional; English disambiguates via has/with/located/part-of/bisect.
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
        'ambiguity_note': 'directional parent/child + partial + adjoin; mostly disambiged',
    },
    'GOVT_FORM_HOLDER': {
        # form_of_government(101) vs office_holder(200) — system vs person.
        # English strongly disambiguates: system-words vs person-words.
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
        'ambiguity_note': 'system-of-govt vs leader; disambiged by person-word vs system-word',
    },
}

# ---------------------------------------------------------------------------
# classify one question for a concept
#   returns (slot_chosen, has_disambig_signal, hard_ambiguity, soft_ambiguity)
# ---------------------------------------------------------------------------
def classify_concept(rels, q):
    ql = (q or '').lower()
    for slot, (kws, disambig) in CONCEPTS_SLOTS.items():
        if any(any(k in r for k in kws) for r in rels):
            chosen = slot
            # does the question carry a slot-specific disambig word?
            has_kw = any(d in ql for d in disambig)
            return slot, has_kw
    return None, False

# flatten slot matchers once
CONCEPTS_SLOTS = {}
for cname, cdef in CONCEPTS.items():
    for slot, (kws, disambig) in cdef['slots'].items():
        CONCEPTS_SLOTS[slot] = (kws, disambig)

# also keep concept->slots mapping for reporting
SLOT_TO_CONCEPT = {}
for cname, cdef in CONCEPTS.items():
    for slot in cdef['slots']:
        SLOT_TO_CONCEPT[slot] = cname

# ---------------------------------------------------------------------------
# HIDDEN-CRITERION detection (reused logic from catalog_implicit_constraints.py)
# ---------------------------------------------------------------------------
def years_in(q):
    return set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', q or ''))

def hidden_time(s, q):
    """dateTime literal whose year is NOT in the question and no now/current word."""
    d = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s or '')
    if not d:
        return False
    date_years = set(dd[:4] for dd in d)
    q_years = years_in(q)
    has_word = any(k in (q or '').lower() for k in
                   ('current', ' now', 'latest', 'last ', 'most recent', 'recent',
                    'currently'))
    return not (date_years & q_years) and not has_word

def has_not_exists(s):
    U = (s or '').upper()
    return 'NOT EXISTS' in U or 'not exists' in (s or '')

# ---------------------------------------------------------------------------
# main scan
# ---------------------------------------------------------------------------
rows = []  # one per case, with flags
for x in SP:
    s = x.get('sparql') or ''
    q = x.get('question') or ''
    cid = x['ID']
    rels = answer_rels(s)
    g = GOLD.get(cid, {})
    gold = g.get('a_entity') or []
    gold_n = len([a for a in gold if str(a).strip()])

    rec = dict(id=cid, q=q, rels=rels, gold_n=gold_n,
               gold=gold, multi_slot={}, hidden={})

    # --- multi-slot concept scan ---
    for cname, cdef in CONCEPTS.items():
        # which slot did this case pick (if any)?
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
        ql = q.lower()
        # does the question carry the keyword for the PICKED slot?
        picked_kws = cdef['slots'][picked][1]
        picked_signal = any(d in ql for d in picked_kws)
        # does it carry a keyword for a DIFFERENT slot (conflicting signal)?
        other_kws = []
        for slot, (_, disambig) in cdef['slots'].items():
            if slot != picked:
                other_kws += disambig
        other_signal = any(d in ql for d in other_kws)
        # grade: picked-signal present => disambiguated. none present => hard.
        #        only other-signal => soft (text points a different way).
        if picked_signal:
            grade = 'disambig'
        elif other_signal:
            grade = 'soft'   # text has a competing slot cue
        else:
            grade = 'hard'   # no slot keyword at all
        rec['multi_slot'][cname] = dict(
            slot=picked, n_slots=n_slots,
            grade=grade, hard=(grade == 'hard'),
            has_soft=(grade == 'soft'), has_strong=(grade == 'disambig'))

    # --- hidden-criterion scan ---
    if hidden_time(s, q):
        rec['hidden']['hidden_time'] = True
    if has_not_exists(s):
        rec['hidden']['not_exists'] = True

    rows.append(rec)

# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def line(c='='): print(c * 78)

line()
print(f"CWQ TEST SET ANNOTATION-AMBIGUITY SCREEN  (N = {N} cases)")
line()

# ---- A. multi-slot ambiguity per concept ----
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
hard_irred_ids = set()   # hard AND picked minority slot  -> true irreducible
hard_default_ids = set() # hard AND picked majority slot -> defaultable
for cname, cdef in CONCEPTS.items():
    cases = [r for r in rows if cname in r['multi_slot']]
    if not cases:
        continue
    # slot distribution
    slot_dist = Counter(r['multi_slot'][cname]['slot'] for r in cases)
    n_slots = len(cdef['slots'])
    majority_slot, majority_n = slot_dist.most_common(1)[0]
    majority_pct = 100 * majority_n / len(cases)
    hard = [r for r in cases if r['multi_slot'][cname]['hard']]
    soft = [r for r in cases if r['multi_slot'][cname]['has_soft']
            and not r['multi_slot'][cname]['has_strong']]
    disambig = [r for r in cases if r['multi_slot'][cname]['has_strong']]
    # split hard into minority-pick (irreducible) vs majority-pick (defaultable)
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

# ---- B. hidden-criterion ambiguity ----
print("\n[B] HIDDEN-CRITERION AMBIGUITY  (criterion in SPARQL, not in English)")
print("-" * 78)
ht_ids = {r['id'] for r in rows if r['hidden'].get('hidden_time')}
ne_ids = {r['id'] for r in rows if r['hidden'].get('not_exists')}
print(f"  hidden-time (dateTime yr not in Q, no now/current word) : {len(ht_ids):>5}  "
      f"({100*len(ht_ids)/N:.1f}%)")
print(f"  NOT-EXISTS clause (data-completeness artifact)          : {len(ne_ids):>5}  "
      f"({100*len(ne_ids)/N:.1f}%)")
hidden_ids = ht_ids | ne_ids

# ---- C. totals ----
line()
print("[C] TOTALS")
line()
all_amb_ids = amb_case_ids | hidden_ids
hard_total = hard_amb_ids | ht_ids | ne_ids      # hard = multi-slot-hard OR hidden
soft_total = soft_amb_ids                        # soft = multi-slot-soft only
# (hidden criteria have no 'soft' grade; they are all hard by construction)
print(f"  multi-slot ambiguity cases (hard or soft): {len(amb_case_ids):>5}  "
      f"({100*len(amb_case_ids)/N:.1f}%)")
print(f"     - hard (no disambig signal)           : {len(hard_amb_ids):>5}  "
      f"({100*len(hard_amb_ids)/N:.1f}%)")
print(f"     - soft (weak cue only)                 : {len(soft_amb_ids):>5}  "
      f"({100*len(soft_amb_ids)/N:.1f}%)")
print(f"  hidden-criterion cases                    : {len(hidden_ids):>5}  "
      f"({100*len(hidden_ids)/N:.1f}%)")
print(f"  UNION (all potential ambiguity)           : {len(all_amb_ids):>5}  "
      f"({100*len(all_amb_ids)/N:.1f}%)")
print(f"  HARD grade (hard multi-slot U hidden)     : {len(hard_total):>5}  "
      f"({100*len(hard_total)/N:.1f}%)")
print(f"  SOFT grade (soft multi-slot only)         : {len(soft_total):>5}  "
      f"({100*len(soft_total)/N:.1f}%)")
overlap = hard_amb_ids & (ht_ids | ne_ids)
print(f"  (overlap: multi-slot AND hidden)          : {len(overlap):>5}")

# ---- D. representative cases per top concept ----
print("\n[D] REPRESENTATIVE HARD-AMBIGUITY CASES per concept")
print("-" * 78)
for cs in sorted(concept_summary, key=lambda c: -c['hard']):
    if cs['hard'] == 0:
        continue
    cname = cs['concept']
    hard_cases = [r for r in rows if cname in r['multi_slot']
                  and r['multi_slot'][cname]['hard']]
    print(f"\n  ## {cname}  (hard={cs['hard']}, "
          f"majority={cs['majority_slot']} {cs['majority_pct']:.0f}%)")
    # show a few majority-slot + a few minority-slot (the surprise ones)
    minority_slots = [s for s in cs['slot_dist'] if s != cs['majority_slot']]
    shown = 0
    for r in hard_cases:
        if r['multi_slot'][cname]['slot'] != cs['majority_slot'] and shown < 2:
            print(f"     [MINORITY {r['multi_slot'][cname]['slot']}] "
                  f"|G|={r['gold_n']} {r['id'].split('_')[0]}")
            print(f"        Q: {r['q'][:78]}")
            print(f"        GOLD: {r['gold'][:5]}")
            shown += 1
    shown = 0
    for r in hard_cases:
        if r['multi_slot'][cname]['slot'] == cs['majority_slot'] and shown < 3:
            print(f"     [{cs['majority_slot']}] "
                  f"|G|={r['gold_n']} {r['id'].split('_')[0]}")
            print(f"        Q: {r['q'][:78]}")
            print(f"        GOLD: {r['gold'][:5]}")
            shown += 1

# ---- E. optimizability ----
print("\n[E] OPTIMIZABILITY  (irreducible vs defaultable)")
print("-" * 88)
print(f"{'concept':16} {'majSlot':22} {'maj%':>5} | {'hard->min':>9} {'hard->maj':>9}  verdict")
print("-" * 88)
for cs in sorted(concept_summary, key=lambda c: -c['hard_minority']):
    # irreducible = minority-slot hard cases (gold picked the surprising reading, no text signal)
    # defaultable  = majority-slot hard cases (default->majority recovers them)
    if cs['hard_minority'] == 0 and cs['majority_pct'] >= 80:
        verdict = 'DEFAULTABLE (no minority surprises; default wins)'
    elif cs['hard_minority'] > 0 and cs['majority_pct'] >= 80:
        verdict = f'MOSTLY-DEFAULTABLE (but {cs["hard_minority"]} irreducible minority)'
    elif cs['majority_pct'] < 65:
        verdict = 'IRREDUCIBLE (no dominant slot; needs text/world knowledge)'
    else:
        verdict = 'WEAK-DEFAULT (risky)'
    print(f"{cs['concept']:16} {cs['majority_slot']:22} {cs['majority_pct']:>4.0f}% | "
          f"{cs['hard_minority']:>9} {cs['hard_majority']:>9}  {verdict}")

print("\n  NOTE: 'hard->min' (minority-slot, no keyword) = TRUE irreducible annotation")
print("  ambiguity. 'hard->maj' is recoverable by defaulting to the majority slot.")

# ---- F1 ceiling rough estimate ----
line()
print("[F] F1-CEILING ROUGH ESTIMATE")
line()
# The honest ceiling loss = irreducible multi-slot + hidden-time (genuine invisible).
# NOT-EXISTS is a SPARQL-completeness artifact (counts separately, model-side not label-side).
# defaultable majority-slot cases do NOT lower the ceiling (model can guess majority).
genuine_irred = hard_irred_ids | ht_ids
print(f"  TRUE irreducible label ambiguity (hard-minority U hidden-time) : "
      f"{len(genuine_irred):>4}  ({100*len(genuine_irred)/N:.1f}%)")
print(f"     - multi-slot minority-slot, no keyword (surprise reading)  : "
      f"{len(hard_irred_ids):>4}")
print(f"     - hidden-time ('now' date invisible in English)            : "
      f"{len(ht_ids):>4}")
print(f"  Defaultable (majority-slot, optimizable by defaulting)        : "
      f"{len(hard_default_ids):>4}  ({100*len(hard_default_ids)/N:.1f}%)")
print(f"  NOT-EXISTS artifact (SPARQL completeness, separate concern)   : "
      f"{len(ne_ids):>4}  ({100*len(ne_ids)/N:.1f}%)")
print()
print(f"  -> F1 ceiling loss from GENUINE annotation ambiguity ~= "
      f"{100*len(genuine_irred)/N:.1f}% of cases.")
print(f"     If those cases fully miss, F1 upper bound ~ "
      f"{100 - 100*len(genuine_irred)/N:.1f}%. Real impact is smaller: some")
print(f"     minority-slot cases still match by partial overlap, and defaultable")
print(f"     cases are recoverable. So annotation ambiguity sets a soft ceiling")
print(f"     in the low-single-digit F1 range, NOT a hard blocker.")

# dump JSON
out = dict(N=N, concept_summary=concept_summary,
           hard_ambiguity_ids=sorted(hard_amb_ids),
           soft_ambiguity_ids=sorted(soft_amb_ids),
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
               soft_grade=len(soft_total),
               genuine_irreducible=len(genuine_irred)),
           hard_irreducible_ids=sorted(hard_irred_ids),
           hard_defaultable_ids=sorted(hard_default_ids))
os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
with open(os.path.join(ROOT, 'reports/ambiguity_cases.json'), 'w') as f:
    json.dump(out, f, indent=2)
print(f"\n[dumped reports/ambiguity_cases.json]")
