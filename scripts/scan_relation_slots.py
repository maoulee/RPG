"""Scan 'implicit relation-slot choice': same English concept maps to multiple
Freebase relations with different breadth (official vs all). The SPARQL picks one;
the model must infer which from context. Generalizes exclusive/accumulative beyond time.
"""
import json, re
from collections import defaultdict

sp = json.load(open('data/cwq_sparql/test.json'))

def answer_rels(s):
    return re.findall(r'ns:([\w.]+)\s+\?x\s*\.', s) + re.findall(r'\?x\s+ns:([\w.]+)\s+', s)

def show_concept(label, keywords):
    print(f"\n=== {label} relation slots ===")
    bucket = defaultdict(list)
    for x in sp:
        s = x.get('sparql') or ''
        for rel in answer_rels(s):
            if any(k in rel.lower() for k in keywords):
                seg = '.'.join(rel.split('.')[-2:])
                bucket[seg].append(x['question'][:58])
    for seg, qs in sorted(bucket.items(), key=lambda kv: -len(kv[1])):
        ex = qs[0] if qs else ''
        print(f"  {seg:40} x{len(qs):<4} e.g. {ex!r}")

show_concept('LANGUAGE', ['language', 'lang'])
show_concept('CURRENCY', ['currency'])
show_concept('GOVERNMENT/FORM', ['government', 'form_of'])
show_concept('BORDER/CONTAIN', ['border', 'contain', 'adjoin', 'nearby'])
show_concept('CAPITAL/SEAT', ['capital', 'seat'])
show_concept('RELIGION', ['religion'])

# Detail: language — show questions split by official vs spoken
print("\n=== LANGUAGE detail: official_language vs languages_spoken ===")
detail = defaultdict(list)
for x in sp:
    s = x.get('sparql') or ''
    rels = answer_rels(s)
    if any('official_language' in r for r in rels):
        detail['official_language'].append(x['question'])
    elif any('languages_spoken' in r for r in rels):
        detail['languages_spoken'].append(x['question'])
for slot, qs in detail.items():
    print(f"\n  [{slot}] x{len(qs)} — sample questions:")
    for q in qs[:5]:
        print(f"     {q[:75]}")
