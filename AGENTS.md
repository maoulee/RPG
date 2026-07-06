# AGENTS.md — subgraph (KGQA agent)

Project-level instruction file for any coding agent working in this repo.
Read it before touching anything. Design rationale and operational memory
live elsewhere (see "Authoritative docs") — this file is only the **rules
of the road**.

## Authoritative docs (read these first)
- **Design spec** — `specs/agent_redesign_spec.md` (§0 = current truth on
  results, §1+ = architecture). This is *why* things are the way they are.
- **Operational memory** — `specs/SESSION_MEMORY.md`. How to run the
  pipeline, where artifacts live, latest results, traps. Update it whenever
  a run finishes or a trap is found.
- **Agent prompt** — `kgqa/agent/AGENTS.md`. The rules the *model* follows
  at inference time (separate from this repo-agent file).

## Repo layout (tracked vs untracked)
```
tracked (safe, survives reset):
  kgqa/          — pipeline source
  scripts/       — run / render / diagnostic scripts
  specs/         — design spec + session memory  ← home for these
  docs/          — historical / reference design notes only
  tests/         — test suite
  config/        — stage prompt sources

untracked (will be LOST on container reset):
  reports/       — run outputs (results.json, trajectories). Reproducible.
  tmp/           — scratch. Never put anything you want to keep here.
  logs/          — server & run logs
  data/          — datasets (LFS exceptions aside)
```

## Rules — keep docs from scattering
This is the rule the user cares about. Follow it for every new artifact:

1. **Design spec and session memory go in `specs/`, nowhere else.**
   No `*.md` spec/memory files in the repo root, under `scripts/`, or loose
   in `docs/`. If you're tempted to drop a `something_notes.md` next to a
   script — don't. Fold it into `specs/SESSION_MEMORY.md`, or file it under
   `docs/`.

2. **No `.txt` scratch / case-study / paste files in the repo root.**
   The root currently has stale `case_study_*.txt`, `pasted-text-*.txt`,
   `pipeline_prompts.txt`, `action_skill_correlation_analysis.txt` — all
   untracked and should not be added to going forward. New scratch belongs
   in `tmp/`; new case studies belong in `docs/case_studies/`.

3. **Run results (`reports/`) are never committed.** They are reproducible
   via `run_agent_batch.py`. Record the *metrics + run path* in
   `specs/SESSION_MEMORY.md`, not the artifacts.

4. **Diagnostic / one-off scripts**: put them in `scripts/` and add them to
   `.gitignore` under the "One-off experiment / diagnostic scripts" block
   unless they're part of the supported pipeline. `run_agent_batch.py` and
   `render_trajectory.py` are supported; `test_*.py` / `probe_*.py` /
   `diag_*.py` are not.

5. **When in doubt about where something goes, ask the user.** Do not
   silently create a new top-level directory.

## Things that are easy to get wrong here
- `reports/` and `tmp/` are BOTH gitignored. Anything written there is gone
  on container reset. If an untracked artifact genuinely matters, copy it
  into `specs/` with a dated name.
- "Deleted" scripts are recoverable from git history
  (`git show <commit>:scripts/<name>.py`); only never-committed files are
  truly lost.
- vLLM's `reasoning_end_str` can leak into `content` and corrupt a tool arg.
  The parse fallback usually saves it. See SESSION_MEMORY trap note.

## Code conventions
- Match the surrounding code: naming, comment density, idioms.
- Reference code as `file_path:line_number` (clickable in the harness).
- Keep functions small; prefer pure helpers for anything tested.