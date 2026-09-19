#!/usr/bin/env python3
"""PERF-4 dispatch-segment replayer (sync-tax measurement, 2026-08-23).

Replays the DISPATCH half of a finished rollout from its results.json: the
trajectory's role=assistant entries are exactly the raw_response strings that
were fed to process_turn at the time, so feeding them back (with the same
sample/ctx reconstruction) reproduces the same dispatch work — parse →
validate → GTE → walk → render → evidence build — WITHOUT calling the LLM.
GTE (:8003) and the walk lanes run for real (deterministic, hot cache), so
the replayed wall includes every wait the real dispatch paid.

Round loop mirrors seq_rollout.rollout(): asyncio.gather + DISPATCH_CONCURRENCY
semaphore, INFLOW top-up, the module-level walk coordinator / GTE collector.

Fidelity check: after the replay, each case's answer/n_turns/n_reject are
compared against the recorded result — divergence means the replay drifted.

Env:
  RESULTS        results.json to replay        (default reports/perf3_r267g3.json)
  SPLIT          sample split                  (default test_v4)
  CASE_FILTER    case-id file                  (default tmp/regress267.txt)
  INFLOW_TARGET  inflow admission target       (default 500, matches perf3)
  REPLAY_N       replay only the first N trajectories (0 = all; warmup/iteration)
  OUT            optional json dump of per-round walls (default tmp/replay_dispatch.json)

Usage:
  scripts/replay_dispatch.py [--profile]     # --profile: cProfile top-30 cumtime
"""
import asyncio
import cProfile
import io
import json
import os
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, "/zhaoshu/subgraph")

import aiohttp

from kgqa.rl.seq_rollout import _load
from kgqa.agent.seq_react_loop import SeqReactCase
from kgqa.agent.loop import _ctx_to_result_dict
from kgqa.core.utils import PHASE_TIMES

# the rollout main() sets these defaults before running; mirror them so the
# coordinator behavior matches the recorded run
os.environ.setdefault("WALK_BATCH_WINDOW", "1.0")
os.environ.setdefault("SEQ_PROMPT", "V21")
os.environ.setdefault("DISPATCH_CONCURRENCY", "64")
# STANDING STACK ENVS: the recorded runs (v06_aligned etc.) ran with the
# SEQ_MULTISTEP stack on — without these the replay silently takes the
# legacy render lane and every comparison is meaningless
os.environ.setdefault("SEQ_MULTISTEP", "1")
os.environ.setdefault("SEQ_RENDER_V38", "1")


def _load_recorded(path):
    recs = json.loads(Path(path).read_text())
    by_traj = {}          # (case_idx, sample_idx) -> [assistant contents in order]
    rsn_by_traj = {}      # same shape -> [reasoning or None per assistant step]
    meta = {}
    traj_ref = {}         # (case_idx, sample_idx) -> [(role, content), ...] oracle ref
    for r in recs:
        k = (r["case_idx"], r["sample_idx"])
        by_traj[k] = [m["content"] for m in r["trajectory"]
                      if m.get("role") == "assistant"]
        rsn_by_traj[k] = [m.get("reasoning") for m in r["trajectory"]
                          if m.get("role") == "assistant"]
        traj_ref[k] = [(m.get("role"), m.get("content"))
                       for m in r["trajectory"]]
        meta[k] = {"case_id": r["case_id"], "answer": r.get("answer", ""),
                   "f1": r.get("f1", 0), "n_turns": r.get("n_turns", 0),
                   "n_reject": r.get("n_reject", 0), "failed": r.get("failed", False)}
    return by_traj, meta, traj_ref, rsn_by_traj


async def replay(by_traj, meta, traj_ref, rsn_by_traj, cases, inflow_target):
    t0 = time.time()
    pilot_rows = [{"case_id": s["id"], "question": s["question"],
                   "gt_answers": s.get("a_entity", [])} for s in cases]

    # expand exactly like the rollout: (case_idx, sample_idx) keyed SeqReactCases
    all_react = []
    for ci, (s, pr) in enumerate(zip(cases, pilot_rows)):
        for gi in range(3):
            k = (ci, gi)
            if k not in by_traj:
                continue
            rc = SeqReactCase(s, pr, ci)
            rc._rec = by_traj[k]          # recorded assistant contents
            rc._rec_rsn = rsn_by_traj[k]  # recorded reasoning per content
            rc._rec_i = 0
            rc._rec_meta = meta[k]
            rc._rec_traj = traj_ref[k]
            all_react.append((rc, k))
    print(f"  trajectories to replay: {len(all_react)}", flush=True)
    # alignment guard: recorded case_id must equal the sample at that index
    for rc, (ci, gi) in all_react:
        assert rc._rec_meta["case_id"] == cases[ci]["id"], \
            f"case_idx {ci} misaligned: {rc._rec_meta['case_id']} != {cases[ci]['id']}"

    if inflow_target and inflow_target > 0:
        react_cases = [rc for rc, _ in all_react[:inflow_target]]
        pending = [rc for rc, _ in all_react[inflow_target:]]
    else:
        react_cases = [rc for rc, _ in all_react]
        pending = []
    print(f"  inflow: {len(react_cases)} admitted, {len(pending)} pending", flush=True)

    round_walls = []
    max_rounds = 16
    dsem = asyncio.Semaphore(int(os.environ.get("DISPATCH_CONCURRENCY", "64")))
    pl_sem = asyncio.Semaphore(16)

    async def _pl(rc):
        async with pl_sem:
            await rc.prelink(session)

    async with aiohttp.ClientSession() as session:
        _t_pl0 = time.time()
        await asyncio.gather(*[_pl(rc) for rc in react_cases])
        print(f"  prelink done in {time.time()-_t_pl0:.0f}s", flush=True)
        _t_admit = time.time()
        for rc in react_cases:
            rc._admit_t = _t_admit

        for rnd in range(max_rounds):
            while pending:
                n_active = sum(1 for rc in react_cases if rc.is_active)
                if n_active >= inflow_target:
                    break
                batch = pending[:inflow_target - n_active]
                del pending[:len(batch)]
                react_cases.extend(batch)
                await asyncio.gather(*[_pl(rc) for rc in batch])
                _t_top = time.time()
                for rc in batch:
                    rc._admit_t = _t_top

            active = [rc for rc in react_cases if rc.is_active]
            if not active:
                if pending:
                    continue
                break

            # instead of the LLM batch: take each active case's next RECORDED
            # assistant content (None when the recording ran out = divergence)
            raws, rsns, diverged = [], [], 0
            for rc in active:
                if rc._rec_i < len(rc._rec):
                    raws.append(rc._rec[rc._rec_i])
                    rsns.append(rc._rec_rsn[rc._rec_i])
                    rc._rec_i += 1
                else:
                    raws.append(None)
                    rsns.append(None)
                    diverged += 1
            if diverged:
                print(f"  ⚠ round {rnd+1}: {diverged} cases exhausted their recorded "
                      f"content while still active", flush=True)

            async def _proc(rc, raw, rsn=None):
                async with dsem:
                    if not raw:
                        rc.messages.append({"role": "assistant", "content": ""})
                        rc.messages.append({"role": "user", "content": rc.allowed_tools_hint()})
                        return
                    await rc.process_turn(session, raw, rsn)

            _tr = time.perf_counter()
            if os.environ.get("ROUND_SCHED", "1") != "0":
                # round-level three-phase dispatch (perf-4): A for all cases →
                # every GTE/walk request fires together → C for all cases. Same
                # per-case semantics as process_turn (run_round_dispatch).
                from kgqa.agent.seq_react_loop import run_round_dispatch
                await run_round_dispatch(list(zip(active, raws, rsns)), session)
            else:
                await asyncio.gather(*[_proc(rc, raw)
                                       for rc, raw in zip(active, raws)])
            round_walls.append(time.perf_counter() - _tr)

            _t_rnd = time.time()
            for rc in active:
                if (rc.done or rc.failed) and getattr(rc, "_done_t", None) is None:
                    rc._done_t = _t_rnd
            done = sum(1 for rc in react_cases if rc.done)
            failed = sum(1 for rc in react_cases if rc.failed)
            print(f"  round {rnd+1}: {len(active)} active → done={done} failed={failed} "
                  f"dispatch={round_walls[-1]:.1f}s [t={time.time()-t0:.0f}s]", flush=True)

    # fidelity check: replayed outcome vs recorded outcome — the full-trajectory
    # byte diff is the equivalence ORACLE for the round-scheduler refactor: any
    # behavioral divergence (tool calls, tool results, harness feedback messages)
    # shows up as a (role, content) sequence mismatch. ORACLE_REF (env) points
    # at a DUMP_TRAJ file from a reference replay — when set, the byte diff runs
    # against THAT (same-process-determinism baseline) instead of the recorded
    # results.json (whose candidate_pool order carries the pre-fix hash noise).
    ref = None
    if os.environ.get("ORACLE_REF"):
        ref = json.loads(Path(os.environ["ORACLE_REF"]).read_text())
    n_match = n_answer_mismatch = n_turn_mismatch = n_reject_mismatch = 0
    n_traj_mismatch = 0
    _first_mismatch = None
    for rc, k in all_react:
        rc.rescue_terminal_answer()
        r = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
        ans = r.get("llm_answer_str", "") or r.get("llm_answer", "") or ""
        n_turns = sum(1 for st in rc.ctx.trajectory if st.get("role") == "assistant")
        n_reject = sum(1 for st in rc.ctx.trajectory
                       if st.get("role") == "tool" and "REJECTED" in (st.get("content") or ""))
        m = rc._rec_meta
        a_ok = (ans == m["answer"])
        t_ok = (n_turns == m["n_turns"])
        r_ok = (n_reject == m["n_reject"])
        n_answer_mismatch += (not a_ok)
        n_turn_mismatch += (not t_ok)
        n_reject_mismatch += (not r_ok)
        n_match += (a_ok and t_ok and r_ok)
        # full trajectory diff: (role, content) pairs, reasoning/name fields ignored
        got = [(st.get("role"), st.get("content")) for st in rc.ctx.trajectory]
        if ref is not None:
            want = [tuple(x) for x in ref.get("|".join(map(str, k)), [])]
        else:
            want = rc._rec_traj
        if got != want:
            n_traj_mismatch += 1
            if _first_mismatch is None:
                _first_mismatch = (k, got, want)
    print(f"  fidelity: {n_match}/{len(all_react)} exact "
          f"(answer≠ {n_answer_mismatch}, turns≠ {n_turn_mismatch}, reject≠ {n_reject_mismatch})",
          flush=True)
    print(f"  TRAJECTORY ORACLE: {len(all_react)-n_traj_mismatch}/{len(all_react)} byte-identical"
          + (" (vs ORACLE_REF)" if ref is not None else " (vs recorded results.json)"),
          flush=True)
    if os.environ.get("DUMP_TRAJ"):
        dump = {"|".join(map(str, k)):
                [[ro, ct] for ro, ct in
                 ((st.get("role"), st.get("content")) for st in rc.ctx.trajectory)]
                for rc, k in all_react}
        Path(os.environ["DUMP_TRAJ"]).write_text(
            json.dumps(dump, ensure_ascii=False))
        print(f"  DUMP_TRAJ → {os.environ['DUMP_TRAJ']}", flush=True)
    if _first_mismatch is not None:
        k, got, want = _first_mismatch
        print(f"  ⚠ first traj mismatch at {k}: got {len(got)} steps, want {len(want)} steps",
              flush=True)
        for i in range(max(len(got), len(want))):
            g = got[i] if i < len(got) else None
            w = want[i] if i < len(want) else None
            if g != w:
                print(f"    step {i}: got={str(g)[:300]!r}\n            want={str(w)[:300]!r}",
                      flush=True)
                break

    # per-case wall distribution (admit → done)
    _walls = sorted(getattr(rc, "_done_t", 0) - getattr(rc, "_admit_t", 0)
                    for rc, _ in all_react if getattr(rc, "_done_t", None))
    if _walls:
        _n = len(_walls)
        print(f"  per-case wall: mean={sum(_walls)/_n:.0f}s p50={_walls[_n//2]:.0f}s "
              f"p90={_walls[int(_n*0.9)]:.0f}s max={_walls[-1]:.0f}s", flush=True)
    return round_walls


def main():
    do_profile = "--profile" in sys.argv
    results_path = os.environ.get("RESULTS", "reports/perf3_r267g3.json")
    split = os.environ.get("SPLIT", "test_v4")
    case_filter = os.environ.get("CASE_FILTER", "tmp/regress267.txt")
    inflow = int(os.environ.get("INFLOW_TARGET", "500") or 0)
    replay_n = int(os.environ.get("REPLAY_N", "0") or 0)

    print(f"═══ dispatch replay: {results_path} (split={split}, inflow={inflow}) ═══",
          flush=True)
    by_traj, meta, traj_ref, rsn_by_traj = _load_recorded(results_path)
    if os.environ.get("REPLAY_ONLY"):
        only = {int(x) for x in os.environ["REPLAY_ONLY"].split(",") if x.strip()}
        by_traj = {k: v for k, v in by_traj.items() if k[0] in only}
        meta = {k: v for k, v in meta.items() if k[0] in only}
        traj_ref = {k: v for k, v in traj_ref.items() if k[0] in only}
        rsn_by_traj = {k: v for k, v in rsn_by_traj.items() if k[0] in only}
        print(f"  REPLAY_ONLY={sorted(only)}: {len(by_traj)} trajectories", flush=True)
    if replay_n > 0:
        keys = sorted(by_traj)[:replay_n]
        by_traj = {k: by_traj[k] for k in keys}
        meta = {k: meta[k] for k in keys}
        traj_ref = {k: traj_ref[k] for k in keys}
        rsn_by_traj = {k: rsn_by_traj[k] for k in keys}
        print(f"  REPLAY_N={replay_n}: limited to {len(by_traj)} trajectories", flush=True)
    if case_filter:
        os.environ["CASE_FILTER"] = case_filter   # _load reads it
    cases = _load(split, 0)
    assert cases, "no cases loaded"
    # RESULTS_ORDER: reorder the pool to the order case_ids FIRST APPEAR in
    # the recorded results — the run's case_idx space is its own pool order
    # (e.g. a 48-case subset selected under a different pool snapshot), so
    # index-based alignment needs the recorded order, not pkl order.
    if os.environ.get("RESULTS_ORDER", "") == "1":
        _order = []
        for k in sorted(by_traj, key=lambda x: (x[0], x[1])):
            cid = meta[k]["case_id"]
            if cid not in _order:
                _order.append(cid)
        _by_id = {s["id"]: s for s in cases}
        _missing = [c for c in _order if c not in _by_id]
        assert not _missing, f"cases missing from pool: {_missing[:3]}"
        cases = [_by_id[c] for c in _order]
        print(f"  RESULTS_ORDER: pool reordered to {len(cases)} recorded cases",
              flush=True)
    assert all(k[0] < len(cases) for k in by_traj), "recorded case_idx out of range"

    t0 = time.time()
    if do_profile:
        prof = cProfile.Profile()
        prof.enable()
    round_walls = asyncio.run(replay(by_traj, meta, traj_ref, rsn_by_traj,
                                     cases, inflow))
    if do_profile:
        prof.disable()
        s = io.StringIO()
        ps = pstats.Stats(prof, stream=s).sort_stats("cumulative")
        ps.print_stats(40)
        print("\n── cProfile top-40 cumtime (dispatch loop incl. waits) ──")
        print(s.getvalue())

    dt = time.time() - t0
    tot = sum(round_walls)
    print(f"\n═══ replay done in {dt:.0f}s: dispatch wall={tot:.0f}s over {len(round_walls)} rounds "
          f"(mean {tot/max(len(round_walls),1):.1f}s/round) ═══", flush=True)
    from kgqa.core.utils import PHASE_TIMES as PT
    print(f"  PHASE_TIMES: walk={PT['walk']:.0f}s (collect={PT.get('walk_collect',0):.0f}s "
          f"wait={PT.get('walk_wait',0):.0f}s exec={PT.get('walk_exec',0):.0f}s) "
          f"render={PT['render']:.0f}s gte={PT['gte']:.0f}s (n={PT.get('gte_n',0):.0f}, "
          f"collect={PT.get('gte_collect',0):.0f}s)", flush=True)
    from kgqa.agent import seq_tools as _st
    ws = _st._WALK_BATCH_STATS
    print(f"  walk-batch: {ws['batches']} flushes (single={ws['single']} burst={ws['burst']}) "
          f"reqs={ws['reqs']} slots={ws['slots']} memo={ws['memo_hits']} "
          f"dedup={ws['dedup_shares']} collect={ws['collect_s']:.1f}s", flush=True)
    from kgqa.stages import stage2_entity as _s2
    gs = _s2._GTE_BATCH_STATS
    print(f"  gte-batch(client): {gs['flushes']} flushes (single={gs['single']} burst={gs['burst']}) "
          f"reqs={gs['reqs']} dedup={gs['dedup']} memo={gs['memo_hits']} "
          f"collect={gs['collect_s']:.1f}s", flush=True)
    print(f"  round dispatch walls: {[round(w,1) for w in round_walls]}", flush=True)

    out = os.environ.get("OUT", "tmp/replay_dispatch.json")
    Path(out).write_text(json.dumps({
        "results": results_path, "n_traj": len(by_traj),
        "dispatch_wall_s": round(tot, 1), "rounds": [round(w, 1) for w in round_walls],
        "phase": {k: round(v, 1) for k, v in PT.items()},
    }, ensure_ascii=False, indent=1))
    print(f"  → {out}", flush=True)


if __name__ == "__main__":
    main()
