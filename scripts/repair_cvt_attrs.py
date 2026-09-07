#!/usr/bin/env python3
"""CVT-attribute flooding repair.

Root cause: RoG subgraphs keep CVT mediator nodes (g.*, m.*) but DROP their
value attributes (measurement_unit.dated_percentage.rate/.number, .date,
.from/.to). So a Brazil cpi_inflation edge points to CVT g.1hhc4_7f1, but
the CVT's rate=2075.89 / date=1994 literals are absent → the model can't see
any numeric/time dimension. This is the "有无问题": data EXISTS in the dump,
the CVT node is IN the subgraph, but its values were never extracted.

Strategy (presence over precision): for every CVT-like node already in the
subgraph, query Virtuoso for ALL its measurement_unit.* / .from / .to /
.date / career_start literal attributes, and flood them into the subgraph as
(name_entity --rel--> literal_value) triples. No SPARQL gold-path matching
needed — we don't care WHICH value is gold; we add them ALL and let the
model reason. This fixes CPI 1.799999, population, roster.from, etc. in one
uniform pass.

Run:
  python scripts/repair_cvt_attrs.py --dataset cwq_test --limit 50  # smoke
  python scripts/repair_cvt_attrs.py --dataset cwq_train             # full
"""
import argparse, os, pickle, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import sparql_query, resolve_names, get_name  # reuse noproxy client
from collections import defaultdict

ROOT = "/zhaoshu/subgraph"
DATASETS = {
    "cwq_test":  "data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl",
    "cwq_train": "data/cwq_processed/train_rog.pkl",
    "webqsp_test": "data/webqsp/test_fixed_path_completed.pkl",
    "webqsp_train": "data/webqsp/train_rog.pkl",
}

# value-attribute relations to flood (presence over precision)
# match by suffix on the FULL predicate URI in dump
VALUE_REL_SUFFIXES = (
    ".rate", ".number", ".date", ".initial_date", ".final_date",
    ".from", ".to", ".start", ".end", ".start_date", ".end_date",
    ".career_start", ".career_end", ".population_number", ".capacity",
    ".elevation", ".area", ".gdp_nominal", ".percentage",
)
# CVT-like node patterns (Freebase CVT mids: m. with lowercase hex, g.*, /guid)
def is_cvt_node(name):
    s = str(name)
    return bool(re.match(r"^(g\.[\w]|m\.[0-9a-z]{4,}|m\.0[a-z0-9])", s)) and not " " in s and len(s) < 40


def flood_cvt_for_case(rec, verbose=False):
    """For each CVT-like node in rec's non_text_entity_list, query Virtuoso
    for its value attributes and add them as literal triples."""
    te = rec["text_entity_list"]; nte = rec["non_text_entity_list"]
    rels = rec["relation_list"]
    h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    node_idx = {n: i for i, n in enumerate(nodes)}
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing = set(zip(h, r, t))

    # collect CVT-like nodes (from non_text — g.* and opaque m.*)
    cvt_nodes = [n for n in nte if is_cvt_node(n)]
    if not cvt_nodes:
        return 0
    # dedup, cap per case (some cases have hundreds of CVT nodes)
    cvt_nodes = list(dict.fromkeys(cvt_nodes))[:200]

    n_new = 0
    new_tris = []
    # batch: VALUES query for up to 50 CVT nodes at once, get ALL their literal attrs
    BATCH = 50
    for i in range(0, len(cvt_nodes), BATCH):
        chunk = cvt_nodes[i:i+BATCH]
        vals = " ".join("ns:%s" % c for c in chunk)
        q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
             "SELECT ?s ?p ?o WHERE { VALUES ?s { %s } ?s ?p ?o . FILTER(isLiteral(?o)) } LIMIT 4000"
             % vals)
        try:
            rows = sparql_query(q, timeout=60)
        except Exception:
            rows = []
        for b in rows:
            s = b["s"]["value"]; s_mid = s[len("http://rdf.freebase.com/ns/"):] if s.startswith("http://rdf.freebase.com/ns/") else s
            p = b["p"]["value"]; p_local = p[len("http://rdf.freebase.com/ns/"):] if p.startswith("http://rdf.freebase.com/ns/") else p
            o_val = b["o"]["value"]
            # only value-attribute predicates (skip type/name etc.)
            if not any(p_local.endswith(suf) or suf in p_local for suf in VALUE_REL_SUFFIXES):
                continue
            # truncate absurd floats (2075.889892578125 -> 2075.89) for readability
            if re.match(r"^-?\d+\.\d{6,}$", o_val):
                o_val = str(round(float(o_val), 4))
            # node slots
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

    h.extend([x[0] for x in new_tris])
    r.extend([x[1] for x in new_tris])
    t.extend([x[2] for x in new_tris])
    rec["text_entity_list"] = te; rec["non_text_entity_list"] = nte
    rec["relation_list"] = rels
    rec["h_id_list"] = h; rec["r_id_list"] = r; rec["t_id_list"] = t
    return n_new


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="cwq_test", choices=list(DATASETS.keys()))
    ap.add_argument("--limit", type=int, default=0, help="0=all")
    ap.add_argument("--ids", default="", help="comma-sep id-prefix filter")
    ap.add_argument("--out", default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    pkl_path = os.path.join(ROOT, DATASETS[args.dataset])
    recs = pickle.loads(open(pkl_path, "rb").read())
    id_filter = [x.strip() for x in args.ids.split(",")] if args.ids else None
    if args.limit: recs = recs[:args.limit]

    total_new = 0; n_changed = 0; n_done = 0
    for rec in recs:
        cid = rec.get("id","")
        if id_filter and not any(cid.startswith(p) for p in id_filter):
            continue
        n_done += 1
        before = len(rec["h_id_list"])
        try:
            added = flood_cvt_for_case(rec, verbose=args.verbose)
        except Exception as e:
            if args.verbose: print(f"  {cid[:24]} ERROR {e}")
            added = 0
        total_new += added
        if added: n_changed += 1
        if args.verbose and added:
            print(f"{cid[:30]:30} +{added:4} CVT-attr triples")
        if n_done % 500 == 0:
            print(f"  ...{n_done} done, {n_changed} changed, +{total_new} so far", flush=True)
    print(f"\n=== {args.dataset}: {n_done} cases, {n_changed} changed (+{n_changed/n_done*100:.0f}%), +{total_new} CVT-attr triples ({total_new/n_done:.1f}/case) ===")
    if args.out:
        pickle.dump(recs, open(args.out, "wb"))
        print(f"  → {args.out}")
