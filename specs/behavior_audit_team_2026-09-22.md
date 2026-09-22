# 四智能体行为审计总报告（IG标记/概率解耦/冗余判定/重复调用）— 2026-09-22

按用户四点目标拉起的并行审计之综合。数据基础 reports/v23_unified_48x3.json
（144 轨迹）。四份子报告全文见本文各节（原样保留关键表格与判据，供裁定）。

## 总览：三句话

1. **解耦成立**：三处打分器的概率族（p0/pF/pG*/d/l/f）对模型实际答案零
   依赖（gold 全部来自数据集 gold 字段；`p_yhat` 是独立答案责任通道）；
   四象限：检索赢·答案赢 110 / **检索赢·答案输 32（22.2%）** / 检索输·
   答案赢 0 / 双输 2。
2. **旧标记体系的病根**：结构域（necessary/pathway/断链）与概率域
   （d/l/f/级联档）被一个级联顺序焊死，用 "effective/harmful" 两个词
   覆盖所有成因；实测 33 嫌疑块人审：**有价值被误标 13（39%）/真冗余
   16（48%）/存疑 4**——误标集中于"值/约束交付"块，漏标集中于
   "同 lane 重走+表面变体"块；旧结论"真边界=N+表面变体"被推翻
   （N 与价值**双向解耦**：N=.97 真冗余与 N=.12 承答块并存）。
3. **重复调用有真 bug**：`_sg_served` 幂等缓存因**键序错误结构性死亡**
   （check 侧取名字/mark 侧取索引，永不相等）；`tool: checkpoint`
   非法工具名导致 80 次/41 轨迹的误导性拒绝；精确重复 104 次（9.1%）
   +表面变体 121 次（10.6%），其中 A-B-A 间隔重复 74 次是相邻签名
   gate 结构上拦不到的。

---

## ① IG 标记词汇审计（子报告要点）

### 旧标记 → RSCC 三类映射（含冲突点）

| 旧标记 | 映射建议 | 冲突点 |
|---|---|---|
| `necessary=yes`（L1） | 保留结构通道，映射 Informative(structural)，**与概率通道分账不互斥** | **2576 s0 块0（GLN）被 RSCC 删除且 pG\* 翻倍**——V1 冲突带共 10 块 |
| `pathway_verdict=unreached` | Structural-invalid 候选，**三条件合取**（unreached∧零引用∧零台阶） | 忠实 unreached（567-s0：performance 边没被走到）≠行为错 |
| `pathway_verdict=redundant` | Redundant-valid 结构查重通道（签名重复） | 与块级 redundant_dup 同名异义 |
| `harmful-break` | 结构负裁决候选，放开为通用（不限 MISS） | 只在 MISS 标，v4 后归零；φ 电位 hub-gold 不可靠 |
| `redundant_dup`（N<0.2） | Redundant-valid 查重通道 | 可靠（3/3 全对）——但见②H2 的 N 双向解耦 |
| `redundant_irr` | **不映射**（系统性误标，动态删除替代） | f 门槛=伪装的答案相关性 |
| `effective` L1 臂 | 拆分：结构必要→Informative(structural)；lineage→由依赖序取代 | lineage 假阳（hub 中心必命中自己块的边）+假阴（迷失链全绿） |
| `effective` L3 g 臂 | g★首达保留为 Informative 的 OR 臂 | — |
| `effective` L3 N∧f 臂 | **废弃 f 臂** | — |
| `harmful`（L2 负） | 不映射负类：RSCC 里同类块=ratio>1（删了更好） | 措辞冲突：旧"有害"≠RSCC"可删且删了更好" |
| 空交付块 | 证伪通道：`Redundant-valid(Δ=0)+falsification`，记 0 | — |

### 措辞误导源（前五）

1. **"effective" 一词三义**（L1 救援/L2 概率/L3 新颖）——1797 harmful
   三条件全满足仍 effective；567-[5] 三概率信号全负仍 effective。
2. pathway **`substitute` 命名反直觉**（实义"正常到达"；626 替代对
   两条通路反而都判 substitute）→ 改名 `reached`。
3. `redundant` 双层同名（pathway 签名重复 vs 块级 N 查重）→ 后者
   改 `signature-dup` 区分。
4. `necessary` 是结构连通域（删除断路）非答案必要性——2576 证明可分叉。
5. `harmful` 在替代对下语义反转（626 mod2 d=−.259 是备份通路）。

---

## ② 冗余-vs-价值判定漏洞审计（子报告要点）

33 嫌疑块逐块人审（读证据原文+后续引用+lane 新旧+gold 距离）。
**误标 13 / 真冗余 16 / 存疑 4。**

### 漏洞清单 H1-H10

- **H1** f/U_THR 伪装的答案相关性（维持）：gold 串首达后一切约束
  验证/判别值块的 f、p_gain 必然≈0（513-blk1 Eastern Europe 约束边、
  2209-blk2 start_date 判别值）。
- **H2（核心新发现）N 与价值双向解耦**：N=.12 的承答块（1797-s2-blk2
  唯一新边=Pemberton 死期）与 N=.97/N=1.0 的真冗余（1379-blk1 书节点、
  2319-blk4 iso 代码）并存——**"真边界=N+表面变体"不成立**；N 测的
  是展示边首现占比，hub 展开刷新边、判别值块只有 1 条新边。
- **H3** width（实体名口径）漏"旧名字间的新边"（1379-blk2
  profession→Priest 答案边 width=0；2152-blk4 later_known_as 桥接边
  width=0 且 necessary=yes——reconcile 只救 irr 不救 repeat）。
- **H4 空交付≠空证据，两层都接不住**：判别值（数值/日期/ID）在 CVT
  内不渲染 → "要的没来"与"重取旧的"在渲染层不可区分；行为层记
  repeat/irr，RSCC 证伪通道用 texts 非空判空也接不住（241/452/25_892f
  家族）。
- **H5** used/引用启发只认绑定实体不认约束值（513-blk1 的约束值在
  delta 里但 checkpoint 只写 ?country=Georgia）。
- **H6** lineage 台阶假阳+假阴双向。
- **H7 合取/交集题"删了更好"悖论（RSCC 修不了的核心）**：gold 串在
  一臂饱和后另一臂成"概率冗余"却是答案程序必需（626-blk1，交集推理
  原文在案）；同理锚块/树根可因 gold 串被后块重交付而删（2576-s0-blk0）。
- **H8** join 块概率双杀（1731-blk1：old harmful ∧ RSCC DEL ratio 3.62，
  但它是两半子图唯一连接器）。
- **H9 标记对采样/重跑不可复现**（旧 4 例 irr 标本形状全变；2576 s0/s2
  冗余块集合不同）——"redundant 计数"口径在 run 间漂移=指标与实际
  差距的体感来源。
- **H10** 表面变体 lane 无检测（founders vs founded、awards vs tvrage_id）。

### 人审操作性判据 D1-D8（给裁定）

- **D1 lane 判据**：同 center+同族=重走旧 lane；同 center+新族=变体
  再试（看目标维度是否变）；新 center=新 lane（默认非冗余）。
- **D2 表面变体**：关系名归一（剥域前缀/复数/同义对）后同已查族。
- **D3 后续引用**（价值证据三条）：(a) 块新边的端点成为后续调用
  center/relations；(b) 块的边或**值**出现在最终 checkpoint/answer
  推理文本；(c) **join 检验**：删块后问题两半在展示图断连。
- **D4 判别值判据**：块交付 answer_type 对应类型的值（哪怕 CVT 内联/
  串位/截断）→有价值，渲染缺陷记环境账。
- **D5 空交付判据**：requested 关系族零边返回=空交付（证伪信息），
  与重取旧信息分开记账；只有对空交付的**原样重试**才是 repeat。
- **D6 gold 距离+反向验证**（Europe∋Georgia 型验证块单向 φ 会漏）。
- **D7 合取保护**：k-约束合取题每臂承证块不可因"gold 串在对侧已现"
  判冗余。
- **D8 采样敏感对照**：跨采样/重跑翻转的块降级存疑，不进冗余分母。

### RSCC 能修/修不了

能修：同 lane 零引用重走（1379-blk1 pG\* 5×↑）、LOO 互顶遮蔽
（2784-s2 Petruccelli 显形）、微概率域事故（ratio 判据）。
修不了：空交付块（H4）、合取臂/锚根块（H7）、join 块（H8）、
渲染毁值块（2209-blk2 keep 属运气）、根因教学缺失（只输出可删性
不输出"该改查什么"）。

---

## ③ 概率解耦验证（子报告要点）

零泄漏实锤（gold 来源/消费逐行：score_layer_op_probs.py L271-278→L144；
rscc_credit.py L218-220→L62-63；seq_advantage.py L282/L384；全文件对
answer/f1/pred_entities 的打分读取为 0）。两个"看似混入实为独立通道"：
`V_yhat`→`p_yhat`（答案责任权重，物理隔离）；annotate 的 v2 label
（score 侧不读）。报告口径建议：dump 双账本分栏（【答案侧】/【检索侧】
+象限角标）；检索优势=Δp=pF−p0 按轨迹记账不与 f1 对消；文本命中代理
须标注（2576 命中但 pF=0.014 vs 1379 f1=1.0 但 pF=0.005）；跨象限
case（13 个）单独列。

## ④ 重复/头铁调用审计（子报告要点）

### 量化（144 轨迹，1141 次调用尝试）

- 精确重复 104 次（9.1%，50 轨迹）：连续 30（gate 拦 8）+ **间隔
  A-B-A 74（相邻签名 gate 结构上拦不到）**。
- 表面变体重复 121 次（10.6%，56 轨迹）。按工具：rr 48（最大家族，
  **零防护**）/answer 40（含梯子按设计邀请的重答）/checkpoint 18/
  sg 13/plan 2。
- 烧满型高轮轨迹（≥14 轮，9 条）重复占 23%；旧"NONE 8-9 次烧死"
  已绝迹（三级放行生效，封顶 3 次）。

### 机制核查（两个真 bug）

| 机制 | 判定 | 证据 |
|---|---|---|
| `_sg_served` 幂等缓存 | **死亡（键序 bug）** | check 侧 seq_tools.py:4007 取元组第 0 元（名字），mark 侧 :5128 取第 1 元（索引）——str vs int **永不相等**，字节级重调也命中不了（241/2319/567 实证）。一行可修 |
| `tool: checkpoint` 反馈 | **缺陷（误导性拒绝）** | 非法工具名→"Wrong tool WORKFLOW ORDER"（与格式错误无关），80 次/41 轨迹；md 正则要求行首前缀故 facts: 内的声明不解析→制造"重走↔被拒"振荡（567-s0 三循环根源） |
| 精确重复 gate | 部分有效 | 只比相邻两次（:1820-1848）；A-B-A 每轮换 sig 逃逸 |
| 预算门 | 有效有盲区 | 只计 sg（seq_harness.py:421-443）；**rr 免费**（2576-s2 同 center 白烧 4 次 rr） |
| 拒绝梯子 | 有效（限流） | NONE 封顶 3；但 11 条顶完两级仍弃权（认知转化弱） |

### 认知成因（五）与提示语草案

①把"没取到"读成"图里不存在"（241/25_892 原文）；②"无已确认判别子→
拒答"先验顶住 §28b（复述 Invariant 21 仍弃权）；③重问=进度感、无
"已试过"记忆（2319 逐字相同 reasoning 三连）；④把拒绝读成"重做上一
个成功步骤"；⑤§22.3 教"改写再问"与 Invariant 17 禁重复的内部张力。

草案（不与现有措辞矛盾，只做操作化）：
1. 同命令同结果·变体版（扩 Invariant 17）：检索由解析后的
   (center,关系族) 定义；换表面形态返回相同证据；发检索前翻上文。
2. 两种空的认知学（补 §17）：已执行但空=此路穷尽→✗empty 或换关系；
   ERROR=表面形态错非数据不存在；"未取到"永远不能升级为"不存在"。
3. 重复前自检问句（补 §18）：这次调用服务的哪个新关系族/新 center
   是此前未覆盖的？答不出名字就不要发。
4. NONE 侧不加规则（杠杆=§28b CASE B worked example，已有裁定）。
5. checkpoint 放置具体化：不存在 tool: checkpoint；行在正文、位于
   tool: 行之前；工具被拒不否决 checkpoint 行。

### 环境侧提案（执法/提醒分类）

执法（程序可证）：**键序一行修**；**checkpoint 特判反馈**+正则容忍
facts: 前缀；rr 同型幂等（同 center+question→缓存+劝告）；预算门扩 rr。
提醒：真换关系集的 sg 变体（静态判不了语义重复，硬拦伤合法探索）；
答案侧 NONE（梯子已限流，worked example 走认知）。

---

## 待裁定清单（合并）

1. **立即修（bug 级，建议直接放行）**：_sg_served 键序；checkpoint
   误导反馈+正则容忍；rr 幂等与预算扩展。
2. **提示语草案 1/2/3/5** 是否落 V2.3。
3. **RSCC 增补**：证伪通道判据改"requested 族 vs 实际交付族"（H4）；
   合取保护 D7 进结构裁决；V1 分账标签 `Redundant-valid(probability-
   channel)`；V3 全局护栏；V2 微概率降级。
4. **标记改名**（substitute→reached、redundant→signature-dup、
   effective 按成因拆分）是否执行——影响 dump/文档同步。
5. §28b CASE B worked example（弃权顽疾，已有裁定方向）。
6. 48×3 重跑（以上并入后）。
