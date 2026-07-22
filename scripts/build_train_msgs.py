#!/usr/bin/env python3
"""Convert sampled agent results (agent_trajectory) → training `messages` + S_*.

The sampled records (sample_full_test.py / full3k_split/*.jsonl) store
`agent_trajectory` in OpenAI tool-call shape ({role:tool, name, content}) with
NO S_plan/S_select/S_reason. The per-stage trainer needs the flattened chat
`messages` (system, user, assistant, user-toolresult, ...) plus the three stage
scores. This script does both:

  1. score_case(record) → S_plan/S_select/S_reason (reuses the live scorer).
  2. agent_trajectory → messages:
       system = agents_md()        (MASKED at train time — only assistant turns
                                    are labeled, so its exact content is not
                                    loss-relevant; it just must render valid
                                    <|im_start|> spans)
       user   = "Question: <q>"    (also masked)
       assistant turn → {role:assistant, content}      (drop `reasoning` key)
       tool result    → {role:user, content:"Tool result (NAME): <json>"}
                        (restores the prefix the live conversation uses, so the
                        masked context matches inference distribution)

Output schema matches the proven test_split/train_msgs.jsonl:
    {case_id, sample_id, messages, llm_f1, S_plan, S_select, S_reason,
     gt_answers, question, agent_failed}

Usage:
    python scripts/build_train_msgs.py \
        --input data/offline_grpo/full3k_split/train.jsonl \
        --output data/offline_grpo/full3k_split/train_msgs.jsonl
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_stage_scorer import score_case
from kgqa.agent.react_loop import agents_md


def traj_to_messages(rec, sys_prompt):
    msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Question: {rec.get('question','')}"},
    ]
    for e in rec.get("agent_trajectory") or []:
        role = e.get("role")
        if role == "assistant":
            m = {"role": "assistant", "content": e.get("content", "")}
            # preserve the model's <think> reasoning (chat template renders it via
            # reasoning_content → <think>...</think> before the action). Without this
            # the training data loses the CoT and the model isn't trained to reason.
            if e.get("reasoning"):
                m["reasoning_content"] = e["reasoning"]
            msgs.append(m)
        elif role == "tool":
            name = e.get("name") or ""
            content = e.get("content", "") or ""
            prefix = f"Tool result ({name}): " if name else ""
            msgs.append({"role": "user", "content": prefix + content})
        elif role == "user":
            msgs.append({"role": "user", "content": e.get("content", "")})
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.input) if l.strip()]
    print(f"Loaded {len(recs)} records from {args.input}")
    sys_prompt = agents_md()
    print(f"  system prompt: {len(sys_prompt)} chars")

    out, skipped = [], 0
    for r in recs:
        if r.get("agent_failed") or not r.get("agent_trajectory"):
            skipped += 1
            continue
        try:
            s = score_case(r)
        except Exception:
            skipped += 1
            continue
        msgs = traj_to_messages(r, sys_prompt)
        # need >= system+user+1 assistant to be trainable
        if sum(1 for m in msgs if m["role"] == "assistant") < 1:
            skipped += 1
            continue
        out.append({
            # BASE case_id (strip the per-sample hash) so build_advantage_dataset
            # and build_hybrid_dataset group ALL samples of a case together for
            # GRPO group-baselining + per-case SFT-seed selection. sample_id
            # (run) disambiguates within-group.
            "case_id": r["case_id"].split("_")[0],
            "sample_id": r.get("run", 0),
            "messages": msgs,
            "llm_f1": r.get("llm_f1", 0.0),
            "S_plan": s.get("S_plan"),
            "S_select": s.get("S_select"),
            "S_reason": s.get("S_reason"),
            "gt_answers": r.get("gt_answers"),
            "question": r.get("question"),
            "agent_failed": False,
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cases = len(set(r["case_id"].split("_")[0] for r in out))
    print(f"Written {len(out)} records ({cases} cases) to {args.output}  (skipped {skipped})")


if __name__ == "__main__":
    main()
