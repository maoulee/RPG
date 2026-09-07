#!/usr/bin/env python3
"""SEQ agent evaluation via the HTTP batch port (production path).

Runs the SEQ iterative-subgraph agent on the CWQ test split using
``run_seq_react_batch`` (turn-synchronous batched LLM calls — the fast,
connection-stable path per the batch-port directive). Model is selected by
the ``KGQA_MODEL_NAME`` env var:

    KGQA_MODEL_NAME=seq_grpo_v1   → trained LoRA (vLLM --lora-modules name)
    KGQA_MODEL_NAME=Qwen3.5-9B    → base (default)

Usage:
    KGQA_MODEL_NAME=seq_grpo_v1 N_CASES=100 python scripts/run_seq_eval.py
    KGQA_MODEL_NAME=Qwen3.5-9B  N_CASES=100 python scripts/run_seq_eval.py   # base ref

Output: reports/seq_eval_<model>_<n>.json  +  prints mean F1 / hit / S_plan...
"""
import asyncio, json, os, pickle, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_PKL = os.environ.get(
    "TEST_PKL",
    "/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl")


def _load(n):
    samples = pickle.loads(Path(TEST_PKL).read_bytes())
    pool = [s for s in samples if s.get("a_entity")]
    # optional: filter to specific case ids (comma-sep CASE_IDS env) for trajectory dumps
    ids = os.environ.get("CASE_IDS", "").strip()
    if ids:
        idset = {x.strip() for x in ids.split(",") if x.strip()}
        pool = [s for s in pool if s["id"] in idset]
    elif n > 0:
        # START/END slice (block runs — the 3.4k single batch deadlocks the
        # turn-synchronous coordinator; blocks of ≤500 are stable)
        start = int(os.environ.get("START", "0"))
        end = int(os.environ.get("END", str(n)))
        pool = pool[start:end]
    return pool


class Args:
    agent_max_iters = 16
    agent_max_tokens = 1024
    batch_chunk = 25


def main():
    n = int(os.environ.get("N_CASES", "100"))
    model = os.environ.get("KGQA_MODEL_NAME", "Qwen3.5-9B")
    out_dir = Path(os.environ.get("OUT_DIR", "reports"))
    tag = os.environ.get("TAG", model.replace("/", "_"))
    out_path = out_dir / f"seq_eval_{tag}_{n}.json"

    print(f"═══ SEQ eval: model={model}  cases={n}  → {out_path} ═══", flush=True)
    cases = _load(n)
    print(f"  loaded {len(cases)} cases", flush=True)

    # build (sample, pilot_row, idx) triples — pilot_row mirrors seq_rollout
    cases_to_run = []
    for i, s in enumerate(cases, 1):
        pr = {"case_id": s["id"], "question": s["question"],
              "gt_answers": s.get("a_entity", [])}
        cases_to_run.append((s, pr, i))

    from kgqa.agent.seq_react_loop import run_seq_react_batch

    t0 = time.perf_counter()
    results = asyncio.run(run_seq_react_batch(cases_to_run, Args()))
    dt = time.perf_counter() - t0

    # flatten + score
    rows = []
    for s, pr, r in results:
        rows.append({
            "case_id": pr["case_id"], "idx": pr.get("case_id"),
            "question": pr["question"], "gold": pr["gt_answers"],
            "answer": r.get("llm_answer_str", "") or r.get("llm_answer", ""),
            "llm_f1": float(r.get("llm_f1", 0) or 0),
            "llm_hit": bool(r.get("llm_hit", False)),
            "failed": bool(r.get("failed", False)) or bool(r.get("failure_reason")),
            "failure_reason": r.get("failure_reason", ""),
            "n_turns": sum(1 for st in r.get("agent_trajectory", [])
                           if st.get("role") == "assistant"),
            "agent_trajectory": r.get("agent_trajectory", []),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    json.dump({"model": model, "n": len(rows), "wall_s": round(dt, 1),
               "results": rows}, open(out_path, "w"), indent=2, ensure_ascii=False)

    n_r = len(rows)
    f1 = sum(r["llm_f1"] for r in rows) / n_r if n_r else 0
    hit = sum(1 for r in rows if r["llm_hit"]) / n_r if n_r else 0
    failed = sum(1 for r in rows if r["failed"])
    avg_turns = sum(r["n_turns"] for r in rows) / n_r if n_r else 0
    print(f"\n═══ {model} | {n_r} cases | {dt:.0f}s ({dt/n_r:.1f}s/case) ═══", flush=True)
    print(f"  F1   = {f1:.4f}", flush=True)
    print(f"  hit  = {hit:.4f}", flush=True)
    print(f"  failed = {failed}/{n_r}  | avg turns = {avg_turns:.1f}", flush=True)
    print(f"  → {out_path}", flush=True)


if __name__ == "__main__":
    main()
