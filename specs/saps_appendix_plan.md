# SAPS Technical-Report Appendix — Plan (target 11–15 pp)

Principle: *report = method flow + experimental evidence; repo = engineering edges.*
Non-RL counterpart = **RPG** (paper/paper_rpg.tex): the 4-tool ReAct agent with NO
process-supervised rollout. SAPS adds the stage-wise group-relative action optimization
on top of the same RPG agent + KG. The appendix's job is to make that delta reproducible.

Reported training unit = **500 cases / round** (one rollout→train iteration).

---

## A. Experimental Details  (2–3 pp)

### A.1 Datasets and Evaluation  (½ pp, one paragraph + table)
- Standard WebQSP + CWQ splits; same Freebase env across all SAPS variants + RPG baseline.
- Gold topic entities = initial linked entities; same entity-normalization + answer-matching as benchmark.
- **Table**: train/test sizes (WebQSP, CWQ). Numbers from `data/cwq_processed/` counts.

### A.2 Implementation and Hyperparameters  (½–1 pp, one table)
Pulled from `SAPS_code/config.yaml` (already verified):
- model Qwen3.5-9B (base FT, LoRA off in reported runs), vLLM TP=2, mem 0.82, max_len 65536.
- agent: thinking budget 1000, GTE top-30, max 16 iters.
- train: lr 1e-5 cosine, eff batch 16 (1×2×8), max_length 14336, 1 epoch, KL β=0.

### A.3 Rollout and Training Procedure  (2 pp) ← **the core**
- Per round: sample 1 seed trajectory per case (500 cases) → **comb best-prefix rollout**:
  decompose (shared) → K=8 plan candidates → score S_plan → keep best prefix → K=8 explore → S_select → best → K=8 reason → S_reason.
- Classification per group: **GRPO** (score variance) / **SFT** (no variance, ≥1 correct) / **skip** (no variance, all wrong).
- Advantage = `(S − μ)/σ` (GRPO) or `1.0` (SFT); **no stage weights** (stages trained jointly; shared prefix ⇒ group-relative advantage flows only to current-stage tokens).
- 1 epoch/round; rollout-policy = current model; iterate (round n model → rollout → train → round n+1).
- **Pseudocode block** (one algo box): `comb_rollout` + `classify_and_assign_advantage`. No per-field data-structure prose.

### A.4 Runtime and Computational Cost  (1 pp, one table)  ← **needs the running 500-case numbers**
| quantity | value | source |
|---|---|---|
| rollout throughput | _N_ cases/min | comb_rollout summary (running) |
| one-round rollout time (500 cases) | _T_ min | measured |
| train step time | ~35 s/step (fast path) | prior log + memory |
| steps / epoch (500 cases) | records/16 ≈ _S_ | from rollout records |
| one-round train time | _S × 35s_ | derived |
| rollout : train ratio | _T : train_ | derived |
| hardware | 2× A100-40GB | — |

Training-step basis (recorded): ~35 s/step @ eff_batch 16, max_len 14336, 2×A100, Qwen3.5
fast path (causal-conv1d + FLA). Older non-fast-path was ~147 s/step (≈4× slower) — cite only
if a footnote on the speedup is wanted.

---

## B. KG Environment and Tool Interfaces  (1.5–2 pp)

One ½-pp "Implementation" paragraph (Freebase snapshot, entity/relation textualization,
adjacency index, deterministic execution) — then **tool boundaries only**:

### B.1 Candidate Retrieval (`decompose` + per-triple GTE)
- Input: question + linked entities → FLOW triples + ENTITIES + ANSWER.
- System runs GTE **within each triple's 2-hop-reachable relation pool** (grounded; never
  sees structurally-unreachable relations) → returns `candidate_relations` per triple.
- Deterministic; does NOT add start points or reorder relations.

### B.2 Evidence Expansion + Fixed-Evidence Reasoning
- `select_relations`: model picks from candidates → system traverses → evidence-tree overview.
- `expand_branches`: expands ONLY selected branches (the evidence subgraph).
- `answer`: reasons over the FIXED evidence subgraph (no further KG access).
- Candidate-subgraph ↔ `decompose`/`select`; evidence-subgraph ↔ `expand`/`answer`.

---

## C. Additional Analyses  (2–3 pp)

### C.1 Training Dynamics
Plan/explore/reason + final F1 across rounds. **Needs multi-round run** — only run if the
final pipeline truly iterates >1 round; otherwise omit (per your "don't manufacture an experiment").

### C.2 Effect of Action-Group Size (K)
Vary K ∈ {4, 8, 16}: F1 vs rollout cost. **One small experiment needed** (re-run 500-case
rollout subset at K=4 and K=16; K=8 is the main run).

### C.3 Action-Group Statistics  ← **the table, from the 500-case records**
| Stage | Avg score | Groups w/ non-zero variance | Groups containing a score-1 action |
|---|---|---|---|
| Planning (select_relations) | _a_ | _b_% | _c_% |
| Exploration (expand_branches) | | | |
| Reasoning (answer) | | | |

Computed automatically from rollout records (`S_X`, `route`, per stage). Proves intra-group
quality variance exists ⇒ group-relative optimization has signal.

Process-score note (your two sentences, verbatim): *"All process scores are computed
automatically from the ground-truth answer set and the structured outcomes returned by the
KG tools, without an auxiliary LLM judge. We follow the same entity normalization and
answer-matching protocol as the benchmark evaluation."* (+ optional one-liner on empty/no-gold ⇒ 0 recall).

---

## D. Prompt Templates  (2–3 pp)
Three condensed prompt cards (planning / exploration / reasoning) in-body; full prompts → repo (`kgqa/agent/AGENTS.md`). Mirror RPG appendix style, no full-page figures.

## E. Case Studies  (2–3 pp, exactly 3)
1. **Planning** — different plans → different candidate-answer coverage.
2. **Exploration** — full-coverage-but-noisy vs selective action.
3. **Trajectory supervision** — final-answer reward mis-aligned with action quality.
(Reasoning folded into case 3; no separate reasoning case.)

---

## Pending empirical collection (from the running 500-case job)
1. rollout throughput (cases/min) + total one-round rollout time → **A.4, C.3**.
2. records produced + per-stage action-group table → **C.3**.
3. skip rate (success %) → confirms rollout health (context for A.3).
4. *(separate, on approval)* K=4 / K=16 sub-runs → **C.2**.
5. *(separate, on approval)* multi-round dynamics → **C.1**.

## Out of scope (→ repo/README only, per your guidance)
alias handling, CVT cleaning, path-counting edge cases, JSON-parse robustness, adjacency
index format, Freebase import/cache, graph-DB config, per-function latency.
