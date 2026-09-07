#!/usr/bin/env python3
"""Repair v3 — SPARQL-driven CVT-attribute flooding (strategy A).

Combines the precision of SPARQL-driven repair with the "presence over
precision" principle that fixes the 1.799999 problem:

1. Parse gold SPARQL → identify the CVT property TYPES it needs
   (e.g. measurement_unit.dated_percentage.rate, sports_team_roster.from,
    topic_server.population_number, career_start).
2. For each TYPE, find ALL nodes in the subgraph whose edges use that TYPE's
   parent (e.g. every CVT reachable via *_percent / cpi_inflation / any
   dated_percentage parent), and flood THEIR values from Virtuoso.
   → "presence": the gold value (1.799999) lands in the subgraph along with
     its siblings, so the model can reason "≈1.8" instead of being asked to
     match a literal the dump stored at different float precision.
3. Bug-1 fix (soft types) from v2 is applied first so the SELECT returns rows
   for the typed-literal cases (Boston career_start "2005").

This is precision (only gold-relevant CVT types, not all dated_*) + presence
(all values of that type, not just gold's exact match).

Run:
  python scripts/repair_v3.py --dataset cwq_test --limit 50   # smoke
  python scripts/repair_v3.py --dataset cwq_train             # full
"""
import argparse, os, pickle, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import sparql_query, resolve_names, get_name
from repair_v2 import to_select_star_v2, repair_case_v2

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

# measurement_unit CVT parent → its value-attribute predicates
# (a "dated_percentage" CVT carries .rate + .date; a "dated_integer" carries .number + .year)
MU_PARENTS = {
    "dated_percentage": ["measurement_unit.dated_percentage.rate", "measurement_unit.dated_percentage.date"],
    "dated_integer":    ["measurement_unit.dated_integer.number", "measurement_unit.dated_integer.year"],
    "dated_metric_ton": ["measurement_unit.dated_metric_ton.number", "measurement_unit.dated_metric_ton.date"],
    "dated_money_value":["measurement_unit.dated_money_value.amount", "measurement_unit.dated_money_value.valid_date"],
    "dated_float":      ["measurement_unit.dated_float.number", "measurement_unit.dated_float.date"],
    "dated_index_value":["measurement_unit.dated_index_value.index", "measurement_unit.dated_index_value.date"],
    "dated_cubic_meters":["measurement_unit.dated_cubic_meters.cubic_meters", "measurement_unit.dated_cubic_meters.date"],
    "dated_kgoe":       ["measurement_unit.dated_kgoe.number", "measurement_unit.dated_kgoe.date"],
    "dated_days":       ["measurement_unit.dated_days.days", "measurement_unit.dated_days.date"],
}
# value-attr relations that are LEAF (not measurement_unit): roster from/to, career_start, population, etc.
LEAF_VALUE_RELS = [
    "sports.sports_team_roster.from", "sports.sports_team_roster.to", "sports.sports_team_roster.number",
    "sports.pro_sports_played.career_start",
    "government.government_position_held.from", "government.government_position_held.to",
    "topic_server.population_number",
    "time.event.start_date", "time.event.end_date",
]


def sparql_value_types(sparql):
    """Extract from gold SPARQL the set of value-attribute predicates AND the
    measurement_unit parent types it touches."""
    preds = set(re.findall(r"ns:([\w.]+)", sparql))
    mu_parents = set()
    leaf_rels = set()
    for p in preds:
        m = re.match(r"measurement_unit\.(dated_\w+)\.", p)
        if m and m.group(1) in MU_PARENTS:
            mu_parents.add(m.group(1))
        # also: if SPARQL touches a *_percent / cpi_inflation / population CVT-relation,
        # the underlying CVT is dated_percentage / dated_integer → add the parent
        if re.search(r"(percent|cpi_inflation|unemployment|gdp_growth)", p):
            mu_parents.add("dated_percentage")
        if re.search(r"(population|number_of)", p):
            mu_parents.add("dated_integer")
    for r in LEAF_VALUE_RELS:
        if r in sparql:
            leaf_rels.add(r)
    return mu_parents, leaf_rels


def flood_value_attrs(rec, mu_parents, leaf_rels, max_cvt=300):
    """For the given CVT types, flood their value-attrs into rec. Returns n_new."""
    if not mu_parents and not leaf_rels:
        return 0
    te = rec["text_entity_list"]; nte = rec["non_text_entity_list"]
    rels = rec["relation_list"]; h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    node_idx = {n: i for i, n in enumerate(nodes)}
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing = set(zip(h, r, t))

    # target predicates to flood
    target_preds = []
    for mu in mu_parents:
        target_preds.extend(MU_PARENTS.get(mu, []))
    target_preds.extend(leaf_rels)
    if not target_preds:
        return 0
    target_set = set(target_preds)

    # collect CVT-like nodes (cap to bound work)
    cvt_nodes = [n for n in nte if re.match(r"^(g\.|m\.[0-9a-z])", str(n)) and " " not in str(n) and len(str(n)) < 40]
    cvt_nodes = list(dict.fromkeys(cvt_nodes))[:max_cvt]
    if not cvt_nodes:
        return 0

    new_tris = []; n_new = 0
    BATCH = 80
    for i in range(0, len(cvt_nodes), BATCH):
        chunk = cvt_nodes[i:i+BATCH]
        vals = " ".join("ns:%s" % c for c in chunk)
        q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
             "SELECT ?s ?p ?o WHERE { VALUES ?s { %s } ?s ?p ?o . FILTER(isLiteral(?o)) } LIMIT 4000" % vals)
        try:
            rows = sparql_query(q, timeout=45)
        except Exception:
            rows = []
        for b in rows:
            s = b["s"]["value"]; s_mid = s.split("/ns/")[-1] if "/ns/" in s else s
            p = b["p"]["value"]; p_local = p.split("/ns/")[-1] if "/ns/" in p else p
            if p_local not in target_set:
                continue
            o_val = b["o"]["value"]
            if re.match(r"^-?\d+\.\d{6,}$", o_val):
                o_val = str(round(float(o_val), 4))
            hi = node_idx.get(s_mid)
            if hi is None:
                nte.append(s_mid); hi = len(te) + len(nte) - 1; node_idx[s_mid] = hi
            if o_val not in node_idx:
                nte.append(o_val); node_idx[o_val] = len(te) + len(nte) - 1
            ti = node_idx[o_val]
            if p_local not in rel_idx:
                rels.append(p_local); rel_idx[p_local] = len(rels) - 1
            ri = rel_idx[p_local]
            if (hi, ri, ti) in existing:
                continue
            existing.add((hi, ri, ti)); new_tris.append((hi, ri, ti)); n_new += 1

    h.extend([x[0] for x in new_tris]); r.extend([x[1] for x in new_tris]); t.extend([x[2] for x in new_tris])
    rec["text_entity_list"] = te; rec["non_text_entity_list"] = nte
    rec["relation_list"] = rels
    rec["h_id_list"] = h; rec["r_id_list"] = r; rec["t_id_list"] = t
    return n_new


def repair_case_v3(rec, gold_sparql, verbose=False):
    """v2 (soft-type materialize) + v3 (CVT-attr flooding for SPARQL value-types)."""
    n1 = repair_case_v2(rec, gold_sparql, verbose=verbose)
    mu_parents, leaf_rels = sparql_value_types(gold_sparql)
    if verbose:
        print(f"  [v3] value-types: mu_parents={mu_parents} leaf_rels={leaf_rels}")
    n2 = flood_value_attrs(rec, mu_parents, leaf_rels)
    return {"n_v2": n1.get("n_new", 0), "n_v3_cvt": n2, "n_new": n1.get("n_new", 0) + n2}


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
    raw = json_load = __import__("json").load(open(os.path.join(ROOT, sq_path)))
    if fmt == "list":
        sq_map = {d["ID"]: d["sparql"] for d in raw}
    elif fmt == "webqsp":
        sq_map = {q["QuestionId"]: (q.get("Parses",[{}])[0].get("Sparql","")) for q in raw.get("Questions",[])}
    else:
        sq_map = {k: (v["sparql"] if isinstance(v, dict) else v) for k, v in raw.items()}

    id_filter = [x.strip() for x in args.ids.split(",")] if args.ids else None
    if args.limit: recs = recs[:args.limit]
    total_v2 = total_v3 = 0; n_changed = 0; n_done = 0
    for rec in recs:
        cid = rec.get("id", "")
        if id_filter and not any(cid.startswith(p) for p in id_filter):
            continue
        sq = next((v for k, v in sq_map.items() if k.startswith(cid.rsplit("_", 1)[0])), "")
        if not sq: continue
        n_done += 1
        before = len(rec["h_id_list"])
        try:
            stats = repair_case_v3(rec, sq, verbose=args.verbose)
        except Exception as e:
            if args.verbose: print(f"  {cid[:24]} ERR {e}")
            stats = {"n_new": 0}
        added = len(rec["h_id_list"]) - before
        total_v2 += stats.get("n_v2", 0); total_v3 += stats.get("n_v3_cvt", 0)
        if added: n_changed += 1
        if args.verbose and added:
            print(f"{cid[:30]:30} v2=+{stats.get('n_v2',0):3} v3_cvt=+{stats.get('n_v3_cvt',0):4}")
        if n_done % 200 == 0:
            print(f"  ...{n_done} done, {n_changed} changed", flush=True)
    print(f"\n=== {args.dataset} v3: {n_done} cases, {n_changed} changed (+{n_changed/max(n_done,1)*100:.0f}%), v2=+{total_v2} cvt=+{total_v3} ===")
    if args.out:
        pickle.dump(recs, open(args.out, "wb")); print(f"  → {args.out}")
