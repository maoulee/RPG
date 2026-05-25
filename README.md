# SubgraphKGQA: Subgraph Retrieval with Chain Decomposition for Knowledge Graph Question Answering

A multi-stage pipeline for Knowledge Graph Question Answering (KGQA) over Freebase, supporting both WebQSP and ComplexWebQuestions (CWQ) datasets.

## Pipeline Overview

The pipeline decomposes complex questions into step-by-step sub-questions, retrieves and prunes candidate relations via GTE embedding retrieval and LLM-based pruning, traverses the knowledge graph to build logical paths, and reasons over the resulting subgraph to produce answers.

**Stages:**

1. **NER Entity Resolution** — GTE-based entity linking (or skip-NER using ground-truth entities)
2. **Question Decomposition** — LLM-based chain decomposition into ordered sub-questions
3. **GTE Relation Retrieval** — Embedding-based retrieval of candidate relations per sub-question
4. **LLM Relation Pruning** — LLM selects top-k relevant relations per step
5. **Graph Traversal** — BFS traversal building logical paths through the KG
6. **Diagnosis & Retry** — Coverage-based retry with fallback strategies
7. **Path Selection** — Deduplication and selection of final reasoning paths
8. **Answer Reasoning** — LLM reads subgraph evidence and produces answers

## Environment Setup

### Requirements

- Python 3.10+
- CUDA-capable GPU(s) for LLM and embedding model inference
- [vLLM](https://github.com/vllm-project/vllm) >= 0.19.1 (for LLM serving)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"
```

### Required Models

| Component | Model | Role |
|-----------|-------|------|
| LLM | Qwen3.5-9B | Decomposition, pruning, reasoning |
| Embedding | Qwen3-Embedding-0.6B | Entity/relation retrieval |

Set model paths via environment variables:

```bash
export LLM_MODEL="Qwen3.5-9B"           # or your local path
export GTE_MODEL_PATH="Qwen3-Embedding-0.6B"  # or your local path
```

## Data Preparation

The pipeline requires pre-processed subgraph data in pickle format. Place the test data files in the `data/` directory:

```
data/
├── webqsp/
│   └── test_fixed_path_completed.pkl    # WebQSP test subgraphs
└── cwq_processed/
    └── test_literal_and_language_fixed_path_completed.pkl  # CWQ test subgraphs
```

These pkl files contain per-question subgraphs with entity lists, relation lists, and head/relation/tail index arrays.

### Download Data

Download the test data files from the [Releases page](../../releases) and place them in the `data/` directory as shown above.

## Running the Pipeline

### 1. Start the Embedding Server

```bash
python scripts/gte_api_server.py --port 8003
```

### 2. Start the LLM Server

The pipeline uses an OpenAI-compatible API. You can use vLLM to serve the LLM:

```bash
# Example: serve Qwen3.5-9B with vLLM
python -m vllm serve Qwen3.5-9B \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len 30000 \
  --dtype auto
```

Or use the provided script:

```bash
bash scripts/start_local_qwen35_server.sh
```

### 3. Run Evaluation

```bash
# WebQSP evaluation
python scripts/run_pipeline.py \
  --dataset webqsp \
  --mode stage \
  --pilot-results reports/pilot_webqsp.json \
  --cwq-pkl data/webqsp/test_fixed_path_completed.pkl \
  --output-dir reports/webqsp_test \
  --limit 1639 \
  --parallel 8

# CWQ evaluation
python scripts/run_pipeline.py \
  --dataset cwq \
  --mode stage \
  --pilot-results reports/pilot_cwq.json \
  --cwq-pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \
  --output-dir reports/cwq_test \
  --limit 3397 \
  --parallel 8
```

### Key Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset` | Dataset preset: `webqsp` or `cwq` | auto-detect |
| `--mode` | Execution mode: `stage` (batch) or `case` | `case` |
| `--limit` | Number of cases to process | 10 |
| `--parallel` | Parallel case count | 1 |
| `--skip-ner` | Skip GTE NER, use q_entity directly | auto (on for webqsp/cwq) |
| `--decomp` | Decomposition mode: `v2` or `cascade` | `cascade` |
| `--topk` | Max relations per step after pruning | 3 |
| `--reason-style` | Reasoning prompt style | `v2` |
| `--dump-trajectories` | Save per-case trajectory files | off |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_URL` | LLM API endpoint | `http://localhost:8000/v1/chat/completions` |
| `LLM_MODEL` | LLM model identifier | `Qwen3.5-9B` |
| `GTE_API_URL` | Embedding API endpoint | `http://localhost:8003` |
| `GTE_MODEL_PATH` | Embedding model path | `Qwen3-Embedding-0.6B` |

## Project Structure

```
kgqa/
├── core/
│   ├── config.py          # Pipeline configuration and prompts
│   ├── case_state.py      # Per-case state container
│   └── utils.py           # String normalization, matching, scoring
├── llm/
│   ├── client.py          # LLM API client with batch coalescing
│   ├── batch.py           # Batch call coordination
│   └── prompts.py         # Prompt templates for each stage
├── stages/
│   ├── runner.py          # Stage-based batch execution orchestrator
│   ├── stage0_ner.py      # NER entity resolution
│   ├── stage1_cascade.py  # Cascade decomposition
│   ├── stage1_decomp.py   # Chain decomposition
│   ├── stage2_gte_prune.py # Combined GTE + pruning
│   ├── stage3_gte.py      # GTE relation retrieval
│   ├── stage4_prune.py    # LLM relation pruning
│   ├── stage5_traverse.py # Graph traversal
│   ├── stage6_diagnosis.py # Diagnosis and retry
│   ├── stage7_select.py   # Path selection
│   └── stage8_reason.py   # Answer reasoning
└── traversal/
    ├── cvt.py             # CVT node expansion
    ├── frontier.py        # BFS frontier management
    ├── k_queue.py         # Priority queue for paths
    └── logical_paths.py   # Logical path construction
```

## Results

| Dataset | Hit@1 | F1 |
|---------|-------|----|
| WebQSP | 86.4 | 76.1 |
| CWQ | 78.1 | 73.5 |

## Citation

```bibtex
@inproceedings{anonymous2026subgraphkgqa,
  title={SubgraphKGQA: Subgraph Retrieval with Chain Decomposition for Knowledge Graph Question Answering},
  author={Anonymous},
  booktitle={Anonymous},
  year={2026}
}
```
