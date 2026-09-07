#!/usr/bin/env python3
"""Recompute turn advantages on EXISTING rollout JSONLs with the v0 (binary) scheme.

Design (2026-08-14 converged spec, binary v0):
  轴1 探索轮:  a_t = scale_t × A_exp
    A_exp  = R_exp − mean_group(R_exp),  R_exp = |gold∩evidence| / |gold|
    scale_t ∈ {0,1}: 1 iff the turn's sg shows ANY value signal:
      G: first-attribution of a gold entity (sg first brought it into evidence)
      F: forward credit > 0 (incremental IG at execution time)
      L: LOO credit > 0 (removal hurts answer probability)
  plan 轮:    scale = 1 iff R_exp > 0 (plan coherent & exploration reached gold)
  轴2 答案轮:  a_ans = F1(pred, gold∩evidence) − mean_group(same);  ∅∩ → 0
  轮内无 ÷n; Σ 无守恒。负轨迹中 scale=0 的轮加 -ε 微惩罚（对抗相对抬升，
  见会话分析：零权重在负轨迹中等价于相对提高该行为概率）。

Consumes v5-style records (messages + gold + credits + forward_credits).
Evidence parsed from displayed tool text (v5 predates structured fields; display
truncation caveat documented — recomputed rollouts on the new harness will carry
structured evidence_entities instead).

Usage:
  python scripts/recompute_advantage_v0.py --inp /tmp/seq_train_v5.jsonl \
      --out /tmp/seq_train_v6adv.jsonl [--eps 0.05]
"""
import argparse, json, math, re
from collections import defaultdict


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).strip()


def fuzzy_in(target, pool):
    t = norm(target)
    return any(t and (t == p or t in p or p in t) for p in pool if p)


def parse_trajectory(rec):
    """Return (blocks, evidence_by_sg, pred_entities).
    blocks: list of (block_name, assistant_msg_idx) in order; block_name in
    {'plan','sg:<id>','answer'} — sg attribution = the fact_id of the tool result
    following the turn's retrieve_subgraph (else the next resolved sg)."""
    msgs = rec.get("messages", [])
    blocks, ev_by_sg = [], {}
    cur_sg = None
    pred = []
    for i, m in enumerate(msgs):
        role = m.get("role")
        c = m.get("content") or ""
        if role == "assistant":
            tools = re.findall(r"tool:\s*(\w+)", c)
            tool = tools[-1] if tools else None
            if tool in ("plan", "decompose"):
                blocks.append(("plan", i))
            elif tool == "answer":
                blocks.append(("answer", i))
                em = re.search(r'"?entities"?\s*[:=]\s*(\[.*?\]|.+?)(?:\n|$)', c)
                if em:
                    v = em.group(1).strip().strip('`')
                    if v.startswith("["):
                        try:
                            j = json.loads(v)
                            pred = [str(x).strip() for x in j if str(x).strip()]
                        except json.JSONDecodeError:
                            pred = []
                    else:
                        pred = [x.strip().strip("\"'") for x in v.split("|") if x.strip()]
            elif tool == "retrieve_subgraph":
                cur_sg = None          # resolved by the following tool result
                blocks.append((f"sg", i))
            elif tool == "retrieve_relations":
                blocks.append((f"sg", i))   # attributed to the sg being explored
        elif role == "tool":
            h = re.search(r"fact_id:\s*(\S+)", c)
            if h:
                cur_sg = h.group(1)
                # retro-label pending sg blocks (those after the previous resolved sg)
                for bi in range(len(blocks) - 1, -1, -1):
                    if blocks[bi][0] != "sg":
                        break
                    blocks[bi] = (f"sg:{cur_sg}", blocks[bi][1])
                ev = set()
                for line in c.split("\n"):
                    for sep in ("-->", "→"):
                        if sep in line:
                            for side in (line.split(sep)[0], line.split(sep)[-1]):
                                for e in side.split("|"):
                                    e = e.strip().strip("[]().,;:'\"")
                                    if e and len(e) > 1 and not e.startswith("["):
                                        ev.add(norm(e))
                            break
                if ev:
                    ev_by_sg.setdefault(cur_sg, set()).update(ev)
    return blocks, ev_by_sg, pred


def f1(preds, golds):
    if not golds:
        return 1.0 if not preds else 0.0
    if not preds:
        return 0.0
    tp = sum(1 for g in golds
             if any(norm(p) == norm(g) or norm(p) in norm(g) or norm(g) in norm(p)
                    for p in preds))
    prec, rec_ = tp / len(preds), tp / len(golds)
    return 2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eps", type=float, default=0.05,
                    help="(superseded by --lambda-red) legacy anti relative-lift")
    ap.add_argument("--lambda-red", type=float, default=-1.0,
                    help="redundant-turn penalty; -1 = auto (0.3*S, S=median group "
                         "range of R_exp — hand-set absolutes were 5-10x the "
                         "differential scale and dominated the gradient)")
    ap.add_argument("--cap-eff", type=float, default=-1.0,
                    help="rescue cap for effective hops in negative traj; -1 = auto (1.0*S)")
    ap.add_argument("--delta-harm", type=float, default=-1.0,
                    help="harmful-hop damage coefficient; -1 = auto (0.5*S/median|Δp_harm|)")
    ap.add_argument("--tau-gain", type=float, default=0.0,
                    help="insufficiency threshold on the probability gain pF-p0: "
                         "below this the evidence did not help the answer at all")
    ap.add_argument("--delta-abs", type=float, default=-1.0,
                    help="insufficiency floor; -1 = auto (0.5*S)")
    ap.add_argument("--r-exp-mode", choices=("display", "tf"), default="display",
                    help="evidence-quality measure: 'display' parses the shown tool "
                         "text (authoritative on new-harness rollouts with structured "
                         "fields); 'tf' uses the (pF-p0) teacher-forcing gain — for "
                         "OLD rollouts whose displayed evidence was truncated "
                         "(pre-Option-B), the TF gain saw the full evidence. The "
                         "multi-entity compression artifact is constant within a "
                         "group, so group-centering absorbs it.")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.inp)]
    groups = defaultdict(list)
    parsed = []
    for rec in recs:
        blocks, ev_by_sg, pred = parse_trajectory(rec)
        gold = [g for g in rec.get("gold", []) if g and not str(g).startswith("g.")]
        all_ev = set().union(*ev_by_sg.values()) if ev_by_sg else set()
        if args.r_exp_mode == "tf":
            r_exp = (rec.get("pF") or 0) - (rec.get("p0") or 0)
        else:
            r_exp = (sum(1 for g in gold if fuzzy_in(g, all_ev)) / len(gold)) if gold else 0.0
        gold_e = [g for g in gold if fuzzy_in(g, all_ev)] if args.r_exp_mode == "display" \
            else [g for g in gold if fuzzy_in(g, all_ev)]
        f_ans = f1(pred, gold_e) if gold_e else 0.0
        p = dict(rec=rec, blocks=blocks, ev_by_sg=ev_by_sg, gold=gold,
                 r_exp=r_exp, f_ans=f_ans, n_asst=sum(1 for m in rec["messages"]
                                                      if m.get("role") == "assistant"))
        parsed.append(p)
        groups[rec.get("case_idx")].append(p)

    # scale anchor S = median within-group range of R_exp ("one typical
    # differential"). All penalty params are multiples of S (auto mode) so they
    # can never dwarf — or vanish under — the group-differential learning signal.
    import statistics as _st
    _ranges = [max(x["r_exp"] for x in ps) - min(x["r_exp"] for x in ps)
               for ps in groups.values() if len(ps) >= 2]
    S = _st.median(_ranges) if _ranges else 0.06
    harm_mag = [abs(d) for p in parsed for d in (p["dp_all"] or []) if d < -0.005] \
        if hasattr(parsed[0], "dp_all") else []
    if args.lambda_red < 0: args.lambda_red = 0.3 * S
    if args.cap_eff < 0:    args.cap_eff = 1.0 * S
    if args.delta_abs < 0:  args.delta_abs = 0.5 * S
    if args.delta_harm < 0: args.delta_harm = (0.5 * S / 0.067) if not harm_mag else (0.5 * S / _st.median(harm_mag))
    print(f"  auto-calibrated on S={S:.4f}: lambda_red={args.lambda_red:.4f} "
          f"cap_eff={args.cap_eff:.4f} delta_abs={args.delta_abs:.4f} "
          f"delta_harm={args.delta_harm:.3f}")

    # exploration axis: group-mean baseline (Monte-Carlo V estimate — evidence
    # quality is relative within the case's sibling trajectories).
    # answer axis: group-mean baseline. A frozen-model value baseline
    # (a_ans = F1 − pF) was tried and REJECTED: pF (exact-token teacher-forcing
    # of the gold string) correlates only ~0.03 with actual F1 — the actor's
    # fuzzy-matched correctness (synonyms, partial lists) is invisible to
    # exact-token likelihood, so the baseline is noise-dominated and over-credits
    # (mean a_ans +0.22, 76% positive in the v9 trial). The group mean remains
    # the practical MC value estimate for the answer axis.
    for g, ps in groups.items():
        mr = sum(x["r_exp"] for x in ps) / len(ps)
        mf = sum(x["f_ans"] for x in ps) / len(ps)
        # GATED Z-SCORE (user spec): ALIVE groups (at least one trajectory's
        # exploration meaningfully raised the answer probability — real signal)
        # get z-scored advantages so the winner's effective retrieval turns take
        # the FULL ±1.0 advantage; DEAD groups (case-level breakage, all gains
        # ≈0 — measurement noise dominates) are NOT amplified.
        gains = [x["r_exp"] for x in ps]
        sd = (sum((v - mr) ** 2 for v in gains) / len(gains)) ** 0.5
        alive = max(gains) > 0.05
        # answer axis: same gated z-score (user directive — symmetric treatment;
        # 56% of groups have saturated F1 (all-correct) where plain centering
        # ≈0; alive answer groups get amplified to ±1 so the answer signal is
        # learnable at the same scale as exploration)
        fsd = (sum((x["f_ans"] - mf) ** 2 for x in ps) / len(ps)) ** 0.5
        ans_alive = fsd > 0.1
        for x in ps:
            if ans_alive:
                x["a_ans"] = max(-1.0, min(1.0, (x["f_ans"] - mf) / fsd))
            else:
                x["a_ans"] = x["f_ans"] - mf
            if alive and sd > 1e-6:
                z = (x["r_exp"] - mr) / sd
                x["a_exp"] = max(-1.0, min(1.0, z))
            else:
                x["a_exp"] = x["r_exp"] - mr
            # absolute insufficiency: the evidence did not improve the answer
            # probability at all (pF−p0 below tau — retrieval unhelpful/flat).
            # Domain-consistent (probability gain, always present) — the naive
            # fwd/loo AND-criterion never fires because single-SG 'credits' are
            # LOG-domain (vF−v0) while multi-SG are probability-domain, and 71%
            # of trajectories have forward_credits=None. Group centering alone
            # cancels this case when the WHOLE group under-retrieves.
            gain = (x["rec"].get("pF") or 0) - (x["rec"].get("p0") or 0)
            x["insufficient"] = gain < args.tau_gain
            if x["insufficient"]:
                x["a_exp"] -= args.delta_abs

    out = open(args.out, "w")
    stats = defaultdict(int)
    for p in parsed:
        rec = p["rec"]
        loo = dict((s, float(v)) for s, v in (rec.get("credits") or []))
        fwd = dict((s, float(v)) for s, v in (rec.get("forward_credits") or []))
        # sequential per-hop probability gains (multi-SG, Vseq insertion order ==
        # addition order): Δp_sg = P(gold|prefix incl sg) − P(gold|prefix before).
        # Used for BLAME allocation in negative trajectories — the original
        # design's asymmetry (A<0 → borne by harmful sgs, not all sgs): a hop
        # that improved the probability escapes punishment even in a losing
        # trajectory ("只有最后一轮错，第一步应该是对的"); harmful/flat hops
        # carry the negative weighted by |Δp| share.
        dp_map, harm_share = None, None
        vseq = rec.get("Vseq")
        if isinstance(vseq, dict) and len(vseq) >= 2 and \
                all(v is not None for v in vseq.values()):
            prev = math.exp(rec.get("V0") or 0.0)
            dp = {}
            for s, v in vseq.items():
                cur = math.exp(v)
                dp[s] = cur - prev
                prev = cur
            dp_map = dp
            # three-way per-hop classification: effective / flat / harmful.
            # flat ≈ redundancy-by-another-name (added nothing); only genuinely
            # negative hops carry blame (+ an absolute damage term so a
            # catastrophic hop is punished even when the group differential is
            # small); effective hops earn their measured gain, bounded.
            harm = {s: -d for s, d in dp.items() if d < -0.005}
            if harm:
                tot = sum(harm.values())
                harm_share = {s: h / tot for s, h in harm.items()}
        # G: first-attribution — walk sgs in trajectory order
        attributed = set()
        sg_order = []
        for name, _ in p["blocks"]:
            m = re.match(r"sg:(.+)", name)
            if m and m.group(1) not in sg_order:
                sg_order.append(m.group(1))
        # per-sg relation sets (short names) for the AMBIGUOUS adjudicator:
        # relation-overlap with prior sgs separates complementary clauses
        # (disjoint relations, 71% of ambiguous) from duplicate re-retrieval
        # (same relations re-fetched, 21%) — probability cannot, structure can.
        sg_rels_map = defaultdict(set)
        for name, mi in p["blocks"]:
            m2 = re.match(r"sg:(.+)", name)
            if m2:
                c = rec["messages"][mi].get("content", "") or ""
                rm = re.search(r"relations:\s*(.+)", c)
                if rm:
                    for x in re.split(r"[|,]", rm.group(1)):
                        x = x.strip().lower().rsplit(".", 1)[-1]
                        if x:
                            sg_rels_map[m2.group(1)].add(x)
        # ── STRUCTURAL TESTS (deterministic, run FIRST per user's priority) ──
        # per-sg evidence edges (h,t) parsed from tool messages
        sg_edges = defaultdict(list)
        anchors = set()
        later_centers = defaultdict(set)   # sg -> centers of LATER retrievals
        cur_sg = None
        seen_sgs = []
        for m in rec["messages"]:
            c = m.get("content", "") or ""
            role = m.get("role")
            if role == "assistant":
                cm = re.search(r"center:\s*(.+)", c)
                tm = re.findall(r"tool:\s*(\w+)", c)
                if cm and tm and tm[-1] == "retrieve_subgraph":
                    _c = cm.group(1).strip()
                    cur_sg = None
                    for _e in re.split(r"[|,]", _c):
                        _e = _e.strip().strip('"\'')
                        if _e:
                            later_centers[cur_sg].add(norm(_e)) if cur_sg else anchors.add(norm(_e))
                    if cur_sg is None and not anchors:
                        pass
                elif cm and tm and tm[-1] == "retrieve_relations" and not anchors:
                    for _e in re.split(r"[|,]", cm.group(1)):
                        _e = _e.strip().strip('"\'')
                        if _e and not _e.startswith("?"):
                            anchors.add(norm(_e))
            elif role == "tool":
                h = re.search(r"fact_id:\s*(\S+)", c)
                if h:
                    cur_sg = h.group(1)
                    if cur_sg not in seen_sgs:
                        seen_sgs.append(cur_sg)
                    for line in c.split("\n"):
                        for sep in ("-->", "→"):
                            if sep in line:
                                l_, r_ = line.split(sep, 1)
                                for _h in l_.split("|"):
                                    for _t in r_.split("|"):
                                        _h2, _t2 = _h.strip().strip('[]().,;:\'"'), _t.strip().strip('[]().,;:\'"')
                                        if _h2 and _t2 and len(_h2) > 1 and len(_t2) > 1:
                                            sg_edges[cur_sg].append((norm(_h2), norm(_t2)))
                                break

        def _reach(edges, srcs, targets):
            adj = defaultdict(set)
            for a, b in edges:
                adj[a].add(b); adj[b].add(a)
            seen, q = set(srcs), list(srcs)
            while q:
                n = q.pop()
                for m2 in adj.get(n, ()):
                    if m2 not in seen:
                        seen.add(m2); q.append(m2)
            return sum(1 for t in targets if t in seen)

        gold_nodes = [norm(g) for g in p["gold"] if norm(g)]
        _all_edges = [e for es in sg_edges.values() for e in es]
        full_reach = _reach(_all_edges, anchors, gold_nodes) if anchors and gold_nodes else 0
        indispensable = {}
        for s in sg_order:
            if not anchors or not gold_nodes:
                indispensable[s] = False
                continue
            wo = [e for s2, es in sg_edges.items() for e in es if s2 != s]
            indispensable[s] = _reach(wo, anchors, gold_nodes) < full_reach
        # lineage (stepping stone): a later retrieval's center came from this sg's entities
        def _fuzzy_in_set(name, s2_):
            for cand in later_centers.get(s2_, set()):
                if name == cand or name in cand or cand in name:
                    return True
            return False
        lineage = {s: any(
            any(_fuzzy_in_set(e, s2) for e in p["ev_by_sg"].get(s, set()))
            for s2 in sg_order[sg_order.index(s)+1:]) for s in sg_order}

        g_first = defaultdict(float)
        for s in sg_order:
            ev = p["ev_by_sg"].get(s, set())
            new_gold = [gm for gm, g in enumerate(p["gold"])
                        if gm not in attributed and fuzzy_in(g, ev)]
            for gm in new_gold:
                attributed.add(gm)
            if new_gold and p["gold"]:
                g_first[s] = len(new_gold) / len(p["gold"])

        turn_advs = [0.0] * p["n_asst"]
        ai = -1
        for name, msg_idx in p["blocks"]:
            # count only assistant indices: blocks store message idx; map to
            # assistant ordinal
            pass
        # simpler: iterate messages; for each assistant msg determine block
        msgs = rec["messages"]
        blk_by_msg = dict((mi, nm) for nm, mi in p["blocks"])
        a_ord = 0
        for mi, m in enumerate(msgs):
            if m.get("role") != "assistant":
                continue
            blk = blk_by_msg.get(mi, "sg:?")
            if blk == "plan":
                scale = 1.0 if p["r_exp"] > 0 else 0.0
                stats["plan_on" if scale else "plan_off"] += 1
            elif blk == "answer":
                turn_advs[a_ord] = p["a_ans"]
                stats["answer"] += 1
                a_ord += 1
                continue
            else:
                s = blk.split(":", 1)[1] if ":" in blk else None
                val = (g_first.get(s, 0) > 0 or fwd.get(s, 0) > 0.01
                       or loo.get(s, 0) > 0.01)
                scale = 1.0 if val else 0.0
                stats["sg_on" if val else "sg_off"] += 1
            if blk != "answer":
                # v12 DISCRETE VALIDITY CREDIT (user spec, final):
                #   positive traj: effective +1.0·A_exp (吃满), partial +0.5·A_exp,
                #     redundant −0.1·|A_exp|, harmful −0.5·|A_exp|
                #   negative traj: effective/partial → 0 (this behavior is
                #     encouraged by OTHER positive trajectories in the batch —
                #     cross-trajectory aggregation), redundant & harmful eat the
                #     FULL negative (waste in a failed trajectory is part of the
                #     failure). A_exp already carries the δ_abs adjustment.
                ae = p["a_exp"]
                if dp_map is not None and s in dp_map:
                    d = dp_map[s]
                    _loo = loo.get(s, 0)
                    # THREE-LAYER VALIDITY (user final spec, deterministic first):
                    #   1. STRUCTURE: removal breaks anchor→gold connectivity, or
                    #      lineage (a later retrieval's center came from this sg)
                    #      → effective / indispensable
                    #   2. PROBABILITY: LOO>τ (removal drops P) → effective;
                    #      Δp<−τ ∧ no-gold → harmful
                    #   3. NOVELTY: new relations + gain → partial; same relations
                    #      re-fetched → redundant
                    # harmful requires ALL THREE negatives: sequential damage ∧
                    # no gold (competition veto) ∧ NO independent info (fwd flat —
                    # an on-path list-flooded retrieval with fwd>0 and neutral
                    # removal is redundant/partial, not damaging; audited: 10/127
                    # borderline, Gilliam-type wrong-entity retrievals have fwd≤0)
                    _harmful = (d < -0.005 and g_first.get(s, 0) <= 0
                                and fwd.get(s, 0) <= 0.005)
                    # ── DECISION CASCADE (deterministic-first, short-circuit) ──
                    if indispensable.get(s) or lineage.get(s):
                        # L1 STRUCTURE: removal breaks anchor→gold connectivity,
                        # or lineage (later retrieval centers came from this sg)
                        adv = ae if ae > 0 else 0.0              # → 有效
                    elif _harmful:
                        # L2a PROBABILITY: adding it DEGRADED the answer
                        # probability and it carries no gold (competition veto)
                        adv = (-0.5 * abs(ae)) if ae > 0 else ae  # → 有害
                    elif d > 0.005 or _loo > 0.005:
                        # L2b PROBABILITY: brought information at addition, or
                        # removal drops the final probability (indispensable)
                        adv = ae if ae > 0 else 0.0              # → 有效
                    elif fwd.get(s, 0) > 0.005:
                        # L3 NOVELTY: carries independent info (alone-value>0)
                        # but flat in-context → complementary vs duplicate
                        idx = sg_order.index(s) if s in sg_order else 0
                        prior = set().union(*[sg_rels_map.get(o, set())
                                              for o in sg_order[:idx]]) if idx else set()
                        my = sg_rels_map.get(s, set())
                        ov = (len(my & prior) / len(my)) if my else 0.0
                        if ov >= 0.5:
                            adv = (-0.5 * abs(ae)) if ae > 0 else ae   # 拷贝→冗余
                        else:
                            adv = (0.5 * ae) if ae > 0 else 0.0        # 互补→部分有效
                    else:
                        # all signals flat → true redundant
                        adv = (-0.5 * abs(ae)) if ae > 0 else ae      # → 冗余
                else:
                    # single-SG / no-Vseq fallback: G/F/L binary validity
                    val = (g_first.get(s, 0) > 0 or fwd.get(s, 0) > 0.01
                           or loo.get(s, 0) > 0.01)
                    if val and ae > 0:
                        adv = ae
                    elif val:
                        adv = 0.0
                    else:
                        adv = (-0.5 * abs(ae)) if ae > 0 else ae
                turn_advs[a_ord] = adv
            a_ord += 1
        if not any(b == "answer" for b, _ in p["blocks"]) and p["n_asst"] > 0:
            # no answer block (rounds exhausted): attach the answer axis to the
            # LAST turn so its punishment is never silently dropped (Bush/Kerry
            # bug: never-answered trajectory kept +0.578×4 exploration credit
            # with no answer penalty → net positive on a failed trajectory)
            turn_advs[p["n_asst"] - 1] += p["a_ans"]
            stats["no_answer_attach"] += 1
        rec["turn_advantages"] = turn_advs
        rec["advantage"] = round(sum(turn_advs), 4)
        rec["_v0_fields"] = {"r_exp": round(p["r_exp"], 4), "a_exp": round(p["a_exp"], 4),
                             "f_ans": round(p["f_ans"], 4), "a_ans": round(p["a_ans"], 4),
                             "insufficient": p["insufficient"]}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    out.close()
    print(f"recomputed {len(parsed)} records → {args.out}")
    print(f"sg turns: valued={stats['sg_on']} zero={stats['sg_off']}; "
          f"plan: on={stats['plan_on']} off={stats['plan_off']}")


if __name__ == "__main__":
    main()
