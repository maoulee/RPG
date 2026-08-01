#!/usr/bin/env python3
"""
Repair TRAIN subgraphs (RoG pkl) whose gold answer is UNREACHABLE from the
question entity. ~22% of RoG-CWQ train cases have this defect (the k-hop BFS
extraction dropped the connecting edges, mostly CVT-mediated). With no gold
SPARQL for train, we use Virtuoso directly: resolve q_entity / a_entity names
to Freebase MIDs, BFS in the real Freebase until the answer is reached, and
inject the connecting triples so the answer becomes reachable (positive
training signal).

For each case:
  1. BFS over the pkl triples: is a_entity reachable from q_entity (<=4 hop)?
  2. If not: resolve q/a names -> MIDs (Virtuoso type.object.name).
  3. Virtuoso BFS (both directions, <=3 hops, frontier capped) from q MIDs;
     stop when an a MID is reached.
  4. Merge the explored connecting triples into the pkl record (names -> TE,
     MIDs/literals -> NTE), resolve english names in batch.

Output: <split>_virtuoso_patched.pkl (originals preserved).

Usage:
  python scripts/repair_train_reachability.py --dataset cwq --split train --limit 50 --verbose
  python scripts/repair_train_reachability.py --dataset cwq --split train
"""
import argparse, os, pickle, re, sys, time
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(__file__))
from repair_subgraph_virtuoso import (sparql_query, resolve_names, get_name,
                                      DATASETS, NS)

ROOT = "/zhaoshu/subgraph"
PKL = {
    "cwq":    {"train": f"{ROOT}/data/cwq_processed/train_rog.pkl",
               "validation": f"{ROOT}/data/cwq_processed/validation_rog.pkl"},
    "webqsp": {"train": f"{ROOT}/data/webqsp/train_rog.pkl",
               "validation": f"{ROOT}/data/webqsp/validation_rog.pkl"},
}
MAX_HOPS_PKL = 4          # reachability check over the existing subgraph
MAX_HOPS_VIRT = 3         # Virtuoso BFS depth
FRONTIER_CAP = 250        # max MIDs expanded per hop (bounds neighborhood size)
INJECT_CAP = 400          # max triples injected per case


# ---------------------------------------------------------------------------
def nodes_of(rec):
    return rec["text_entity_list"] + rec["non_text_entity_list"]

def reachable_in_pkl(rec, max_hops=MAX_HOPS_PKL):
    """Return set of a_entity nodes reachable from q_entity within max_hops."""
    te, nte = rec["text_entity_list"], rec["non_text_entity_list"]
    h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte
    adj = defaultdict(set)
    for i in range(len(h)):
        adj[nodes[h[i]]].add(nodes[t[i]]); adj[nodes[t[i]]].add(nodes[h[i]])
    qe = [q for q in rec.get("q_entity") or [] if q]
    ae = set(rec.get("a_entity") or [])
    seen = set(qe); frontier = deque((q, 0) for q in qe if q in adj)
    while frontier:
        n, d = frontier.popleft()
        if d >= max_hops:
            continue
        for m in adj.get(n, ()):
            if m not in seen:
                seen.add(m); frontier.append((m, d + 1))
    return seen & ae, ae


# ---------------------------------------------------------------------------
def uri_mid(b):
    v = b.get("value", "")
    return v[len(NS):] if v.startswith(NS) and re.match(r"^[mg]\.\w", v[len(NS):]) else None

def pred_local_uri(v):
    return v[len(NS):] if v.startswith(NS) else None

def virt_bridge(frontier_mids, a_mids):
    """Find 1-hop and 2-hop connections between ANY frontier MID and ANY a_mid
    (batched VALUES join). Used to bridge the existing partial path (frontier =
    nodes q already reaches in the subgraph) to the answer, so 3-4 hop CWQ
    questions become repairable. Returns list of (s_mid, rel, obj_mid)."""
    if not frontier_mids or not a_mids:
        return []
    F = " ".join("ns:%s" % m for m in frontier_mids[:40])
    A = " ".join("ns:%s" % m for m in a_mids[:6])
    triples = []
    # 1-hop: f --p--> a  OR  a --p--> f
    q1 = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
          "SELECT ?f ?p ?a ?dir WHERE { VALUES ?f { %s } VALUES ?a { %s } "
          "{ ?f ?p ?a . BIND(1 AS ?dir) } UNION { ?a ?p ?f . BIND(2 AS ?dir) } } LIMIT 60"
          % (F, A))
    for b in sparql_query(q1, timeout=30):
        p = pred_local_uri(b.get("p", {}).get("value", ""))
        f = uri_mid(b.get("f", {})); a = uri_mid(b.get("a", {}))
        if not (p and f and a):
            continue
        if b.get("dir", {}).get("value") == "1":
            triples.append((f, p, a))
        else:
            triples.append((a, p, f))
    if triples:
        return triples
    # 2-hop via mediator m, 4 direction combos (return f, m, a)
    q2 = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
          "SELECT ?f ?m ?p1 ?p2 ?a ?dir WHERE { VALUES ?f { %s } VALUES ?a { %s } "
          "{ ?f ?p1 ?m . ?m ?p2 ?a . BIND(1 AS ?dir) } "
          "UNION { ?a ?p1 ?m . ?m ?p2 ?f . BIND(2 AS ?dir) } "
          "UNION { ?f ?p1 ?m . ?a ?p2 ?m . BIND(3 AS ?dir) } "
          "UNION { ?m ?p1 ?f . ?m ?p2 ?a . BIND(4 AS ?dir) } } LIMIT 80" % (F, A))
    for b in sparql_query(q2, timeout=45):
        f = uri_mid(b.get("f", {})); m = uri_mid(b.get("m", {})); a = uri_mid(b.get("a", {}))
        p1 = pred_local_uri(b.get("p1", {}).get("value", ""))
        p2 = pred_local_uri(b.get("p2", {}).get("value", ""))
        d = b.get("dir", {}).get("value")
        if not (f and m and a and p1 and p2 and d):
            continue
        if d == "1":   triples += [(f, p1, m), (m, p2, a)]
        elif d == "2": triples += [(a, p1, m), (m, p2, f)]
        elif d == "3": triples += [(f, p1, m), (a, p2, m)]
        elif d == "4": triples += [(m, p1, f), (m, p2, a)]
    return triples


def name_to_mids(name, limit=8):
    """Resolve an english name to Freebase m. MIDs via type.object.name."""
    if not name:
        return []
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    q = ('PREFIX ns: <http://rdf.freebase.com/ns/>\n'
         'SELECT DISTINCT ?s WHERE { ?s ns:type.object.name "%s"@en } LIMIT %d'
         % (esc, limit))
    out = []
    for b in sparql_query(q, timeout=30):
        m = uri_mid(b.get("s", {}))
        if m and m.startswith("m."):
            out.append(m)
    return out


def names_to_mids_batch(names, per_name=2):
    """Batch name -> MID resolution in ONE VALUES query. Returns name -> [mids]."""
    names = [n for n in names if n]
    if not names:
        return {}
    vals = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in names)
    q = ('PREFIX ns: <http://rdf.freebase.com/ns/>\n'
         'SELECT ?n ?s WHERE { VALUES ?n { %s } ?s ns:type.object.name ?n . '
         'FILTER(STRSTARTS(STR(?s), "http://rdf.freebase.com/ns/m.")) }'
         % vals)
    out = defaultdict(list)
    for b in sparql_query(q, timeout=45):
        nm = b.get("n", {}).get("value")
        m = uri_mid(b.get("s", {}))
        if nm and m and len(out[nm]) < per_name:
            out[nm].append(m)
    return out


def virt_find_path(q_mid, a_mids, two_hop=True):
    """Targeted join queries (NOT neighborhood BFS) connecting q_mid to any
    a_mid. Tries 1-hop then 2-hop (through a CVT mediator). Returns list of
    (s_mid, rel, obj_term) connecting triples. Much lighter than BFS on a
    148GB DB."""
    a_vals = " ".join("ns:%s" % a for a in a_mids[:6])
    Q = "ns:%s" % q_mid
    triples = []
    # ---- 1-hop: q --p--> a  OR  a --p--> q ----
    q1 = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
          "SELECT ?p ?x ?dir WHERE { "
          "{ %s ?p ?x . VALUES ?x { %s } . BIND('q->a' AS ?dir) } "
          "UNION { ?x ?p %s . VALUES ?x { %s } . BIND('a->q' AS ?dir) } } LIMIT 50"
          % (Q, a_vals, Q, a_vals))
    for b in sparql_query(q1, timeout=30):
        p = pred_local_uri(b.get("p", {}).get("value", ""))
        am = uri_mid(b.get("x", {}))
        if not p or not am:
            continue
        if b.get("dir", {}).get("value") == "q->a":
            triples.append((q_mid, p, am))
        else:
            triples.append((am, p, q_mid))
    if triples or not two_hop:
        return triples
    # ---- 2-hop via mediator m: 4 direction combos (return ?x = the a_mid) ----
    q2 = ("PREFIX ns: <http://rdf.freebase.com/ns/>\n"
          "SELECT ?m ?p1 ?p2 ?x ?dir WHERE { "
          "{ %s ?p1 ?m . ?m ?p2 ?x . VALUES ?x { %s } . BIND(1 AS ?dir) } "
          "UNION { ?x ?p1 ?m . ?m ?p2 %s . VALUES ?x { %s } . BIND(2 AS ?dir) } "
          "UNION { %s ?p1 ?m . ?x ?p2 ?m . VALUES ?x { %s } . BIND(3 AS ?dir) } "
          "UNION { ?m ?p1 %s . ?m ?p2 ?x . VALUES ?x { %s } . BIND(4 AS ?dir) } "
          "} LIMIT 60" % (Q, a_vals, Q, a_vals, Q, a_vals, Q, a_vals))
    for b in sparql_query(q2, timeout=45):
        m = uri_mid(b.get("m", {}))
        x = uri_mid(b.get("x", {}))
        p1 = pred_local_uri(b.get("p1", {}).get("value", ""))
        p2 = pred_local_uri(b.get("p2", {}).get("value", ""))
        d = b.get("dir", {}).get("value")
        if not (m and x and p1 and p2 and d):
            continue
        if d == "1":   triples += [(q_mid, p1, m), (m, p2, x)]
        elif d == "2": triples += [(x, p1, m), (m, p2, q_mid)]
        elif d == "3": triples += [(q_mid, p1, m), (x, p2, m)]
        elif d == "4": triples += [(m, p1, q_mid), (m, p2, x)]
    return triples


# ---------------------------------------------------------------------------
def repair_case(rec, verbose=False):
    seen, ae = reachable_in_pkl(rec)
    if not ae or seen >= ae:
        return {"status": "already-reachable", "n_new": 0}
    # resolve q/a names -> mids
    q_mids = []
    for nm in (rec.get("q_entity") or []):
        q_mids += name_to_mids(nm)
    a_mids = []
    for nm in (rec.get("a_entity") or []):
        a_mids += name_to_mids(nm)
    if not q_mids or not a_mids:
        return {"status": "no-mid-resolve", "n_new": 0, "q": bool(q_mids), "a": bool(a_mids)}
    reached = False
    explored = []
    for qm in q_mids[:3]:
        explored += virt_find_path(qm, a_mids)
        if len(explored) >= INJECT_CAP // 2:
            break
    if explored:
        reached = True
    if not reached:
        # frontier-bridge: nodes q already reaches in the subgraph are the bridge
        # points for 3-4 hop questions. Use reachable m./g. MIDs directly PLUS
        # reachable named entities resolved to MIDs (named entities — e.g. a person
        # who lived in region X — are the actual bridge points).
        f_mids = [n for n in seen if n[:2] in ("m.", "g.")][:20]
        named = [n for n in seen
                 if n[:2] not in ("m.", "g.") and not n.startswith("/")
                 and not (n[:1].isdigit())][:25]
        if named:
            for ms in names_to_mids_batch(named).values():
                f_mids += ms[:1]
        f_mids = list(dict.fromkeys(f_mids))[:40]
        if f_mids:
            explored = virt_bridge(f_mids, a_mids)
            reached = bool(explored)
        if not reached:
            return {"status": "not-found", "n_new": 0}
    # batch-resolve english names for all explored MIDs
    mids = set(q_mids) | set(a_mids)
    for s, p, o in explored:
        if isinstance(s, str):
            mids.add(s)
        if isinstance(o, str):
            mids.add(o)
    resolve_names(mids)
    # merge into pkl
    te, nte = rec["text_entity_list"], rec["non_text_entity_list"]
    rels = rec["relation_list"]; h, r, t = rec["h_id_list"], rec["r_id_list"], rec["t_id_list"]
    nodes = te + nte; node_idx = {}
    for i, n in enumerate(nodes): node_idx.setdefault(n, i)
    rel_idx = {rr: i for i, rr in enumerate(rels)}
    existing = set(zip(h, r, t))

    def slot(term):
        if isinstance(term, tuple):
            # literal / foreign uri -> NTE by string
            key = term[1]
            if key in node_idx: return node_idx[key]
            nte.append(key); idx = len(te) + len(nte) - 1; node_idx[key] = idx; return idx
        # mid
        nm = get_name(term)
        key = nm if nm else term
        if key in node_idx: return node_idx[key]
        if nm:
            te.append(nm); idx = len(te) - 1
        else:
            nte.append(term); idx = len(te) + len(nte) - 1
        node_idx[key] = idx; return idx

    n_new = 0
    for s, p, o in explored[:INJECT_CAP]:
        if p not in rel_idx:
            rels.append(p); rel_idx[p] = len(rels) - 1
        hi = slot(s); ri = rel_idx[p]; ti = slot(o)
        if (hi, ri, ti) in existing:
            continue
        existing.add((hi, ri, ti)); h.append(hi); r.append(ri); t.append(ti); n_new += 1
    rec["text_entity_list"], rec["non_text_entity_list"] = te, nte
    rec["relation_list"] = rels; rec["h_id_list"], rec["r_id_list"], rec["t_id_list"] = h, r, t
    # verify reachability post-repair
    seen2, _ = reachable_in_pkl(rec)
    return {"status": "repaired" if seen2 else "injected-unreachable",
            "n_new": n_new, "reached_a": len(seen2)}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(PKL), required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    src = PKL[args.dataset][args.split]
    recs = pickle.load(open(src, "rb"))
    if args.limit:
        recs = recs[:args.limit]
    print(f"[{args.dataset}/{args.split}] {len(recs)} cases")
    from collections import Counter
    status = Counter(); t0 = time.time()
    for n, r in enumerate(recs):
        st = repair_case(r, verbose=args.verbose)
        status[st["status"]] += 1
        if args.verbose or (n and n % 200 == 0):
            print(f"  [{n+1}/{len(recs)}] {r['id'][:28]} -> {st}")
    dt = time.time() - t0
    print(f"\n[done {dt:.0f}s] status: {dict(status)}")
    out = src.replace("_rog.pkl", "_virtuoso_patched.pkl")
    pickle.dump(recs, open(out, "wb"))
    print(f"  wrote {out} ({os.path.getsize(out)//1024//1024} MB)")


if __name__ == "__main__":
    main()
