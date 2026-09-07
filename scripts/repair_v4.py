#!/usr/bin/env python3
"""Repair v4 — SPARQL-filter attribute recall on candidate entities.

The user's precise insight: RoG subgraphs keep the candidate entities (e.g.
Portuguese-speaking countries) but DROP the value dimension of filter
attributes (child_labor rate, population, roster.from). Fix:

1. Parse gold SPARQL → extract the VALUE-attribute predicates in FILTER
   conditions (dated_percentage.rate, roster.from, population_number...).
   These are the attributes the question constrains on.
2. Find the CANDIDATE ENTITIES — entities in the subgraph connected to that
   attribute (or, for CVT-mediated attrs, the entities whose CVTs carry it).
   Also resolve candidates named in the SPARQL via the subgraph.
3. For each candidate, recall ALL values of that attribute from Virtuoso
   (no exact match, no min/max sort — just PRESENCE). Add as triples.
4. The model then reasons which value satisfies the constraint.

This is precise (only the SPARQL-filtered attribute, not all dated_*) +
presence-oriented (all candidate values, not gold's exact match).

Run:
  python scripts/repair_v4.py --dataset cwq_test --limit 100   # smoke
  python scripts/repair_v4.py --dataset cwq_train --out ...
"""
import argparse, os, pickle, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import sparql_query
from repair_v2 import to_select_star_v2, repair_case_v2  # Bug-1 fix reuse

ROOT = "/zhaoshu/subgraph"
DATASETS = {
    "cwq_test":  ("data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl",
                  "data/cwq_sparql/test.json", "list"),
    "cwq_train": ("data/cwq_processed/train_rog.pkl",
                  "data/cwq_sparql_full/train.json", "dict"),
    "webqsp_test": ("data/webqsp/test_fixed_path_completed.pkl",
                    "data/webqsp/WebQSP.test.json", "webqsp"),
    "webqsp_train": ("data/webqsp/train_rog.pkl",
                     "data/webqsp/WebQSP.train.sparql.json", "dict"),
}

# value-attribute predicates that appear in FILTERs (leaf + CVT-mediated)
# For CVT-mediated (measurement_unit.*, the CVT carries the value attrs)
MU_VALUE_ATTRS = {
    "measurement_unit.dated_percentage": ["measurement_unit.dated_percentage.rate", "measurement_unit.dated_percentage.date"],
    "measurement_unit.dated_integer":    ["measurement_unit.dated_integer.number", "measurement_unit.dated_integer.year"],
    "measurement_unit.dated_metric_ton": ["measurement_unit.dated_metric_ton.number", "measurement_unit.dated_metric_ton.date"],
    "measurement_unit.dated_money_value":["measurement_unit.dated_money_value.amount", "measurement_unit.dated_money_value.valid_date"],
    "measurement_unit.dated_float":      ["measurement_unit.dated_float.number", "measurement_unit.dated_float.date"],
    "measurement_unit.dated_index_value":["measurement_unit.dated_index_value.index", "measurement_unit.dated_index_value.date"],
}
# map: a statistical_region-style relation → its CVT's measurement_unit parent
# e.g. location.statistical_region.child_labor_percent → CVT is dated_percentage
REL_TO_MU = {
    "cpi_inflation": "measurement_unit.dated_percentage",
    "child_labor_percent": "measurement_unit.dated_percentage",
    "unemployment_rate": "measurement_unit.dated_percentage",
    "gdp_growth": "measurement_unit.dated_percentage",
    "population": "measurement_unit.dated_integer",
    "co2_emissions_per_capita": "measurement_unit.dated_metric_ton",
    "internet_users_percent": "measurement_unit.dated_percentage",
}
# leaf value predicates (value directly on subject, no CVT)
LEAF_VALUE_RELS = [
    "sports.sports_team_roster.from", "sports.sports_team_roster.to", "sports.sports_team_roster.number",
    "sports.pro_sports_played.career_start",
    "government.government_position_held.from", "government.government_position_held.to",
    "topic_server.population_number",
    "time.event.start_date", "time.event.end_date",
]


def extract_filter_attrs(sparql):
    """Return (cv_attr_sets, leaf_rels):
       cv_attr_sets: list of (entity_rel, mu_value_attrs) — for CVT-mediated attrs,
                      the entity→CVT relation + the CVT's value predicates to recall.
       leaf_rels: set of leaf value predicates to recall on candidate subjects."""
    cv_attr_sets = []
    leaf_rels = set()
    preds = set(re.findall(r"ns:([\w.]+)", sparql))
    for p in preds:
        # CVT-mediated: location.statistical_region.X → dated_Y
        for rel_key, mu_parent in REL_TO_MU.items():
            if rel_key in p and mu_parent in MU_VALUE_ATTRS:
                cv_attr_sets.append((p, MU_VALUE_ATTRS[mu_parent]))
                break
        else:
            # direct measurement_unit predicate
            for mu_parent, attrs in MU_VALUE_ATTRS.items():
                if p.startswith(mu_parent + "."):
                    cv_attr_sets.append((mu_parent, attrs))
                    break
        # leaf
        if p in LEAF_VALUE_RELS:
            leaf_rels.add(p)
        # roster/gov from/to detection by suffix
        if re.search(r"\.(from|to)$", p) and ("roster" in p or "government_position" in p or "pro_sports_played" in p):
            leaf_rels.add(p)
    return cv_attr_sets, leaf_rels


def _normalize(v):
    if re.match(r"^-?\d+\.\d{6,}$", v):
        return str(round(float(v), 4))
    return v


def recall_filter_attrs(rec, cv_attr_sets, leaf_rels, verbose=False):
    """Recall filter-attr values for candidate entities in subgraph."""
    if not cv_attr_sets and not leaf_rels:
        return 0
    te = rec["text_entity_list"]; nte = rec["non_text_entity_list"]
    rels = rec["relation_list"]; h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    node_idx = {n: i for i, n in enumerate(nodes)}
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing = set(zip(h, r, t))
    new_tris = []

    edges = list(zip(h, r, t))
    # For CVT-mediated attrs: find CVT nodes the candidate entities point to via the entity_rel,
    # then recall the CVT's value attrs.
    cvt_nodes_to_query = set()   # (cvt_mid, [value_attr_preds])
    for entity_rel, value_attrs in cv_attr_sets:
        # find subgraph edges whose relation matches entity_rel (by substring)
        for hh, rr, tt in edges:
            rn = str(rels[rr])
            if entity_rel.split(".")[-1] in rn or entity_rel in rn:
                # tail is a CVT node (g.* or m.*)
                tail = nodes[tt]
                if re.match(r"^(g\.|m\.[0-9a-z])", str(tail)) and " " not in str(tail):
                    cvt_nodes_to_query.add((str(tail), tuple(value_attrs)))
    # For leaf attrs: find candidate subjects (entities that have any roster/gov/career edge,
    # or are named in the question). Recall the leaf attr on them directly.
    leaf_subjects = set()
    if leaf_rels:
        # candidate subjects = entities that appear as head of roster/government/sports edges
        for hh, rr, tt in edges:
            rn = str(rels[rr]).lower()
            if any(k in rn for k in ["roster.player", "pro_athlete", "government_position", "politician", "office_holder"]):
                # this entity is a candidate (player/office-holder)
                head = nodes[hh]
                if not re.match(r"^(g\.|m\.[0-9a-z])", str(head)) or " " in str(head):
                    leaf_subjects.add(str(head))

    n_new = 0
    # query CVT value attrs (batch)
    cvt_list = list(cvt_nodes_to_query)
    BATCH = 80
    for i in range(0, len(cvt_list), BATCH):
        chunk = cvt_list[i:i+BATCH]
        vals = " ".join("ns:%s" % c[0] for c in chunk)
        # union of value attrs across the chunk
        all_attrs = set()
        for _, attrs in chunk: all_attrs.update(attrs)
        attr_filter = " || ".join("?p = ns:%s" % a for a in all_attrs)
        q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\nSELECT ?s ?p ?o WHERE { VALUES ?s { %s } ?s ?p ?o . FILTER(%s) } LIMIT 3000"
             % (vals, attr_filter))
        try:
            rows = sparql_query(q, timeout=45)
        except Exception:
            rows = []
        for b in rows:
            s_mid = b["s"]["value"].split("/ns/")[-1]
            p_local = b["p"]["value"].split("/ns/")[-1]
            o_val = _normalize(b["o"]["value"])
            hi = node_idx.get(s_mid)
            if hi is None:
                nte.append(s_mid); hi = len(te)+len(nte)-1; node_idx[s_mid]=hi
            if o_val not in node_idx:
                nte.append(o_val); node_idx[o_val]=len(te)+len(nte)-1
            ti = node_idx[o_val]
            if p_local not in rel_idx: rels.append(p_local); rel_idx[p_local]=len(rels)-1
            ri = rel_idx[p_local]
            if (hi,ri,ti) in existing: continue
            existing.add((hi,ri,ti)); new_tris.append((hi,ri,ti)); n_new += 1

    # query leaf attrs on candidate subjects
    if leaf_rels and leaf_subjects:
        # need MIDs for subjects — resolve via subgraph (subjects are names; find their MID if in nte)
        # Simpler: query dump by name → mid, then query leaf rel. But batch by mid if available.
        # Many leaf subjects are names in te; their MIDs may not be in subgraph. Query dump directly.
        subj_mids = []
        for name in list(leaf_subjects)[:60]:
            # find mid in nte matching this name? names are in te, mids in nte — no direct link.
            # Use dump name→mid lookup.
            qn = 'PREFIX ns:<http://rdf.freebase.com/ns/> SELECT ?s WHERE { ?s ns:type.object.name "%s"@en } LIMIT 1' % name.replace('"','')
            try:
                r2 = sparql_query(qn, timeout=15)
                if r2:
                    m = r2[0]["s"]["value"].split("/ns/")[-1]
                    if re.match(r"^[mg]\.", m): subj_mids.append(m)
            except Exception: pass
        for lr in leaf_rels:
            BATCH2 = 50
            for i in range(0, len(subj_mids), BATCH2):
                vals = " ".join("ns:%s" % m for m in subj_mids[i:i+BATCH2])
                q = "PREFIX ns:<http://rdf.freebase.com/ns/> SELECT ?s ?o WHERE { VALUES ?s { %s } ?s ns:%s ?o } LIMIT 500" % (vals, lr)
                try:
                    rows = sparql_query(q, timeout=30)
                except Exception: rows=[]
                for b in rows:
                    s_mid = b["s"]["value"].split("/ns/")[-1]
                    o = b["o"]
                    o_val = _normalize(o.get("value",""))
                    hi = node_idx.get(s_mid)
                    if hi is None:
                        nte.append(s_mid); hi=len(te)+len(nte)-1; node_idx[s_mid]=hi
                    if o_val not in node_idx:
                        nte.append(o_val); node_idx[o_val]=len(te)+len(nte)-1
                    ti=node_idx[o_val]
                    if lr not in rel_idx: rels.append(lr); rel_idx[lr]=len(rels)-1
                    ri=rel_idx[lr]
                    if (hi,ri,ti) in existing: continue
                    existing.add((hi,ri,ti)); new_tris.append((hi,ri,ti)); n_new+=1

    h.extend([x[0] for x in new_tris]); r.extend([x[1] for x in new_tris]); t.extend([x[2] for x in new_tris])
    rec["text_entity_list"]=te; rec["non_text_entity_list"]=nte; rec["relation_list"]=rels
    rec["h_id_list"]=h; rec["r_id_list"]=r; rec["t_id_list"]=t
    return n_new


def repair_case_v4(rec, gold_sparql, verbose=False):
    n2 = repair_case_v2(rec, gold_sparql, verbose=verbose)  # Bug-1 soft-type materialize
    cv_attrs, leaf_rels = extract_filter_attrs(gold_sparql)
    if verbose: print(f"  [v4] filter attrs: cv={len(cv_attrs)} leaf={leaf_rels}")
    n4 = recall_filter_attrs(rec, cv_attrs, leaf_rels, verbose=verbose)
    return {"n_v2": n2.get("n_new",0), "n_v4": n4, "n_new": n2.get("n_new",0)+n4}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="cwq_test", choices=list(DATASETS.keys()))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    pkl_path, sq_path, fmt = DATASETS[args.dataset]
    recs = pickle.loads(open(os.path.join(ROOT, pkl_path), "rb").read())
    raw = __import__("json").load(open(os.path.join(ROOT, sq_path)))
    if fmt == "list": sq_map = {d["ID"]: d["sparql"] for d in raw}
    elif fmt == "webqsp": sq_map = {q["QuestionId"]: (q.get("Parses",[{}])[0].get("Sparql","")) for q in raw.get("Questions",[])}
    else: sq_map = {k:(v["sparql"] if isinstance(v,dict) else v) for k,v in raw.items()}

    id_filter = [x.strip() for x in args.ids.split(",")] if args.ids else None
    if args.limit: recs = recs[:args.limit]
    tot2=tot4=0; changed=0; done=0
    for rec in recs:
        cid = rec.get("id","")
        if id_filter and not any(cid.startswith(p) for p in id_filter): continue
        # match SPARQL by LONGEST sparql-id that is a PREFIX of the pkl id (full hash
        # match). The old `cid.rsplit("_",1)[0]` + startswith matched WebQTest-1251 to
        # WebQTest-12_* (90% wrong-match bug). Correct: pkl id starts with sparql id.
        sq = ""
        best_len = -1
        for k, v in sq_map.items():
            if cid.startswith(k) and len(k) > best_len:
                sq = v; best_len = len(k)
        if not sq: continue
        done += 1
        before = len(rec["h_id_list"])
        try: st = repair_case_v4(rec, sq, verbose=args.verbose)
        except Exception as e:
            if args.verbose: print(f"  {cid[:24]} ERR {e}")
            st = {"n_new":0}
        added = len(rec["h_id_list"])-before
        tot2 += st.get("n_v2",0); tot4 += st.get("n_v4",0)
        if added: changed += 1
        if args.verbose and added: print(f"{cid[:30]:30} v2=+{st.get('n_v2',0):3} v4=+{st.get('n_v4',0):4}")
        if done % 200 == 0: print(f"  ...{done} done, {changed} changed", flush=True)
    print(f"\n=== {args.dataset} v4: {done} cases, {changed} changed (+{changed/max(done,1)*100:.0f}%), v2=+{tot2} v4=+{tot4} ===")
    if args.out:
        pickle.dump(recs, open(args.out,"wb")); print(f"  → {args.out}")
