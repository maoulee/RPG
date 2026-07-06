# Session Memory — subgraph (KGQA agent)

> **Purpose**: This file survives container resets. It is the operational
> working memory across sessions — how to run things, where artifacts live,
> what's in progress, and traps we've hit. The chat log inside the container
> gets wiped on provider reset; **this file is git-tracked and will not**.
>
> Update it whenever: a run finishes, a command/prefix changes, a trap is
> discovered, or a milestone is hit. Keep entries dated and concise.
> Design rationale lives in `specs/agent_redesign_spec.md` (§0) — this file is
> about *operations*, not *why*.

---

## How to run the pipeline (current, 2026-07-06)

### Services required
The agent needs two services up before any run:

| service | port | what | model |
|---|---|---|---|
| vLLM (LLM) | `:8000` | chat completions + reasoning field | `/zhaoshu/llm/Qwen3.5-9B` |
| GTE embeddings | `:8003` | relation/entity semantic retrieval | `/zhaoshu/llm/Qwen3-Embedding-0.6B` |

No separate graph server — traversal runs **in-process** (`stage_5_graph_traversal`), so only the two HTTP services above are needed.

### Start commands
```bash
# GTE (light, ~1GB VRAM) — start first so vLLM can coexist
CUDA_VISIBLE_DEVICES=1 GTE_MODEL_PATH=/zhaoshu/llm/Qwen3-Embedding-0.6B \
  nohup python scripts/gte_api_server.py --port 8003 > logs/gte_server.log 2>&1 &

# vLLM (TP=2, both GPUs, ~8.5GB weights + KV)
nohup bash scripts/start_local_qwen35_server.sh > logs/vllm_server.log 2>&1 &
# ~3 min to first response (weight load 48s + torch.compile 38s + warmup 80s)
```

### Health checks
```bash
curl -s http://localhost:8003/retrieve -X POST -H 'Content-Type: application/json' \
  -d '{"query":"x","candidates":["a"],"top_k":1}'          # GTE up?
curl -s http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"Qwen3.5-9B","messages":[{"role":"user","content":"ok"}],"max_tokens":10}'  # LLM up?
```

### Run a batch
```bash
# 100-case eval (the standard benchmark slice), parallel=16
python scripts/run_agent_batch.py --start 0 --end 100 \
  --output reports/<NAME>/results.json --parallel 16
# smoke first to verify the path:  --start 0 --end 1
```
`run_agent_batch.py` hardcodes pilot = `reports/cwq_gte_bridge_100/results.json`
(100 rows) and CWQ pkl = `data/cwq_processed/...completed.pkl`. Masked
wrong-type ids (`data/cwq_processed/mask_wrong_type_ids.json`) are excluded
automatically → typically yields **99 cases**.

### Render a trajectory
```bash
# results.json is a list; extract one case, then render
python scripts/render_trajectory.py tmp/<case>_raw.json tmp/<case>_trajectory.txt
```
`render_trajectory.py` takes a **single case dict** as input. To pull one case
out of a `results.json` list:
```python
import json
r=json.load(open('reports/X/results.json'))
c=next(x for x in r if x.get('case_num')==N)
json.dump(c, open('tmp/caseN.json','w'), ensure_ascii=False)
```

---

## Current state (2026-07-06)

### What just landed
4-tool merge (`decompose` + `select_relations` + `expand_branches` + `answer`).
`retrieve` and `select` are folded in: decompose runs GTE inline, select_relations
runs traversal inline. Per-case turns dropped ~7 → ~4. Spec: `specs/agent_redesign_spec.md` §0.

### Latest 100-case result — `reports/cwq_merged_100/results.json`
| metric | merged 4-tool | prior baseline (`cwq_fromwhere_100`) |
|---|---|---|
| GT hit | **91/99 (0.919)** | 90/99 (0.909) |
| LLM hit | 87/99 (0.879) | 88/99 (0.889) |
| Overall F1 | 0.7888 | 0.7935 |
| GT-hit F1 | 0.8472 | 0.8617 |
| GT-hit Prec | 0.8599 | 0.8878 |
| GT-hit Recall | 0.9045 | 0.9095 |

**Verdict**: merge held GT-hit (+1) and recall (~flat); small precision drop
(−0.028) from over-emitting candidates. Net: noise-level, acceptable for the
tool-count halving. Committed in `ab7ec0a`.

### Workspace triage (2026-07-06)
Cleaned a pile of uncommitted work on `agent-toolcall` into focused commits:
- `110eafe` — two default-off experimental features: `--adaptive-routing`
  (simple/complex split, zero-LLM classifier in `stage1_cascade.classify_complexity`)
  and `KGQA_DIRECTED_TRAVERSAL=1` (directed Freebase edges). **Neither
  benchmarked yet.** Also adds `agent`/`free` reason-styles to stage8.
- `0f2d80c` — `agent_stage_scorer.py` now parses `select_pool` + reports
  `S_plan`/`S_select`/`S_reason` (3-stage GT-recall decomposition).
- `7c10abf` — `_BATCH_SIZE` 500→100 (vLLM prefill-queue at 500), plus
  `KGQA_LLM_BATCH_TEMPERATURE`/`_TOP_P` env overrides.
- `81696f4` — tracked the react entry scripts (`run_react.py`,
  `run_cwq_react_eval.py`, `run_webqsp_agent_eval.py`, `render_trajectory.py`)
  + `tests/test_skill_aggregation.py`. Were untracked despite being the
  only way to run the already-committed agent.
- `05b1362` — removed `start_graph_server.sh` (graph traversal is in-process
  now) and `run_webqsp_qwen35_local.sh` (replaced by `start_local_qwen35_server.sh`).

Three RL-era dirs (`config/`, `configs/`, `prompts/`) — unreferenced by active
code — moved to `_archive/rl_{config,configs,prompts}/` (gitignored, kept on
disk in case RL is revisited).

### Reference trajectory
`tmp/case1_merged_trajectory.txt` (367 lines) — the canonical 4-tool example:
Lou Seal → SF Giants → 2014 World Series, F1=1.0, 4 clean turns.
Use it as the "what good looks like" sample.

---

## Traps & gotchas

### `tmp/` AND `reports/` are both gitignored — artifacts are NOT safe
`.gitignore` excludes **both** `tmp/` and `reports/`. Trajectories, dumps,
run results, scratch JSONs written to either **will be lost on container
reset**. Decision (2026-07-06): keep `reports/` entirely untracked — the
run results are reproducible by re-running `run_agent_batch.py`, so we
record only the *metrics + run path* here in memory, never the artifacts.
Only `specs/`, `scripts/`, `kgqa/`, and `docs/` are git-tracked (safe).
If an untracked artifact genuinely matters (e.g. a one-off trajectory to
keep), copy it into `specs/` with a dated name, or it's gone on reset.

### "Deleted" scripts aren't actually lost
39 scripts show up under `git log --diff-filter=D` (e.g. `test_chain_decomp_v2.py`,
`build_case_skills.py`). They were removed by a commit but remain in history —
recover with `git show <commit>:scripts/<name>.py`. Only **untracked** files
(things never committed) are truly gone on reset.

### `reasoning_end_str` leaks into content
vLLM's reasoning boundary phrase (`"I will now emit the tool call..."`) can
bleed into the `content` field, corrupting a tool arg mid-JSON (seen in
case1 turn 3: `branch_ids: ["1I will now emit..."`). The `parse_react_output`
truncation-recovery fallback usually saves it by taking a later valid JSON,
so results don't break — but it's a latent parsing-robustness issue. Watch
for it if a case fails with a malformed-args rejection.

### GTE port conflict
If `:8003` is already bound (another shell started it), a new GTE process
exits with `Errno 98 address already in use` after loading the model. Check
`ss -tlnp | grep 8003` and `pgrep -af gte_api_server` before starting —
there's likely one already alive (health check returns 200).

---

## TODO / open levers
- [x] **Commit** the 4-tool merge + 100-case result + this memory file. (done)
- [x] Update `specs/agent_redesign_spec.md` §0 with the `cwq_merged_100` numbers. (done)
- [ ] **Benchmark** the two new default-off features landed 2026-07-06:
      `--adaptive-routing` (simple/complex split) and
      `KGQA_DIRECTED_TRAVERSAL=1` (directed Freebase traversal). Neither
      has a run in `reports/` yet. See commits `110eafe`.
- [ ] Investigate the 1 flip-in / 2 flip-out cases (vs `cwq_fromwhere_100`)
      to localize the precision drop.
- [ ] (optional) Harden `parse_react_output` against the `reasoning_end_str`
      leak (strip the phrase before parsing).

---

## File map (what lives where)
- **Design spec** (why): `specs/agent_redesign_spec.md` §0 = current truth.
- **Operational memory** (how): `specs/SESSION_MEMORY.md` (this file).
- **Agent prompt** (the model's rules): `kgqa/agent/AGENTS.md`.
- **Results**: `reports/<run_name>/results.json` — **gitignored**, reproducible.
  Record metrics here, not the files.
- **Trajectories**: rendered into `tmp/` (gitignored — see trap above).
- **Historical/reference docs**: `docs/` (legacy design notes, experiments).
- **Archived RL-era code**: `_archive/rl_{config,configs,prompts}/`
  (gitignored, kept on disk in case RL is revisited).
- **Logs**: `logs/{gte,vllm}_server.log`, `logs/run_*.log`.
- **Models**: `/zhaoshu/llm/Qwen3.5-9B`, `/zhaoshu/llm/Qwen3-Embedding-0.6B`.
