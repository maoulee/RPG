"""Scan exclusive (time-bound) relations: how is time resolved when 题干 gives no explicit date?

For government_position_held (leader/governor/president), classify each test case by:
  - date-filter shape in SPARQL: SINGLE-DATE (= "now"/current), RANGE, NONE
  - the "now" date value used (is it always ~2015?)
  - question phrasing: tense (is/was), number (the/X vs Xs), "current"/"now"
  - gold cardinality
Question the user asks: does "unspecified time → latest" hold, or are there exceptions
(no-time but full set / no-time but a non-latest holder)?
"""
import json, re
from collections import Counter

sp = json.load(open('data/cwq_sparql/test.json'))

def date_shape(s):
    """Classify the date filter on the position_held CVT."""
    s = s or ''
    # actual CWQ datetime literal format: "2015-08-10"^^xsd:dateTime
    dts = re.findall(r'"([^"]+)"\^\^xsd:dateTime', s)
    has_fromto = bool(re.search(r'government_position_held\.(from|to)', s))
    if not has_fromto:
        return ('no-date-attr', dts)
    if not dts:
        return ('has-attr-no-filter', dts)
    dates = sorted(set(d[:10] for d in dts))
    # point-in-time: a single date D with from<=D AND to>=D (the "as of now" pattern)
    has_from_le = bool(re.search(r'\.from\b[^;]*<=', s))
    has_to_ge = bool(re.search(r'\.to\b[^;]*>=', s))
    if len(dates) == 1 and has_from_le and has_to_ge:
        return ('point-in-time', dates)
    if has_from_le or has_to_ge:
        return ('filtered-range', dates)
    return ('filtered-other', dates)

rows = []
for x in sp:
    s = x.get('sparql') or ''
    if 'government_position_held' not in s:
        continue
    q = x.get('question') or ''
    shape, dates = date_shape(s)
    # tense / number cues
    ql = q.lower()
    present = bool(re.search(r'\bis\s+(the|a|our|its)\s', ql)) or 'current' in ql or ' now' in ql
    past = bool(re.search(r'\bwas\s+(the|a|our|its)\s', ql))
    plural = bool(re.search(r'\b(leaders|governors|presidents|officials|rulers|heads)\b', ql))
    gold_n = '?'  # we don't have gold from sparql alone; mark cardinality proxy via LIMIT/DISTINCT
    has_limit = 'LIMIT' in s.upper()
    rows.append(dict(id=x['ID'].split('_')[0], q=q, shape=shape, dates=dates,
                     present=present, past=past, plural=plural, limit=has_limit))

print(f"=== government_position_held cases: {len(rows)} ===\n")
print("date-filter shape distribution:")
shc = Counter(r['shape'] for r in rows)
for k,v in shc.most_common():
    print(f"  {k:20} {v}")

# the "now" date values used in SINGLE-DATE / filtered cases
print("\ndatetime literals used (top 15):")
dtc = Counter()
for r in rows:
    for d in r['dates']:
        dtc[d[:10]] += 1
for d,c in dtc.most_common(15):
    print(f"  {d}  x{c}")

# breakdown: phrasing × shape
print("\n=== phrasing × date-shape ===")
print(f"{'':28} {'filtered':>9} {'no-date-attr':>13} {'has-attr-no-filter':>19}")
for label, key in [('present (is/current/now)','present'), ('past (was)','past'),
                   ('plural (governors/leaders)','plural')]:
    cnt = Counter(r['shape'] for r in rows if r[key])
    print(f"{label:28} {cnt.get('filtered',0):>9} {cnt.get('no-date-attr',0):>13} {cnt.get('has-attr-no-filter',0):>19}")

# EXCEPTIONS the user cares about: present-tense but NOT a single-date filter (i.e. "is the X" but returns full set)
print("\n=== EXCEPTION candidates: present-tense / 'current' but NOT point-in-time filter ===")
exc = [r for r in rows if (r['present'] and r['shape']!='filtered')]
print(f"count: {len(exc)} / {sum(1 for r in rows if r['present'])} present-tense cases")
for r in exc[:12]:
    print(f"  [{r['shape']}] {r['id']}  Q={r['q'][:80]}")

# also: no-time-attr at all (relation returned raw) — are these full-set "default"?
print("\n=== no-date-attr cases (CVT has no from/to used) — full set? ===")
nda = [r for r in rows if r['shape']=='no-date-attr']
for r in nda[:12]:
    print(f"  plural={r['plural']} past={r['past']}  {r['id']}  Q={r['q'][:75]}")
