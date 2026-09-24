# 本段会话（2026-09-23）修复链审计报告 — 供外部审计（GPT-6 Astral）

仓库：/zhaoshu/subgraph（分支 agent-toolcall，远程 anon=github.com/maoulee/RPG.git）
基线：v23_final 48×3 = 0.669/75.0%（CASE_FILTER=tmp/v21_cohort.txt 对齐）。
运行序列：v24a(0.569)→v24b(0.615)→v24c(0.647)→v24d(0.630)→v25(0.601)→v26(0.517)。
v26 掉分主因已定位为'执行截断'（树键归一 a07add4 修复中，537 s0 已恢复 f1=1.0，s1-s5 第二断点调查中）。

## 一、修复链总表（动机 → commit → 验证）

| # | 问题（用户人审实锤） | commit | 文件 | 验证 |
|---|---|---|---|---|
| 1 | bridge 注入提交关系集 + lane-2 frontier 一跳 | 7d8ee88 | seq_tools | 1731 ROR 行消失；对齐后 -10pp（触发后续连锁排查）|
| 2 | 渲染 delta 精确键漏网（逆关系/方向翻转） | 7d8ee88 | seq_tools/render_v38 | 单元验证 inverse-fold/direction-norm |
| 3 | answer dispatch 崩溃（list 邻接当 dict）| 58d246a | tools.py:2176 | 崩溃 124→0；0.615→0.647 |
| 4 | 层可行性只认 1-hop 直连（桥接非法）| 9b12d35 | seq_tools | 21_ 0.33→1.00 |
| 5 | 提示语缺关系多选规则（只选最佳丢对照）| 2a6c13d/e6bf921 | SEQ_AGENTS_V23/seq_tools | 576 曾 0→1.00 |
| 6 | id 型中转节点耗命名跳 | 3391914 | tools.py | 25_db96 池可达 |
| 7 | join 合拢机制丢失（edc8004 revert）| fae69b8..161eb06 | seq_react_loop/tools | 桥检索+GTE 排序+公平契约 |
| 8 | merge bounce 打断合法答案 | c47d040→220619f→499f683 | 同上+seq_tools | 触发 6 次中 5 次答错→改信息性 note |
| 9 | rr GTE 埋没 CVT 桥关系族 | 0f6fa6b | seq_tools | jurisdiction_of_office 进候选 |
| 10 | 残段链铸裸 bridge 标签 | 1ffe41e | seq_triples | patterns 行无裸段 |
| 11 | 回显重复（center/grouped）| 883370b | seq_rows/seq_tools | 去重复述 |
| 12 | **执行截断：declared 键 root、查表键 center** | a07add4 | seq_tools | 537 s0 恢复 1.0；s1-s5 第二断点调查中 |

## 二、核心修复代码（当前 HEAD 实况，供直接审计）


### 12-执行截断修复：execute 侧树键归一（入口）
`kgqa/agent/seq_tools.py` (line ~4567):
```python
    _root_of = treq.get("root_of") or {}
    _inv = _ctx_inverse_rels(ctx)
    _shown_facts = {_edge_fact_key(str(h), str(r), str(t), _inv)
```


### 12-执行截断修复：prepare 侧 _multistep 构建归一
`kgqa/agent/seq_tools.py` (line ~4233):
```python
                _ci_r = _root_of.get(_ci, _ci) if isinstance(_root_of, dict) else _ci
                if _ci_r in _declared:
                    _multistep[_ci_r] = _declared[_ci_r]
                    _inf = _infeas_map.get(_ci_r)
                    if _inf:
                        # BRIDGE-LEGAL FALLBACK (user ruling 2026-09-23): the
                        # direct-unreachable submissions ride FREE DERIVATION
                        # — 1..3-hop patterns ENDING in the submitted relation
                        # (the design's "two hops, submitted relation last"
                        # semantics) — sharing the render with the declared
                        # chain instead of being silently dropped.
                        try:
```


### 4-桥接合法回退（infeasible 收集）
`kgqa/agent/seq_tools.py` (line ~4137):
```python
                        # BRIDGE-LEGAL FALLBACK (user ruling 2026-09-23):
                        # the layer-assignment feasibility above is 1-hop
                        # DIRECT reach and used to DISCARD the rest — but the
                        # design allows a BRIDGE: every layer's relation only
                        # needs to be reachable "within two hops, ENDING in
                        # the submitted relation" (the relation_expansion
                        # direct+bridge semantics). A frontier-bridged
                        # submission (21_ specimen: government_positions_held
                        # from Ethiopia via jurisdiction_of_office) is NOT
                        # droppable — collect it for free derivation at the
```


### 7-join rescue 池键规范化
`kgqa/agent/tools.py` (line ~2259):
```python
    # KEY CANONICALIZATION (integration audit 2026-09-23): join_flag
    # passes DECLARED fids ('sg2.f2') but the pools are keyed through
    # fact_key_map's canonical fid ('f2') — the raw lookup missed every
    # pool and the rescue silently returned None in real rollouts
    # (function verified fine in isolation). Resolve both ways.
    _fkm = getattr(ctx, "fact_key_map", None) or {}
    _fcp = getattr(ctx, "fact_candidate_pool", None) or {}
    _fev = getattr(ctx, "fact_evidence", None) or {}
    pools = {}
    for _fid in fids[:2]:
        _key = _fkm.get(_fid, _fid)
        pl = _fcp.get(_key) or _fcp.get(_fid)
```


### 7-公平契约（永不锚定 gold）
`kgqa/agent/tools.py` (line ~2236):
```python
    FAIRNESS CONTRACT (user ruling 2026-09-23): the search is POOL-TO-POOL
    shortest + GTE-on-question ranking — NEVER gold-anchored. The bridge
    must not be constructed to pass through the answer; any landing near
    the answer is the natural consequence of pool proximity, and the
    external feedback carries existence only (no chain, no endpoint)."""
    def _name_idx(name):
        nm = str(name)
        for i, e in enumerate(ctx.ents):
            if str(e) == nm:
                return i
```


### 8-推理时刻 merge note（一次性信息性）
`kgqa/agent/seq_react_loop.py` (line ~1262):
```python
        """REASONING-TIME merge note (user ruling 2026-09-23): when the
        model starts its final reasoning (ANSWER_ANALYSIS detected) and the
        walked pools never merged while a bridge exists, deliver the
        EXISTENCE note ONCE as an informational message — no interruption,
        no redo demand, no per-subgraph repetition."""
        try:
            ctx = self.ctx
            if getattr(ctx, "_merge_noted", False):
                return
            fcp = getattr(ctx, "fact_candidate_pool", None) or {}
            if len(fcp) < 2:
                return
```


### 6-id 型中转透明
`kgqa/agent/tools.py` (line ~792):
```python
        # ID-TYPE TRANSIT NODE (user ruling 2026-09-23, 25_db96 specimen):
        # opaque code nodes (travel ids etc.) carry no answer semantics —
        # they are transit surfaces exactly like CVTs. Without this they
        # cost a NAMED hop, pushing their relations to the 3rd named hop,
        # outside the pool (travelid's relations unreachable).
        return (len(name) <= 24 and " " not in name
                and bool(_re_idlike.search(r"\d{2,}", name)))

```


### 10-残段链不铸裸标签
`kgqa/agent/seq_triples.py` (line ~125):
```python
                # FULL-DEPTH ONLY (user ruling 2026-09-23): a chain whose
                # edge sequence is SHORTER than the pattern's hop count is
                # an expansion remnant (hop landed on a CVT, passthrough
                # satisfied the last-hop "found" without instantiating the
                # submitted relation — 567: [award_winner⭢directed_by]'s
                # hop-1-only chain minted the bare `award_winner` label).
                # Remnants never become independent render groups.
                if _rel_t and len(_rel_t) == len(_names):
                    _s.add(_rel_t)
    _key_count = {}
```


### 3-answer 收割 CVT 段修复（索引化访问）
`kgqa/agent/tools.py` (line ~2241):
```python
    def _name_idx(name):
        nm = str(name)
        for i, e in enumerate(ctx.ents):
            if str(e) == nm:
                return i
        return None

    if len(fids) < 2:
        return None
    from kgqa.agent.tools import _full_adj
    adj = _full_adj(ctx)
    n = len(ctx.ents)
```


### 9-rr CVT 桥保底槽（函数头）
`kgqa/agent/seq_tools.py` (line ~3061):
```python
def _rr_bridge_reserved(ctx, reqs, cands, scored, top_n):
    """CVT-BRIDGE reserved slots for the rr FIRST screen (Ethiopia specimen
    21_660138373d19bbffdd3d3f7a30234e4a, 2026-09-23). A mediation CVT adjacent
```


## 三、关键设计裁定（本段用户裁定，审计对照用）

1. **bridge 只是模式路径中间关系**，从不进提交关系集；模式终点=提交关系（2026-09-22 维持）。
2. **层可行性=两跳内以提交关系为末跳**（允许桥接），非 1-hop 直连。
3. **continuation=树更新后从 root 重走全链**（5 月 k_queue 语义的分轮化）；**center 只确认关系，walk 与 center 无关**。
4. **排序=步数覆盖优先→长度优先→GTE 组内精排→per-terminal topk**。
5. **去重=事实键**（方向归一+逆关系折叠），链级丢全旧链，边级渲染跳过已交付边。
6. **join 合拢失败→存在性提醒**（mind-map：不给关系链/不给终点/不给排序；池到池最短+GTE 排序，永不锚定 gold）。
7. **回显去重**：命令有的信息结果不重复（center 回显删除、grouped_relations 删除）。
8. **评估（RSCC v3）**：p_g=exp(mean token logprob)；判定 ∃g:[Δp≥0.05 或 (Δp>τ_noise 且 R=Δp/L>τ_share)]；L=通路固定锚；L<τ_lift 弃权保留。

## 四、遗留问题（审计重点候选）

1. **537 s1-s5 第二断点**（子智能体调查中）：空渲染 sg 的调用形态与 s0 分叉——新实体 center 无树映射时是否仍走完整派生。
2. **2784 大段证据丢失嫌疑**：残段链过滤（1ffe41e）把链的边也踢出渲染——"只滤 label 不过边"的改窄未做。
3. **回显删除的全局上下文效应**未消融（v26 唯一全局消息变化）。
4. v26 指标 0.517 的完整归因（树键修复后待 48×3 复验）。
5. RSCC v3 的 τ_lift=0.02 校准（55 负 lift vs 2 零 lift abstain 分野）。

## 五、审计材料索引（specs/ 下）

- regress_v26_2026-09-23.md / wipeout_cluster_2026-09-23.md / merge_bounce_cases_2026-09-23.md（对比轨迹）
- rscc_v26v3_dump / rscc_v3fast_dump（概率评估全链路）
- SESSION_MEMORY.md（全程操作记忆，最新在最上）
