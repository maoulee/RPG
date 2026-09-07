#!/usr/bin/env python3
"""v1.5 credit rules vs stored v12 credit — same data, turn-layer delta only.

Deltas vs the v12 cascade (recompute_advantage_v0.py), per the 2026-08-18
adjudication (specs/credit_assignment_mechanism.md §10.8):
  1. PLAN FIX: plan/decompose turn gets its own rule (scale = 1{R_exp>0} × A_exp)
     instead of inheriting the LAST sg's cascade class (the identity leak).
  2. L3 N×U: when d (sequential delta) and l (LOO) are flat, the old
     relation-overlap adjudicator is replaced by displayed-triple novelty N
     ∧ standalone value U (=fwd), with gold first-attribution g as OR arm:
       g>0 ∨ (N≥n_thr ∧ U>u_thr) → effective (FULL credit, was +0.5 partial)
       else redundant (subtype: N< thr = duplicate; N≥thr ∧ U≤thr = irrelevant)
  3. REFERENCE PROTECTION (failed trajectories): if no gold entity ever entered
     evidence, redundant/harmful turns whose (center, relation-set) matches a
     successful sibling's subgraph are protected → 0 credit instead of penalty.
Trajectory layer (a_exp/a_ans/r_exp) is REUSED from stored _v0_fields so the
comparison isolates turn-rule changes. Stored turn_advantages = "old".

Usage: python scripts/recompute_advantage_v15.py --inp tmp/seq_train_v12adv.jsonl
"""
import argparse, importlib.util, json, math, os, random, re
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("v0", os.path.join(_here, "recompute_advantage_v0.py"))
v0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v0)
norm, fuzzy_in, parse_trajectory = v0.norm, v0.fuzzy_in, v0.parse_trajectory

TAU = 0.005
N_THR = 0.2          # displayed-edge novelty fraction to count as "new info"
U_THR = 0.005        # standalone forward value to count as "useful"
REF_SIM_THR = 0.5    # structural similarity to a successful sibling for protection


def parse_sg_structure(rec, blocks):
    """Per-sg displayed edges / relations / centers + anchors + later centers.
    (Adapted from the v0 main() structural block — same parsing, plus centers.)"""
    msgs = rec["messages"]
    sg_edges, anchors, later_centers = defaultdict(list), set(), defaultdict(set)
    sg_centers, sg_rels = {}, defaultdict(set)
    cur_sg = None
    pending_center = None
    for m in msgs:
        c = m.get("content", "") or ""
        role = m.get("role")
        if role == "assistant":
            cm = re.search(r"center:\s*(.+)", c)
            tm = re.findall(r"tool:\s*(\w+)", c)
            tool = tm[-1] if tm else None
            if cm and tool == "retrieve_subgraph":
                pending_center = cm.group(1).strip()
                parts = [norm(x.strip().strip('"\'')) for x in re.split(r"[|,]", cm.group(1))
                         if x.strip().strip('"\'')]
                if cur_sg is None:
                    anchors.update(p for p in parts if p)
                else:
                    later_centers[cur_sg].update(p for p in parts if p)
            elif cm and tool == "retrieve_relations" and not anchors:
                anchors.update(norm(x.strip().strip('"\'')) for x in re.split(r"[|,]", cm.group(1))
                               if x.strip().strip('"\'') and not x.strip().startswith("?"))
        elif role == "tool":
            h = re.search(r"fact_id:\s*(\S+)", c)
            if h:
                cur_sg = h.group(1)
                if pending_center:
                    for pc in re.split(r"[|,]", pending_center):
                        sg_centers.setdefault(cur_sg, norm(pc.strip().strip('"\'')))
                for line in c.split("\n"):
                    for sep in ("-->", "→"):
                        if sep in line:
                            l_, r_ = line.split(sep, 1)
                            for _h in l_.split("|"):
                                for _t in r_.split("|"):
                                    h2 = _h.strip().strip('[]().,;:\'"')
                                    t2 = _t.strip().strip('[]().,;:\'"')
                                    if h2 and t2 and len(h2) > 1 and len(t2) > 1:
                                        sg_edges[cur_sg].append((norm(h2), norm(t2)))
                            break
    # relation sets from the assistant retrieve_subgraph turns (per block msg idx)
    # strip reasoning-leak suffixes ("rel - this looks like ...") that pollute
    # overlap/StructSim; drop non-relation tokens ("center=x", "question=...")
    for name, mi in blocks:
        m2 = re.match(r"sg:(.+)", name)
        if m2:
            c = msgs[mi].get("content", "") or ""
            rm = re.search(r"relations:\s*(.+)", c)
            if rm:
                for x in re.split(r"[|,]", rm.group(1)):
                    x = x.strip().lower().split(" - ")[0].strip()
                    x = x.rsplit(".", 1)[-1]
                    if x and "=" not in x and " " not in x:
                        sg_rels[m2.group(1)].add(x)
    return sg_edges, anchors, later_centers, sg_centers, sg_rels


def _reach(edges, srcs, targets):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, q = set(srcs), list(srcs)
    while q:
        n = q.pop()
        for m2 in adj.get(n, ()):
            if m2 not in seen:
                seen.add(m2)
                q.append(m2)
    return sum(1 for t in targets if t in seen)


def compute_sg_signals(rec, p, blocks, ev_by_sg):
    """All per-sg measurements: d, l, f, g, edges, rels, center, structure, N."""
    sg_edges, anchors, later_centers, sg_centers, sg_rels = parse_sg_structure(rec, blocks)
    loo = {s: (float(v) if v is not None else 0.0) for s, v in (rec.get("credits") or [])}
    fwd = {s: (float(v) if v is not None else 0.0) for s, v in (rec.get("forward_credits") or [])}

    dp_map = None
    vseq = rec.get("Vseq")
    if isinstance(vseq, dict) and len(vseq) >= 2 and all(v is not None for v in vseq.values()):
        prev, dp = math.exp(rec.get("V0") or 0.0), {}
        for s, v in vseq.items():
            cur = math.exp(v)
            dp[s] = cur - prev
            prev = cur
        dp_map = dp

    # sg order + gold first-attribution
    sg_order, attributed = [], set()
    for name, _ in blocks:
        m2 = re.match(r"sg:(.+)", name)
        if m2 and m2.group(1) not in sg_order:
            sg_order.append(m2.group(1))
    g_first = defaultdict(float)
    for s in sg_order:
        ev = ev_by_sg.get(s, set())
        new_gold = [gi for gi, g in enumerate(p["gold"])
                    if gi not in attributed and fuzzy_in(g, ev)]
        for gi in new_gold:
            attributed.add(gi)
        if new_gold and p["gold"]:
            g_first[s] = len(new_gold) / len(p["gold"])

    # structure: indispensable (anchor→gold reachability drop) + lineage
    gold_nodes = [norm(g) for g in p["gold"] if norm(g)]
    all_edges = [e for es in sg_edges.values() for e in es]
    full_reach = _reach(all_edges, anchors, gold_nodes) if anchors and gold_nodes else 0
    indispensable = {}
    for s in sg_order:
        if not anchors or not gold_nodes:
            indispensable[s] = False
            continue
        wo = [e for s2, es in sg_edges.items() for e in es if s2 != s]
        indispensable[s] = _reach(wo, anchors, gold_nodes) < full_reach

    def _fuzzy_in_set(name, s2):
        for cand in later_centers.get(s2, set()):
            if name == cand or name in cand or cand in name:
                return True
        return False

    lineage = {s: any(any(_fuzzy_in_set(e, s2) for e in ev_by_sg.get(s, set()))
                      for s2 in sg_order[sg_order.index(s) + 1:]) for s in sg_order}

    # displayed-edge novelty N: fraction of sg's displayed edges not seen in PRIOR sgs
    novelty = {}
    seen_edges = set()
    for s in sg_order:
        edges = sg_edges.get(s, [])
        newc = sum(1 for e in edges if e not in seen_edges)
        novelty[s] = (newc / len(edges)) if edges else 0.0
        seen_edges.update(edges)

    info = {}
    for s in sg_order:
        info[s] = {
            "d": dp_map.get(s) if dp_map else None,
            "l": loo.get(s, 0.0), "f": fwd.get(s, 0.0), "g": g_first.get(s, 0.0),
            "indispensable": indispensable[s], "lineage": lineage[s],
            "N": novelty[s], "rels": sg_rels.get(s, set()),
            "center": sg_centers.get(s), "edges": sg_edges.get(s, []),
        }
    return sg_order, info, dp_map, loo, fwd, g_first


def struct_sim(a, b):
    """Center match + relation-set Jaccard; center mismatch halves the score."""
    if a["rels"] and b["rels"]:
        j = len(a["rels"] & b["rels"]) / len(a["rels"] | b["rels"])
    else:
        j = 0.0
    ca, cb = a.get("center"), b.get("center")
    cmatch = bool(ca and cb and (ca == cb or ca in cb or cb in ca))
    return j if cmatch else 0.5 * j


def classify_v15(si, failed, ref_infos, ae):
    """v1.5 cascade for one sg. Returns (class, adv)."""
    d, l, f, g = si["d"], si["l"], si["f"], si["g"]
    if si["indispensable"] or si["lineage"]:
        cls = "effective"
    elif d is not None and d < -TAU and g <= 0 and f <= TAU:
        cls = "harmful"
    elif (d is not None and d > TAU) or l > TAU:
        cls = "effective"
    elif g > 0 or (si["N"] >= N_THR and f > U_THR):
        cls = "effective"       # masked complementary/substitute — FULL credit
    elif si["N"] < N_THR:
        cls = "redundant_dup"   # nothing new fetched
    else:
        cls = "redundant_irr"   # new but useless (irrelevant exploration)
    # reference protection: failed trajectory + matches a successful sibling
    if failed and cls in ("redundant_dup", "redundant_irr", "harmful"):
        sref = max((struct_sim(si, rsi) for rinfos in ref_infos for rsi in rinfos.values()),
                   default=0.0)
        if sref >= REF_SIM_THR:
            return "ref_protected", 0.0
    if cls == "effective":
        return cls, (ae if ae > 0 else 0.0)
    if cls in ("redundant_dup", "redundant_irr"):
        return cls, ((-0.5 * abs(ae)) if ae > 0 else ae)
    return cls, ((-0.5 * abs(ae)) if ae > 0 else ae)  # harmful


def classify_v12(si, ae):
    """Replicated v12 cascade (incl. the plan-leak semantics for sg turns)."""
    d, l, f, g = si["d"], si["l"], si["f"], si["g"]
    if si["indispensable"] or si["lineage"]:
        return "effective", (ae if ae > 0 else 0.0)
    _harmful = d is not None and d < -TAU and g <= 0 and f <= TAU
    if _harmful:
        return "harmful", ((-0.5 * abs(ae)) if ae > 0 else ae)
    if (d is not None and d > TAU) or l > TAU:
        return "effective", (ae if ae > 0 else 0.0)
    if f > TAU:
        # old adjudicator: relation overlap with prior sgs (recomputed by caller
        # via si["ov"]; kept here for replication)
        if si.get("ov", 0.0) >= 0.5:
            return "redundant_dup", ((-0.5 * abs(ae)) if ae > 0 else ae)
        return "partial", ((0.5 * ae) if ae > 0 else 0.0)
    return "redundant_dup", ((-0.5 * abs(ae)) if ae > 0 else ae)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--out", default=None, help="audit jsonl (per-turn old-vs-new)")
    ap.add_argument("--train-out", default=None,
                    help="write a TRAINING-READY jsonl: same records with "
                         "turn_advantages replaced by the v1.5 values (new_advs)")
    ap.add_argument("--anchors", default="", help="comma substrings of questions to dump")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.inp)]
    groups = defaultdict(list)
    parsed = []
    for rec in recs:
        blocks, ev_by_sg, pred = parse_trajectory(rec)
        gold = [g for g in rec.get("gold", []) if g and not str(g).startswith("g.")]
        all_ev = set().union(*ev_by_sg.values()) if ev_by_sg else set()
        gold_e = [g for g in gold if fuzzy_in(g, all_ev)]
        p = dict(rec=rec, blocks=blocks, ev_by_sg=ev_by_sg, gold=gold, gold_e=gold_e)
        parsed.append(p)
        groups[rec.get("case_idx")].append(p)

    # failed trajectory = DISPLAYED evidence never showed gold (the agent could
    # not answer from what it saw). The structured ctx-level field includes
    # hidden/truncated leaves and saturates (v7 finding) — unusable here.
    def _gold_seen(p):
        return bool(p["gold_e"])

    # pass 1: parse signals for every record
    for p in parsed:
        sg_order, info, dp_map, loo, fwd, g_first = compute_sg_signals(
            p["rec"], p, p["blocks"], p["ev_by_sg"])
        # relation overlap for v12 replication (same formula as v0)
        for s in sg_order:
            idx = sg_order.index(s)
            prior = set().union(*[info[o]["rels"] for o in sg_order[:idx]]) if idx else set()
            my = info[s]["rels"]
            info[s]["ov"] = (len(my & prior) / len(my)) if my else 0.0
        p["sg_order"], p["sg_info"], p["dp_map"] = sg_order, info, dp_map

    # per-group reference infos: per-sg signals of gold-reaching trajectories
    group_infos = {}
    for g, ps in groups.items():
        group_infos[g] = [p["sg_info"] for p in ps if _gold_seen(p) and p.get("sg_info")]

    out_f = open(args.out, "w") if args.out else None
    stats = defaultdict(int)
    l3_confusion = defaultdict(int)   # (old_cls, new_cls) -> n
    plan_stats = defaultdict(float)
    audit_lines = []
    anchor_dump = [a.strip().lower() for a in args.anchors.split(",") if a.strip()]

    # pass 2: classify + compare against stored turn_advs
    n_match = n_turns_checked = 0
    for p in parsed:
        rec = p["rec"]
        vf = rec.get("_v0_fields") or {}
        a_exp, a_ans, r_exp = vf.get("a_exp", 0.0), vf.get("a_ans", 0.0), vf.get("r_exp", 0.0)
        stored = rec.get("turn_advantages") or []
        failed = not _gold_seen(p)
        ref_infos = group_infos[rec.get("case_idx")]
        blk_by_msg = {mi: nm for nm, mi in p["blocks"]}
        new_advs, old_rep = [], []
        turn_audit = []
        a_ord = 0
        has_answer = any(b == "answer" for b, _ in p["blocks"])
        for mi, m in enumerate(rec["messages"]):
            if m.get("role") != "assistant":
                continue
            blk = blk_by_msg.get(mi, "sg:?")
            if blk == "answer":
                new_advs.append(a_ans)
                old_rep.append(stored[a_ord] if a_ord < len(stored) else 0.0)
                turn_audit.append(("answer", "answer", a_ans, a_ans, None))
                a_ord += 1
                continue
            s = blk.split(":", 1)[1] if ":" in blk else None
            si = p["sg_info"].get(s) if s else None
            if blk == "plan":
                # NEW: plan gets its own rule
                new_adv = (1.0 if r_exp > 0 else 0.0) * a_exp
                new_cls = "plan_on" if r_exp > 0 else "plan_off"
                new_advs.append(new_adv)
                old_rep.append(stored[a_ord] if a_ord < len(stored) else 0.0)
                plan_stats["old_mean"] += old_rep[-1]
                plan_stats["new_mean"] += new_adv
                if old_rep[-1] < -1e-9 and new_adv >= -1e-9:
                    plan_stats["neg_to_nonneg"] += 1
                if abs(old_rep[-1] - new_adv) > 1e-9:
                    plan_stats["changed"] += 1
                plan_stats["n"] += 1
                turn_audit.append(("plan", new_cls, old_rep[-1], new_adv, None))
            elif si is not None and p["dp_map"] is not None and s in p["dp_map"]:
                old_cls, old_adv = classify_v12(si, a_exp)
                new_cls, new_adv = classify_v15(si, failed, ref_infos, a_exp)
                new_advs.append(new_adv)
                old_rep.append(old_adv)
                # replication check vs stored (a_exp is stored rounded to 4dp,
                # so stored turn values differ by up to ~5e-4 — tolerance 1e-3)
                n_turns_checked += 1
                if stored and a_ord < len(stored) and abs(stored[a_ord] - old_adv) < 1e-3:
                    n_match += 1
                stats[f"old:{old_cls}"] += 1
                stats[f"new:{new_cls}"] += 1
                # L3 subset: d,l flat (where old adjudicator was active)
                if si["d"] is not None and abs(si["d"]) <= TAU and si["l"] <= TAU:
                    l3_confusion[(old_cls, new_cls)] += 1
                turn_audit.append((f"sg:{s}", new_cls, old_adv, new_adv,
                                   dict(d=round(si["d"], 4) if si["d"] is not None else None,
                                        l=round(si["l"], 4), f=round(si["f"], 4),
                                        g=round(si["g"], 2), N=round(si["N"], 3),
                                        ov=round(si["ov"], 2),
                                        ind=si["indispensable"], lin=si["lineage"],
                                        rels=sorted(si["rels"])[:6],
                                        center=si["center"], failed=failed)))
            else:
                # fallback (single-SG / no Vseq): identical G∨F∨L in both
                val = (p["sg_info"].get(s, {}).get("g", 0) > 0
                       or p["sg_info"].get(s, {}).get("f", 0) > 0.01
                       or p["sg_info"].get(s, {}).get("l", 0) > 0.01) if s else False
                cls = "fb_effective" if val else "fb_redundant"
                adv = (a_exp if (val and a_exp > 0) else
                       (0.0 if val else ((-0.5 * abs(a_exp)) if a_exp > 0 else a_exp)))
                new_advs.append(adv)
                old_rep.append(stored[a_ord] if a_ord < len(stored) else 0.0)
                stats[f"fb:{cls}"] += 1
                turn_audit.append((f"sg:{s}", cls, old_rep[-1], adv, None))
            a_ord += 1
        if not has_answer and new_advs:
            new_advs[-1] += a_ans
        p["new_advs"], p["turn_audit"] = new_advs, turn_audit
        if anchor_dump and any(a in (rec.get("question") or "").lower() for a in anchor_dump):
            audit_lines.append((rec, turn_audit))

    if args.train_out:
        with open(args.train_out, "w") as tf:
            for p in parsed:
                rec = dict(p["rec"])
                rec["turn_advantages"] = p["new_advs"]
                tf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\ntraining-ready jsonl → {args.train_out} "
              f"({len(parsed)} records, v1.5 turn rules)")

    # ── report ──
    print(f"\n=== {args.inp}")
    print(f"records={len(parsed)} groups={len(groups)}")
    print(f"v12 replication vs stored turn_advs: {n_match}/{n_turns_checked} "
          f"({n_match / max(n_turns_checked, 1):.1%}) exact match")
    print("\n-- class distribution (multi-SG cascade turns) --")
    keys = sorted(set(k.split(":", 1)[1] for k in stats if k.startswith(("old:", "new:"))))
    for k in keys:
        print(f"  {k:18s} old={stats.get(f'old:{k}', 0):6d}  new={stats.get(f'new:{k}', 0):6d}")
    print("\n-- L3 subset (d,l flat) confusion old→new --")
    for (oc, nc), n in sorted(l3_confusion.items(), key=lambda x: -x[1]):
        print(f"  {oc:14s} → {nc:18s} {n}")
    print("\n-- plan turns (leak fixed) --")
    n = max(plan_stats["n"], 1)
    print(f"  n={int(plan_stats['n'])} old_mean={plan_stats['old_mean'] / n:+.3f} "
          f"new_mean={plan_stats['new_mean'] / n:+.3f} changed={int(plan_stats['changed'])} "
          f"neg→nonneg={int(plan_stats['neg_to_nonneg'])}")
    print(f"  ref_protected turns (new): {stats.get('new:ref_protected', 0)}")

    if out_f:
        for p in parsed:
            rec = p["rec"]
            out_f.write(json.dumps({
                "case_id": rec.get("case_id"), "sample_idx": rec.get("sample_idx"),
                "question": rec.get("question"), "gold_reached": not (
                    not any(fuzzy_in(g, (rec.get("evidence_entities") or [])) for g in p["gold"])),
                "turns": p["turn_audit"], "new_sum": round(sum(p["new_advs"]), 4),
                "old_sum": rec.get("advantage"),
            }, ensure_ascii=False) + "\n")
        out_f.close()
        print(f"\naudit → {args.out}")

    if audit_lines:
        print("\n=== anchor cases ===")
        for rec, ta in audit_lines[:6]:
            print(f"\nQ: {rec.get('question')[:80]}  case={rec.get('case_idx')} "
                  f"sample={rec.get('sample_idx')}")
            for name, cls, ov_, nv_, sig in ta:
                sig_s = ""
                if sig:
                    sig_s = (f"d={sig['d']} l={sig['l']} f={sig['f']} g={sig['g']} "
                             f"N={sig['N']} ov={sig['ov']} ind={int(bool(sig['ind']))} "
                             f"lin={int(bool(sig['lin']))} rels={sig['rels']}")
                print(f"  {name:10s} old={ov_:+.3f} new={nv_:+.3f} [{cls}] {sig_s}")


if __name__ == "__main__":
    main()
