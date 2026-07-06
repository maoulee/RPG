# RPG Agent Redesign — Spec for Continuation

> **Current status (2026-07-05)** — see §0 below for the latest validated state.
> The remainder of this document (§1+) is the historical spec from the
> native-toolcall era; it is kept for context but §0 supersedes it where they
> disagree.

---

## 0. Current State (2026-07-06, commit `ab7ec0a`)

### Tool workflow merge: 6→4 tools (2026-07-06, commit `ab7ec0a`)

Merged redundant tool round-trips. Each LLM call now carries substantive
information — no wasted turns:

| step | tool | what it does |
|---|---|---|
| 1 | `decompose` | Model writes facts + picks anchor/endpoints (LLM ambiguity analysis). System runs GTE for each fact inline, returns candidate_relations. |
| 2 | `select_relations` | Model picks relations from candidates. System traverses graph inline, returns evidence tree (≤3 candidates per branch + ellipsis, no entity list in header). |
| 3 | `expand_branches` | Model expands relevant branches. Returns CVT-expanded candidates + triples + trie. |
| 4 | `answer` | FROM→WHERE→SELECT reasoning, emit entities. |

`retrieve` and `select` are no longer separate steps. retrieve remains as an
optional fallback (re-fetch a fact's candidates with a revised hint).

### Anchor/endpoint analysis (2026-07-06)

The model now performs LLM ambiguity analysis during decompose, picking
`anchor` (lowest-ambiguity concrete entity) and optional `endpoints`
(constraint entities). This replaces the blind `q_entity[0]` heuristic in
`_resolve_anchor` — the model's choice is authoritative, with q_entity as
fallback. Mirrors stage's `ENTITY_ANALYSIS_PROMPT`:
- Specific names (people, events, unique titles) → LOW ambiguity → good anchor
- Generic type words (Country, Person, Sport) → HIGH ambiguity → NEVER use
- Endpoints = constraint entities from remaining q_entity list

10-case smoke: 7/10 hit, mean_f1=0.8182. Tool calls per case dropped from ~7
to ~4.

### Reasoning capture GAP (2026-07-06 discovery, fixed commit `5be7ef0`)

vLLM with `thinking_token_budget` returns the model's chain-of-thought in a
**separate `reasoning` field** on the response message — NOT inside `content`.
Live test confirmed:

```
message keys: ['role','content','refusal','annotations','audio',
               'function_call','tool_calls','reasoning']
content:  "\n\nParis is the capital of France."      ← only the tool call / answer
reasoning: "The user is asking a simple factual..."   ← the CoT (530 chars)
```

**Current `_call_single_direct` (client.py L215) returns only `content`** — the
`reasoning` field is silently dropped. This means:
1. **Trajectories contain NO thinking process** — only the final tool call text.
2. Training-data generation (SFT/GRPO) would lose the reasoning entirely.
3. Case 16's "think/tool contradiction" is actually invisible in the trajectory
   — we only see the content (which sometimes contradicts what the reasoning
   concluded, but we can't detect it because reasoning isn't stored).

**Fix needed:** `_call_single_direct` should return `(content, reasoning)`, and
`react_loop` should store reasoning alongside content in the trajectory — either
as a `reasoning` key on the assistant step, or concatenated. This is a
prerequisite for trajectory generation and for diagnosing reasoning-answer
consistency issues.

### Answer-reasoning failure analysis (2026-07-06, gold-grounded)

Classified all 29 f1<1 cases from the FROM→WHERE 100-case run:

| mode | count | root cause | fixable via prompt? |
|---|---|---|---|
| WRONG (fully wrong) | 14 | retrieve miss / select miss / candidate pool wrong | partially |
| gold-subset (model right, GT narrower) | 10 | model correctly kept ALL; GT prefers subset | no (gold issue) |
| under (missing candidates) | 3 | traverse recall incomplete | no |
| EMPTY | 1 | vLLM disconnect | no |
| partial | 1 | traverse recall | no |

Deep-dived case 16 (NBA, 0.11) and case 36 (Missouri River, 0.29) with gold
subgraph cross-check:

- **case 36**: logic path CORRECT (`partially_contains`/`partially_containedby`
  selected, matching gold). expand candidate pool COMPLETE (all 6 GT states
  present). Failure = **reasoning didn't systematically traverse the FROM set**
  — model checked only Iowa ("explicitly shown") and stopped, didn't verify the
  other 5 states also satisfy WHERE. **This is a reasoning-discipline issue
  (jump-to-first-match), NOT a logic-path or data issue. Prompt cannot fix.**
- **case 16**: model's content says "output full pool" but emits 1 entity.
  Without the `reasoning` field captured, we cannot tell whether the CoT
  actually concluded keep-all (then the tool call contradicted it) or the CoT
  itself was inconsistent.

**Verdict:** current prompt + tool layer is at its ceiling (88.9% hit / 0.794
f1). Remaining failure modes require either:
1. **Fine-tuning** (SFT/GRPO) to instill reasoning discipline (systematic WHERE
   traversal, reasoning→answer consistency). Needs reasoning captured in
   trajectories first (see GAP above).
2. **Subgraph extraction fix** (CVT value edges) to unlock numeric-constraint
   cases (73/98/99/11). Blocked on extraction server.

### Protocol: content-only (NOT native tool_calls)

The agent uses the **content protocol** (`react_loop.run_react_case`), not native
tool_calls. Native tool_calls (`loop.py` + `tool_choice="required"`) was
**abandoned** because vLLM's hermes parser fails on Qwen3.5's `<function=>` XML
tool-call format (`JSONDecodeError`), which intermittently broke the
`thinking_token_budget` hard cap and caused empty-output `max_iters` failures.
`loop.py` is kept as a native-toolcall archive; all evaluation entry points
(`run_agent_batch.py`, `run_cwq_react_eval.py`, `run_webqsp_agent_eval.py`) use
`react_loop`.

- Each turn: `call_llm` returns free-form content; `parse_react_output` extracts
  the `tool: {"tool":..., "args":...}` anchor. Bypasses vLLM tool-call parsing
  entirely → reasoning hard cap stays reliable → batch throughput preserved.

### Tool flow (content protocol, 6 tools, strict order)
`decompose → retrieve (per fact) → select_relations → select → expand_branches → answer`

- `expand_branches` is **plural/batch** (the singular `expand_branch` was a
  latent bug; harness normalizes legacy singular → plural defensively).
- `decompose` facts now carry an optional **`start_type`** (anchor name for f1,
  type noun like "airport"/"country" for f2+) used to contextualize retrieval.

### Retrieve: candidate contextualization (GTE deep-semantic gap)

The model writes natural-language hints ("bordering countries of France"); the
KG stores schema names (`location.adjoining_relationship.adjoins`). Bare-id
candidate texts make GTE miss these — `bordering`↔`adjoining_relationship` have
no surface overlap, so adjoins never enters the top-15.

Fix: for relations in the fact's structural scope, candidate_text becomes
`"<start_type> <last-two-schema-segments>"` (e.g. `"France adjoining relationship
adjoins"`). The leading domain segment is **dropped** — it is a generic bucket
word (`location`/`government`) that disturbs ordinary-case ranking. Validated
honestly (query contains no `adj-` root, simulating what the model actually
writes): adjoins rises from "not in top-15" to rank 2-3, while ordinary cases
(case 7 GTE ranking) stay bit-identical to bare id.

This is **not answer leakage**: the candidate carries the relation's own schema
name (legitimate KG structure), and the model's hint carries only natural
language. The full-schema variant (keeping the leading domain) regressed
ordinary cases and was rejected.

### Results (100-case)

| dataset | prompt version | llm_hit | gt_hit | mean F1 | empty |
|---|---|---|---|---|---|
| CWQ | content + retrieve ctx (3707cac) | 83.8% | 89.9% | 0.778 | 1/99 |
| CWQ | + parallel-constraint prompt (f458620) | 84.8% | — | 0.786 | — |
| CWQ | + parallel union + FROM→WHERE (63af4ee) | **88.9%** | — | **0.794** | — |
| CWQ | + 4-tool merge 6→4 (`ab7ec0a`, 100-case re-run) | 87.9% | **91.9%** | 0.789 | 0/99 |
| WebQSP | content + retrieve ctx | 91.0% | 93.0% | 0.804 | — |

**4-tool merge verdict (2026-07-06, `reports/cwq_merged_100`):** the merge
folded `retrieve` into `decompose` (GTE runs inline) and `select` into
`select_relations` (traversal runs inline). Per-case turns dropped ~7 → ~4.
Against the prior `cwq_fromwhere_100` baseline: GT-hit **+1 (90→91)**, recall
~flat (0.910→0.905), small precision drop (−0.028, 0.888→0.860) from
over-emitting candidates. Net noise-level — the tool-count halving cost no
recall and no GT-hit. Not yet committed.

The FROM→WHERE→SELECT answer-reasoning framework (commit `63af4ee`) is the
biggest single gain: **+4 hit (84→88)** in one change. Replaces the old
"two-layer removal" with an explicit structured-query analogy that forces the
model to enumerate the full candidate pool (FROM) before applying constraints
(WHERE), preventing the common error of jumping to a single answer. Case 21
(Vicksburg, long-standing miss) went 0→1 — the model used explicit FROM/WHERE/
SELECT notation to find CSA via `location.country.capital`.

Regressions after FROM→WHERE (case 11/16/26) are NOT framework-caused: case11
is the known CVT-value readability gap (model correctly said "no graph evidence
for child labor %" → kept all, but GT needs the one country with that value);
case16 is a 9B think/tool contradiction (reasoning says "output full pool" but
the tool call emits one entity); case26 is an empty candidate pool (retrieve
failure). All three trace to pre-existing bottlenecks, not the reasoning rule.

CWQ react vs stage (same 99 cases, both scored by `llm_hit`): react now leads
**88.9% vs stage 83.8%**, with the FROM→WHERE framework accounting for the gap.
Stage stronger on multi-anchor cases (4/21); react stronger on multi-constraint
and singular-focus cases.

### What's next (the open levers)

**Multi-anchor convergence — EVALUATED AND DEFERRED.** Multi-anchor = ≥2 named
entities that each independently constrain the answer (e.g. case 4:
"country bordering France contains airport serving Nijmegen"). A dual-chain
mechanism was designed (decompose into 2 chains with `start_entity`, traverse
each independently, intersect leaf + CVT-attribute sets, fall back to forced
shortest-path bridging). After gold-grounded evaluation it was **deferred**:

- **Data reachability:** gold-subgraph BFS confirms case 4/21/33 are each
  reachable from BOTH anchors (≤4 hops), and the two chains' leaf sets
  intersect at the gold answer. So A' is *structurally* feasible.
- **GTE recall:** the gold-required relations appear in GTE top-15 for case 4
  (chain B selected `location.adjoining_relationship.adjoins` ✓ under explicit
  multi-anchor hint) and case 33 (chain B selected
  `film.film_character.portrayed_in_films` ✓). Case 21's gold relations
  (`location.country.capital`, `base.culturalevent.event.entity_involved`) do
  NOT appear in GTE top-15 — the gold annotation makes a semantic jump
  ("based in Montgomery" → "capital = Montgomery") that GTE cannot bridge.
- **Model capability:** with an explicit user-prompt hint naming the two
  anchors, the model correctly decomposes into two `start_entity` chains and
  selects the right relations for each. **Without** the hint (current
  AGENTS.md), the model walks a single chain in 3/3 cases — it does not
  self-identify multi-anchor questions.
- **Verdict:** real ROI is +1 case (case 33; case 4 already hits via single
  chain, case 21 is gold-annotation-blocked). Too low to justify the
  traversal-layer cost. The existing stage `_endpoint_bridge_paths` forced-
  bridge fallback covers the "two anchors both reachable" case adequately.
  The `start_entity` data-path layer (commit `df2aed1`) is left in place
  (harmless dead code) but the AGENTS.md guidance for it is removed.
  **Revisit only if a future model self-identifies multi-anchor reliably.**

**GTE retrieve optimization — CONFIRMED WORKING, no change needed.** The
candidate-text contextualization (`start_type` + last-two schema segments)
bridges the deep-semantic ↔ surface-wording gap. Validated on the adjoins
case with three controlled GTE queries (same hint, varying candidate text):

| candidate text construction | adjoins in top-15? | rank |
|---|---|---|
| bare dot-notation id (`location.adjoining_relationship.adjoins`) | ❌ no | — |
| `France` + last-two schema segments | ✅ yes | 7, 8 |
| `country` + last-two schema segments | ✅ yes | 6, 8 |

The entity-context anchor (entity name for f1, type noun for f2+) is what
makes GTE recall adjoins — without it, "bordering" never matches "adjoining".
Measured on 20 cases: f2+ `relation_hint` contains the `start_type` word in
21/21 facts (100%), f1 in 18/20. So both the query side (model-written hint)
and the candidate side (program-built text) carry the same type context,
which is what lets them match. **This mechanism is already shipped; no further
work.**

**Parallel constraints — PROMPT + TRAVERSAL UNION LANDED.** When the
answer must satisfy ≥2 independent attribute filters on the SAME entity (e.g.
a leader whose term started before X AND ended after Y; a country whose
GDP = A AND CPI = B), those filters are NOT sequential hops — they read
different attributes of one entity. Design (mirrors stage's
`_merge_constraint_steps` + `DECOMP_PROMPT` find/verify split):

- **Decompose convention (DONE — AGENTS.md updated):** the model emits sibling
  facts with shared step number: `f2.1`, `f2.2` (both belong to step 2). Each
  has its own `relation_hint` and optional `satisfies` label. AGENTS.md now
  carries an abstract example (a "[person] held which position starting before
  2000 and ending after 2005?" → f1 + f2.1 + f2.2 decomposition).
- **Retrieve/select:** each sibling runs its own GTE retrieve + model
  `select_relations` (independent precision, like stage). Already works —
  harness parses `f2.1`/`f2.2` ids correctly (verified).
- **Traversal union (DONE — `_group_parallel_facts` in tools.py):** `_do_select`
  detects the `f{N}.{k}` id pattern, unions the selected relations of all
  siblings with step N, and walks them at the same level (one step, relation
  union). NOT two sequential hops. Without this, f2.1→entity→f2.2 would chain
  them serially (verified bug on case 14 before fix). Unit-tested: plain
  chains unchanged, siblings merged with dedup.
- **Tool presentation (lightweight):** the evidence tree currently renders the
  merged step as one block (id `f2.1+f2.2`). Per-sibling sub-blocks with
  continuing numbering is a future refinement; the merged view is already
  correct (all relations visible to the model at one level).
- **System role (boundary only):** the system does NOT decide when to split —
  that's the model's job, guided by the abstract example. The system only
  enforces: no empty answer (existing retry), no missing relation selection
  (existing reject), and tolerates non-`.` ids (falls back to plain multi-hop).

**Validation:** unit tests pass (plain chain unchanged, siblings merged with
dedup, lone `f2.1` tolerated). 20-case smoke after fix: 19/20 bit-identical to
pre-fix run; the 1 changed case (case 16) has NO parallel constraints in its
decomposition (`['f1','f2','f3']`) so the fix never touched its path — the
change is intrinsic model variance.

**Stability test (2026-07-06, 20 cases × 3 runs):** 0 crashes / 0 format
errors across 60 decompose calls. 13/20 cases fully stable (same fact count
across 3 runs); the 7 unstable are intrinsic 9B decompose variance (2↔3
facts), unrelated to parallel constraints. The model emitted `f{N}.k` parallel
constraints in 2/20 cases (case 11, case 14) on some runs — **triggering is
unstable** (the hint is soft), but acceptable: parallel-constraint is an
optimization, and when the model decomposes serially instead (f2→f3) the
current traversal still works (just one extra hop). The union mechanism in
`_do_select` is therefore a **no-regression optional path**: model uses
`f{N}.k` → union; model uses f2,f3 → plain multi-hop.

**CVT-value readability — highest-leverage UNADDRESSED lever (~+3 cases).**
Case 73/98/99 (GDP/CPI numeric filters): gold confirms GT is in the candidate
pool and the right relations were selected, but the model can't read the
numeric value (the CVT expands to nothing because the value is not a named
entity — it lives on the CVT's value edges, which the agent's CVT expansion
does not traverse). This is a **subgraph-extraction / value-read gap**, not
a presentation fix. Likely needs a new tool or subgraph-layer change to
surface CVT numerics. Out of scope for the parallel-constraint work.

**Training trajectory regeneration.** Content protocol is stable; ready to
regenerate trajectories for SFT/GRPO.

### Commits on agent-toolcall branch (this work)
- `3707cac` content protocol (react_loop) + expand_branches plural fix + retrieve
  candidate contextualization (start_type + last-two schema segments).
- `81596bd` this spec update (§0).
- `e82071d` quality: comment/code alignment (full→last-two) + de-case-ify
  AGENTS.md examples.
- `6d6201d` gitignore one-off experiment scripts + stray txt.
- `df2aed1` multi-anchor data-path layer (start_entity field, no traversal change).
  **Now deferred** — start_entity guidance removed from AGENTS.md; data-path
  code left as harmless dead code.
- `ab22d75` spec §0 expansion (multi-constraint diagnosis + commit log).
- (pending) AGENTS.md: remove multi-anchor `start_entity` guidance; add parallel-
  constraint guidance (sibling ids `f{N}.1`/`f{N}.2` + abstract example). Spec:
  multi-anchor deferred, GTE confirmed, parallel-constraint design + stability
  test results.
- (pending) tools.py: `_group_parallel_facts` merges `f{N}.k` siblings into one
  step (relation union) in `_do_select`. Unit-tested; 20-case smoke shows
  19/20 bit-identical (1 changed case has no parallel constraints, so the fix
  never touched its path).
- `63af4ee` AGENTS.md: FROM→WHERE→SELECT answer reasoning. Replaces two-layer
  removal with explicit structured-query analogy (list FROM candidates → apply
  each WHERE constraint → SELECT survivors). 100-case: +4 hit (84→88), +0.008
  f1. Strengthens definite-article singular ("THE stadium" → pick current/
  primary, not alternates). Spec results table updated.

### Live probe (2026-07-06) — gold-grounded failure attribution

Ran the agent on the 4 diagnosed multi-anchor cases and 6 multi-constraint
cases with the current code (data-path layer in place, **core traversal
unchanged** — single-chain `_do_select`). To distinguish *data unreachable*
from *model tool-call failure*, the model's trajectory was cross-checked
against the CWQ **gold subgraph** (`q_entity_id_list`, `a_entity_id_list`,
`h/r/t_id_list`): the answer node's touching-edges reveal which relation the
model NEEDED; comparing against the model's retrieved- and selected-relation
sets localizes the failure to one of
`DATA_UNREACHABLE / RETRIEVE_MISS / SELECT_MISS / TRAVERSE_MISS / ANSWER_MISS`.

**Multi-anchor (4 cases):**

| case | Q | verdict | gold-grounded detail |
|---|---|---|---|
| 4 | country bordering France, contains airport serving Nijmegen | **HIT** (Germany) | Single-chain worked; gold answer `Germany` (id 257) appeared in pool. Multi-anchor layer-4 not exercised (chain is structurally unique). |
| 23 | popular sport in Spain, team won 2010 FIFA World Cup | **HIT** | Gold answer in pool; model picked it. (Diagnosis flagged a f2 SELECT_MISS — `sports.sports_team.championships` was retrieved but not selected — yet the answer still surfaced via f1, so it's not actually a miss.) |
| 21 | group fought at Vicksburg, based in Montgomery | **TRAVERSE_MISS** | Gold `Confederate States of America` (id 237) **NOT in pool**. Gold subgraph has the answer attached via `base.culturalevent.event.entity_involved` (Vicksburg→CSA) and `military.armed_force.military_combatant` — neither was selected. Model picked `military.military_unit.place_of_origin` for f1, which goes city→Louisiana→regiments (wrong direction). This is a **selection error**, not data unreachable. |
| 33 | movie with character Teklel Hafouli, Ron Howard | **TRAVERSE_MISS** | Gold `The Journey` (id 729) **NOT in pool**. Gold edges show `film.performance.character` and `film.film.starring` (film→performance→character). Model selected `film.personal_film_appearance.person` + `film.performance.character` for f2 — but f1 picked `film.director.film`/`film.film.directed_by`, traversing Ron Howard's filmography; the f2 character-filter wasn't applied structurally. Leaf-intersection (layer-4) would catch this: Ron Howard's films ∩ films containing Teklel Hafouli. |

**Verdict on layer-4 necessity:** reinforced. Case 21 & 33 are genuine
multi-anchor cases where the single-chain can't structurally express the
AND of two constraints. Layer-4 (dual-chain + leaf intersection) is the right
fix for both. Gain ceiling: **+2 cases (21, 33)** → 83.8% → ~86%. (Case 4
already hits via single chain; case 23 already hits.)

**Multi-constraint (6 cases):**

| case | Q | GT | verdict | gold-grounded detail |
|---|---|---|---|---|
| 22 | country in ASEAN Common TZ, largest population | India | **SELECT_MISS** | Gold: India (id 193) IS in the subgraph, connected to ASEAN Common TZ (id 4) via `location.location.time_zones` (h193→t194). Model **retrieved** `location.location.time_zones` for f1 but **selected** `time.time_zone.locations_in_this_time_zone` instead — which returns the continent Asia. So this is a **selection error**, NOT a structural dead-end. (Caveat: GT India is dubious — India is UTC+5:30, not in ASEAN TZ UTC+6:5 — likely a gold-labeling issue.) |
| 41 | location in Anadyr TZ, biggest population | India | **SELECT_MISS** | Same as 22: model retrieved `location.location.time_zones` but selected the wrong relation. (Caveat: GT India is wrong — India is not in Anadyr TZ UTC+12.) |
| 67 | "modern" in country whose anthem is Bilady³ | Modern Standard Arabic | **TRAVERSE_MISS** | f1 anthem→Egypt worked. Gold: MSA (id 123) attaches to Egypt (id 30) via **`location.country.official_language`** (h30→t123) — which the model DID retrieve for f2 but **selected** `common.topic.notable_for`/`notable_types` instead. Pure f2 select error; not a decomposition/prompt gap as first thought. |
| 73 | country speaking Portuguese, GDP=100349905926 | South Africa | **ANSWER_MISS** | Gold `South Africa` (id 498) **IS in pool** (16 entities). Retrieve + select correct (both `language...countries_spoken_in` and `gdp_real` chosen). Bottleneck = model can't READ the GDP numeric (stored as CVT Freebase IDs `g.1hhc...`) to filter. |
| 98 | country CPI=-1.61, speaks Portuguese | Macau | **ANSWER_MISS** | Gold `Macau` (id 322) **IS in pool**. Same as 73: CVT-value readability. |
| 99 | country CPI=-1.56, speaks Portuguese | Macau | **HIT** (recall 0.15) | Model dumped all 12 Portuguese countries (Macau among them) since it can't read CPI — got partial credit. |

**Revised multi-constraint verdict — four distinct failure modes:**

1. **CVT-value readability** (73/98/99, the GDP/CPI cluster — **highest leverage,
   ~+3 cases**): GT is reachable and in the pool; the model selected the right
   relations; it just can't read the numeric value (rendered as bare Freebase
   IDs `g.1hhc...`) to apply the filter. Fix = surface CVT value attributes
   (numerics, dates) in `expand_branches` / tree rendering. Presentation-layer
   fix, no traversal change.
2. **f2 selection error** (67, +1 case): the right relation
   (`location.country.official_language`) was retrieved and in the candidate
   list; model picked `notable_for` instead. Fix = stronger AGENTS.md guidance
   ("prefer typed-domain relations over generic topic.* when both are
   candidates for the same hint") OR a re-rank that downweights
   `common.topic.*`. **No code mechanism needed.**
3. **TZ-relation selection error** (22/41): same shape as 67 — `location.location.time_zones`
   was retrieved but `time.time_zone.locations_in_this_time_zone` was selected.
   BUT GT India is mislabeled for both (wrong timezone), so even a correct
   selection wouldn't help. **Skip until gold labels are verified.**
4. **Multi-anchor (21/33)**: layer-4 leaf intersection — see above.

**Bottom line:** the single highest-ROI fix is **CVT-value readability**
(presentation-layer), worth ~+3 cases. Second is **layer-4 multi-anchor**
(+2). Third is **f2-selection nudging** (+1, prompt-only). The TZ cases (22/41)
are blocked on gold-label verification, not on the agent.

### Commits on agent-toolcall branch (this work)
- `3707cac` content protocol (react_loop) + expand_branches plural fix + retrieve
  candidate contextualization (start_type + last-two schema segments).
- `81596bd` this spec update (§0).
- `e82071d` quality: comment/code alignment (full→last-two) + de-case-ify
  AGENTS.md examples.
- `6d6201d` gitignore one-off experiment scripts + stray txt.
- `df2aed1` multi-anchor data-path layer (start_entity field, no traversal change).

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
