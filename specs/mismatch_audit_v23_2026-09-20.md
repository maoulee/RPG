# V2.3 错误案例深度审计：设计理念 × 实际行为错配总报告 — 2026-09-20

> 三审计代理（弃权族 27 / 实答下跌族 31 / 结构对比 144v144）并行解剖，
> 本报告为交叉合成。素材：reports/v23_envfix_48x3.json vs v06 基线，
> 错误清单 tmp/error_manifest.json。所有结论带思考原文佐证。

## 总判决（设计 vs 行为）

**V2.3 的计划改写本身近乎轮数中性（facts/plan 1.98→2.06）；回归发生在
答案阶段**：+2 轮/轨迹中 **75% 花在首次作答之后**——弃权梯子的乒乓球
（57.5% 的 answer 调用被弹回 vs 基线 11.3%，浪费答案轮 169 vs 23），
27 个终局 NONE 中 25 个走过梯子、**0/27 被梯子转化为正确提交**；
26/27 死在 17 轮上限，且 **21/27 的 gold 字符串就在工具输出里**。

## 错配一：梯子的语义泄漏（最核心，双路径）

设计=harness 只执法不释法；实际=两条路径都在替模型裁决：
- **ladder 被读作零支持判决**（241_97bf 标本）：模型思考里**先正确应用
  了 §28b**（"submit the best graph-supported bindings anyway"），然后
  `"But wait…The system said 'NONE → ladder'…This suggests there's no
  confirmed fact supporting ANY binding"` → 收回正确结论改交 NONE。
- **二拒绑定清单被当作系统指定答案**（6 例逐字投降）：124 标本思考原文
  `"While my earlier retrieval showed different titles, the system
  indicates these four have sufficient support"`——清单本身还是**陈旧的**
  （新 walk 已超集：2784 的 Juice 在 t20 渲染、清单 t22 仍是旧四片）。
  Wave-1 把清单收窄到 answer-var 反而使它更像裁决。
- 372 例清单**错误**（声称无绑定而 ledger 持 [God|Jesus Christ|…]）；
  1171 只列了一侧。

## 错配二：§28b 的两向误用（一条规则毁两边）

- **弃权侧（10 例）"ANY binding"范围扩展**：1171 思考原文 `"we DO have
  evidence for ?person from both subgraphs…So technically we have
  bindings, just not ones that satisfy both constraints"` → 仍 NONE——
  把"约束未满足"偷换成"无绑定支持"。
- **提交侧（7 例）union dump**：判别子不可得时 §28b 令其"submit the
  best graph-supported bindings"——模型读复数=**全交**（1557 三校全交
  vs 基线单交 McGill；1840 三语全交）。精确度被 satisfice 摧毁。
- 派生：精确等值不容差（Belgium 10.1284≈10.126703、Juice 01-17≈01-01
  各弃权）；答案值嵌实体名自禁提取（2209"2008 NBA Finals"在手，
  "answer_type: year…需要独立 year 实体"）。

## 错配三：证据在图里、不在屏幕上（渲染欠 spec）

- **判别值未渲染（6+）**：日期/时长/ISO 值在 CVT/事件节点内被丢
  （626 date_adopted 空三元组；25 runtime 空；537_4346 film: 槽缺，
  只渲染 character:→1923 答了角色名 f1 0.455→0）。
- **枚举方差（4+）**：同关系不同采样不同尾集（576 vs 1812 同查
  North America 成员表互缺 gold；241 边事件只展开 2/11）——license
  采样 + 2-of-N CVT 展开帽按采样过滤 gold。
- **slot 错配**：括号渲染不按 answer_type 选键（问 film 给 character）。

## 错配四：链式单树计划形态（V2.3 自伤）

sg/plan 1.92→**1.40**（87/144 单 sg 链）——V2.3 的 answer-bearing chain
引导 + "变量留在产出它的 view 里"使断链即全断、无第二证据路 → 44 例进
梯子（基线 5）。对照：MULTI-TREE REMINDER（运行时提醒多树）命中 80%。

## 错配五：门的组合病

- **per-sg 预算门 0→15 拒绝**：3×facts 对大中间绑定集的链不友好
  （567 28 片单子被 4 次预算拒）。
- **answer-var 语法纪律 × rescue 互拆台**：2209 年份值被门弹（不在池），
  轮尽后 rescue_terminal_answer 又**把被拒值原样捞回**（rescued=True）——
  刚立的硬不变式被救援路径击穿。
- workflow-order 门 ×3 拒绝同一轨迹（2576 空 fact 后想重 plan 被连拒）。
- checkpoint 语法严格（2152 "variable ?team has no declared bindings"×4
  烧 6 轮）。

## 错配六：zh 移除的隐性代价

5/19 题的计划读法退化与失去 paraphrase 一致（493 语义槽读法→4 跳字面
时区链；2209 2 跳实体答→3 跳年份抽取；452/1731/2576 同族）——zh 不只是
错读放大器+gold 泄漏源，还是**语义压缩器**。需要中性替代（见修复 7）。

## 正面确认（要保住的）

MULTI-TREE REMINDER（80% hit）、NO_EVIDENCE 分层诊断（56% hit，优于旧
文案）、多工具打包（小节轮）、语义槽修复在 1379 族生效（0→双满）。

## 修复清单（合并三审计，按杠杆排序）

1. **梯子语义中立化**（治错配一，杠杆最大）：二拒清单改为"ledger
   snapshot（可能陈旧，非裁决）"并从**最新证据层**重算；或二拒时若
   answer-var 有绑定直接以绑定终局（0/27 转化率证明梯子纯浪费）；
   NONE→ladder 文案明示"对支持度的判断以你的 ledger 为准"。
2. **§28b 双向改写**（治错配二）：操作化——"数 ledger 里 answer-var
   绑定数；≥1 ⇒ 提交是强制的；约束 UNKNOWN 永不清空 ledger；提交
   **最小完全支持子集/单选最优**，永不是并集"；加容差句（日期/浮点
   就近）与"答案值可从绑定实体名提取"。
3. **rescue 不得捞回被门拒绝的值** + per-sg 预算改 per-fact（治错配五）。
4. **计划形态回多树**：MULTI-TREE 提升为 plan 时规则（治错配四）。
5. **渲染三修**（治错配三）：判别值（日期/数值）必渲染；括号 slot 按
   answer_type 优先；license 采样做 gold-recall 审计。
6. workflow-order：空 fact 关闭后允许 plan 重构（2576 型）；checkpoint
   语法放宽到 status:✓+内联值。
7. **zh 角色重审（需用户裁定）**：中性语义压缩替代（如 plan 前一句
   模型自述复述+槽声明，或恢复 zh 但去权威+修 6 条）。
