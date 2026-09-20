# 环境对抗机制审计 + 直接问答语义测试 — 2026-09-20

> 用户目标：优化环境的对抗问题。方法：①全量盘点环境反向压力机制
> （触发条件/压力形态/失败模式/实测量化）；②把问题裸丢给模型直接回答
> （thinking 2000 / max_tokens 3000），隔离"模型固有语义错读"与
> "环境诱发语义错读"。

## 一、直接问答测试（48 题 × 2 变体，vLLM Qwen3.5-9B, temp 0.3）

变体 A=裸英文问题；变体 B=附加管线同款中文重述（"以这一版语义为准"）。
脚本 scripts/probe_direct_answer.py（gitignored），结果
tmp/direct_answer.json。

| 变体 | hit | miss | abstain |
|---|---|---|---|
| A 裸英文 | 14/48 | 34 | 0 |
| B +中文权威 | 15/48 | 31 | 2 |

（裸答 ~30% 远低于管线 81.9%——参数知识 vs 图检索，正常。）

### 关键个案：语义错读的源头在挂载，不在模型

| 案例 | gold | A 裸英文 | B 挂中文重述 |
|---|---|---|---|
| **1379** | Priest | **Pianist**（读法=职业✓，知识错） | **"None (Franz Liszt died in 1886)"**（读法被重述带偏→撞时间矛盾→弃权） |
| 1171 | James Earl Jones | James Earl Jones ✓ | ✓ |
| 1812 | Barbados | Saint Kitts and Nevis ✗ | **Barbados ✓**（重述反而纠对） |
| Trn-21 | Hailemariam Desalegn | Abiy Ahmed | Abiy Ahmed + **模型当场困惑原文**："if I follow the Chinese instruction 'treat as authoritative', the question becomes 'What currency is the Ethiopian Peso?'…" |
| 2209 | NBA Finals 列表 | 2017 ✗ | None |

**结论**：裸英文下模型对 1379 的"career"**天然读成职业**（答 Pianist）——
管线里的职务错读**不是模型固有问题**；挂上错误重述后错读复现（A→B 从
职业型答案翻成弃权）。语义错读的充分原因 = 重述内容错 + 权威措辞。

技术注记：vLLM 0.25.1（重建容器）下 `chat_template_kwargs.thinking_budget`
软提示**失效**（74/96 finish=length、content 空——思考吞满 3000）；
改用顶层 `thinking_token_budget: 2000`（client.py 同款硬帽）后正常。
重放/管线默认走 client.py 硬帽路径，不受影响。

## 二、环境对抗机制全量盘点（fire rate = 基线 144 轨迹实测）

| # | 机制 | 位置(seq_react_loop) | 触发 | 压力形态 | fire | 失败模式 |
|---|---|---|---|---|---|---|
| 1 | 纯度环提醒 | 1796 | 同中心第 3 次相似措辞查询 | ⚠ BEHAVIOR PATTERN + Stop-Rule 提醒 | (并入#2) | 证据真不存在时仍施压重问 |
| 2 | HARNESS CLOSURE | 1804-1817 | ≥4-5 次相似查询 | 强制关事实 ✗ unresolved-after-repair，禁再探 | 2 | 关闭的是"事实"而非"判别子不存在"这一现实 |
| 3 | 工具重复门 | 1587-1603, 516 | 同工具同参数重复 | loop_nudge"已调用过，结果相同" | 2 | 良性（防呆） |
| 4 | NONE→ladder | 1638-1646 | 首次 NONE/弃权 | 强制"退一级重选关系/探新/[explore✗none]" | 5 | **只压关系层，从不质疑 plan 语义** |
| 5 | Second refusal | 1652-1654 | 二次 NONE | 强制作答+**枚举当前绑定**为唯一依据 | 4 | **绑定继承错误 plan 的变量**（1379：问 position 绑 org） |
| 6 | RESTART | 1218-1290 | [explore✗none] 声明 | 全量重置+教训注入；仅一次 | 1 | 重 plan 仍沿旧语义（无语义层帮助） |
| 7 | workflow-order REJECTED | schema/repeat 门 | 检索期工具序错 | REJECTED+正确序提示 | 1 | **restart 后首调 plan 被拒**（1379 耗掉唯一 n_reject） |
| 8 | 越池答案拒绝 | answer 校验 | 答案实体不在证据 | error+劝扩枝 | ~0 | 良性（合法性） |
| 9 | 全事件节点拒绝 | §7.5 | 答案全是 m./g. | error+绑属性指引 | 1 | 良性 |
| 10 | CVT 绑定剥离 | 1413 | checkpoint 绑 CVT | ⚠ 剥离+§7.5 指引 | 19 | 高频且保护性 |
| 11 | 冻结绑定 REJECT | 1427 | 改已冻结绑定 | "hallucination"拒绝 | 5 | 保护性 |
| 12 | 幻觉实体 REJECT | 1443 | 绑从未出现的实体 | 拒绝 | — | 保护性 |
| 13 | 语义幂等门 | seq_tools | 同根同关系重调用 | evidence_repeat 劝用旧证据 | 0 | 未触发（1379 ?org 复调漏网待修） |

**损伤结构**：高频机制（10/11/12）是防幻觉的，方向正确；真正"对抗性"
的是 4/5/6/7 这条**弃权-惩罚链**——fire 率低（8-10/144）但命中即毁
（1379 三样本全灭）。核心缺陷两条：**链上没有任何一环触及 plan 语义**
（restart 重 plan 无语义辅助→原样犯错）；**终点（Second refusal）把
错误 plan 的绑定当作唯一合法答案源**。

## 三、优化提案（按损伤链排序，待裁定）

- **P1 语义逃生门（治本）**：ladder 第一级增加第三个选项——
  "重读问题、回 plan 层改读法"（若问句含 career/profession/职业 类
  问词，显式提示双读法）。弃权有时是"问错了"而非"没探到"。
- **P2 强制作答类型校验**：Second refusal 枚举绑定前，绑定变量类型
  ≠ plan answer_type（问 position、绑 org）⇒ 提示类型错位并允许一次
  回 plan，而非硬压提交。
- **P3 restart 后首调豁免**：restart 重置后首个 `plan` 调用合法
  （workflow-order 只管检索期顺序，不该烧掉唯一的 n_reject）。
- **P4 纯度环分级**：第 3 次相似查询的提醒区分两种现实——"换个措辞
  再试"vs"判别子可能不在图里：转向其他 fact 或按支持度作答"。
- **P5 zh 挂载治理**（前案提案 a）：修 5-6 条错位重述 + 措辞降级
  "辅助参考"；直接问答测试已证明错误重述+权威措辞足以单独倾覆语义。
