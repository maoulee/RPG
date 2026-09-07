# 游走层 × 展示层：设计意图 vs 实现现状审计（2026-08-20）

方法论：不打地鼠。把各层的设计不变量（来自项目历次裁决）列出，对照实现的
真实语义，找**类**级偏差；每条已观察到的 bug 必须能归因到某个偏差，否则
说明审计不全。

## 1. 设计不变量（D = design intent）

| # | 不变量 | 来源裁决 |
|---|---|---|
| D1 | 池=可走：GTE 候选池 = 游走可达关系（2 命名跳预算，CVT 透明） | 2026-08-19 命中逻辑统一 |
| D2 | 模式路径纪律：边进证据 ⟺ 末跳为选定关系 + 最短优先 + CVT 处处透明 | Nordic/Düsseldorf/Ethiopia 四案例裁决 |
| D3 | **证据自含**：每次 retrieve_subgraph 的三元组对其声称的 (路径语境, 选定关系) 给出**该边在 KG 里的完整外延**——模型在当前视图内即可判别，不需要跨轮回溯拼集合 | "triples are the evidence" 工具契约 |
| D4 | 事件节点不是答案；答案用其命名属性 | CVT 渲染裁决 |
| D5 | 判别属性以自身边显示，模型据其筛 latest/largest/incumbent | 显示契约 note |
| D6 | 经济性：重复信息不重复渲染（prompt 预算） | 200 行预算 / 已示边去重 |
| D7 | **候选池稳定**：candidates 行 = 可答案集合，语义单调一致 | 答案边界校验的显示对应物 |
| D8 | 导航契约：下一中心从"当前 triples"里选 | 工具契约 note |

## 2. 各层实现的真实语义（代码为准）

### 游走/证据构建层（pattern 粒度）
- SAPS K-路径游走 → compress_paths → 逻辑模式 → `build_pattern_evidence_triples`
  (formatting.py:226)。证据三元组有**三个入流通道**，各有自己的准入：
  1. witness + **有界 sibling 裸路径**（docstring 明言 "bounded number of sibling
     raw paths ... without exploding into full pattern-level expansion",
     formatting.py:232-235）——尾集是**有界抽样**，不是边外延；
  2. Option-B 末跳叶枚举（同前缀不同叶 = 一个模式 N 叶，seq_tools.py:1499 注释）；
  3. path_edge 支持路径通道 + CVT 桥（formatting.py:493-520，_hop_ok 裁决）。
- `_TOP_PATTERNS=5`（seq_tools.py:1483）：每中心只保留前 5 个模式——模式层
  cap 会决定哪些边根本不进证据。
- **净语义：一条边显示哪些尾，取决于它被哪个通道、哪个模式、哪次游走带到
  ——没有任何一层对"边的完整外延"负责。**

### 展示层（edge 粒度的外观）
- `_render_records`（seq_tools.py:679）：把到达的三元组按 (h,r) 分组合并成
  `h --rel--> t1|t2|...` 行——**对外呈现边的语义**；
- 跨调用去重 `_shown_edge_key = (h, r, t)`（seq_tools.py:675）——**三元组粒度**
  压制：同边旧尾被压、新尾另起一行 → 边被拆碎跨子图（Faroese 类）；
- `candidates:` 行 = **本次调用** top-5 模式的 `pe.candidates` 并集
  （seq_tools.py:1490-1498）——不是答案池，语义在调用间漂移；
- 经济性 cap：`_MERGE_TAIL_CAP`（分支引用 #center::relation）、
  `_TREE_LINE_BUDGET=200`、`max_grouped_lines=120`。

### 答案/累积层（entity 粒度）
- `ctx.all_candidates` + `accumulated_triples`（`_accumulate`,
  seq_tools.py:952-989）：单调累积的命名实体池，答案边界校验用它；
  **内部语义正确，但不显示**。

## 3. 偏差分析（类，不是例）

### 根因：三 层三种粒度，层间契约未定义
游走产 **模式**（路径模板 × 有界叶抽样），展示渲染 **边**，答案校验 **实体池**。
工具契约（D3/D7/D8）全部用"边"的语言承诺，而底层没有边权威对象。

| 偏差 | 违反 | 已观察 manifestation |
|---|---|---|
| B1 边外延无人负责：sibling 有界抽样 + 通道差异 → 同边尾集随入口路径变化 | D3 | sg1 显示 Denmark--languages_spoken-->Faroese\|Danish，sg2 显示 German\|Greenlandic——判别时刻当前视图缺关键尾。**精确机制（2026-08-20 用户解剖确认）**：Option-B 全尾枚举只锚定在每模式唯一 witness 的 `w_nodes[-2]`（formatting.py:513-533）；其余路径走 ≤24 条支撑碎片、每条只带单边（:403-424）。实体是模式A终端、模式B中间时，其A角色边完整性无保证。展示层再把跨模式碎片按 (r,尾集) 合并成"边"的外观 |
| B2 跨调用去重在 (h,r,t) 粒度 → 同边拆碎跨子图 | D3, D6 冲突未裁决 | 同上例：4 尾全集从未在单一视图出现，模型靠跨轮记忆拼合。**核心机制（2026-08-20 用户定性：去重的是边，不是实体）**：seq_tools.py:799-815 先按三元组键移除旧尾，剩余部分再按 (h,r) 合并渲染 → 合并行呈现的是增量却被读作边的外延 → 三元组压制经边级合并放大为实体屏蔽。修复不变量：**边要么整条重渲染，要么整条跳过，绝不渲染部分尾集** |
| B3 candidates 行 = 本次模式端点 ≠ 答案池 | D7 | sg1 行缺 Danish（但答案层接受它）；sg2 行含被压制显示的尾——语义漂移 |
| B4 压制掉的尾不出现在当前 triples → 不能"从当前 triples 选中心" | D8 | 导航需回溯旧轮（同一断裂类） |
| B5 `_TOP_PATTERNS`/sibling 界/caps 同时承担**完整性**与**经济性**两个职责 | D3 vs D6 纠缠 | cap 调大→prompt 爆炸；调小→证据残缺——没有独立旋钮 |
| D1 已实现且验证（池=可走，含噪声过滤对齐） | ✓ | GTE 候选=可遍历（Nordic 复核） |
| D2 已实现（_hop_ok 最短优先 + CVT 透明） | ✓ | 四案例矩阵通过 |

## 4. 设计级修复选项（择一，非补丁）

### Option A：边权威证据契约（推荐）
- 证据单位 = (路径语境, 边)：凡被 D2 准入的边，从原始 `node_edges` 枚举
  **完整尾集**进证据；模式退化为**准入与排序机制**（决定哪些边进），不再切尾。
  **精确化（对应 B1 witness 锚定机制）**：全尾枚举的锚点从「每模式唯一
  witness 的 `w_nodes[-2]`」改为「每一条通过 `_hop_ok` 的合格支撑路径的
  扇出锚点（`nodes[-2]`, `relations[-1]` 对）去重后的全集」——准入仍由
  模式纪律管，外延按边权威枚举。
- 展示去重粒度升到 (h,r)：再遇新尾时**并集重渲染整行**（或注记
  `+N shown earlier: ...` 的轻量变体）。
- `candidates:` 行改显 `ctx.all_candidates`（真正的可答案池，单调）。
- 完整性（语义）与经济性（渲染）分离：caps 只作用于渲染层（行数/折叠），
  永不作用于证据集合本身；分支引用 #center::relation 保持为渲染折叠手段。
- 结果：D3/D7/D8 由构造成立；B1-B5 全部消失。

### Option B：模式权威显示
保留模式碎片，但渲染时显式标注每个碎片的完备性（"此为模式的 2/4 叶"），
candidates 行同样改池。prompt 更复杂，模型需理解模式语义——与现有工具
契约语言（边）不一致，不推荐。

## 5. 验证计划（显示层改动必须实测——GRAPH-STRUCTURE GATE 教训）
1. 单元：四案例矩阵（Ethiopia/Nordic/Finland/Düsseldorf）+ Faroese 例必须
   全量尾集单视图呈现；
2. A/B：1091 错误集 + 100 例易切片 3-seed，主指标 = 阶段归因里 ANSWER-MISS
   桶占比（当前 40% 损失质量）与 mean F1；观测 prompt 长度增量；
3. 回归：WALK_POOL 遍历行为不变（游走层不动，只动证据构建的叶枚举来源与
   渲染去重粒度）。

## 6. 终裁与实施（2026-08-20）

**用户终裁：彻底放弃跨调用三元组去重。** 理由：去重是游走膨胀时代的经济性
权宜；准入控制已由游走层的模式路径纪律（D2）承担；压制"符合当前子图模式
路径要求"的三元组会破坏路径完整性（Faroese 例）。已实施（seq_tools.py）：
- `shown_edges` 改为 **per-call 局部集合**——跨调用零压制；调用内多通道
  重复仍折叠；
- 工具 note 同步：删除 "Edges already shown in a PRIOR subgraph are NOT
  repeated"，改为 "Each subgraph shows the FULL evidence its pattern paths
  justify — an edge may legitimately reappear across subgraphs with its
  complete tail set"；
- 单测验证：Faroese 形态（sg2 四尾整行）、调用内去重、CVT 记录形态全过；
  select_expand 冒烟三阻断点 FIXED。
- 经济性边界：渲染层 cap（_TREE_LINE_BUDGET=200 / _MERGE_TAIL_CAP 分支引用）
  仍然生效；Option A 其余条目（candidates 行改显 ctx.all_candidates、
  witness 锚定问题 B1）待后续裁决。

## 7. 原待裁决项（历史）
- Option A vs B；
- (h,r) 并集重渲染 vs "+N shown earlier" 注记变体；
- 是否同步把 `_TOP_PATTERNS` 从证据准入降为渲染排序。
