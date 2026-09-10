# 游走(Walk)子系统优化分析 — Codex 交接文档

> 日期:2026-09-10 | 分支:walk-perf | 目的:评估游走提速方案
> 本文档自带全部相关代码(网页版可直接读),无需访问仓库。

## 0. 硬约束(任何方案必须满足)

- **4 核 cgroup**:容器只见 128 核但被限制为 4 物理核;walk 用 3 个
  spawn 进程 lane + 主进程 asyncio loop + vLLM(CPU 侧 prefill)共享。
  实测 4 lane 比 3 lane 更慢(核争用 + 打包碎片化)。
- **结果等价性验证方法**:同一输入(7 组合:case×center×rels,含稠密
  hub case)新旧游走输出 pickle 后 sha256 逐字节比对;48×3 rollout
  mean_f1 带内;tests 141 passed。
- **纯 CPU**:游走 worker 内禁止任何 LLM/GTE 调用(输入只有
  ents/rels/h_ids/r_ids/t_ids 数组)。
- **规模**:单 case 图 7k+ 边、hub 节点度 900+;一次 48case×3sample
  run 约 350 次 sg 调用 → ~1800-2300 个 (center, relset) 游走单元。

## 1. 系统上下文:游走在哪

Agent 检索环(每 case ~8 轮):
```
LLM → retrieve_relations(GTE 排序) → retrieve_subgraph(游走)
    → 渲染证据树 → LLM 下一轮 → ... → answer
```
`retrieve_subgraph` 的 B 段 = 本文的游走。每次调用可带 1..N 个 center
(变量绑定展开),每个 center 一个 (center, rel_idxs) 游走单元(slot),
关系集 rel_idxs 通常 1-7 条(family/bridge 展开后)。

## 2. 成本模型(实测结论,已验证)

**RPE 是全环境游走,与关系集宽度无关**:`_search_terminal_relation_paths`
的桥跳(bridge hop)可以走任何非选中关系,只有段终止(terminal)由选中
关系决定 → 遍历覆盖 anchor 的整个 3-hop 环境,relset 只影响哪些段被记录。
因此"关系集变宽"不增加单次游走成本。

**时间线**(48×3,walk exec = lane 进程累计):
| 时期 | walk exec | 总墙钟 | 变化 |
|---|---|---|---|
| walk-perf 基线(2026-09-07) | 364s | 378s | 邻接 memo + GC 调优后 |
| 现在(多绑定×模式修复期) | 2150-2400s | ~19-20min | 质量弧线 0.664→0.693 的代价 |

**增长来源**(已定量):
- slot 数 ~800 → 1800-2300:`?var` 多绑定展开(19 队联赛类,单调用
  10-50 个 center)+ walk_extra 账本(已 cap 6,+0.8pp f1)。
- 单 slot 成本 ~0.4s → 0.9-1.2s:关系集更宽(1.5→4-5 条)在
  "全环境游走"模型下→记录路径更多,但遍历本身等价。
- **exec 集中在 hub**:砍掉廉价叶子 slot(-23%)后 exec 不降
  (2152s 持平)——贵的是 hub 中心的 3-hop 环境 × 不同 relset 重试
  (memo 只认精确 (center, relset) 对)。

**相位分解**(patprefix run,重叠累计口径):
```
llm=27193s dispatch=87917s
  inside-dispatch: walk=87480s (collect=262s wait=49952s exec=2408s)
                   render=53s gte=231s (n=2933)
walk-batch: 190 flushes reqs=351 slots=1867 memo=170 ipc=253MB
```
- 纯 LLM 21.6s/turn(正常);墙钟每轮 ~120s 的大头是 walk 排队
  (wait 5 万秒是 3-lane 吞吐地板 + 拥塞记账)。
- exec 2408s / 3 lane ≈ 800s 串行地板,决定总墙钟。

**历史 profile**(walk-perf 时代,单 walk 级):
- 稀疏 case 热点:证据构建 formatting._is_latinish 58%(已字符级 memo 修复);
- 稠密 case 热点:relation_prior_expand 76%;
- 邻接三处全量重建(已 per-case memo 修复,id() 键 + 数组自 pin)。

## 3. 已验证的事实与被否决方案(勿重复)

| 方案 | 判决 | 数据 |
|---|---|---|
| WALK_POOL 3→4 + 窗口 0.3s | **负** | 墙钟 +18%(核争用 exec+19%,burst 62→29 碎片化) |
| GTE 批窗口 0.08/0.02 | **正,已锁** | GTE collect 1967→162s(-92%),p50 墙钟 -12% |
| walk_extra 近因 cap 6 | **正,已锁** | slots -23%,f1 0.6849→0.6930 |
| 模式态前缀 mask(RPE 不入已走领地) | **负,默认关** | 速度零增益(exec 2408≈2152),f1 -2.4pp;RPE 大头=每绑定 3-hop 新边疆(hop2-3 不在前缀),mask 只省 hop1 回头路 |
| 原点 2 步链式(从第一子图中心重走) | **设计错误,已回退** | 第一子图 2 跳深,原点重走=回退烧预算 |
| 同中心环境缓存+每 relset 记账 | **理论可行未做** | RPE 的 beam 剪枝在探索中依赖 relset(coverage 排序),拆分不保结果等价 |

## 4. 执行链与代码

### 4.1 入口:sg 调用 → 游走提交(agent 侧)

`_sg_execute`(kgqa/agent/seq_tools.py)把每个 center 打包成
(center_idx, rel_idxs, fid[, prefix]) 元组交给 `_run_walk_packed`;
WALK_POOL>0 + WALK_BATCH_WINDOW>0 时走**批协调器**(默认路径)。

```python
def _walk_case_steps(case_key, d, steps):
    """Worker-side traversal of ONE case's steps (d = its cached arrays).
    Pure: identical inputs → identical output list (per-center dict[label ->
    PatternEvidence], {} when the walk reached nothing). Shared by the
    per-call lane task (_walk_call_spawn) and the round-level batch task
    (_walk_batch_spawn).
    Step tuples are (center_idx, rel_idxs, fid) or, for a PATTERN-PREFIX
    continuation (user design 2026-09-10), (center_idx, rel_idxs, fid,
    prefix_names): the center is a tail of an earlier pattern and the
    prefix = the earlier walk's node NAMES — RPE records target edges INTO
    that territory but never expands through it (状态保持,不重复回去)."""
    sample, pilot_row, ents, rels, h_ids, r_ids, t_ids, rel_texts = d
    import asyncio as _aio
    n2i = None
    cases = []
    for step in steps:
        center_idx, rel_idxs, fid = step[0], step[1], step[2]
        cs = CaseState(case_id=case_key[0], case_num=case_key[1],
                       sample=sample, pilot_row=pilot_row)
        cs.anchor_idx = center_idx
        cs.anchor_name = ents[center_idx] if 0 <= center_idx < len(ents) else ""
        cs.h_ids, cs.r_ids, cs.t_ids = h_ids, r_ids, t_ids
        cs.ents, cs.rels, cs.rel_texts = ents, rels, rel_texts
        cs.step_relations = [set(rel_idxs)]
        cs.steps = [{"id": fid or "f"}]
        cs.breakpoints = {}
        cs.active = True
        if len(step) > 3 and step[3]:
            # names → idx set (once per call: the map is shared by all steps)
            if n2i is None:
                n2i = {}
                for j, e in enumerate(ents):
                    n2i.setdefault(str(e), j)
            cs.prefix_nodes = frozenset(
                n2i[nm] for nm in step[3]
                if nm in n2i and n2i[nm] != center_idx)
        cases.append(cs)
    try:
        _aio.run(stage_5_graph_traversal(cases))
    except Exception:
        return [{} for _ in steps]
    out = []
    for step, cs in zip(steps, cases):
        center_idx, rel_idxs = step[0], step[1]
        paths = cs.paths or []
        patterns = (compress_paths(paths, ents, rels, center_idx, set())
                    if paths else (cs.logical_paths or []))
        valid = [lp for lp in patterns if isinstance(lp, dict) and lp.get("best_raw_path")]
        valid = materialize_selected_logical_patterns(
            valid, ents, rels, h_ids, r_ids, t_ids, center_idx, set())
        if not valid:
            out.append({})
            continue
        out.append(build_pattern_evidence_triples(
            valid, ents, rels, h_ids, r_ids, t_ids, center_idx,
            max_grouped_lines=120, selected_rel_ids=set(rel_idxs)))
    return out


def _walk_call_spawn(task):
    """Worker body for ONE retrieve_subgraph call: task = (case_key, ctx_data,
    steps) with steps = [(center_idx, rel_idxs, fid), ...]. All centers of the
    call share the case arrays, so they traverse in ONE stage_5 batch (its
    native multi-case mode — per-case state only, thread-isolated inside the
    worker). Returns a per-center list aligned with steps, each entry a
    dict[label -> PatternEvidence], or {} when that center's walk reached
    nothing; "MISS" when the case arrays are not cached (caller reships with
    data)."""
    case_key, ctx_data, steps = task
    if ctx_data is not None:
        if len(_W_CASE_CACHE) > 512:
            _W_CASE_CACHE.clear()
        _W_CASE_CACHE[case_key] = ctx_data
    d = _W_CASE_CACHE.get(case_key)
    if d is None:
        return "MISS"          # sentinel: caller reships this task with data

```

### 4.2 批协调器:_walk_flush_async(去重/memo/sticky-lane/打包)

**一次 flush:slot 去重 → memo 查询 → 每 lane 一个打包任务 → MISS 重发 → 回填 memo → 解析 future。** slot 键 =(center_idx, frozenset(rel_idxs), prefix)。

```python
    window counted from the first arrival (mirrors the GTE _collect_batch
    adaptive two-stage window)."""
    b = _WALK_BATCH
    if b is None:
        return
    if len(b["reqs"]) > 1:
        import time as _t
        _full = float(os.environ.get("WALK_BATCH_WINDOW", "1.0") or 0)
        remain = (b["t_first"] + _full) - _t.perf_counter()
        if remain > 0:
            b["loop"].call_later(remain, _walk_flush_now)
            return
    _walk_flush_now()


def _walk_flush_now():
    """Close the open batch (later arrivals open a fresh one) and hand it to
    the async flusher."""
    global _WALK_BATCH
    b, _WALK_BATCH = _WALK_BATCH, None
    if b is not None and b["reqs"]:
        b["loop"].create_task(_walk_flush_async(b))


async def _walk_flush_async(batch):
    """One flush: dedup → memo lookup → sticky lane grouping (ONE packed task
    per lane) → MISS reship → memo fill → resolve every request future."""
    import asyncio as _aio
    import pickle as _pkl
    import time as _t
    from kgqa.core.utils import PHASE_TIMES
    reqs = batch["reqs"]
    st = _WALK_BATCH_STATS
    n_req_steps = sum(len(r["steps"]) for r in reqs)
    t_flush = _t.perf_counter()
    st["batches"] += 1
    st["single" if len(reqs) == 1 else "burst"] += 1
    st["reqs"] += len(reqs)
    st["collect_s"] += sum(t_flush - r["t0"] for r in reqs)
    st["burst_span_s"] += max(r["t0"] for r in reqs) - min(r["t0"] for r in reqs)
    PHASE_TIMES["walk_collect"] += sum(t_flush - r["t0"] for r in reqs)
    # flush WALL (first arrival → every future resolved) — the batch-view cost;
    # flushes overlap each other/GTE, so the SUM upper-bounds the walk share.
    _t_first = min(r["t0"] for r in reqs)
    try:
        # 1. unique execution slots per case, memo hits served for free.
        # slot key = (center_idx, frozenset(rel_idxs), prefix) — the walk
        # consumes rel_idxs as a SET, so order never affects the result; the
        # PATTERN-PREFIX set (continuation walks, user design 2026-09-10) is
        # part of the identity: the same center+rels walked with a different
        # prefix is a different result.
        def _step_key(s):
            i, rel_idxs = s[0], s[1]
            _pf = s[3] if len(s) > 3 else None
            return (i, frozenset(rel_idxs), _pf)

        case_slots, case_ctx = {}, {}
        for r in reqs:
            ck = r["case_key"]
            slots = case_slots.setdefault(ck, {})
            case_ctx.setdefault(ck, r["ctx"])
            for s in r["steps"]:
                slots.setdefault(_step_key(s), (s[0], s[1],
                                                s[3] if len(s) > 3 else None))
        # memo-covered slots are NOT re-executed: drop them from the lane
        # payload, and resolve requests whose steps are ALL memo hits right
        # now (they must not wait out the lane tasks).
        n_memo = 0
        pending = {}
        for ck, slots in case_slots.items():
            mcase = _WALK_MEMO.get(ck) or {}
            pend = {}
            for k, step in slots.items():
                if k in mcase:
                    n_memo += 1
                else:
                    pend[k] = step
            pending[ck] = pend
        done_reqs = []
        for r in reqs:
            ck = r["case_key"]
            mcase = _WALK_MEMO.get(ck) or {}
            if all(_step_key(s) in mcase for s in r["steps"]):
                if not r["fut"].done():
                    r["fut"].set_result([mcase[_step_key(s)] for s in r["steps"]])
                done_reqs.append(r)
        done_ids = {id(r) for r in done_reqs}
        reqs = [r for r in reqs if id(r) not in done_ids]
        n_slots = sum(len(p) for p in pending.values())
        st["memo_hits"] += n_memo
        st["slots"] += n_slots
        st["dedup_shares"] += n_req_steps - n_slots - n_memo
        if not reqs:
            return
        # 2. sticky lane assignment over the PENDING (non-memo) slots:
        # existing map / resident sent-set first, then NEW cases greedy-LPT
        # by slot count (balanced AND resident).
        lanes = _get_walk_lanes(int(os.environ.get("WALK_POOL", "0") or 0))
        n = len(lanes)
        load = [0] * n
        by_lane = [[] for _ in range(n)]
        run_cases = [ck for ck in case_slots if pending[ck]]
        for ck in run_cases:
            lane = _WALK_CASE_LANE.get(ck)
            if lane is None:
                lane = next((i for i, s in enumerate(_SENT_BY_LANE) if ck in s),
                            None)
            if lane is not None and 0 <= lane < n:
                _WALK_CASE_LANE[ck] = lane
                by_lane[lane].append(ck)
                load[lane] += len(pending[ck])
        for ck in sorted((c for c in run_cases if c not in _WALK_CASE_LANE),
                         key=lambda c: -len(pending[c])):
            lane = min(range(n), key=lambda i: load[i])
            _WALK_CASE_LANE[ck] = lane
            by_lane[lane].append(ck)
            load[lane] += len(pending[ck])
        # 3. one packed task per lane: ship the arrays of cases this lane has
        # not seen yet (sticky lanes keep them resident across rounds).
        loop = batch["loop"]
        t_submit = _t.perf_counter()
        lane_jobs = []
        for li in range(n):
            if not by_lane[li]:
                continue
            payload = []
            for ck in by_lane[li]:
                ctx_data = None
                if ck not in _SENT_BY_LANE[li]:
                    ctx = case_ctx[ck]
                    ctx_data = (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                                ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts)
                    _SENT_BY_LANE[li].add(ck)
                payload.append((ck, ctx_data,
                                [(i, rel_idxs, "", pf) for i, rel_idxs, pf
                                 in pending[ck].values()]))
            lane_jobs.append((li, payload, loop.run_in_executor(
                lanes[li], _walk_batch_spawn_timed, (payload, t_submit))))
        results = await _aio.gather(*(j[2] for j in lane_jobs),
                                    return_exceptions=True)
        # lane results are (entry_list, lane_wait, lane_exec) — accumulate the
        # wait/exec split (queue wait behind other lanes' tasks vs traversal).
        slot_pe = {}
        reship = {}
        for (li, payload, _f), res in zip(lane_jobs, results):
            if isinstance(res, BaseException):
                # crashed lane job (huge-flush pickling/OOM) — visible, not
                # silent: affected slots resolve {} ("walk reached nothing")
                import sys as _sys
                print(f"  ⚠ walk lane job failed (lane {li}, {len(payload)} cases): "
                      f"{type(res).__name__}: {res}", file=_sys.stderr, flush=True)
                continue                       # crashed lane → {} per slot below
            entries, _wait, _exec = res
            PHASE_TIMES["walk_wait"] += _wait
            PHASE_TIMES["walk_exec"] += _exec
            st["ipc_bytes"] += len(_pkl.dumps(entries, protocol=4))
            for (ck, _d, steps), entry in zip(payload, entries):
                if entry == "MISS":
                    reship.setdefault(li, []).append(ck)
                else:
                    for s, pe in zip(steps, entry):
                        _pf = s[3] if len(s) > 3 else None
                        slot_pe.setdefault(
                            (ck, s[0], frozenset(s[1]), _pf), pe)
        if reship:
            # 4. worker cache evicted for these cases → reship WITH data on the
            # SAME lanes (sticky), one follow-up task per affected lane.
            jobs2 = []
            for li, cks in reship.items():
                payload = []
                for ck in cks:
                    ctx = case_ctx[ck]
                    payload.append((ck,
                                    (ctx.sample, ctx.pilot_row, ctx.ents, ctx.rels,
                                     ctx.h_ids, ctx.r_ids, ctx.t_ids, ctx.rel_texts),
                                    [(i, rel_idxs, "", pf) for i, rel_idxs, pf
                                     in pending[ck].values()]))
                jobs2.append((payload, loop.run_in_executor(
                    lanes[li], _walk_batch_spawn_timed,
                    (payload, _t.perf_counter()))))
            for (payload, _f), res in zip(
                    jobs2, await _aio.gather(*(f for _, f in jobs2),
                                             return_exceptions=True)):
                if isinstance(res, BaseException):
                    continue
                entries, _wait, _exec = res
                PHASE_TIMES["walk_wait"] += _wait
                PHASE_TIMES["walk_exec"] += _exec
                for (ck, _d, steps), entry in zip(payload, entries):
                    if entry == "MISS":
                        continue
                    for s, pe in zip(steps, entry):
                        _pf = s[3] if len(s) > 3 else None
                        slot_pe.setdefault(
                            (ck, s[0], frozenset(s[1]), _pf), pe)
        # 5. fill the cross-batch memo (evict whole oldest cases when bound).
        for (ck, i, rels_fs, _pf), pe in slot_pe.items():
            mcase = _WALK_MEMO.get(ck)
            if mcase is None:
                if len(_WALK_MEMO) >= _WALK_MEMO_MAX_CASES:
                    _WALK_MEMO.pop(next(iter(_WALK_MEMO)))
                mcase = _WALK_MEMO[ck] = {}
            mcase[(i, rels_fs, _pf)] = pe
        # 6. resolve every request from memo + fresh slots.
        for r in reqs:
            ck = r["case_key"]
            mcase = _WALK_MEMO.get(ck) or {}
            out = []
            for s in r["steps"]:
                _pf = s[3] if len(s) > 3 else None
                k = (s[0], frozenset(s[1]), _pf)

```

### 4.3 stage_5:混合游走编排(kgqa/stages/stage5_traverse.py)

**主** = build_mode_level_logical_paths(关系引导);**fallback** = k_queue_traverse;**RPE 兜底** — agent 单步游走 n_steps≤1 使 RPE **无条件触发**(成本大头,见 §2)。

```python
async def stage_5_graph_traversal(cases: List[CaseState]):
    """Hybrid graph traversal: frontier-first, relation_prior_expand fallback for weak cases."""
    _t0 = time.perf_counter()
    active = [cs for cs in cases if cs.active]

    def _traverse_one(cs: CaseState):
        if cs.anchor_idx is None:
            cs.needs_direct_answer = True
            return

        # Merge constraint steps into one step before traversal
        _merge_constraint_steps(cs)

        bp_set = set(cs.breakpoints.values()) - {cs.anchor_idx, None} if cs.breakpoints else set()
        n_steps = len(cs.steps)
        # explicit_targets from resolved endpoints (same as e2e)
        explicit_targets = list(bp_set) if bp_set else None

        # -- Primary: mode-level logical path traversal (handles step skip, endpoint bridge) --
        kq_step_rels = [(set(rs) if rs else set()) for rs in cs.step_relations]

        # Primary: mode-level logical path traversal
        logical_paths = build_mode_level_logical_paths(
            cs.anchor_idx, kq_step_rels, cs.h_ids, cs.r_ids, cs.t_ids, cs.ents, cs.rels,
            bp_set, beam_width=80, max_hops_per_step=2, relation_list=cs.rels)

        if logical_paths:
            # Extract witness raw paths from logical paths
            seen_witness = set()
            paths = []
            for lp in logical_paths:
                witness = lp.get("best_raw_path")
                if not witness:
                    continue
                sig = (tuple(witness.get("nodes", [])), tuple(witness.get("relations", [])))
                if sig in seen_witness:
                    continue
                seen_witness.add(sig)
                paths.append(witness)
            max_depth = max((p.get("depth", 0) for p in paths), default=0)
            max_cov = max((len(p.get('covered_steps', frozenset())) for p in paths), default=0)
            cs.logical_paths = logical_paths
        else:
            # Fallback: k_queue_traverse
            paths, max_depth, max_cov = k_queue_traverse(
                cs.anchor_idx, kq_step_rels, cs.h_ids, cs.r_ids, cs.t_ids, cs.ents,
                beam_width=80, max_hops_per_step=2, relation_list=cs.rels)

        # RPE fallback for broader coverage
        if max_cov < n_steps or n_steps <= 1:
            rpe_paths, rpe_depth, rpe_cov = relation_prior_expand(
                cs.anchor_idx, [set(rs) for rs in cs.step_relations],
                cs.h_ids, cs.r_ids, cs.t_ids, cs.ents,
                explicit_targets=explicit_targets,
                prefix_nodes=getattr(cs, "prefix_nodes", None))
            if rpe_cov > max_cov:
                paths, max_depth, max_cov = rpe_paths, rpe_depth, rpe_cov
            elif rpe_paths:
                existing_sigs = {(tuple(p["relations"][:3]), p["nodes"][-1]) for p in paths}
                for rp in rpe_paths:
                    sig = (tuple(rp["relations"][:3]), rp["nodes"][-1])
                    if sig not in existing_sigs:
                        paths.append(rp)
                        existing_sigs.add(sig)
        # Prefer paths hitting breakpoint endpoints
        paths = prefer_breakpoint_hit_paths(
            paths, cs.breakpoints, cs.h_ids, cs.r_ids, cs.t_ids, cs.ents
        )
        if paths:
            max_depth = max(p.get("depth", 0) for p in paths)
            max_cov = max(len(p.get("covered_steps", frozenset())) for p in paths)
        cs.paths = paths
        cs.max_depth = max_depth
        cs.max_cov = max_cov

        # Collect subgraph nodes
        cs.all_subgraph_nodes = {cs.anchor_idx}
        for path in cs.paths:
            cs.all_subgraph_nodes.update(path["nodes"])

        # HR frontier: path-level (h+r) forward + (r+t) reverse triples
        expanded_rels = [set(rs) for rs in cs.step_relations]
        hr_triples, hr_nodes = _collect_hr_frontier(
            cs.anchor_idx, expanded_rels, cs.h_ids, cs.r_ids, cs.t_ids,
            paths=cs.paths)
        cs.all_subgraph_nodes |= hr_nodes

        # Answer candidates from last step's BFS walk (+ CVT expansion)
        answer_candidates = _last_step_candidates(
            cs.paths, cs.anchor_idx, cs.step_relations, cs.h_ids, cs.r_ids, cs.t_ids, cs.ents)

        seen = set()
        unique = []
        for c in answer_candidates:
            nc = normalize(c)
            if len(nc) < 2:
                continue
            # REMOVED: if not c.isascii() - was too aggressive for non-English entities
            if nc not in seen:
                seen.add(nc)
                unique.append(c)

        # Merge logical_path candidates
        logical_paths = getattr(cs, 'logical_paths', [])
        for lp in logical_paths:
            for c in lp.get("candidates", []):
                nc = normalize(c)
                if len(nc) < 2 or nc in seen:
                    continue
                seen.add(nc)
                unique.append(c)

```

### 4.4 RPE:relation_prior_expand(kgqa/traversal/frontier.py,成本核心)

全环境 3-hop 层进展开;`_search_terminal_relation_paths` 是热循环(桥跳任意关系、段终止于选中关系);`_prune_paths` 按 (endpoint, covered_steps) 分组保 per_branch_width。含 pattern-prefix mask(默认关)与 walk-perf 邻接 memo。

```python
def relation_prior_expand(anchor_idx, step_relations, h_ids, r_ids, t_ids, entity_list,
                          explicit_targets=None, max_hops=3, beam_width=80, per_branch_width=5,
                          prefix_nodes=None):
    """Forward layer-by-layer relation-prior expansion.

    New behavior:
    1. Start from current entity frontier (initially the anchor).
    2. For layer i, search all paths within max_hops whose LAST hop relation is in R_i.
    3. Use the endpoints of those matched paths as the start frontier for the next layer.
    4. If a layer has no hit, skip it and continue from the current frontier.
    5. If explicit endpoint targets exist, connect the final frontier to those targets
       via a shortest path search within max_hops.

    This removes the backward-target template and avoids the repeated-relation
    penetration issue seen in bidirectional matching such as r1 -> r1 collapse.

    Performance optimizations (v2):
    - Paths stored as tuples (nodes, rels, depth, real_hops, covered, matched)
      instead of dicts, avoiding dict creation overhead in the hot inner loop.
    - CVT status pre-computed once as a boolean list.
    - Adjacency neighbor lists stored as tuples for faster iteration.
    - BFS in _connect_to_targets uses collections.deque.
    - Reduced frozenset churn: only create new frozensets when coverage changes.
    - _prune_paths uses frozenset directly as hash key instead of sorted tuple.
    """
    n_steps = len(step_relations)
    if n_steps == 0:
        return [], 0, 0

    # -- Build adjacency (directed if KGQA_DIRECTED_TRAVERSAL=1, else undirected) --
    # MEMOIZED per case (walk-perf, 2026-09-07): the single-step agent walk
    # fires RPE on EVERY call (n_steps<=1 makes the fallback unconditional),
    # and each call rebuilt the identical adjacency — dense cases pay 26ms+
    # per rebuild at degree 900+. Downstream is read-only (adj.get iteration).
    _rkey = (id(h_ids), id(r_ids), id(t_ids), len(h_ids), DIRECTED_TRAVERSAL)
    _hit = _RPE_ADJ_CACHE.get(_rkey)
    adj = _hit[0] if _hit is not None else None
    if adj is None:
        adj = {}
        for i in range(len(h_ids)):
            h, r, t = h_ids[i], r_ids[i], t_ids[i]
            if h in adj:
                adj[h] = adj[h] + ((t, r),)
            else:
                adj[h] = ((t, r),)
            if not DIRECTED_TRAVERSAL:
                if t in adj:
                    adj[t] = adj[t] + ((h, r),)
                else:
                    adj[t] = ((h, r),)
        if len(_RPE_ADJ_CACHE) > 16:
            _RPE_ADJ_CACHE.clear()
        # pin the source arrays: id() keys stay valid while the entry lives
        # (audit 2026-09-07 — stale-id collision impossible)
        _RPE_ADJ_CACHE[_rkey] = (adj, (h_ids, r_ids, t_ids))
    adj_empty = ()

    # -- Pre-compute CVT mask (avoids re.match per hop) --
    is_cvt = [is_cvt_like(name) for name in entity_list]
    n_ents = len(entity_list)

    # -- Build reverse mapping --
    rel_to_step: Dict[int, set] = {}
    for si, rs in enumerate(step_relations):
        for r in rs:
            rel_to_step.setdefault(r, set()).add(si)
    all_layer_rels = set(rel_to_step.keys())

    # -- Helpers --
    def _real_hop_inc(curr_idx, next_idx):
        """Real hop increment for the hop-limit check.

        CVT nodes count as a hop (NOT passthrough). Rationale: a CVT-mediated
        path (anchor -> CVT -> leaf) is 2 structural hops, and downstream logic
        (compress_paths, candidate collection, pattern matching) all operate on
        actual path length (len(rels)/len(nodes)). Treating CVT as 0-hop here
        would let RPE explore longer *structural* paths than max_hops allows,
        creating an inconsistency with logical_paths (which counts CVT as a hop)
        and with compress_paths (which uses len(rels) for depth/tier).
        With max_hops_per_step=2, single CVT chains (2 structural hops) are
        reachable within one step. Only 3+-hop CVT chains would be truncated —
        and those are rare (8% of GT is 2-hop CVT, ~0% need 3+ CVT hops).
        """
        return 1

    def _coverage_rank_fast(path):
        """Path is tuple: (nodes, rels, depth, real_hops, covered_steps, matched_rels)."""
        covered = path[4]
        depth = path[2]
        if not covered:
            return (0, -1, 0)
        return (len(covered), max(covered), -depth)

    def _prune_paths(paths, limit):
        if len(paths) <= limit:
            return paths
        # Group by (endpoint, covered_steps) -- frozenset is directly hashable
        grouped: Dict[tuple, list] = {}
        for p in paths:
            sig = (p[0][-1], p[4])  # (nodes[-1], covered_steps)
            if sig in grouped:
                grouped[sig].append(p)
            else:
                grouped[sig] = [p]
        result = []
        overflow = []
        for group in grouped.values():
            group.sort(key=_coverage_rank_fast, reverse=True)
            result.extend(group[:per_branch_width])
            overflow.extend(group[per_branch_width:])
        if len(result) < limit and overflow:
            overflow.sort(key=_coverage_rank_fast, reverse=True)
            result.extend(overflow[: limit - len(result)])
        if len(result) > limit:
            result.sort(key=_coverage_rank_fast, reverse=True)
            result = result[:limit]
        return result

    def _search_terminal_relation_paths(start_paths, target_rels, layer_idx):
        """From start_paths, search local segments that terminate at the FIRST hit of target_rels.

        Rules:
        - bridge hops may not use any selected layer relation
        - once a target relation is hit, the segment ends immediately
        - same-layer relations cannot chain within one segment
        - PATTERN-PREFIX mask (user design 2026-09-10, 状态保持/不重复回去):
          with prefix_nodes set (a continuation walk from a pattern tail), a
          neighbor INSIDE the earlier walk's territory is never EXPANDED —
          only a target-relation edge INTO it is recorded (connection
          evidence); bridge hops into the prefix are skipped entirely.
        """
        if not target_rels:
            return []
        pfx = set(prefix_nodes) if prefix_nodes else None
        active = list(start_paths)
        matched = []
        seen_matched = set()
        layer_idx_frozen = frozenset({layer_idx})

        for _ in range(max_hops * 3):
            if not active:
                break
            new_active = []
            for path in active:
                nodes, rels, depth, real_hops, covered, matched_rels = path
                current = nodes[-1]
                neighbors = adj.get(current, adj_empty)
                for neighbor, rel in neighbors:
                    if neighbor in nodes:
                        continue
                    # -- Inverse-pair loop detection: same rel twice = trivial cycle --
                    if rels and rels[-1] == rel:
                        continue
                    inc = _real_hop_inc(current, neighbor)
                    new_real_hops = real_hops + inc
                    if new_real_hops > max_hops:
                        continue

                    is_target_rel = rel in target_rels
                    is_any_layer_rel = rel in all_layer_rels
                    in_prefix = pfx is not None and neighbor in pfx

                    if not is_target_rel and is_any_layer_rel:
                        continue
                    if in_prefix and not is_target_rel:
                        continue          # back into walked territory — dead end

                    new_nodes = nodes + (neighbor,)
                    new_rels = rels + (rel,)
                    new_depth = depth + 1

                    rel_steps = rel_to_step.get(rel)
                    if rel_steps:
                        new_covered = covered | rel_steps
                        new_matched = matched_rels | frozenset({rel})
                    else:
                        new_covered = covered
                        new_matched = matched_rels

                    new_path = (new_nodes, new_rels, new_depth, new_real_hops, new_covered, new_matched)

                    if is_target_rel:
                        final_covered = new_covered | layer_idx_frozen
                        final_path = (new_nodes, new_rels, new_depth, new_real_hops, final_covered, new_matched)
                        key = (new_nodes, new_rels)
                        if key not in seen_matched:
                            seen_matched.add(key)
                            matched.append(final_path)
                    else:
                        new_active.append(new_path)
            active = _prune_paths(new_active, beam_width)
        return _prune_paths(matched, beam_width)

    def _connect_to_targets(paths, targets):
        """Attach final frontier endpoints to explicit targets by shortest unconstrained path."""
        if not targets or not paths:
            return paths
        targets_set = set(targets) - {anchor_idx, None}
        if not targets_set:
            return paths

        connected = []
        seen = set()
        for base in paths:
            start = base[0][-1]  # nodes[-1]
            queue = deque([(start, (start,), (), 0)])
            local_seen = {(start, 0)}
            best = []
            while queue:
                node, nodes_seq, rel_seq, rhops = queue.popleft()
                if node in targets_set and node != start:
                    merged = (
                        base[0] + nodes_seq[1:],
                        base[1] + rel_seq,
                        base[2] + len(rel_seq),
                        base[3] + rhops,
                        base[4],
                        base[5],
                    )
                    best.append(merged)
                    continue
                for neighbor, rel in adj.get(node, adj_empty):
                    if neighbor in nodes_seq:
                        continue
                    inc = _real_hop_inc(node, neighbor)
                    new_hops = rhops + inc
                    if new_hops > max_hops:
                        continue
                    state_key = (neighbor, new_hops)
                    if state_key in local_seen:
                        continue
                    local_seen.add(state_key)
                    queue.append((neighbor, nodes_seq + (neighbor,), rel_seq + (rel,), new_hops))
            best.sort(key=_coverage_rank_fast, reverse=True)
            for p in best[:per_branch_width]:
                key = (p[0], p[1])
                if key not in seen:
                    seen.add(key)
                    connected.append(p)
        return _prune_paths(connected, beam_width) if connected else paths

    # -- Main expansion logic --
    # Internal path format: (nodes_tuple, rels_tuple, depth, real_hops, covered_steps, matched_rels)
    frontier_paths = [((anchor_idx,), (), 0, 0, frozenset(), frozenset())]
    all_result_paths = []
    matched_layer_indices = []
    nonempty_layers = [i for i, rs in enumerate(step_relations) if rs]

    for layer_idx, target_rels in enumerate(step_relations):
        if not target_rels:
            continue
        matched = _search_terminal_relation_paths(frontier_paths, target_rels, layer_idx)
        if not matched:
            continue
        frontier_paths = matched
        all_result_paths = matched
        matched_layer_indices.append(layer_idx)

    # Minimal repair: only repair the final non-empty layer if it was missed.
    if nonempty_layers and matched_layer_indices:
        last_nonempty_idx = nonempty_layers[-1]
        if last_nonempty_idx not in matched_layer_indices and frontier_paths:
            repaired = _search_terminal_relation_paths(frontier_paths, step_relations[last_nonempty_idx], last_nonempty_idx)
            if repaired:
                merged = list(all_result_paths or []) + repaired
                merged.sort(key=_coverage_rank_fast, reverse=True)
                all_result_paths = _prune_paths(merged, beam_width)

    if explicit_targets:
        all_result_paths = _connect_to_targets(all_result_paths or frontier_paths, explicit_targets)
    elif not all_result_paths:
        all_result_paths = frontier_paths

    if not all_result_paths:
        return [], 0, 0

    # Dedup + post-hoc cycle filter
    dedup = []
    seen = set()
    for p in all_result_paths:
        key = (p[0], p[1])
        if key not in seen:
            seen.add(key)
            dedup.append(p)

    # Remove paths with cycles (repeated nodes)
    acyclic = [p for p in dedup if len(set(p[0])) == len(p[0])]
    if acyclic:
        dedup = acyclic

    dedup.sort(key=_coverage_rank_fast, reverse=True)
    dedup = _prune_paths(dedup, beam_width)

    # Convert internal tuple format back to dict format for API compatibility
    result_dicts = []
    for p in dedup:
        result_dicts.append({
            "nodes": list(p[0]),
            "relations": list(p[1]),
            "depth": p[2],
            "real_hops": p[3],
            "covered_steps": p[4],
            "matched_relations": p[5],
        })

    max_cov = max((len(p[4]) for p in dedup), default=0)
    max_depth = max((p[2] for p in dedup), default=0)
    return result_dicts, max_depth, max_cov


# ---------------------------------------------------------------------------
# Layer diagnostics (requires graph_tool)
# ---------------------------------------------------------------------------


```

### 4.5 主游走:build_mode_level_logical_paths(kgqa/traversal/logical_paths.py,节选)

```python
def build_mode_level_logical_paths(anchor_idx, step_relations, h_ids, r_ids, t_ids,
                                   ents, rels_list, breakpoint_indices,
                                   beam_width=80, max_hops_per_step=2,
                                   max_states=1200, max_raw_paths_per_pattern=90,
                                   relation_list=None):
    """Traverse relation modes first and keep bounded witness paths.

    The model selects logical modes before raw path materialization, so this
    routine keeps one short witness plus a few siblings per mode instead of
    enumerating every raw entity path up front.
    """
    if anchor_idx is None or not step_relations:
        return []

    noisy_rel_ids = set()
    if relation_list is not None:
        for ri, rname in enumerate(relation_list):
            if _is_noisy_path_relation(rname):
                noisy_rel_ids.add(ri)

    adj = _build_adj(h_ids, r_ids, t_ids, with_edge_idx=True, skip_rel_ids=noisy_rel_ids)

    def _hit_paths(state, target_rels, step_idx):
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        hits = []

        def _make_hit(extra_nodes, extra_rels, extra_edges, hit_rel):
            return {
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),
                "covered_steps": state["covered_steps"] | frozenset({step_idx}),
                "terminal_rels": state["terminal_rels"] + (hit_rel,),
                "skipped_steps": state["skipped_steps"],
                "endpoint_steps": state.get("endpoint_steps", frozenset()),
                "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
                "depth": state["depth"] + len(extra_rels),
            }

        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if rel1 in target_rels:
                hits.append(_make_hit((nb1,), (rel1,), (e1,), rel1))
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            # ORIGINAL DESIGN (per-relation last-hop walk, restored 2026-08-19):
            # enumerate ALL 2-hop completions whose LAST hop rides a selected
            # relation — from EVERY first hop, target-hit or not. The old
            # "hit-and-stop" (CASE A continue / CASE B non-target-only) made a
            # bridge+payload selection walkable only when the graph happened
            # to store a reverse-direction UNSELECTED edge for the bridge
            # (Greeley contains/containedby luck); single-direction data
            # silently lost the payload relation (Bernie Brewer specimen).
            # Detour pruning (same-relation back-edge chains, Nordics) lives
            # in the evidence adjudication layer (_hop_ok), NOT here — the
            # walk only enumerates, direction constraints live downstream.
            # The 1-hop-target CVT extension below is subsumed by this loop
            # (CVT mids are traversed like any other).
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if rel2 in target_rels:
                    hits.append(_make_hit((nb1, nb2), (rel1, rel2),
                                           (e1, e2), rel2))
            # CASE C: CVT-transparent 3-edge path — end -> nb1 -> nb2 -> nb3 (rel3 in target).
            # A CVT mediator collapses its in/out edges into ONE logical hop, so a 3-graph-hop
            # path with EXACTLY ONE CVT mediator (at nb1 or nb2) is within the 2-logical-hop
            # budget. This is what makes the WALK match the relation POOL's reachability:
            # _seq_pool_relids surfaces a relation behind a CVT bridge + one named hop (e.g.
            # museum --org_rel--> CVT --child--> university, then university's `colors`) via its
            # CVT-transparent hop, the model selects it, and CASE C lets the walk actually
            # traverse it — without it, retrieve_relations returns a relation the walk can't
            # reach ("reached nothing"). Gated: FINAL edge must be a target relation (emitted
            # endpoints are target answers, few) and exactly one CVT mediator (no CVT->CVT) —
            # so no beam explosion.
            nb1_is_cvt = 0 <= nb1 < len(ents) and is_cvt_like(ents[nb1])
            if not nb1_is_cvt:
                continue   # the common CVT-bridge case has the mediator at the front (nb1);
            # nb1-is-CVT covers museum->CVT->university->target. (nb2-CVT symmetric case is
            # rarer and would fire here too if the `continue` above were removed; kept narrow
            # to bound fan-out.)
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1 or nb2 == end or nb2 == nb1:
                    continue
                if 0 <= nb2 < len(ents) and is_cvt_like(ents[nb2]):
                    continue   # CVT->CVT: skip (ambiguous, rare)
                used2 = used1 | frozenset({e2})
                for nb3, rel3, e3 in adj.get(nb2, ()):
                    if e3 in used2 or rel3 not in target_rels:
                        continue
                    if nb3 == end or nb3 == nb1 or nb3 == nb2:
                        continue
                    hits.append(_make_hit((nb1, nb2, nb3), (rel1, rel2, rel3),
                                           (e1, e2, e3), rel3))
        return hits

    endpoint_targets = set(breakpoint_indices or ()) - {anchor_idx, None}
    nonempty_step_indices = [i for i, rels_for_step in enumerate(step_relations) if rels_for_step]
    endpoint_bridge_step = nonempty_step_indices[-1] if nonempty_step_indices else None

    def _endpoint_bridge_paths(state, step_idx):
        if not endpoint_targets or step_idx != endpoint_bridge_step:
            return []
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        if end in endpoint_targets:
            return []

        hits = []
        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if nb1 in endpoint_targets:
                hits.append((1, (nb1,), (rel1,), (e1,)))
                continue
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if nb2 in endpoint_targets:
                    hits.append((2, (nb1, nb2), (rel1, rel2), (e1, e2)))

        if not hits:
            return []
        min_depth = min(depth for depth, _, _, _ in hits)
        bridged = []
        endpoint_marker = -100000 - step_idx
        for _, extra_nodes, extra_rels, extra_edges in hits:
            if len(extra_nodes) != min_depth:
                continue
            bridged.append({
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),

```

### 4.6 fallback:k_queue_traverse(kgqa/traversal/k_queue.py)

```python
def k_queue_traverse(anchor_idx, step_relations, h_ids, r_ids, t_ids, entity_list,
                     beam_width=80, max_hops_per_step=2, relation_list=None):
    """Single BFS from anchor, K independent queues each tracking their own step_relations.

    Instead of processing steps sequentially, one BFS pass tracks ALL target
    relations simultaneously via rel_to_step mapping. After each hop that matches
    a target relation, check_order computes which steps are covered in order.

    Returns (paths, max_depth, max_coverage_tier).
    """
    n_steps = len(step_relations)
    if n_steps == 0:
        return [], 0, 0
    if not any(step_relations):
        return [], 0, 0

    # Build noise relation blacklist
    noisy_rel_ids = set()
    if relation_list is not None:
        for ri, rname in enumerate(relation_list):
            if _is_noisy_path_relation(rname):
                noisy_rel_ids.add(ri)

    # Build adjacency (directed if KGQA_DIRECTED_TRAVERSAL=1, else undirected).
    # Directed mode respects Freebase's named-direction relations (contains vs
    # containedby) instead of treating them as bidirectional.
    # MEMOIZED per case (walk-perf, 2026-09-07): same-arrays rebuilds are pure
    # waste — see logical_paths._build_adj; downstream is read-only iteration.
    _akey = (id(h_ids), id(r_ids), id(t_ids), len(h_ids),
             DIRECTED_TRAVERSAL,
             frozenset(noisy_rel_ids) if noisy_rel_ids else None)
    _hit = _KQ_ADJ_CACHE.get(_akey)
    if _hit is not None:
        adj = _hit[0]
    else:
        adj = None
    if adj is None:
        adj = {}
        for i in range(len(h_ids)):
            h, r, t = h_ids[i], r_ids[i], t_ids[i]
            if r in noisy_rel_ids:
                continue
            adj.setdefault(h, []).append((t, r))
            if not DIRECTED_TRAVERSAL:
                adj.setdefault(t, []).append((h, r))
        if len(_KQ_ADJ_CACHE) > 16:
            _KQ_ADJ_CACHE.clear()
        # pin the source arrays: id() keys stay valid while the entry lives
        # (audit 2026-09-07 — stale-id collision impossible)
        _KQ_ADJ_CACHE[_akey] = (adj, (h_ids, r_ids, t_ids))

    # Build rel_to_step mapping: each relation → set of step indices it belongs to
    rel_to_step = {}
    all_target_rels = set()
    for step_idx, rel_set in enumerate(step_relations):
        for rel in rel_set:
            rel_to_step.setdefault(rel, set()).add(step_idx)
            all_target_rels.add(rel)

    max_hops = max_hops_per_step * n_steps
    max_total_paths = 5000

    # -- Single BFS from anchor --
    # State: flat arrays with frozenset loop detection.
    # (Previously used bigint bitmask `1 << node_idx`, which creates huge bigints
    #  on large subgraphs — O(N/64) per bitwise op. frozenset is faster for
    #  sparse visited sets and avoids the latent `1 << negative` crash.)
    flat_nodes = [anchor_idx]
    flat_parent = [-1]
    flat_rel = [-1]
    flat_visited = [frozenset({anchor_idx})]
    flat_rels_list = [[]]  # accumulated path relations for check_order
    flat_depth = [0]

    frontier = [0]
    completed = []  # paths that hit at least one target relation

    for hop in range(max_hops):
        if not frontier:
            break
        new_frontier = []
        for eidx in frontier:
            cur = flat_nodes[eidx]
            visited = flat_visited[eidx]
            path_rels = flat_rels_list[eidx]
            cur_depth = flat_depth[eidx]

            for nb, rel in adj.get(cur, []):
                if nb in visited:
                    continue
                new_visited = visited | {nb}
                new_rels = path_rels + [rel]
                new_depth = cur_depth + 1

                nidx = len(flat_nodes)
                flat_nodes.append(nb)
                flat_parent.append(eidx)
                flat_rel.append(rel)
                flat_visited.append(new_visited)
                flat_rels_list.append(new_rels)
                flat_depth.append(new_depth)

                # Check if this hop uses a target relation
                if rel in all_target_rels:
                    # Reconstruct path nodes
                    r_nodes = [nb]
                    pi = eidx
                    while pi >= 0:
                        r_nodes.append(flat_nodes[pi])
                        pi = flat_parent[pi]
                    r_nodes.reverse()

                    # Compute covered steps via check_order
                    covered = _check_order(new_rels, step_relations)
                    tier = _coverage_tier(covered)

                    completed.append({
                        "nodes": r_nodes,
                        "relations": new_rels,
                        "covered_steps": frozenset(covered),
                        "covered_rels": frozenset(r for r in new_rels if r in all_target_rels),
                        "depth": new_depth,
                        "coverage_tier": tier,
                    })

                # Continue expanding regardless — other watchers may need further hops
                new_frontier.append(nidx)

        # Beam prune: keep most promising entries by coverage potential
        if len(new_frontier) > beam_width * 2:
            # Score by how many target relations found so far in path
            scored = []
            for nidx in new_frontier:
                path_rels = flat_rels_list[nidx]
                hit_count = sum(1 for r in path_rels if r in all_target_rels)
                scored.append((hit_count, nidx))
            scored.sort(key=lambda x: -x[0])
            new_frontier = [s[1] for s in scored[:beam_width * 2]]

        frontier = new_frontier

        if len(completed) > max_total_paths:
            break

    if not completed:
        return [], 0, 0

    # Dedup by (nodes, relations) signature
    seen_sigs = set()
    deduped = []
    for p in completed:
        sig = (tuple(p["nodes"]), tuple(p["relations"]))
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            deduped.append(p)

    all_steps = frozenset(range(n_steps))

    def _step_rank(path):
        covered = path.get("covered_steps", frozenset())
        return (
            covered == all_steps,
            len(covered),
            max(covered) if covered else -1,
            -path["depth"],
        )

    # Sort by matched decomposition steps first. Hop count is only a tie-breaker
    # because one logical step may span multiple graph hops.
    deduped.sort(key=_step_rank, reverse=True)

    if len(deduped) > max_total_paths:
        deduped = deduped[:max_total_paths]

    # Build output — include partial coverage paths too (not just full-coverage)
    output_paths = [p for p in deduped if p["depth"] > 0 and p.get("covered_rels")]

    if not output_paths:
        return [], 0, 0

    output_paths.sort(key=_step_rank, reverse=True)

    for p in output_paths:
        p["matched_relations"] = frozenset(p.get("covered_rels", frozenset()))

    max_depth = max(p["depth"] for p in output_paths)
    max_cov = max(len(p.get("covered_steps", frozenset())) for p in output_paths)

    return output_paths, max_depth, max_cov

```

### 4.7 游走后处理(证据构建,稀疏 case 曾占 58%)

- `compress_paths`(kgqa/traversal/path_utils.py:136):路径→模式压缩。
- `build_pattern_evidence_triples`(kgqa/stages/formatting.py:239):
  模式→PatternEvidence(triples/candidates/tree_data),selected_rel_ids
  过滤。此层已优化(_is_latinish 字符 memo);稠密 case 热点仍在 RPE。

## 5. 给 Codex 的评估问题

1. **RPE hub 剪枝**:beam_width=80 / per_branch_width=5 在度 900+ 的
   anchor 上,active 集每层爆炸后靠 _prune_paths 截断——有什么保结果
   分布的分层剪枝(degree-decay / coverage-weighted / frontier-cap)
   能把稠密 case 的 76% 占比打下来?剪枝语义改变多少算可接受
   (我们有 pickle-sha256 + f1 带内两道验收)?
2. **C 层替换**:邻接已 memo(元组 dict);热循环是纯 Python 的
   neighbor 迭代 + tuple 拼接。igraph/自定义 C 扩展(或 numpy CSR +
   向量化 BFS)能否在"路径输出逐条等价"要求下替换
   _search_terminal_relation_paths?哪些部分天然可替换(无顺序依赖),
   哪些有顺序依赖(_prune_paths 的排序稳定性)?
3. **环境级复用的真实空间**:同 center 不同 relset 重游整环境
   (memo 只认精确对)。在"RPE 全环境 + relset 只定终止"的模型下,
   能否缓存"全路径池"(一次无终止遍历),再按 relset 后过滤?
   障碍 = _prune_paths 的 coverage 排序依赖 relset(保留高覆盖路径)。
   量化:多小的 relset 间差异下后过滤与原结果重合?
4. **RPE 无条件触发是否冗余**:n_steps≤1 时主游走(logical_paths)
   与 RPE 都跑,输出如何合并(rpe_cov>max_cov 则替换/否则补路径)?
   两者遍历的重叠有多少可共享(一次遍历喂两个记录器)?
5. **数据结构级**:tuple-of-tuples 邻接 vs CSR 数组;path 元组拼接
   (nodes+(neighbor,)) 的分配压力;frozenset covered_steps 的 churn
   (v2 已减少)。还有什么 5-20% 级别的免费午餐?

## 6. 验收工具

- 等价 battery:同输入新旧游走输出 pickle sha256(walk-perf 时代方法论);
- 48×3 rollout:f1 带(wallexcap 基线 0.6930 / rest43 0.6948 / hit 77.1%
  / wall_mean 809s / walk exec 2152s / slots 1796);
- 冒烟:tmp/test_pattern_prefix.py(RPE 语义)、tests/ 141 项;
- 相位计时:PHASE_TIMES + walk-batch/gte-batch 统计行(§2 样例)。
