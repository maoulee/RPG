# 代码地图 — 机制审计同步审核用 — 2026-09-24

分支 audit/gpt6-2026-09-23（已推送）。管线四层：关系扩展→模式派生→链重建→渲染。
审计焦点：①层间隐式契约（键/边/实体三种形态的层间漂移）②设计外 cap/折叠/车道
③同一语义多处实现（去重/桥接/可行性）。标记(修)=本段会话修复点。

| 机制 | 文件 | 行 |
|---|---|---|
| 关系扩展/桥收集 _sg_prepare | kgqa/agent/seq_tools.py | 3686 |
| bridge 桶(_bids) | kgqa/agent/seq_tools.py | 3924 |
| 树匹配/根映射 _root_of | kgqa/agent/seq_tools.py | 4065 |
| 层可行性 classify | kgqa/agent/seq_tools.py | 3578 |
| 桥接合法回退(infeas 收集) | kgqa/agent/seq_tools.py | 4137, 4238 |
| 模式派生 derive | kgqa/agent/seq_tools.py | 4282 |
| 枚举天花板 cap=60 | kgqa/agent/seq_tools.py | 4421 |
| 语义选择层 per-terminal quota=3 | kgqa/agent/seq_tools.py | 4832 |
| 链重建 walk | kgqa/agent/seq_tools.py | 4438 |
| CVT 穿透分支 | kgqa/agent/seq_tools.py | 4473 |
| 终跳边补挂 term_edge(修) | kgqa/agent/seq_tools.py | 4461, 4510 |
| pe 组装/树键归一(修) | kgqa/agent/seq_tools.py | 4226 |
| delta 事实键(修) | kgqa/agent/seq_tools.py | 4598 |
| 事实键工具 | kgqa/agent/seq_tools.py | 833 |
| 渲染入口 render_v38_ack | kgqa/agent/seq_render_v38.py | 50 |
| 边级 prior 过滤(修) | kgqa/agent/seq_render_v38.py | 61 |
| store 组装 collect | kgqa/agent/seq_triples.py | 36 |
| FULL-DEPTH 残段校验(修) | kgqa/agent/seq_triples.py | 125 |
| ADMIT_TOTAL=24 配额 | kgqa/agent/seq_triples.py | 149 |
| 行渲染 render_rows | kgqa/agent/seq_rows.py | 41 |
| _GROUP_CAP 行块配额 | kgqa/agent/seq_rows.py | 20, 137 |
| 车道准入 CVT 尾(修) | kgqa/agent/seq_rows.py | MISS:cvt_kv\[t\] and cvt_kv |
| answer 工具 _do_answer | kgqa/agent/tools.py | 2073 |
| 结构化收割索引修复 | kgqa/agent/tools.py | 2185 |
| join rescue(模块级) | kgqa/agent/tools.py | 2230 |
| 公平契约 | kgqa/agent/tools.py | 2236 |
| 关系池 2-hop+id 透明 | kgqa/agent/tools.py | 742 |
| rr 候选+保底槽 | kgqa/agent/seq_tools.py | 3061, 3163 |
| 推理时刻 merge note | kgqa/agent/seq_react_loop.py | 1262 |

## 本段修复 commit 对照（最新在上，docs/diag 略）

d9a7175 render: context-tail lane admits attr-carrying CVT tails (1812 pure-literal terminal specimen)
caea2b4 walk+render: materialize last-hop re-discovery edges; bracket CVT heads in incoming rows (Eleanor-1392 specimen)
eb604a5 render: admit mid-chain CVT pass-through chains in pattern reconstruction (537 second breakpoint)
a07add4 walk: tree-keyed resolution — centers confirm relations, walks start at the root (design realignment, user ruling 2026-09-23)
883370b render/rr: duplication removal, not truncation (user correction 2026-09-23)
9d9e4b0 render: echo budget for center/frontier lines + same-sample compare pairing (user rulings 2026-09-23)
79af503 docs+dump: v26 verdict (three-step decline, ablation queued) + RSCC v3 rerun on v26
1ffe41e render: expansion remnants never mint bare pattern labels (567 specimen)
0f6fa6b rr: CVT-bridge reserved slots on the first screen (21_ specimen)
499f683 join: merge note at reasoning time (both ANSWER_ANALYSIS entries, one-shot, informational)
bde37bb join: merge note moves to retrieval-completion (information, not interrupt — user ruling 2026-09-23)
161eb06 join: fairness contract documented — pool-to-pool shortest + ranking, never gold-anchored (user ruling 2026-09-23)
220619f join: existence-only merge reminder (user ruling — no method, no chain, no ranking in the feedback)
58fff27 join: leak guard actually sealed (render branch landed — silent patch miss fixed with assert)
18a04e0 join: mind-map reminder — bridge endpoint hidden (answer-leak guard, user ruling 2026-09-23)
c47d040 join: answer-time structural merge check (user ruling — actual walked variables, never message parsing)
88c7407 join: rescue pool-key canonicalization (integration audit, no-rollout verification)
fa46b35 join: rescue renders CVT-mediated bridges (bug: named-pair edge lookup dropped them)
