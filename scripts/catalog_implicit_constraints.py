"""Catalog constraint types across all 3531 test SPARQL, classify each as
EXPLICIT (readable from 题干 English) vs IMPLICIT (only in SPARQL).

The implicit ones are what the model must recover but cannot read from text.
Key implicit suspects:
  - hidden "now" time (dataset ref date, not in 题干)
  - specific type/title mid bindings (题干 uses a vaguer word)
  - NOT EXISTS data-completeness clauses (pure SPARQL artifact)
"""
import json, re
from collections import Counter

sp = json.load(open('data/cwq_sparql/test.json'))

def years_in(q):
    return set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', q or ''))

stats = Counter()
hidden_time_examples = []
implicit_type_examples = []

for x in sp:
    s = x.get('sparql') or ''
    q = x.get('question') or ''
    U = s.upper()
    qy = years_in(q)

    # --- time ---
    dts = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s)
    has_fromto = bool(re.search(r'(from|to|start_date|end_date|\.date)\b', s, re.I))
    date_literals = sorted(set(d[:10] for d in dts))
    if dts:
        # is the date's year mentioned in 题干?
        date_years = set(d[:4] for d in date_literals)
        explicit = bool(date_years & qy) or any(
            kw in q.lower() for kw in ('current','now','latest','last ','most recent','recent'))
        if not explicit:
            stats['time-IMPLICIT(hidden)'] += 1
            if 'government_position' in s and len(hidden_time_examples) < 6:
                hidden_time_examples.append((x['ID'].split('_')[0], q[:70], date_literals))
        else:
            stats['time-explicit'] += 1
    elif has_fromto:
        stats['time-attr-only(no literal)'] += 1

    # --- type/title mid bindings (the answer typed by a specific FB node) ---
    type_rels = re.findall(r'ns:[\w.]+\s+ns:(common.topic.notable_types|government.government_position_held.basic_title|government.government_position_held.office_position_or_title|people.person.profession|people.person.gender|location.location.advertisement_slogans|common.topic.notable_for)\s+ns:m.\w+', s)
    if type_rels:
        stats['type-binding'] += 1

    # --- NOT EXISTS (data-completeness permissive clause) ---
    if 'NOT EXISTS' in U or 'not exists' in s:
        stats['NOT-EXISTS-clause'] += 1

    # --- LIMIT ---
    if 'LIMIT' in U:
        stats['LIMIT'] += 1
    # --- COUNT ---
    if re.search(r'\bCOUNT\s*\(', U):
        stats['COUNT'] += 1
    # --- ORDER BY (ranking/superlative) ---
    if 'ORDER BY' in U:
        stats['ORDER-BY'] += 1
    # --- negation FILTER (?x != entity) ---
    neg = re.findall(r'FILTER\s*\(\s*\?x\s*!=', s)
    if neg:
        stats['negation(!=)'] += 1

print(f"=== constraint catalog across {len(sp)} test SPARQL ===\n")
print(f"{'constraint':28} {'count':>6} {'%':>6}")
for k, v in stats.most_common():
    print(f"{k:28} {v:>6} {100*v/len(sp):>5.1f}%")

print("\n=== time-IMPLICIT (hidden date not in 题干) examples ===")
for cid, q, dl in hidden_time_examples:
    print(f"  {cid} | dates={dl} | Q={q}")

# how many cases have AT LEAST one implicit feature
def hidden_time(s, q):
    d = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s)
    if not d:
        return False
    date_years = set(dd[:4] for dd in d)
    q_years = set(re.findall(r'1[6-9]\d{2}|20\d{2}', q))
    has_word = any(k in q.lower() for k in ('current','now','latest','last ','most recent','recent'))
    return not (date_years & q_years) and not has_word

print("\n=== how many questions carry hidden time / NOT-EXISTS (the truly invisible) ===")
hidden = sum(1 for x in sp if hidden_time(x.get('sparql') or '', x.get('question') or ''))
print(f"hidden-time cases: {hidden} ({100*hidden/len(sp):.1f}%)")
