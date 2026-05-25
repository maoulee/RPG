# RPG: Relation-Prior Tree for Knowledge Graph Reasoning with Large Language Models

**Prior is Enough: Relation-Prior Tree for Knowledge Graph Reasoning with Large Language Models**

RPG mitigates the accuracy-efficiency trade-off in LLM-based KG reasoning by using LLM-derived relation priors to construct a **Relation-Prior Tree** that guides efficient, low-noise evidence acquisition on the knowledge graph.

## Method

RPG consists of two core mechanisms:

1. **Relation-Prior Tree Construction** — Decomposes the question into ordered relation requirements, aligns the resulting relation priors with KG relations, and organizes them into a tree of candidate reasoning patterns.

2. **Logic-Constrained Pattern Walking** — Verifies KG realizations under the Relation-Prior Tree, pruning invalid branches and extracting compact evidence without iterative LLM calls during traversal.

The final evidence is restricted to KG-instantiated patterns that are consistent with the relation-prior tree, reducing noisy graph evidence for downstream reasoning.

## Pipeline Stages

| Stage | Description |
|-------|-------------|
| Stage 0 | NER entity resolution (GTE-based or skip-NER) |
| Stage 1 | Question decomposition (chain / cascade mode) |
| Stage 2 | GTE relation retrieval + LLM pruning |
| Stage 3 | Relation retrieval via embedding similarity |
| Stage 4 | LLM-based relation pruning (top-k selection) |
| Stage 5 | Graph traversal with k-queue BFS |
| Stage 6 | Diagnosis and retry with fallback strategies |
| Stage 7 | Path deduplication and selection |
| Stage 8 | LLM answer reasoning over subgraph evidence |

## Results

| Dataset | F1 |
|---------|----|
| WebQSP | 84.3 |
| CWQ | 76.6 |

Achieved with a 9B-parameter model.

## Environment Setup

### Requirements

- Python 3.10+
- CUDA-capable GPU(s)
- [vLLM](https://github.com/vllm-project/vllm) >= 0.19.1
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
uv sync
# or
pip install -e .
```

### Required Models

| Component | Model | Role |
|-----------|-------|------|
| LLM | Qwen3.5-9B | Decomposition, pruning, reasoning |
| Embedding | Qwen3-Embedding-0.6B | Entity/relation retrieval |

```bash
export LLM_MODEL="Qwen3.5-9B"
export GTE_MODEL_PATH="Qwen3-Embedding-0.6B"
```

## Data Preparation

Place test data in the `data/` directory:

```
data/
├── webqsp/
│   └── test_fixed_path_completed.pkl
└── cwq_processed/
    └── test_literal_and_language_fixed_path_completed.pkl
```

Download from the [Releases page](../../releases).

## Running

### 1. Start Services

```bash
# Embedding server
python scripts/gte_api_server.py --port 8003

# LLM server
bash scripts/start_local_qwen35_server.sh
```

### 2. Run Evaluation

```bash
# WebQSP
python scripts/run_pipeline.py \
  --dataset webqsp --mode stage \
  --cwq-pkl data/webqsp/test_fixed_path_completed.pkl \
  --output-dir reports/webqsp_test \
  --limit 1639 --parallel 8

# CWQ
python scripts/run_pipeline.py \
  --dataset cwq --mode stage \
  --cwq-pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \
  --output-dir reports/cwq_test \
  --limit 3397 --parallel 8
```

### Key Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset` | `webqsp` or `cwq` | auto-detect |
| `--decomp` | `v2` (chain) or `cascade` | `cascade` |
| `--topk` | Max relations per step | 3 |
| `--reason-style` | Reasoning prompt style | `v2` |
| `--skip-ner` | Use q_entity directly | auto |
| `--dump-trajectories` | Save per-case trajectory files | off |

## Project Structure

```
kgqa/
├── core/
│   ├── config.py          # Configuration and prompt templates
│   ├── case_state.py      # Per-case state container
│   └── utils.py           # Normalization, matching, scoring
├── llm/
│   ├── client.py          # LLM API client with batch coalescing
│   ├── batch.py           # Batch call coordination
│   └── prompts.py         # Stage-specific prompt templates
├── stages/
│   ├── runner.py          # Stage-based batch orchestrator
│   ├── stage0_ner.py      # NER entity resolution
│   ├── stage1_cascade.py  # Cascade decomposition
│   ├── stage1_decomp.py   # Chain decomposition
│   ├── stage2_gte_prune.py
│   ├── stage3_gte.py      # GTE relation retrieval
│   ├── stage4_prune.py    # LLM relation pruning
│   ├── stage5_traverse.py # Graph traversal
│   ├── stage6_diagnosis.py
│   ├── stage7_select.py   # Path selection
│   └── stage8_reason.py   # Answer reasoning
└── traversal/
    ├── cvt.py             # CVT node expansion
    ├── frontier.py        # BFS frontier management
    ├── k_queue.py         # Priority queue for paths
    └── logical_paths.py   # Logical path construction
```

## Citation

```bibtex
@inproceedings{anonymous2026rpg,
  title={Prior is Enough: Relation-Prior Tree for Knowledge Graph Reasoning with Large Language Models},
  author={Anonymous},
  year={2026}
}
```
