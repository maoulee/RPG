#!/usr/bin/env python3
"""Minimal attribute-flooding repair (the user's insight):

  "We don't need SPARQL, gold paths, or min/max. Just ensure the subgraph
   HAS the entity's attribute values. Retrieve the attributes corresponding
   to the entities in the subgraph."

So: for every entity/CVT-node already in the subgraph, query Virtuoso for
its VALUE attributes (numeric/date/percentage — the dimension RoG drops),
and add them. No SPARQL parsing, no gold matching, no type filtering. The
goal is purely PRESENCE — the model reasons about which value matches.

This is simpler, faster (one VALUES query per case for all CVT nodes), and
uniformly fixes the "有无问题" (CPI 1.799999, population, roster.from,
career_start) regardless of question type.

Value-attribute predicates (by suffix — any predicate ending in these is a
value attr): .rate .number .date .from .to .amount .capacity .population_number
.start_date .end_date .career_start .index .year .cubic_meters .days

Run:
  python scripts/flood_attrs_simple.py --dataset cwq_test --limit 100
  python scripts/flood_attrs_simple.py --dataset cwq_train --out ...
"""
import argparse, os, pickle, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import sparql_query

ROOT = "/zhaoshu/subgraph"
DATASETS = {
    "cwq_test":  "data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl",
    "cwq_train": "data/cwq_processed/train_rog.pkl",
    "cwq_val":   "data/cwq_processed/validation_rog.pkl",
    "webqsp_test": "data/webqsp/test_fixed_path_completed.pkl",
    "webqsp_train": "data/webqsp/train_rog.pkl",
}

# value-attribute suffixes (predicates carrying these are value attrs)
VALUE_SUFFIXES = (
    ".rate", ".number", ".date", ".from", ".to", ".amount", ".capacity",
    ".population_number", ".start_date", ".end_date", ".career_start",
    ".index", ".year", ".cubic_meters", ".days", ".initial_date",
    ".final_date", ".valid_date", ".valid_from", ".valid_to",
    ".elevation", ".area_total", ".percentage",
)


def is_value_attr(pred_local):
    return any(pred_local.endswith(suf) for suf in VALUE_SUFFIXES)


def flood_case(rec, max_cvt=400, verbose=False):
    """Add value-attrs of subgraph's CVT-like nodes from Virtuoso."""
    te = rec["text_entity_list"]; nte = rec["non_text_entity_list"]
    rels = rec["relation_list"]; h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    node_idx = {n: i for i, n in enumerate(nodes)}
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing = set(zip(h, r, t))

    cvt_nodes = [n for n in nte
                 if re.match(r"^(g\.|m\.[0-9a-z])", str(n)) and " " not in str(n) and len(str(n)) < 40]
    cvt_nodes = list(dict.fromkeys(cvt_nodes))[:max_cvt]
    if not cvt_nodes:
        return 0

    new_tris = []; n_new = 0
    BATCH = 100
    for i in range(0, len(cvt_nodes), BATCH):
        chunk = cvt_nodes[i:i+BATCH]
        vals = " ".join("ns:%s" % c for c in chunk)
        q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
             "SELECT ?s ?p ?o WHERE { VALUES ?s { %s } ?s ?p ?o . FILTER(isLiteral(?o)) } LIMIT 6000" % vals)
        try:
            rows = sparql_query(q, timeout=45)
        except Exception:
            rows = []
        for b in rows:
            s = b["s"]["value"]; s_mid = s.split("/ns/")[-1] if "/ns/" in s else s
            p = b["p"]["value"]; p_local = p.split("/ns/")[-1] if "/ns/" in p else p
            if not is_value_attr(p_local):
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="cwq_test", choices=list(DATASETS.keys()))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--max-cvt", type=int, default=400)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    recs = pickle.loads(open(os.path.join(ROOT, DATASETS[args.dataset]), "rb").read())
    id_filter = [x.strip() for x in args.ids.split(",")] if args.ids else None
    if args.limit: recs = recs[:args.limit]

    total = 0; changed = 0; done = 0
    for rec in recs:
        cid = rec.get("id", "")
        if id_filter and not any(cid.startswith(p) for p in id_filter):
            continue
        done += 1
        before = len(rec["h_id_list"])
        try:
            added = flood_case(rec, max_cvt=args.max_cvt, verbose=args.verbose)
        except Exception as e:
            if args.verbose: print(f"  {cid[:24]} ERR {e}")
            added = 0
        total += added
        if added: changed += 1
        if args.verbose and added:
            print(f"{cid[:30]:30} +{added:4}")
        if done % 200 == 0:
            print(f"  ...{done} done, {changed} changed, +{total}", flush=True)
    print(f"\n=== {args.dataset}: {done} cases, {changed} changed (+{changed/max(done,1)*100:.0f}%), +{total} triples ({total/max(done,1):.0f}/case) ===")
    if args.out:
        pickle.dump(recs, open(args.out, "wb")); print(f"  → {args.out}")
