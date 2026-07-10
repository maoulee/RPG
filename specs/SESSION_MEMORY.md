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

## RL data sampling + EoG study (2026-07-07)

> Added mid-session to preserve context across resets. Source: ZCode
> session on `agent-toolcall` branch. Sampling artifacts live in
> `reports/samp_val_pool/` (**gitignored** — see trap; reproduce via
> `scripts/resume_sample.py`).

### Sampling pipeline (`reports/samp_val_pool/`)
- **Driver**: `scripts/resume_sample.py --batch-size 50 --max-batches 60`
  (nohup, PID was 267675 on 2026-07-07). Reads state from
  `reports/samp_val_pool/state.json` (`{next_offset, batches_done}`),
  writes one `batch_###.jsonl` per 50 cases × 4 samples = 200 traj.
- **Source**: `data/cwq_processed/val.pkl` (**3519 cases total**).
  Started at case 750 (`batch_013`), running to ~case 3750.
- **Per-traj schema** (`batch_###.jsonl`, one JSON per line): `case_id`,
  `sample_id`, `question`, `gt_answers`, `messages`, `gt_hit`, `llm_hit`,
  `llm_f1`, `llm_answer`, `S_plan`, `S_select`, `S_reason`, `total_score`,
  `scorer_notes`, `agent_failed`, `n_steps`.
  ⚠️ **The reward field is `llm_f1`, NOT `f1`.** Confusing two caused
  an earlier miscount (showed 0 SFT / 400 all-wrong). Always use `llm_f1`.
- **`grpo.jsonl` / `sft.jsonl` are OVERWRITE-per-batch** (not cumulative).
  They only reflect the last batch run. To get cumulative counts, aggregate
  across all `batch_*.jsonl` with `llm_f1` per `case_id`.

### Cumulative training pool (as of batch_020, case 750–1050, 1600 traj)
| bucket | rule | cases |
|---|---|---|
| all-correct → SFT | all 4 samples `llm_f1 ≥ 0.99` | **89** |
| mixed → GRPO | otherwise | **205 cases (205 samples)** |
| all-wrong → flag | all 4 samples `llm_f1 < 0.01` | **106** |
Total 400 cases. Ratio ~22/51/27. Mixed dominates → good for GRPO
(both + and − reward present). SFT 89 is thin but ok for cold-start.

### ⭐ Decisive diagnosis: bottleneck is `S_plan`, not data
On the **120 all-wrong cases** (3-stage GT-recall decomposition, best of 4):
```
S_plan = 0  (decompose/relation-select loses GT):  99/120 = 82%
S_plan > 0  (plan found GT, lost downstream):      21/120 = 18%
```
**Implication**: the failure is the agent picking the wrong relation
direction at the decompose/`select_relations` step — a **model-decision**
problem, not a data/recall problem. GRPO with a path-reward is exactly
the right lever (penalize wrong relation choice, reinforce gold path).

⚠️ **Open question to close before training**: is the gold path's relation
even in the GTE candidate set for those 99 `S_plan=0` cases? If yes →
pure decision problem, train. If no → real recall limit, must fix GTE
candidate strategy first. **TODO: sample 20 `S_plan=0` cases, check gold
relation membership in GTE candidates. ~30 min.**

### EoG repo study — `github.com/ysq111333/EoG` (ICLR 2026)
Cloned to `/tmp/EoG_ref/` (scratch; not in repo). Read `reward_func.py`,
`data/EoG_process.py`, `test/eog_eval.py`, `run_rog_cwq.sh`. Findings:
- **EoG is NOT an agent loop.** `eog_eval.py` dumps the **entire subgraph**
  (`graph_info`) into one prompt; the LLM "reasons" in `<think>` and emits
  `<answer>`. `grep search_entity|search_relation` → **0 hits in code**.
  The tool-action framing in the paper is conceptual; the impl is
  single-turn reasoning over a pre-extracted subgraph.
- **Same data as us**: default input is
  `qald_10_en_test_original_2hop_remove_errors.jsonl` (2-hop CWQ subgraph).
  No data advantage.
- **Reward = path-match only**: `total = hits@1*0 + f1*0 + reasoning*1.0`
  (`reward_func.py:45-49`). Pure process reward, final answer weight 0.
  Reasoning score = extracted triplets ∩ gold `reasoning_path` / |path|.
  Same family as our S_plan/S_select/S_reason, but more aggressive.
- **"EoG's search_relation bypasses pre-extracted subgraph" — FALSE.**
  This was the prior hypothesis for why EoG might be better; the code
  shows it operates on the same pre-extracted subgraph we do. Our agent
  (stepwise expand) is arguably the more flexible design.
- **Net**: EoG is same-family, same-data, same-reward-idea, but **no agent
  loop**. Our agent-ization is the differentiator, not a disadvantage.

### Decisions pending (this session)
1. **Verify gold-relation-in-GTE-candidates** on 20 S_plan=0 cases — **DONE
   2026-07-08** at scale (n=3013). Verdict: DATA 49% > MODEL-DECISION 36% >
   RETRIEVAL 15%. See "Plan-failure root-cause diagnosis" below.
2. Continue sampling to ~3750 cases (nohup, ~4h remaining as of 2026-07-07).
3. Then start training (89 SFT cold-start → GRPO on mixed).

---

## Plan-failure root-cause diagnosis (2026-07-08)

**Question**: for S_plan==0 (plan-failed) cases, is the failure model DECISION,
system RETRIEVAL, or DATA? Tool: `scripts/diagnose_plan_failures.py` (offline;
reads `reports/samp_val_pool/batch_*.jsonl` + val.pkl; gold relation = BFS
anchor→answer path in the case's own subgraph, generic rels filtered; adversarially
audited by a 6-agent workflow). Full JSON: `reports/samp_val_pool/plan_failure_diagnosis.json`
(**gitignored**).

⚠️ **SPARQL cannot label val.pkl cases** — `cwq_sparql/test.json` aligns to the
TEST pkl (3531/3531), NOT val.pkl (0 id/question overlap). Gold relations are
derived intrinsically per case. If SPARQL labels are wanted, sample the test pkl.

**Result (n=3013 S_plan==0 samples, after fixing 2 measurement bugs the audit
found — `normalize()` empty-string match + short-literal false-match)**:
| side | % | detail |
|---|---|---|
| DATA/SUBGRAPH | **48.7%** | gold answer entity absent from the case subgraph (BFS anchor→answer unreachable). Validated 8/8 by spot-check. |
| MODEL-DECISION | **36.0%** | TRAVERSAL 25.4% (gold rel retrieved AND selected, but graph walk missed answer) + DECISION 9.3% (gold in L2, not selected) + ANCHOR_MISS 1.4% (rooted on a type node). DECISION/TRAVERSAL validated 8/8 / 7/8. |
| SYSTEM-RETRIEVAL | **15.3%** | GTE_MISS 10.3% (gold in scope, GTE didn't surface) + SCOPE_MISS 5.0% (pruned by structural scope). Upper bound; the genuinely-GTE-accuracy subset is smaller (some are anchor-quality artifacts). |

**Headline**: plan failures are dominated by **DATA (~49%)** and **MODEL-DECISION
(~36%)**; **SYSTEM-RETRIEVAL (~15%)** is the smallest. Model-decision ≫ retrieval
(~2.4×), but BOTH are outweighed by the subgraph-coverage problem. **This overturns
the prior "S_plan=0 = decision problem → GRPO is the lever" framing: ~49% of plan
failures are unreachable by any model/GTE/prompt change (answer not in graph) —
GRPO cannot move them.**

**Actionable code defects flagged by the audit (production agent, NOT yet fixed)**:
1. **Traversal/materialization** (largest validated lever): on the
   `influence.influence_node.*` family the model selected the correct outgoing
   gold edge that 1-hop reaches the answer, yet the answer never entered the
   plan-reachable pool. Pure code fix, near-100% conversion on that family. Also:
   forward-only-traversal vs undirected-gold mismatch on symmetric pairs
   (influenced/influenced_by); multi-hop branch expansion fails when the 2nd-hop
   relation is outside the anchor scope.
2. **Over-conservative L3 selection**: `select_relations` picks l3_union_size
   1–6 vs l2_union_size 7–19 — drops available gold. Relax the budget so l3
   scales with l2.
3. **Anchor selection**: type/meta-node rejection when a concrete q_entity exists
   (Turkey→"Country"); degree tiebreak for name collisions (":Sydney" stub vs
   city); **possible RUNTIME anchor-propagation bug** — verify the ReAct BATCH
   path propagates the model's decompose anchor to `ctx.anchor_idx` before
   `_gte_for_fact` (single-case path does via `_resolve_anchor`; batch
   `_process_one` may not).
4. Genuine GTE-accuracy failure is the SMALL minority — don't over-invest; GTE is
   hard-capped by the per-case subgraph (Freebase can't be loaded).

**Recommended order**: (a) verify+fix the batch anchor-propagation bug + the
influence-node materialization defect (highest certainty, pure code); (b)
quantify DATA recoverability — count "one-hop-short" cases (intermediate
discriminator present, final answer edge dropped) for targeted deeper
re-extraction; (c) relax L3 budget + improve relation-name display; (d) then
revisit RL — train only on the model-decision subset, exclude the data-side.

---

## GrailQA / GraphQuestions integration (2026-07-09)

**Status: cannot run here — needs Freebase KG for subgraph extraction.**

The framework does inference on **pre-extracted per-case subgraph pkls** (val.pkl /
test pkl format: `h_id_list/r_id_list/t_id_list` + ents/rels). Freebase cannot be
loaded in this container. Any new Freebase dataset (GrailQA, GraphQuestions) must
have its candidate subgraphs extracted on a server WITH Freebase, then the pkls
brought here for inference.

**Data sources (QA only, NO subgraphs):**
- GraphQuestions FB15: `dki-lab/GrailQA` repo `data/graphquestions_v1_fb15_*.json`
  (gold graph = query pattern, avg 2.5 nodes; **answer in it 0%** — NOT a candidate
  subgraph).
- GrailQA QA data: https://dl.orangedox.com/WyaCpL/ (same gold-graph format).

**KG (for extraction):** full Freebase via Virtuoso (`dki-lab/Freebase-Setup`) or
FastRDFStore/Sempre (per `ysu1989/GraphQuestions` README). NOT a simple file
download. ArcaneQA's `cache/` = SPARQL result caches, NOT subgraphs. The on-disk
FB15k/FB15k237 (`/zhaoshu/kgc/`) are KGC subsets, incompatible (7.6% mid overlap
with GraphQuestions).

**Server-side extraction steps (do where Freebase is available):**
1. Set up Freebase (Virtuoso via `dki-lab/Freebase-Setup`, or FastRDFStore).
2. For each GrailQA/GraphQuestions question: entity-link the topic entity, extract
   a 2-3 hop candidate subgraph (`data/deploy_bundle/graph_server.py` does this;
   produces h/r/t + ents/rels per case — same as how val.pkl/test pkl were built).
3. Serialize to the pkl format: `id, question, q_entity, text_entity_list,
   non_text_entity_list, relation_list, h_id_list, r_id_list, t_id_list, a_entity`.
4. Copy the pkl here; run inference via `run_agent_batch` (ReAct, the current
   agent) or `run_pipeline` (legacy stage).

**Architecture mismatch (why "direct" doesn't work):** GrailQA/GraphQuestions/
ArcaneQA query Freebase at runtime via SPARQL; our framework retrieves from
pre-extracted per-case subgraphs. Converting requires the KG for extraction.

---

## Hit@1 + scoring fixes + F1<1 analysis (2026-07-10)

### Commits this session
- `5813eb3` traversal: CVT transparency in _hit_paths (+4.36pp F1, ReAct greedy A/B)
- `d381143` score: S_plan from structured pool (not overview regex); answer_candidates captured
- `6a27056` agent: Hit@1 metric in react_loop + minimal "first=most-certain" SELECT
- `cc06462` score: fuzzy threshold 0.92→0.95 (stop collapsing year-variant events)

### Current metrics (100-case test, greedy, corrected matcher)
GT-hit 90.9% > llm_hit 85.9% > **Hit@1 79.8% > F1 77.2%** (standard hierarchy).

### CWQ SPARQL constraint distribution (n=3531)
**92.3% list-all** (no LIMIT) → keep-ALL default is CORRECT. **7.7% LIMIT-1** → irreducible
ambiguity (English doesn't convey SPARQL constraint). Don't default to "most recent."

### F1<1 failure classification (32/99)
- **5 LIMIT-1** (irreducible hidden constraint): Lou Seal/Crazy Crab "what year" w/ SPARQL LIMIT 1.
- **27 list-all** (actionable): OVER_EMIT 9 (junk in set, CVT dates not displayed), UNDER_EMIT 7
  (world knowledge narrowing — NBA model said "From world knowledge, Brad Stevens..."),
  SELECTION_MISS 6 (wrong entity), RETRIEVAL_MISS 9 (gold alias / missing / granularity).
- **84% of multi-entity answers are alphabetically sorted** (LLM habit) → gold often alpha-later → Hit@1 wrong.

### Key case findings
- **Libya leader**: expand 80 triples but only 2 with dates. 7/8 leaders lack CVT tenure dates → model can't distinguish → over-emit 8.
- **NBA Finals**: model used WORLD KNOWLEDGE ("Brad Stevens coached 2013-2021") to narrow 17→1. Violated "graph only."
- **Lou Seal**: always emitted all 3 WS (baseline too). F1=1.0 was inflated by fuzzy 0.92. After fix F1=0.5 (honest).

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

## TODO / open levers (updated 2026-07-10)

### Done this session
- [x] CVT transparency fix (commit 5813eb3, +4.36pp F1 ReAct greedy A/B)
- [x] S_plan from structured pool (commit d381143)
- [x] Hit@1 metric + minimal "first=most-certain" prompt (commit 6a27056, +2pp Hit@1)
- [x] Fuzzy threshold 0.92→0.95 (commit cc06462, F1 honest, Hit@1 > F1)
- [x] F1<1 failure classification + CWQ SPARQL distribution (92.3% list-all)
- [x] GrailQA spec: needs Freebase KG extraction (commit 77a16b3)

### Open — answer layer (27 actionable list-all F1<1)
- [ ] **expand_branches CVT 属性值补全**: Libya 7/8 leaders lack tenure dates in evidence. Investigate why (candidate cap? CVT expansion logic?).
- [ ] **World knowledge enforcement**: NBA model said "From world knowledge, Brad Stevens coached 2013-2021" — violated "graph only". Strengthen prompt or add post-hoc check.
- [ ] **Info-analysis (Step 3)**: when CVT/graph attributes ARE available, use them to FILTER junk (wrong-type, wrong-time) — NOT default-narrow to "most recent" (breaks 92.3%). Target: reduce OVER_EMIT (9 cases).
- [ ] **OVER_EMIT type-filter**: FROM should pre-filter by type (question asks country → FROM only lists countries).
- [ ] **UNDER_EMIT recall**: NBA 1/17 — model over-narrowed. Strengthen "no constraint → list ALL" execution.

### Open — RL / data
- [ ] **val.pkl unrepaired** (19.1% answers not in subgraph). Filter GT-suspect before training.
- [ ] **Re-sample RL data with fixed code** (CVT fix + scorer fix + answer_candidates). Old samp_val_pool has buggy scorer + no CVT fix.
- [ ] Start RL: SFT cold-start → GRPO. Reward = total_score. Can add top-1 reward for Hit@1.

### Open — lower priority
- [ ] Benchmark adaptive-routing + directed-traversal (commits 110eafe, default-off).
- [ ] GrailQA: needs Freebase KG on a server (see GrailQA section above).

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
