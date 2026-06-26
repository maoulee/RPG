# KGQA Pipeline Refactor Design

**Date**: 2026-05-04
**Status**: Approved
**Scope**: Refactor `scripts/test_chain_decompose.py` (7710 lines) into a domain-based package structure.
**Out of scope**: All other scripts in `scripts/`, RL-related files in root (`collate_server.sh`, `colloate_gym*.sh`, `train_grpo.sh`).

## Motivation

The main pipeline lives in a single 7710-line file. It contains 8 pipeline stages, 2 traversal engines, LLM batching, a CaseState class, prompt templates, formatting helpers, and CLI argument parsing. This makes it difficult to navigate, test, and maintain. The V2 reasoning prompt changes are interleaved with the original logic rather than cleanly separated.

## Architecture

Domain-based grouping with 4 sub-packages:

```
kgqa/
  __init__.py
  core/
    __init__.py
    config.py          (~150 lines)
    case_state.py      (~250 lines)
    utils.py           (~200 lines)
  traversal/
    __init__.py
    k_queue.py         (~200 lines)
    frontier.py        (~400 lines)
    cvt.py             (~100 lines)
    path_utils.py      (~300 lines)
  llm/
    __init__.py
    client.py          (~100 lines)
    batch.py           (~150 lines)
    prompts.py         (~300 lines)
  stages/
    __init__.py
    stage0_ner.py       (~60 lines)
    stage1_decomp.py    (~270 lines)
    stage2_entity.py    (~110 lines)
    stage3_gte.py       (~100 lines)
    stage4_prune.py     (~230 lines)
    stage5_traverse.py  (~250 lines)
    stage6_diagnosis.py (~250 lines)
    stage7_select.py    (~150 lines)
    stage8_reason.py    (~700 lines)
    runner.py           (~400 lines)
    formatting.py       (~600 lines)
scripts/
  run_pipeline.py       (~200 lines, new entry point)
```

Original `test_chain_decompose.py` remains frozen in place (not deleted, not modified).

## Module Details

### kgqa/core/config.py (~150 lines)

All module-level constants from the original file (lines 19-30):
- `ROOT`, `LLM_API_URL`, `LLM_MODEL`, `GTE_API_URL`, `GTE_TASK_DESC`
- `REASON_STYLE`, `SKIP_NER`, `ALLOW_1STEP`
- Path constants: `DEFAULT_PILOT`, `DEFAULT_CWQ`, `MASK_WRONG_TYPE`, `DEFAULT_OUTPUT`

No functions. Pure constants. Stages import as `from kgqa.core.config import LLM_API_URL`.

### kgqa/core/case_state.py (~250 lines)

The `CaseState` class (original lines 508-751). Field definitions only, no logic changes.
Stages import as `from kgqa.core.case_state import CaseState`.

### kgqa/core/utils.py (~200 lines)

Pure utility functions with no kgqa-internal dependencies:
- `normalize()`, `rel_to_text()`, `rel_to_text_short()`
- `extract_xml_tag()`, `get_entity_contexts()`
- `candidate_hit()`, `strict_candidate_hit()`, `compute_match_stats()`

Note: `is_cvt_like()` lives in `traversal/cvt.py`, not here.

### kgqa/traversal/cvt.py (~100 lines)

CVT-related graph operations on index arrays:
- `is_cvt_like()`, `expand_cvt_leaves()`, `expand_through_cvt()`
- `expand_node()`

No kgqa-internal dependencies.

### kgqa/traversal/k_queue.py (~200 lines)

`k_queue_traverse()` — the primary traversal engine (original lines 5721-5916).
Depends on: `kgqa/core/utils.py` for `_is_noisy_path_relation`.

### kgqa/traversal/frontier.py (~400 lines)

Alternative traversal and expansion engines:
- `frontier_expand_layers()`, `relation_prior_expand()`
- `diagnose_layers()`, `_coverage_rank()`, `_merge_paths()`
- `chain_expand()`, `chain_expand_v2()`, `bidirectional_expand()`

Depends on: `kgqa/traversal/cvt.py`.

### kgqa/traversal/path_utils.py (~300 lines)

Path processing utilities:
- `compress_paths()`, `expand_to_triples()`
- `_path_hits_breakpoints()`, `prefer_breakpoint_hit_paths()`
- `_extract_relation_segments_from_path()`, `_extract_path_candidates()`
- `_is_noisy_path_relation()`, `_path_relation_names()`

Depends on: `kgqa/traversal/cvt.py`.

### kgqa/llm/prompts.py (~300 lines)

All prompt templates as string constants:
- `DECOMP_PROMPT` (entity analysis + chain decomposition)
- Pruning prompts, diagnosis prompts
- V1 reasoning prompt, V2 reasoning prompt (fact-match + constraint filter)
- No logic. Pure strings.

### kgqa/llm/client.py (~100 lines)

Single LLM call functions:
- `call_llm()`, `_call_single_direct()`

Depends on: `kgqa/core/config.py` for `LLM_API_URL`, `LLM_MODEL`.

### kgqa/llm/batch.py (~150 lines)

Batched LLM calls:
- `_BatchCoalescer` class, `batch_call_llm()`

Depends on: `kgqa/llm/client.py`.

### kgqa/stages/stage0_ner.py through stage8_reason.py

Each stage is a single `async def stage_N_xxx(session, cases: List[CaseState])` function, identical to current logic. Stages modify CaseState in-place.

**stage0_ner.py** (~60 lines): NER entity resolution via GTE.
**stage1_decomp.py** (~270 lines): Entity analysis + chain decomposition. Includes `parse_decomposition()`, `parse_chain()`, `llm_prune_all_relations()`, `llm_reselect_single_step_relation()`.
**stage2_entity.py** (~110 lines): GTE + LLM entity resolution. Includes `llm_resolve_entity()`, `resolve_anchor_ner()`.
**stage3_gte.py** (~100 lines): Concurrent GTE relation retrieval. Includes `gte_retrieve()`, `score_causal_tier()`.
**stage4_prune.py** (~230 lines): LLM relation pruning + reranker alternative. Includes `_build_prune_all_prompt()`, `_parse_prune_result()`.
**stage5_traverse.py** (~250 lines): Graph traversal orchestration. Includes `build_endpoint_rescue_patterns()`, `build_pattern_evidence_triples()`, `_PatternEvidence` class.
**stage6_diagnosis.py** (~250 lines): Diagnosis and retry for failed cases.
**stage7_select.py** (~150 lines): Path selection. Includes `evaluate_step_relations()`, candidate filtering.
**stage8_reason.py** (~700 lines): V1 and V2 answer reasoning. Includes answer validation and None-retry logic.

### kgqa/stages/runner.py (~400 lines)

Orchestration:
- `_run_stage_mode()` — main stage-by-stage loop over batches of cases
- `_run_case_wrapper()` — single case execution mode
- `_case_state_to_result_dict()` — result dict construction
- Aggregate summary printing

Depends on: all stage modules, `kgqa/core/`.

### kgqa/stages/formatting.py (~600 lines)

Evidence formatting for LLM consumption:
- `format_subgraph_with_cvt()`, `format_pattern_evidence()`
- `_render_path_tree()`, `_render_entity_tree()`
- `format_grouped_triples()`, `collect_local_subgraph_triples()`

### scripts/run_pipeline.py (~200 lines)

New CLI entry point:
- argparse configuration (from original lines 4574-4703)
- `amain()` — async entry: load data, call `runner.run_stage_mode()`
- `if __name__ == "__main__"` block

Depends on: `kgqa.stages.runner`, `kgqa.core.config`.

## Dependency Graph

```
run_pipeline.py
  └─ kgqa.stages.runner
       ├─ kgqa.stages.stage0..stage8
       │    ├─ kgqa.llm (client, batch, prompts)
       │    ├─ kgqa.traversal (k_queue, frontier, cvt, path_utils)
       │    └─ kgqa.core (config, case_state, utils)
       └─ kgqa.stages.formatting
            └─ kgqa.core.utils
```

No circular dependencies. All arrows point downward.

## Migration Strategy

1. Create `kgqa/` package with `__init__.py` and sub-package directories
2. Move functions bottom-up (leaves first):
   - core/ (config, case_state, utils)
   - traversal/ (cvt, k_queue, frontier, path_utils)
   - llm/ (prompts, client, batch)
   - stages/ (stage0-8, formatting, runner)
3. Add proper imports to each module
4. Create `scripts/run_pipeline.py` with CLI parsing
5. Verify: `python scripts/run_pipeline.py --limit 5 --reason-style v2 --skip-ner` produces identical results
6. Keep `test_chain_decompose.py` frozen (not deleted)

## Constraints

- Do NOT modify any files outside `kgqa/` and the new `run_pipeline.py`
- Do NOT touch RL-related scripts in root directory
- Do NOT change any logic — pure structural refactoring
- All stage function signatures remain `async def stage_N(session, cases: List[CaseState])`
- CaseState fields and mutation patterns unchanged
- Prompt text unchanged (just moved to prompts.py)
