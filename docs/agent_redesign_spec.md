# RPG Agent Redesign — Spec for Continuation

> Status: model-driven retrieval SOLVED (gt_hit 97%), 1-hop winning (+6.2 F1). 2-hop answer blocked by evidence-presentation issue. This spec captures the full diagnosis + the user's design direction for the next phase.

---

## 1. What's Done (validated on WebQSP 100-case A/B, branch `agent-toolcall`)

### Architecture
- **Native tool_calls** (Qwen3.6-27B-FP8 + `--tool-call-parser qwen3_coder`).
- **Independent module** `kgqa/agent/` (loop.py, harness.py, tools.py, AGENTS.md). Does NOT touch kgqa/stages/*.
- **Model-autonomous**: AGENTS.md + tools given once; model decides calls; harness enforces ORDER only (INIT→RETRIEVE→SELECT→EXPAND→ANSWER→DONE).
- **Harness** rejects out-of-order/skip/merge calls + re-prompts + deterministic fallback.

### Tool set (current)
| tool | what it does | status |
|---|---|---|
| `decompose` | model → {facts[], conditions[]} | ✅ works, elicits precise relation_hint |
| `retrieve` | GTE(hint) → stores relation sets per fact | ✅ model-driven, fixes the 46% retrieval miss |
| `select` | stage_5_graph_traversal(multi-step) + compress_paths → evidence | ✅ traversal correct (gt_hit 97%), ❌ evidence presentation broken |
| `expand_branch` | drill into a branch's candidates | ⚙️ works mechanically but branch candidates missing CVT-expanded entities |
| `answer` | model emits entities | ✅ |

### Results
| metric | v2 stage baseline | agent (this work) | delta |
|---|---|---|---|
| gt_hit (retrieval) | 91% | **97%** | **+6** ✅ |
| 1-hop F1 | 74.9% | **81.1%** | **+6.2** ✅ |
| 2-hop F1 | 81.0% | ~58% | **−23** ❌ |
| 2-hop recall R | — | 0.679 | under-output |

### Root cause of 2-hop failure
`compress_paths` returns pattern-level candidates = raw path endpoints (CVT node IDs, not expanded). But `cs.answer_candidates` (from `_last_step_candidates` in stage_5) DOES include CVT-expanded entities (e.g. Kasich, Strickland). The model sees "branch #11 governing_officials → 0 candidates" but Kasich is in the flat `answer_candidates`. This disconnect → the model can't connect candidates to branches → wastes iterations or picks wrong.

---

## 2. The User's Design Direction (for the next phase)

### Core insight: don't look at hit rate — look at whether the model SELECTS the right path

> "命中率不重要，关键是模型是否选择对了" — gt_hit (retrieval found the answer) is not the goal. The goal is the model **selecting the most appropriate path** and reasoning to the correct answer. The score is a function of path SELECTION quality, not retrieval coverage.

### The paradigm: Stage 7 = path selection, Stage 8 = branch reasoning

The pipeline's essence maps to:
- **Stage 7's core role = SELECT PATHS** — from all traversed patterns, pick the ones that best match the question.
- **Stage 8's core role = REASON on the selected branch** — expand the selected branch's evidence and derive the answer.

In the agent, this becomes:
1. `select` returns a **structured pattern-tree overview** (all branches, numbered, with candidate info).
2. The model **analyzes which branch best answers the question** (this IS Stage 7's selection, done by the model not a separate LLM call).
3. `expand_branch(N)` **expands the selected branch** — shows the detailed evidence (triples, CVT attributes, candidates) for that branch. This IS Stage 8's evidence expansion.
4. `answer` — the model reasons from the expanded branch.

### What "structured expansion" means (the user's specification)

> "我们对模式路径做结构化展开是让模型分析哪个分支更好地回答问题，Stage 8则展开对应的分支做推理"

- The **overview** (`select`) shows the tree structure: each branch's relation chain + candidate count + key candidates. The model uses this to JUDGE which branch is relevant (like Stage 7's selection).
- The **expansion** (`expand_branch(N)`) shows the FULL evidence for branch N: the triples, CVT attributes (office, from-date, to-date), and named entities. The model uses this to REASON (like Stage 8).
- The model may expand 1-N branches (or none if the overview is sufficient).

### Numbering format (user's specification)

> "编号最好放在每个分支的右侧" + "树状图没有你想的这么平整，因为有些路径是最后一跳才分开的，因此需要右边放置，以Stage 8的那种形式"

- Branch numbers (#1, #2, ...) go on the **RIGHT side** of each leaf/fork line.
- The tree is NOT flat — some paths only split at the last hop. The numbering follows the trie structure (from `_render_path_tree` in formatting.py), placing numbers at the branching points, not all at level 1.
- Use Stage 8's trie format (YAML-like nested indentation from `_render_path_tree`).

---

## 3. What Needs Fixing (the blockers)

### Blocker A: compress_paths candidates don't include CVT-expanded entities

**Current**: `compress_paths` (path_utils.py:133) extracts candidates from path endpoints. For CVT relations (e.g. `governmental_jurisdiction → governing_officials → CVT → office_holder`), the endpoint is the CVT node (m.0xxx), not the office_holder name (Kasich).

**Needed**: The pattern candidates in the `select` overview MUST include the CVT-expanded named entities (what `_last_step_candidates` in stage_5 produces = `cs.answer_candidates`). The model needs to see "branch #N → Kasich, Strickland" not "branch #N → 0 candidates".

**Approach**: In `_do_select` (tools.py), after compress_paths, enrich each pattern's candidates with the corresponding entries from `cs.answer_candidates`. Map answer_candidates back to patterns by checking which paths/relation-chains they belong to. OR: use `build_pattern_evidence_triples` (formatting.py:186) which DOES handle CVT expansion via `tree_data` — it builds `PatternEvidence` objects with proper candidates + tree_data (the nested trie with CVT attributes displayed).

**Recommended**: replace the current `compress_paths` + manual evidence building in `_do_select` with `build_pattern_evidence_triples` + `_render_path_tree` from formatting.py. These are the PROVEN Stage 8 evidence builders that correctly expand CVTs and render the trie.

### Blocker B: the overview must present the tree (not a flat candidate list)

**Current**: `_do_select` returns a flat list of patterns + a flat candidate list. The model gets confused (too many candidates, no structure).

**Needed**: Return a TREE overview (using `_render_path_tree`'s YAML-like trie) with:
- Right-side branch numbers at each leaf/fork.
- Candidate names (CVT-expanded) shown at the leaves.
- The model uses the tree to SELECT which branch(es) to expand.

### Blocker C: expand_branch must show full CVT detail

**Current**: `_do_expand_branch` returns the pattern's candidates (from compress_paths — missing CVT entities).

**Needed**: expand_branch(N) should return:
- The branch's relation chain.
- The full triples (subject, relation, object) with CVT attributes expanded.
- Named entities (office_holder names, not CVT IDs).
- This is what `build_pattern_evidence_triples` produces per pattern (the `PatternEvidence.triples` + `tree_data`).

---

## 4. Implementation Plan (for the next session)

### Step 1: Fix _do_select to use formatting.py's proven evidence builders

Replace the current compress_paths + manual evidence in `_do_select` with:
```python
from kgqa.stages.formatting import build_pattern_evidence_triples, _render_path_tree

# After stage_5 + compress_paths → patterns:
pat_evidence = build_pattern_evidence_triples(
    patterns, ctx.ents, ctx.rels, ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.anchor_idx,
    max_grouped_lines=120)
# pat_evidence: dict[label, PatternEvidence] — each has .candidates (CVT-expanded), .triples, .tree_data

# Build numbered tree overview with right-side #N:
for i, (label, pe) in enumerate(sorted(pat_evidence.items(), key=lambda x: -len(x[1].candidates)):
    bid = str(i + 1)
    tree_lines = _render_path_tree(pe.tree_data, max_lines=20)
    # Append #N to the right of each leaf line
    ctx.branches[bid] = {"candidates": pe.candidates, "triples": pe.triples, "tree_lines": tree_lines, ...}
    overview_lines.append(f"  #{bid}  {pe.readable}  →  {len(pe.candidates)} candidates")
```

### Step 2: Fix _do_expand_branch to return full triples + tree

```python
def _do_expand_branch(args, ctx):
    br = ctx.branches[bid]
    return {
        "branch_id": bid,
        "readable": br["readable"],
        "candidates": br["candidates"][:30],      # CVT-expanded names
        "triples": br["triples"][:20],             # full (h, r, t) triples
        "tree": br["tree_lines"],                  # rendered trie with CVT attrs
    }
```

### Step 3: Adjust AGENTS.md for the select→expand→answer flow

```
After select, you see a numbered evidence tree.
- ANALYZE which branch(es) best answer the question (this is your path selection).
- Call expand_branch(N) for the branch(es) you chose, to see their detailed evidence.
- Then call answer with entities from the expanded evidence.
- You may skip expand_branch if the overview already shows the answer clearly.
```

### Step 4: Increase max_iters (16+) for multi-expand cases

### Step 5: A/B test — 100 cases, compare:
- **Path-selection quality**: of the branches the model expanded, how many contained the GT? (This is the REAL metric — not gt_hit, but "did the model select the right branch?")
- **2-hop F1**: does the structured tree + expand fix the regression?

---

## 5. Key Files

| file | role | current status |
|---|---|---|
| `kgqa/agent/tools.py` | tool schemas + dispatch (decompose/retrieve/select/expand_branch/answer) | select needs formatting.py reuse; expand_branch needs CVT triples |
| `kgqa/agent/harness.py` | order state machine (INIT→RETRIEVE→SELECT→EXPAND→ANSWER) | ✅ EXPAND state added |
| `kgqa/agent/loop.py` | orchestrator (agent_call loop + CaseContext) | ✅ works |
| `kgqa/agent/AGENTS.md` | system prompt | needs update for expand_branch guidance |
| `kgqa/stages/formatting.py` | PROVEN evidence builders (build_pattern_evidence_triples, _render_path_tree) | **reuse these** — they handle CVT expansion correctly |
| `kgqa/stages/stage5_traverse.py` | stage_5_graph_traversal (the robust traversal) | ✅ reused in _do_select |
| `kgqa/traversal/path_utils.py` | compress_paths | used but candidates incomplete (Blocker A) |
| `scripts/run_agent.py` | entry point | ✅ works |
| `kgqa/llm/client.py` | agent_call (tool_calls support) | ✅ additive, stage mode unaffected |

## 6. Key Data Points (for reference)

- Server: Qwen3.6-27B-FP8, `--tool-call-parser qwen3_coder --enable-auto-tool-choice`, no MTP (MTP crashed under load; enable for production speed later).
- GTE: Qwen3-Embedding-0.6B on :8003.
- Env: `KGQA_MODEL_NAME=/zhaoshu/llm/Qwen3.6-27B-FP8`, `KGQA_LLM_API_URL=http://localhost:8000/v1`, `GTE_API_URL=http://localhost:8003`.
- Branch: `agent-toolcall` (off `agent-skill`).
- Baseline: reports/baselineA_400 (v2 stage, 85.8% hit / 0.749 F1 on 400 cases).
- Agent runs: reports/agent_100 (pre-fix), reports/agent_100_stage5 (stage_5 alignment), reports/agent_expand_smoke* (expand_branch).

## 7. The User's Core Principle (put in spec)

> "命中率不重要，关键是模型是否选择对了。Stage 7的核心是选择路径，我们对模式路径做结构化展开是让模型分析哪个分支更好地回答问题，Stage 8则展开对应的分支做推理。"

Translation: Hit rate doesn't matter; what matters is whether the model SELECTS the right path. Stage 7 = path selection. Structured pattern expansion lets the model analyze which branch better answers the question. Stage 8 = expand the chosen branch for reasoning. The agent's `select` = Stage 7 (model selects branch from tree overview). The agent's `expand_branch` = Stage 8 (model expands the selected branch for detailed reasoning). The metric to optimize is **path-selection accuracy** (did the model expand the branch containing the GT?), not raw gt_hit.
