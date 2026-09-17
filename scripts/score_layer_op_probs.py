"""Teacher-forcing probability family for layer-op modules (user ruling
2026-09-17: p_gain was a COVERAGE ratio, not a probability — the trajectory
must carry REAL model values).

Per trajectory, per information module (v4 blocks = each sg delivery):
  p0       = P_base(gold | question only)                — model's direct answer
  pF       = P_base(gold | question + ALL module texts)  — full evidence
  p_minus  = P_base(gold | question + all EXCEPT module i)  — counterfactual
             removal; l_i = pF − p_minus is the removal damage
  p_alone  = P_base(gold | question + ONLY module i)     — module standalone
Scores via the running vLLM server (/v1/completions, echo+logprobs), the
HTTP equivalent of OfflineVLLM.gold_logprob_batch (marker "\n\nAnswer: ",
mean gold-token logprob, single gold string " | ".join(sorted(gold))).
Module text follows the seq_advantage display cap (15 lines).

Usage: python scripts/score_layer_op_probs.py reports/<run>.json \
           [--out specs/layer_op_probs_2026-09-17.json]
"""
import concurrent.futures as cf
import json
import re
import sys

import requests

sys.path.insert(0, "scripts")
from annotate_layer_ops import annotate, mark_break_points, \
    mark_necessity, reconcile_necessity

BASE = "http://127.0.0.1:8000/v1/completions"
MODEL = "Qwen3.5-9B"
MARKER = "\n\nAnswer: "
MAX_LINES = 15

PICK = ["WebQTest-1379:0", "WebQTest-1379:1", "WebQTest-1797:1",
        "WebQTrn-567_11fd:0", "WebQTrn-567_df97:0", "WebQTrn-2784_b64:2",
        "WebQTrn-21_:0", "WebQTrn-2209_c13:0",
        "WebQTrn-2316_b8e:0", "WebQTrn-1731_4ee:0", "WebQTrn-2784_b64:0",
        "WebQTest-626_01a:0", "WebQTrn-2576_872:0"]


def trunc(text, max_lines=MAX_LINES):
    lines = [l for l in text.split("\n") if l.strip()]
    return "\n".join(lines[:max_lines])


def gold_logprob(prefix, gold):
    """Mean logprob of the gold tokens under teacher forcing (echo mode).
    The final echo token is the 1 generated token (max_tokens=1) — dropped."""
    try:
        r = requests.post(BASE, json={
            "model": MODEL, "prompt": prefix + MARKER + gold,
            "max_tokens": 1, "echo": True, "logprobs": 1,
        }, timeout=120)
        r.raise_for_status()
        lp = r.json()["choices"][0]["logprobs"]
        toks, tl = lp["tokens"], lp["top_logprobs"] or []
        # marker boundary: last 'Answer' token followed by ':'
        boundary = None
        for i in range(len(toks) - 2, 0, -1):
            if toks[i].strip() == "Answer" and toks[i + 1].strip() == ":":
                boundary = i + 1
                break
        if boundary is None:
            return None
        lps = []
        for j in range(boundary + 1, len(toks) - 1):   # -1: drop gen token
            e = tl[j] if j < len(tl) and tl[j] else None
            v = list(e.values())[0] if e else None
            if isinstance(v, float):
                lps.append(v)
        return sum(lps) / len(lps) if lps else None
    except Exception:
        return None


def score_case(rec, c):
    q = rec.get("question", "")
    gold = " | ".join(sorted(rec["_gold_list"])) or "unknown"
    blocks = c.get("blocks", [])
    texts = [trunc(rec["trajectory"][b["idx"]]["content"]) for b in blocks]
    pairs, meta = [], []
    pairs.append((f"Question: {q}", gold)); meta.append(("p0", None))
    all_txt = "\n\n".join(t for t in texts if t)
    pairs.append((f"Question: {q}\n\nEvidence:\n{all_txt}", gold))
    meta.append(("pF", None))
    for i, t in enumerate(texts):
        if not t:
            continue
        minus = "\n\n".join(x for j, x in enumerate(texts) if j != i and x)
        prefix = (f"Question: {q}\n\nEvidence:\n{minus}" if minus
                  else f"Question: {q}")
        pairs.append((prefix, gold)); meta.append(("p_minus", i))
        pairs.append((f"Question: {q}\n\nEvidence:\n{t}", gold))
        meta.append(("p_alone", i))
    with cf.ThreadPoolExecutor(8) as ex:
        vals = list(ex.map(lambda p: gold_logprob(*p), pairs))
    import math
    out = {"p0": None, "pF": None, "modules": {}}
    for (kind, i), v in zip(meta, vals):
        p = math.exp(v) if v is not None else None
        if kind == "p0":
            out["p0"] = p
        elif kind == "pF":
            out["pF"] = p
        else:
            m = out["modules"].setdefault(i, {})
            m["p_" + ("minus" if kind == "p_minus" else "alone")] = p
    pF = out["pF"]
    for i, m in out["modules"].items():
        pm = m.get("p_minus")
        m["l_i"] = round(pF - pm, 4) if (pF is not None and pm is not None) \
            else None
    return out


def main():
    path = sys.argv[1]
    out_path = "specs/layer_op_probs_2026-09-17.json"
    for a in sys.argv[2:]:
        if a == "--out":
            out_path = sys.argv[sys.argv.index(a) + 1]
    import ast
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
    mark_break_points(cases,
                      "data/cwq_processed/test_v4_repaired.pkl")
    reconcile_necessity(cases)
    results = {}
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
            results[key] = score_case(rec, c)
            r = results[key]
            print(f"  p0={r['p0']:.4f} pF={r['pF']:.4f}" if r["p0"] and r["pF"]
                  else "  (score failed)")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
