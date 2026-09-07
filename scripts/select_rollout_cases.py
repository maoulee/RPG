#!/usr/bin/env python3
"""Select the training-informative case subset for GRPO rollout.

Attribution (rebase 3-seed CWQ base, 2026-08-14): relation-selection errors carry
72.6% of the F1 loss (39.7% variance + 32.9% stable-wrong); intent/noise 26.4%;
answer-size 0.9%. GRPO signal only exists where the group has reward spread —
stable-correct cases produce all-f1=1 groups → exactly-zero gradient (20% of v5
was zero-advantage dead weight). Rolling out ONLY the informative cases cuts
rollout time ~3x with zero mathematical loss.

Selection = wrong cases (mean F1 < 1) + unstable cases (F1 flips across seeds)
from multi-seed eval reports. Stable-correct cases are dropped (keep `--keep-correct N`
as a calibration buffer if ever needed).

Usage:
  python scripts/select_rollout_cases.py \
      --tags rebase_cwq_base_s11 rebase_cwq_base_s22 rebase_cwq_base_s33 \
      --out tmp/rollout_case_filter.txt
  # then: CASE_FILTER=tmp/rollout_case_filter.txt N_CASES=0 python <rollout>
"""
import argparse, json, statistics as st
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True,
                    help="multi-seed eval report tags (reports/seq_eval_<tag>_100.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-correct", type=int, default=0)
    args = ap.parse_args()

    runs = [{r["case_id"]: r for r in json.load(open(f"reports/seq_eval_{t}_100.json"))["results"]}
            for t in args.tags]
    cases = sorted(set.intersection(*[set(d) for d in runs]))

    sel, n_wrong, n_flip, n_stable_correct = [], 0, 0, 0
    for c in cases:
        f1s = [d[c]["llm_f1"] for d in runs]
        if st.mean(f1s) < 0.99:
            sel.append(c); n_wrong += 1
        elif max(f1s) - min(f1s) > 0.01:
            sel.append(c); n_flip += 1
        else:
            n_stable_correct += 1
    kept_correct = [c for c in cases if c not in set(sel)][: args.keep_correct]
    sel.extend(kept_correct)

    Path(args.out).write_text("\n".join(sorted(sel)) + "\n")
    print(f"{len(cases)} cases → selected {len(sel)} "
          f"(wrong {n_wrong} + flip-correct {n_flip} + correct-buffer {len(kept_correct)}; "
          f"dropped stable-correct {n_stable_correct - len(kept_correct)})")
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
