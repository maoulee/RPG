# 1379 语义审计：问题语义挂载 / 关系选中 / 环境-模型对抗 — 2026-09-20

> 用户假设："最大的问题不是工具的问题，而是问题语义记忆关系选中的问题"。
> 本审计以 1379（gold=**Priest**）s1 完整轨迹（含逐条模型思考）为标本验证。
> **结论：假设成立**——工具层（GTE 排序、候选列表）反复把正确关系族递到
> 手边，语义层（中文重述→plan→子问题措辞）从未伸手；对抗机制随后把
> "正确弃权"锻造成"错误提交"。

---

## 发现 1：中文语义挂载把错误读法钉死（问题语义层）

- gold = `["Priest"]`——**问的是职业**（"What was Franz Liszt' career that
  had him ending up leading a religious organization..."）。
- 挂载机制正常工作：`tmp/zh_questions_48.json` 的中文重述附加到首条
  user 消息，且措辞为**"以这一版语义为准 / treat as authoritative"**
  （seq_react_loop.py:640-654；gold 刻意不注入——设计正确）。
- 但 1379 的重述本身写错了：
  **"Franz Liszt 在 1993 年 3 月 27 日之前担任的宗教组织领导职务是什么？"**
  ——把 "career" 读成"宗教组织的**领导职务**"；正确读法是
  "什么**职业**使他最终领导宗教组织"（答案=职业名 Priest）。
- 模型在 MSG 0 思考里原样引用并以其为准（"Chinese restatement … 担任的
  宗教组织领导职务是什么？"），MSG 6 再次"Chinese restatement confirms
  the date constraint"。两次 plan 均锚定 `?religious_leadership_position /
  answer_type: position`。
- **机制性问题：审定语义的钩子给策展错误加了权威权重。**

### 中文重述 48 条 QC（gold 类型 vs 重述读法）

| 案例 | gold | 重述读法 | 判定 |
|---|---|---|---|
| WebQTest-1379 | **Priest**（职业） | "宗教组织领导职务" | **错位**（本例） |
| WebQTrn-21 | Hailemariam Desalegn（人） | "埃塞俄比亚比索是哪种货币？" | **完全错题**（张冠李戴） |
| WebQTrn-1812 | Barbados×2（实体） | "…是一个…国家**吗**？" | **类型错**（是否型 vs 实体型） |
| WebQTrn-2209 | NBA Finals 列表（实体） | "…获得**吗**？" | **类型错**（是否型） |
| WebQTest-1171 | James Earl Jones（配音演员） | "…部队士兵是谁？" | 疑似错位（锚定士兵非配音者） |
| WebQTrn-2576 | Americas | "…所属的大洲是？"（语病） | 意图对但句子残缺 |

**错位率 ≈ 5-6/48（~11%）**；挂载是权威措辞 ⇒ 每条错位可倾覆其 3 个
sample。其余 42 条读法与 gold 类型一致。

## 发现 2：关系选中忠实执行了错误语义（记忆→选中层）

GTE 排序无罪——6 次 `retrieve_relations` 的候选列表里**职业关系族反复
出现**，模型从未对其派发 subgraph：

| 次数 | 子问题（由 plan 派生） | 职业族候选及排名 |
|---|---|---|
| 1 | "which religious organizations did he lead/manage" | people_with_this_profession #11；person.religion #3 |
| 6（restart 后） | "which religious leadership positions did he hold" | **person.religion #1**；people_with_this_profession #5；character_occupation；employment_history |

链条：中文重述钉错 → plan 声明错（R1"led a religious organization"）→
子问题措辞错 → GTE 按子问题忠实排序（组织族置顶——**正确执行**）→
模型选组织族。**工具层把正确候选递到手边，语义层从未伸手。**

## 发现 3：环境-模型对抗把"正确弃权"锻造成"错误提交"

s1 时序（详见下文轨迹）：

1. f2（离职日期判别子）在该图切片**不存在** → 模型换 3 种措辞重问 →
   纯度环施压（3 次相似查询 Stop-Rule 提醒，≥4-5 harness 强制关事实）。
2. 模型答 NONE——**在其（错误）计划下这是理性且正确的认识论状态**。
3. 环境逐级对抗：`NONE → ladder`（强制重选关系）→ 模型 declare
   `[explore ✗ none]` → restart → 重 plan（**仍是错误语义**——证明对抗
   不触及语义层）→ 重 plan 后首调 `plan` 被 REJECTED（workflow-order
   规则，耗掉唯一 n_reject）→ 再探再 NONE。
4. **"Second refusal — answer from current support NOW"** 并枚举绑定
   `?org=['Freemasonry', 'Franz Liszt Academy of Music, Budapest']` →
   模型被迫从**错误变量的绑定**里挑了 Freemasonry（f1=0）。

关键缺陷：**强制作答的绑定枚举继承错误 plan 的变量**（plan 问 position、
绑定是 org），终局压力从不质疑 plan 语义，只往下游施压。

- s0：叠加 restart 重置 crash 家族（dict-append，2026-09-19 已修）耗尽
  轮次，answer NONE → 空 rescued。
- s2：卡死在重复拒绝尾巴（msgs 22-34 全是 Second refusal），**连实体
  答案都没产出**（rescued None）。

## 规则修正提案（待裁定）

- **a. zh 挂载措辞降级**："以这一版语义为准"→"辅助参考，若与英文原文
  冲突以原问为准"；或先做 48 条策展 QC（修掉上表 5-6 条）再保留权威。
- **b. 强制作答类型校验**：Second-refusal 枚举绑定前，若绑定变量类型
  ≠ plan 的 answer_type（问 position、绑定是 org），压力消息提示类型
  错位并允许一次回 plan，而非直接强制提交。
- **c. plan 双读法提示**：问句含 career/profession/职业 词时，plan
  阶段提示"答案可能是职业名而非组织/职务"。

---

# 附：1379 s1 完整轨迹（34 步，模型思考逐条原文）

question: What was Franz Liszt' career that had him ending up leading a
religious organization before March 27, 1993?　gold=["Priest"]　f1=0.0

## MSG 0 — assistant（plan）【转折①：语义锚定错误】

> The user is asking me to plan the retrieval for this question. Let me
> analyze what's being asked:
>
> Question: What was Franz Liszt' career that had him ending up leading a
> religious organization before March 27, 1993?
>
> Chinese restatement: Franz Liszt 在 1993 年 3 月 27 日之前担任的宗教组织领导职务是什么？
>
> This asks about: 1. Franz Liszt (the person) 2. A religious organization
> leadership position he held 3. Before March 27, 1993
>
> …（略：R1/FILTER/D1 拆解）…
>
> But I also need to capture the temporal constraint (before March 27,
> 1993). This might require a second fact…

content:
```
tool: plan
entities: Franz Liszt
answer: ?religious_leadership_position
answer_type: position
R1.kind: structural
R1.text: Franz Liszt led a religious organization
sg1.f1: Franz Liszt | which religious organizations did he lead/manage as member or founder | ?org
sg1.f2: ?org | when did Franz Liszt's leadership of this organization end | ?end_date
```

→ tool: flow f1 确认。

## MSG 2 — assistant（retrieve_relations f1）

> …I need to find relations that connect Franz Liszt to religious
> organizations he led or was a member of…

## MSG 3 — tool（候选列表，GTE 排序）

`organization.founders | organizations_founded | person.religion #3 |
member_of | genre.artists | … | people_with_this_profession #11 | …`
【职业族在手边，未被选中】

## MSG 4 — assistant（subgraph 选中组织族）

> …the most relevant relations are: organization.founders,
> organization_founder.organizations_founded, organization_member.member_of…

## MSG 5 — tool（块#0 渲染：FL→LoFL→{m.0cr70y2[Freemasonry], Academy}）

## MSG 6 — assistant（f1 提交 + 转向 f2）【转折②：模型自己也注意到了语义疑点但被中文重述压回】

> …Freemasonry is NOT typically considered a religious organization in
> the traditional sense… Franz Liszt Academy of Music - not religious…
>
> I'm noticing a potential issue with the entity identification. Franz
> Liszt lived from 1811-1886, which means he couldn't have held any
> position before March 27, 1993…
>
> The Chinese restatement confirms the date constraint: "Franz Liszt 在
> 1993 年 3 月 27 日之前担任的宗教组织领导职务是什么？" - asking about a
> religious leadership role before that specific date.
>
> Given the temporal impossibility, I need to determine whether to flag
> this as an unanswerable question or work with the available evidence…【模型发现时间矛盾，仍按错误重述继续】

## MSG 8 — assistant（f2: members|company subgraph）

> …For determining when someone ended leading… membership/tenure
> relations… Neither Freemasonry nor Academy are explicitly religious…
> work with what the graph provides…

## MSG 9 — tool（块#1：无日期边）

## MSG 10 — assistant（f2 ✗ unresolved + 重问）【对抗环起点】

> …The key issue is that we don't have date information… the question
> requires … BEFORE March 27, 1993… I need to continue retrieving…

## MSG 12 — assistant（f2 第二轮：membership 全家桶）

## MSG 13 — tool（块#2：仍无日期）

## MSG 14 — assistant（f2 ✗ 第三次重问，转向"是否宗教组织"）

> …there was people.person.religion as a candidate relation which wasn't
> included in my first retrieval. This might be more relevant…【又摸到 religion 族，仍非 profession】
> …Without date evidence, I cannot verify this constraint. However…
> the open fact f2 covers the same requirement R1… it could potentially
> re-bind the answer variable. Since I lack temporal evidence… I need to
> continue searching…【停止规则被 open-fact 条款拖住】

## MSG 16 — assistant（org_type 族 subgraph）

## MSG 17 — tool（块#3：类型链渲染，Freemasonry/Academy 无宗教类型标记）

## MSG 18 — assistant（f2 ✗，"neither explicitly marked as religious"）

> …person.religion shows his personal religion (Catholicism), not an
> organizational role… Neither candidate is shown as religious… STOP
> RULE: Would the missing evidence potentially change WHICH NAMED ENTITY…
> …I'll need to systematically review…

## MSG 20 — assistant（?org 复调用 org_membership 族）

## MSG 21 — tool（块#4）

## MSG 22 — assistant（ANSWER_ANALYSIS → NONE）【正确弃权】

> …Neither candidate satisfies the "religious organization" requirement…
> Missing evidence (religious classification + temporal constraint) cannot
> be obtained from the graph…
> PROVISIONAL_FINAL: NONE … tool: answer entities: NONE

## MSG 23 — tool（对抗第一级）

`NONE → ladder: re-select relations; [explore ✗ none] restarts once …
You may fall back ONE level: re-select the weakest subgraph's relation set…`

## MSG 24 — assistant（restart 重 plan）【转折③：重 plan 仍是错误语义——对抗不触及语义层】

> …The previous attempt failed because… neither was classified as
> religious… Let me re-plan with different relations… religious
> positions/roles… church-related… religious institution leadership…
> 也许 there's a connection through religious compositions…

content: plan（answer: ?religious_leadership_position, f1 "which religious
leadership positions did he hold"）

## MSG 25 — tool（REJECTED: workflow-order，耗掉唯一 n_reject）

`REJECTED: Wrong tool in the retrieve phase — … retrieve_relations must
come BEFORE retrieve_subgraph … facts: ✓f1 ⬜f2 (retrieved 5/2)`

## MSG 26 — assistant（按序重走：retrieve_relations "religious leadership positions"）

## MSG 27 — tool（候选：**person.religion #1**、people_with_this_profession
#5、character_occupation、employment_history【职业族最高位出现，仍未选】）

## MSG 28 — assistant（subgraph 仍选组织族：founders|org_founded|member_of|membership.member）

> …These could potentially encode religious leadership if the
> organizations are religious…【语义反了：先找宗教组织再推职务，而非直接问职业】

## MSG 29 — tool（块#5）

## MSG 30 — assistant（再 NONE，分析同 MSG22）

## MSG 31 — tool（对抗第二级：强制作答）【转折④：错误绑定被枚举为唯一依据】

`Second refusal — answer from current support NOW (bindings so far:
?org=['Freemasonry', 'Franz Liszt Academy of Music, Budapest']).`

## MSG 32 — assistant（被迫选 Freemasonry）【最终错误提交】

> …the protocol requires me to answer from available support rather than
> withhold… Freemasonry appears most relevant given its historical
> religious connections… I'll go with Freemasonry as the best match
> despite the gaps in verification.

content: `PROVISIONAL_FINAL: Freemasonry … tool: answer entities: Freemasonry`

→ tool: `{"entities": ["Freemasonry"]}`　f1=0.0（gold=Priest）

## s0 / s2 简记

- s0：同错误 plan 路径；restart 后两次 subgraph 撞 dict-append crash
  （已修的 2026-09-19 重置 bug 家族），answer NONE → 空，rescued 0.1。
- s2：f1 同路径；answer NONE 后进入拒绝尾巴——msgs 22-34 全是反复
  ANSWER_ANALYSIS/Second refusal，轨迹在拒绝中结束，无实体答案。

---

**一句话总结**：1379 三样本全错（f1=0）的共同根因不在工具层——中文重述
把"career=职业"钉成"宗教组织职务"（权威措辞），plan/子问题随之全错，
GTE 忠实服务于错误子问题（职业族候选反复在手边从未被选）；切片里不存在的
判别子（离职日期）触发纯度环与拒绝阶梯，强制作答机制最终把枚举到的错误
变量绑定（?org=组织）锻造成最终答案。规则修正提案 a/b/c 待裁定。
