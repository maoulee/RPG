#!/usr/bin/env python3
"""Repair v2 — fixes two bugs in repair_subgraph_virtuoso.py:

  Bug 1 (xsd type mismatch): SPARQL literals like "2005"^^xsd:dateTime don't
    match dump's xsd:gYear. SELECT * returns 0 rows → entire case unrepaired.
    FIX: retry with soft type matching — strip the ^^xsd:type suffix from
    literal filters so Virtuoso does implicit conversion, OR wrap in STR().

  Bug 2 (EXISTS local vars): relations inside FILTER(NOT EXISTS){...} use
    local vars (?sk1) that SELECT * doesn't return → never materialized.
    The second pass was meant to fix this but depends on `rows` (the SELECT
    results) to collect subject MIDs. When Bug 1 makes rows empty, second
    pass gets no MIDs either.
    FIX: collect subject MIDs for EXISTS relations from the OUTER patterns
    too (the CVT subject ?y is bound in pattern 1/2, not just via SELECT),
    then query those relations directly.

This module reuses repair_subgraph_virtuoso's helpers but overrides
repair_case with the fixes. Run on specific case IDs for validation.
"""
import argparse, json, os, pickle, re, sys, urllib.parse, urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from repair_subgraph_virtuoso import (  # reuse helpers
    sparql_query, parse_bgp, pred_local, term_value, uri_mid,
    resolve_names, get_name, NS, ENDPOINT,
)

ROOT = "/zhaoshu/subgraph"


def to_select_star_v2(sparql):
    """SELECT * + soft type matching for literal filters (Bug 1 fix).
    Freebase stores year literals as xsd:gYear "2005-08:00", but CWQ SPARQL
    queries them as "2005"^^xsd:dateTime → strict equality returns 0 rows.
    FIX: (a) in FILTER comparisons, drop ^^xsd:type + the typed-wrapper so
    Virtuoso compares as strings; (b) for triple-object literal equalities
    (?c date "2009"^^xsd:dateTime) rewrite as a ?var + FILTER(STRSTARTS(...))
    so "2009" matches "2009-08:00". Keep DISTINCT/LIMIT."""
    s = re.sub(r"\bSELECT\b\s+(?:DISTINCT\s+|REDUCED\s+)?[^.]*?\bWHERE\b",
               "SELECT * WHERE", sparql, count=1, flags=re.IGNORECASE | re.DOTALL)

    # (a) inside FILTER(...): drop ^^xsd:type from typed literals so Virtuoso
    #     compares as plain strings, and strip xsd:datetime(...) wrappers.
    #     e.g. FILTER(xsd:datetime(?sk1) <= "2015-08-10"^^xsd:dateTime)
    #       → FILTER(STR(?sk1) <= "2015-08-10")
    s = re.sub(r'xsd:datetime\((\?\w+)\)', r'STR(\1)', s)
    s = re.sub(r'"([^"]+)"\^\^xsd:\w+', r'"\1"', s)

    # (b) triple-object literal equality: ?c ns:rel "2009"^^xsd:dateTime .
    #     Rewrite to ?c ns:rel ?_lit_N . FILTER(STRSTARTS(STR(?_lit_N),"2009"))
    #     so it matches the stored gYear "2009-08:00". Only rewrite 4-digit-year
    #     and date literals (the RoG-lost value dimension).
    _counter = [0]
    def _rew(m):
        pred, obj = m.group(1), m.group(2)
        # only fire on full-date or year literals
        if not re.match(r'^\d{4}(-\d{2}.*?)?$', obj):
            return m.group(0)
        _counter[0] += 1
        v = "_lit%d" % _counter[0]
        # match prefix (year) so "2009" hits "2009-08:00"; for full dates use equality
        if re.match(r'^\d{4}$', obj):
            cond = 'FILTER(STRSTARTS(STR(%s),"%s"))' % (v, obj)
        else:
            cond = 'FILTER(STR(%s)="%s")' % (v, obj)
        return '%s ns:%s ?%s . %s' % (m.group(0).split()[0] if False else '?_s%d' % _counter[0], '', v, cond)
    # NOTE: the object-equality rewrite needs the subject — handle inline:
    def _rew_obj(m):
        subj, pred, obj = m.group(1), m.group(2), m.group(3)
        if not re.match(r'^\d{4}(-\d{2}.*?)?$', obj):
            return m.group(0)
        _counter[0] += 1
        v = "_lit%d" % _counter[0]
        if re.match(r'^\d{4}$', obj):
            cond = 'FILTER(STRSTARTS(STR(?%s),"%s"))' % (v, obj)
        else:
            cond = 'FILTER(STR(?%s)="%s")' % (v, obj)
        return '%s %s ?%s . %s' % (subj, pred, v, cond)
    s = re.sub(r'(\?\w+|ns:[\w./-]+)\s+(ns:[\w./-]+)\s+"(\d{4}(?:-\d{2}.*?)?)"(?:\^\^xsd:\w+)?\s*\.',
               _rew_obj, s)

    if not re.search(r"\bLIMIT\b", s, re.IGNORECASE):
        s = s.rstrip().rstrip(";") + "\n LIMIT 2000"
    return s


def repair_case_v2(rec, gold_sparql, verbose=False):
    """Repair with Bug 1 (soft types) + Bug 2 (EXISTS via outer-pattern MIDs)."""
    te = rec["text_entity_list"]; nte = rec["non_text_entity_list"]
    rels = rec["relation_list"]
    h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    node_idx = {}
    for i, n in enumerate(nodes):
        node_idx.setdefault(n, i)
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing_triples = set(zip(h, r, t))
    orig_rel_set = set(rel_idx.keys())
    new_triples = []

    def node_slot(kind, value):
        if kind == "literal":
            key = value
            if key in node_idx: return node_idx[key], False
            nte.append(key); idx = len(te) + len(nte) - 1
            node_idx[key] = idx; return idx, True
        name = get_name(value)
        if name:
            if name in node_idx: return node_idx[name], False
            te.append(name); idx = len(te) - 1
            node_idx[name] = idx; return idx, True
        if value in node_idx: return node_idx[value], False
        nte.append(value); idx = len(te) + len(nte) - 1
        node_idx[value] = idx; return idx, True

    bgp = parse_bgp(gold_sparql)
    if not bgp:
        return {"n_new": 0, "reason": "no BGP parsed"}

    # === Bug 1 fix: soft-type SELECT ===
    sel = to_select_star_v2(gold_sparql)
    rows = sparql_query(sel, timeout=90)
    if verbose:
        print(f"  [v2] SELECT * (soft-type) → {len(rows)} rows")

    # collect MIDs from bindings
    mid_terms = set()
    for (s, p, o) in bgp:
        for tok in (s, o):
            if tok.startswith("ns:") and re.match(r"ns:[mg]\.", tok):
                mid_terms.add(tok[3:])
    for b in rows:
        for (s, p, o) in bgp:
            sv = term_value(s, b); ov = term_value(o, b)
            if sv and sv[0] == "mid": mid_terms.add(sv[1])
            if ov and ov[0] == "mid": mid_terms.add(ov[1])
    if mid_terms: resolve_names(mid_terms)

    # main loop: materialize from rows
    for b in rows:
        for (s, p, o) in bgp:
            prel = pred_local(p)
            if not prel: continue
            sv = term_value(s, b); ov = term_value(o, b)
            if not sv or not ov: continue
            hi, _ = node_slot(sv[0], sv[1]); ti, _ = node_slot(ov[0], ov[1])
            if prel not in rel_idx:
                rels.append(prel); rel_idx[prel] = len(rels) - 1
            ri = rel_idx[prel]
            if (hi, ri, ti) in existing_triples: continue
            existing_triples.add((hi, ri, ti)); new_triples.append((hi, ri, ti))
    n_new = len(new_triples)

    # === Bug 2 fix: EXISTS relations — collect subject MIDs even when rows empty ===
    # Identify relations that are in FILTER(EXISTS) and weren't materialized.
    added_rels = {rels[x[1]] for x in new_triples}
    # subject MIDs: from rows (var_mids) AND from OUTER BGP patterns bound to known entities.
    # For an EXISTS pattern (?y rel ?sk), ?y is also a subject in an outer pattern
    # (?y roster.team ?z) → if ?z is a known MID in the SPARQL, we can find ?y in dump.
    var_mids = {}
    for b in rows:
        for (s, p, o) in bgp:
            if s.startswith("?"):
                sv = term_value(s, b)
                if sv and sv[0] == "mid":
                    var_mids.setdefault(s, set()).add(sv[1])

    # Bug 2 extra: for EXISTS subjects not bound by SELECT, resolve them via the
    # outer pattern chain. E.g. EXISTS{?y roster.from ?sk} where ?y is bound by
    # "ns:m.0bwjj roster ?y" — query dump for ?y directly.
    sp2 = []
    for (s, p, o) in bgp:
        pl = pred_local(p)
        if not pl or pl in orig_rel_set or pl in added_rels: continue
        if s.startswith("?"):
            smids = var_mids.get(s, set())
            if not smids:
                # Bug 2 extra: try to resolve ?s via a co-occurring outer pattern
                # where ?s is subject and object is a known MID/token.
                smids = _resolve_via_outer(s, bgp, rec)
        elif s.startswith("ns:") and re.match(r"ns:[mg]\.", s):
            smids = {s[3:]}
        else:
            smids = set()
        if not smids: continue
        vals = " ".join("ns:%s" % m for m in list(smids)[:60])
        q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
             "SELECT ?s ?o WHERE { VALUES ?s { %s } ?s ns:%s ?o } LIMIT 500"
             % (vals, pl))
        try:
            for b2 in sparql_query(q, timeout=45):
                sm = uri_mid(b2.get("s", {})); ob = b2.get("o", {})
                if not sm: continue
                if ob.get("type") == "uri":
                    om = uri_mid(ob)
                    o_term = ("mid", om) if om else ("literal", ob.get("value", ""))
                else:
                    o_term = ("literal", ob.get("value", ""))
                sp2.append((sm, pl, o_term))
        except Exception as e:
            if verbose: print(f"  [v2] EXISTS rel {pl} query failed: {e}")
    if sp2:
        resolve_names([s for s, _, o in sp2] + [o[1] for _, _, o in sp2 if o[0] == "mid"])
        for sm, pl, o_term in sp2:
            hi, _ = node_slot("mid", sm); ti, _ = node_slot(o_term[0], o_term[1])
            if pl not in rel_idx:
                rels.append(pl); rel_idx[pl] = len(rels) - 1
            ri = rel_idx[pl]
            if (hi, ri, ti) in existing_triples: continue
            existing_triples.add((hi, ri, ti)); new_triples.append((hi, ri, ti))
    n_new = len(new_triples)

    h.extend([x[0] for x in new_triples])
    r.extend([x[1] for x in new_triples])
    t.extend([x[2] for x in new_triples])
    rec["text_entity_list"] = te; rec["non_text_entity_list"] = nte
    rec["relation_list"] = rels
    rec["h_id_list"] = h; rec["r_id_list"] = r; rec["t_id_list"] = t
    return {"n_new": n_new, "n_bind": len(rows), "n_bgp": len(bgp)}


def _resolve_via_outer(var, bgp, rec):
    """Bug 2 helper: if `var` is a subject in an EXISTS pattern but wasn't bound
    by SELECT, find it via another BGP pattern where it's subject and the object
    is a known entity/MID. Query dump for that pattern to get the var's MIDs."""
    # find a pattern: (var, pred, known_obj) where known_obj is ns:m.xxxx
    for (s, p, o) in bgp:
        if s == var and o.startswith("ns:") and re.match(r"ns:[mg]\.", o):
            pl = pred_local(p)
            if not pl: continue
            q = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
                 "SELECT ?s WHERE { ?s ns:%s %s } LIMIT 200" % (pl, o))
            try:
                return {uri_mid(b.get("s", {})) for b in sparql_query(q, timeout=45)
                        if uri_mid(b.get("s", {}))}
            except Exception:
                continue
    return set()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="cwq_test", choices=[
        "cwq_test", "cwq_train", "cwq_val", "webqsp_test", "webqsp_train"])
    ap.add_argument("--ids", help="comma-separated case-id prefixes to repair (empty=all)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    # load pkls + sparql
    cfgs = {
        "cwq_test": ("data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl",
                     "data/cwq_sparql/test.json", "ID", "list"),
        "cwq_train": ("data/cwq_processed/train_rog.pkl",
                      "data/cwq_sparql_full/train.json", "ID", "dict"),
    }
    pkl_path, sq_path, _, fmt = cfgs[args.dataset]
    recs = pickle.loads(open(os.path.join(ROOT, pkl_path), "rb").read())
    raw = json.load(open(os.path.join(ROOT, sq_path)))
    if fmt == "list":
        sq_map = {d["ID"]: d["sparql"] for d in raw}
    else:
        sq_map = {k: (v["sparql"] if isinstance(v, dict) else v) for k, v in raw.items()}

    id_filter = [x.strip() for x in args.ids.split(",")] if args.ids else None
    out_recs = []
    total_new = 0; n_done = 0; n_changed = 0
    for rec in recs:
        cid = rec["id"]
        if id_filter and not any(cid.startswith(p) for p in id_filter):
            continue
        sq = next((v for k, v in sq_map.items() if k.startswith(cid.rsplit("_", 1)[0])), "")
        if not sq:
            continue
        before = len(rec["h_id_list"])
        try:
            stats = repair_case_v2(rec, sq, verbose=args.verbose)
        except Exception as e:
            if args.verbose: print(f"  [v2] {cid} ERROR: {e}")
            stats = {"n_new": 0, "reason": str(e)}
        after = len(rec["h_id_list"])
        added = after - before
        total_new += added; n_done += 1
        if added: n_changed += 1
        if args.verbose or added:
            print(f"{cid[:30]:30} +{added:4} triples (rows={stats.get('n_bind',0)})")
        out_recs.append(rec)
    print(f"\n=== v2 repair: {n_done} cases, {n_changed} changed, +{total_new} triples total ===")
    if args.out:
        pickle.dump(recs if not id_filter else out_recs,
                    open(args.out, "wb"))
        print(f"  written → {args.out}")
