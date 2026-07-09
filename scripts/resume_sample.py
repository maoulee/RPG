#!/usr/bin/env python3
"""Auto-resume val.pkl sampling: runs 50-case batches back-to-back, writes
incrementally, and tracks progress so it can be killed/restarted freely.

Each batch writes to reports/samp_val_pool/batch_NNN.jsonl (incremental).
A state file tracks the next case offset to run.

Usage:
  python scripts/resume_sample.py --batch-size 50 --max-batches 60
"""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "reports/samp_val_pool"
STATE = POOL / "state.json"
TOTAL_CASES = 3519  # val.pkl size

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"next_offset": 0, "batches_done": 0}

def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--max-batches", type=int, default=999)
    ap.add_argument("--pkl", default="data/cwq_processed/val.pkl")
    args = ap.parse_args()

    st = load_state()
    POOL.mkdir(parents=True, exist_ok=True)

    while st["next_offset"] < TOTAL_CASES and st["batches_done"] < args.max_batches:
        start = st["next_offset"]
        end = min(start + args.batch_size, TOTAL_CASES)
        batch_n = st["batches_done"]
        out = POOL / f"batch_{batch_n:03d}.jsonl"

        print(f"\n>>> batch {batch_n}: case {start}-{end}  {time.strftime('%H:%M:%S')}", flush=True)
        t0 = time.time()
        # No timeout here — the batch runs to completion however long it takes.
        # Each batch writes incrementally, so a kill only loses the in-flight
        # batch, not earlier ones. state.json tracks the resume point.
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts/sample_trajectories.py"),
             "--mixed",
             "--cwq-pkl", str(ROOT / args.pkl),
             "--webqsp-pkl", "",
             "--cwq-start", str(start),
             "--cwq-limit", str(args.batch_size),
             "--webqsp-limit", "0",
             "--num-samples", "4",
             "--batch-chunk", "100",
             "--output", str(out)],
            env={**os.environ,
                 "KGQA_LLM_BATCH_TEMPERATURE": "0.8",
                 "KGQA_LLM_BATCH_TOP_P": "0.95"},
            capture_output=True, text=True,
        )
        elapsed = time.time() - t0
        # Extract summary line
        for line in r.stdout.splitlines():
            if any(k in line for k in ("Sampled", "SFT:", "GRPO:", "flagged")):
                print(f"  {line.strip()}", flush=True)
        if r.returncode != 0:
            print(f"  batch {batch_n} FAILED (rc={r.returncode}, {elapsed:.0f}s)", flush=True)
            print(f"  stderr tail: {r.stderr[-300:]}", flush=True)
            # Still advance — don't get stuck on one batch
        st["next_offset"] = end
        st["batches_done"] = batch_n + 1
        save_state(st)
        print(f"  done in {elapsed:.0f}s, next offset={end}", flush=True)

    print(f"\n=== Sampling complete: {st['batches_done']} batches, "
          f"offset {st['next_offset']}/{TOTAL_CASES} ===", flush=True)

if __name__ == "__main__":
    main()
