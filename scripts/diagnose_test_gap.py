#!/usr/bin/env python3
"""Diagnose the gold-path gap in a CWQ/WebQSP subgraph pkl vs the gold SPARQL.
For each case: parse the gold SPARQL BGP and check, per gold relation:
  (1) RELATION present: is the relation name in the subgraph's relation_list?
  (2) TRIPLE present: for patterns with a concrete subject MID, does the edge
      (subject, relation) exist in the subgraph? (name-aware: subgraph stores
      named entities by NAME, so we resolve the MID->name and check both.)
Aggregates: case-level missing-relation / missing-triple counts, and the
top missing relations (relation-level vs triple-level).
Usage: python scripts/diagnose_test_gap.py --pkl <pre-repair.pkl> [--compare <post-repair.pkl>]
"""
import argparse, json, os, pickle, re, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import (parse_bgp, pred_local, load_gold_sparql,
                                      resolve_names, get_name, DATASETS)

MID_RE = re.compile(r"^[mg]\.\w")


def diagnose(recs, gold):
    rel_missing_cases = 0          # cases with >=1 gold relation absent from relation_list
    tri_missing_cases = 0          # cases with >=1 concrete-subject gold edge absent
    rel_counter = Counter()        # relation-level absence (per relation, n cases)
    tri_counter = Counter()        # triple-level absence (concrete subj, edge missing)
    rel_present_tri_absent = Counter()   # relation name present but no edge (CVT attr case)
    n_case = 0; n_rel_total = 0; n_tri_total = 0
    case_rel_missing = []

    for r in recs:
        cid = r["id"]
        sq = gold.get(cid)
        if not sq:
            continue
        n_case += 1
        bgp = parse_bgp(sq)
        if not bgp:
            continue
        # batch-resolve names for concrete subject mids in this case
        subj_mids = [s[3:] for (s, p, o) in bgp if s.startswith("ns:") and MID_RE.match(s[3:])]
        if subj_mids:
            resolve_names(subj_mids)
        rels = set(r["relation_list"])
        nodes = r["text_entity_list"] + r["non_text_entity_list"]
        h, rr, t = r["h_id_list"], r["r_id_list"], r["t_id_list"]
        edges = defaultdict(set)
        for i in range(len(h)):
            edges[(nodes[h[i]], r["relation_list"][rr[i]])].add(nodes[t[i]])

        case_rel_miss = 0; case_tri_miss = 0
        for (s, p, o) in bgp:
            pl = pred_local(p)
            if not pl:
                continue
            n_rel_total += 1
            rel_here = pl in rels
            if not rel_here:
                rel_counter[pl] += 1; case_rel_miss += 1
            # triple-level check (concrete subject only)
            if s.startswith("ns:") and MID_RE.match(s[3:]):
                n_tri_total += 1
                sm = s[3:]; name = get_name(sm)
                keys = {sm} | ({name} if name else set())
                edge_here = any(edges.get((k, pl)) for k in keys)
                if not edge_here:
                    tri_counter[pl] += 1; case_tri_miss += 1
                    if rel_here:
                        rel_present_tri_absent[pl] += 1
        if case_rel_miss:
            rel_missing_cases += 1; case_rel_missing.append((cid, case_rel_miss))
        if case_tri_miss:
            tri_missing_cases += 1

    return {
        "n_case": n_case, "n_rel_total": n_rel_total, "n_tri_total": n_tri_total,
        "rel_missing_cases": rel_missing_cases, "tri_missing_cases": tri_missing_cases,
        "rel_counter": rel_counter, "tri_counter": tri_counter,
        "rel_present_tri_absent": rel_present_tri_absent,
    }


def show(label, st):
    nc = st["n_case"]
    print(f"\n========== {label} ==========")
    print(f"cases with SPARQL: {nc}")
    print(f"  RELATION-level: {st['rel_missing_cases']} cases ({100*st['rel_missing_cases']/nc:.1f}%) have >=1 gold relation NAME absent from subgraph")
    print(f"  TRIPLE-level:   {st['tri_missing_cases']} cases ({100*st['tri_missing_cases']/nc:.1f}%) have >=1 gold EDGE absent (concrete subj)")
    print(f"  (total gold relation-slots checked: {st['n_rel_total']}; concrete-subject edge-slots: {st['n_tri_total']})")
    print(f"\n  TOP missing relations (NAME absent, relation-level):")
    for r, c in st["rel_counter"].most_common(15):
        print(f"    {c:4d}  {r}")
    print(f"\n  TOP missing EDGES (concrete subj -> rel, triple-level):")
    for r, c in st["tri_counter"].most_common(15):
        print(f"    {c:4d}  {r}")
    print(f"\n  relation NAME present but EDGE absent (CVT-attribute signature):")
    for r, c in st["rel_present_tri_absent"].most_common(12):
        print(f"    {c:4d}  {r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkl", required=True)
    ap.add_argument("--compare", default="")
    ap.add_argument("--sparql", default="")   # default: CWQ test
    args = ap.parse_args()
    cfg = DATASETS["cwq"]
    sparql_path = args.sparql or cfg["sparql"]
    gold = load_gold_sparql({**cfg, "sparql": sparql_path})
    recs = pickle.load(open(args.pkl, "rb"))
    st = diagnose(recs, gold)
    show(args.pkl, st)
    if args.compare:
        recs2 = pickle.load(open(args.compare, "rb"))
        st2 = diagnose(recs2, gold)
        show(args.compare, st2)


if __name__ == "__main__":
    main()
