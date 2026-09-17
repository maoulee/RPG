"""Teacher-forcing probability family for layer-op modules — v2, ALIGNED
with the existing IG machinery (user correction 2026-09-17: the earlier
rewrite skipped established mechanisms; valid/invalid/redundant are
PROBABILITY rulings, structure rules necessity only).

Reuses the seq_advantage semantics exactly:
  - per-entity scoring: one pair per gold entity (cap 8, deterministic
    sample seed), V = log-mean-exp — length-debiased
  - signals per module: d (sequential gain, Vseq diff), l = pF − p_minus
    (leave-one-out damage, probability domain), f = p_alone − p0 (forward
    standalone), g (gold first delivery), N (displayed-edge novelty)
  - v1.5 cascade labels (TAU=0.005, N_THR=0.2, U_THR=0.005):
      L1 structure: pathway-necessary ∨ lineage → effective
      L2 probability: d<−τ ∧ g=0 ∧ f≤τ → harmful;  d>τ ∨ l>τ → effective
      L3 novelty:    g>0 ∨ (N≥0.2 ∧ f>0.005) → effective;
                     N<0.2 → redundant_dup;  N≥0.2 ∧ f≤0.005 → redundant_irr
Module segmentation = v4 blocks (incremental sg deliveries). Scores via the
running vLLM server (echo+logprobs), the HTTP twin of
OfflineVLLM.gold_logprob_batch.

Usage: python scripts/score_layer_op_probs.py reports/<run>.json \
           [--out specs/layer_op_probs_2026-09-17.json]
"""
import ast
import concurrent.futures as cf
import json
import math
import random
import re
import sys

import requests

sys.path.insert(0, "scripts")
from annotate_layer_ops import (annotate, mark_break_points,
                                mark_necessity, reconcile_necessity,
                                edges_of, norm)

BASE = "http://127.0.0.1:8000/v1/completions"
MODEL = "Qwen3.5-9B"
MARKER = "\n\nAnswer: "
MAX_LINES = 15
MAX_ENTITIES = 8
TAU = 0.005
N_THR = 0.2
U_THR = 0.005

PICK = ["WebQTest-1379:0", "WebQTest-1379:1", "WebQTest-1797:1",
        "WebQTrn-567_11fd:0", "WebQTrn-567_df97:0", "WebQTrn-2784_b64:2",
        "WebQTrn-21_:0", "WebQTrn-2209_c13:0",
        "WebQTrn-2316_b8e:0", "WebQTrn-1731_4ee:0", "WebQTrn-2784_b64:0",
        "WebQTest-626_01a:0", "WebQTrn-2576_872:0"]


def trunc(text, max_lines=MAX_LINES):
    return "\n".join(l for l in text.split("\n") if l.strip())[:max_lines] \
        if False else "\n".join(
            [l for l in text.split("\n") if l.strip()][:max_lines])


def gold_logprob(prefix, gold):
    try:
        r = requests.post(BASE, json={
            "model": MODEL, "prompt": prefix + MARKER + gold,
            "max_tokens": 1, "echo": True, "logprobs": 1,
        }, timeout=180)
        r.raise_for_status()
        lp = r.json()["choices"][0]["logprobs"]
        toks, tl = lp["tokens"], lp["top_logprobs"] or []
        boundary = None
        for i in range(len(toks) - 2, 0, -1):
            if toks[i].strip() == "Answer" and toks[i + 1].strip() == ":":
                boundary = i + 1
                break
        if boundary is None:
            return None
        lps = []
        for j in range(boundary + 1, len(toks) - 1):   # drop the 1 gen token
            e = tl[j] if j < len(tl) and tl[j] else None
            v = list(e.values())[0] if e else None
            if isinstance(v, float):
                lps.append(v)
        return sum(lps) / len(lps) if lps else None
    except Exception:
        return None


def _lme(vs):
    """log-mean-exp (seq_advantage's length-debiased V)."""
    vs = [x for x in vs if x is not None]
    if not vs:
        return None
    m = max(vs)
    return m + math.log(sum(math.exp(x - m) for x in vs) / len(vs))


def score_case(rec, c, ti):
    q = rec.get("question", "")
    gold_list = sorted(set(str(g) for g in rec["_gold_list"]
                           if str(g).strip())) or ["unknown"]
    if len(gold_list) > MAX_ENTITIES:
        rng = random.Random(1234 + ti)
        gold_list = sorted(rng.sample(gold_list, MAX_ENTITIES))
    blocks = c.get("blocks", [])
    texts = [trunc(rec["trajectory"][b["idx"]]["content"]) for b in blocks]
    # novelty N (v1.5 semantics): fraction of this module's displayed edges
    # that are FIRST deliveries
    seen = set()
    novelties = []
    for b in blocks:
        es = edges_of(rec["trajectory"][b["idx"]]["content"])
        first = sum(1 for e in es if e not in seen)
        seen.update(es)
        novelties.append(first / len(es) if es else 0.0)
    # lineage: a LATER module's call center came from this module's evidence
    lineage = []
    for j, b in enumerate(blocks):
        m = re.search(r"^center:\s*(.+)$",
                      rec["trajectory"][max(0, b["idx"] - 1)]["content"], re.M) \
            if rec["trajectory"][b["idx"] - 1]["role"] == "assistant" else None
        cen = norm(m.group(1).split(" | ")[0]) if m else None
        hit = False
        if cen:
            for k in range(j + 1, len(blocks)):
                if k == j:
                    continue
                es = edges_of(rec["trajectory"][blocks[k]["idx"]]["content"])
                if any(h == cen or t == cen for (h, _r, t) in es):
                    hit = True
                    break
        lineage.append(hit)
    # g: gold first delivery per module (text hit)
    gseen, gfirst = set(), []
    gold_n = {norm(g) for g in gold_list}
    for b in blocks:
        content_n = norm(rec["trajectory"][b["idx"]]["content"])
        here = {g for g in gold_n if g in content_n}
        gfirst.append(bool(here - gseen))
        gseen |= here
    # pairs (per entity) — V0, Vseq cumulative, Vloo minus, Valone
    pairs, meta = [], []
    all_txt = "\n\n".join(t for t in texts if t)
    for g in gold_list:
        pairs.append((f"Question: {q}", g)); meta.append(("V0", None))
        pairs.append((f"Question: {q}\n\nEvidence:\n{all_txt}", g))
        meta.append(("VF", None))
        acc = ""
        for i, t in enumerate(texts):
            acc = (acc + "\n\n" + t).strip() if t else acc
            pairs.append((f"Question: {q}\n\nEvidence:\n{acc}", g))
            meta.append(("Vseq", i))
        for i, t in enumerate(texts):
            minus = "\n\n".join(x for j, x in enumerate(texts) if j != i and x)
            prefix = (f"Question: {q}\n\nEvidence:\n{minus}" if minus
                      else f"Question: {q}")
            pairs.append((prefix, g)); meta.append(("Vloo", i))
            if t:
                pairs.append((f"Question: {q}\n\nEvidence:\n{t}", g))
                meta.append(("Valone", i))
    with cf.ThreadPoolExecutor(8) as ex:
        vals = list(ex.map(lambda p: gold_logprob(*p), pairs))
    raw = {}
    for (kind, i), v in zip(meta, vals):
        raw.setdefault((kind, i), []).append(v)
    V = {k: _lme(vs) for k, vs in raw.items()}
    p = lambda v: math.exp(v) if v is not None else None
    out = {"p0": p(V.get(("V0", None))), "pF": p(V.get(("VF", None))),
           "modules": {}}
    pF = out["pF"]
    prev_seq_p = out["p0"]            # d in the PROBABILITY domain (v1.5:
    for i in range(len(blocks)):      # dp[s] = exp(Vseq[s]) − prev, log-domain
        vs = V.get(("Vseq", i))       # diffs are always >τ near zero)
        vl = V.get(("Vloo", i))
        va = V.get(("Valone", i))
        vs_p = p(vs)
        d = (vs_p - prev_seq_p) if (vs_p is not None
                                    and prev_seq_p is not None) else None
        # l in PROBABILITY domain (pF − p_minus), per _ig_credit
        pl, pa = p(vl), p(va)
        l = (pF - pl) if (pF is not None and pl is not None) else None
        f = (pa - out["p0"]) if (pa is not None and out["p0"] is not None) \
            else None
        nec = blocks[i].get("necessary")
        # v1.5 cascade — structure rules NECESSITY (L1), probability rules
        # the effective/redundant classes (user ruling 2026-09-17)
        if nec == "yes" or lineage[i]:
            cls = "effective"
        elif d is not None and d < -TAU and not gfirst[i] \
                and (f is not None and f <= TAU):
            cls = "harmful"
        elif (d is not None and d > TAU) or (l is not None and l > TAU):
            cls = "effective"
        elif gfirst[i] or (novelties[i] >= N_THR and f is not None
                           and f > U_THR):
            cls = "effective"
        elif novelties[i] < N_THR:
            cls = "redundant_dup"
        else:
            cls = "redundant_irr"
        out["modules"][str(i)] = {
            "d": None if d is None else round(d, 4),
            "l": None if l is None else round(l, 4),
            "f": None if f is None else round(f, 4),
            "p_minus": None if pl is None else round(pl, 4),
            "p_alone": None if pa is None else round(pa, 4),
            "g": gfirst[i], "N": round(novelties[i], 3),
            "lineage": lineage[i], "cls": cls,
        }
        prev_seq_p = vs_p if vs_p is not None else prev_seq_p
    return out


def main():
    path = sys.argv[1]
    out_path = "specs/layer_op_probs_2026-09-17.json"
    for a in sys.argv[2:]:
        if a == "--out":
            out_path = sys.argv[sys.argv.index(a) + 1]
    ops, cases = annotate(path)
    recs = {}
    for rec in json.load(open(path)):
        tr = rec["trajectory"]
        if isinstance(tr, str):
            tr = ast.literal_eval(tr)
        if isinstance(rec["gold"], list):
            gl = rec["gold"]
        else:
            try:
                gl = json.loads(rec["gold"])
            except Exception:
                gl = ast.literal_eval(rec["gold"])
        rec["_gold_list"] = gl
        rec["trajectory"] = tr
        recs[(rec["case_id"], str(rec.get("sample_idx")))] = rec
    mark_necessity(cases, recs)
    mark_break_points(cases, "data/cwq_processed/test_v4_repaired.pkl")
    reconcile_necessity(cases)
    results = {}
    ti = 0
    for p in PICK:
        pref, s = (p.split(":") + [""])[:2] if ":" in p else (p, "")
        for c in cases:
            if not c["case_id"].startswith(pref):
                continue
            if s and str(c["sample"]) != s:
                continue
            if not c["ops"]:
                continue
            rec = recs[(c["case_id"], str(c["sample"]))]
            key = f"{c['case_id']}|s{c['sample']}"
            print(f"scoring {key} ({len(c['blocks'])} blocks)...", flush=True)
            results[key] = score_case(rec, c, ti)
            ti += 1
            r = results[key]
            if r["p0"] is not None and r["pF"] is not None:
                clss = [m["cls"] for m in r["modules"].values()]
                print(f"  p0={r['p0']:.4f} pF={r['pF']:.4f}  "
                      f"classes={clss}")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
