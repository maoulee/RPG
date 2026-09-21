# RSCC 讨论原稿（与 Codex）— Reverse Sequential Counterfactual Credit — 2026-09-21

> 用户与 Codex 的机制讨论原文，作为行为评估（credit assignment）实现分析的
> 素材。实现分析报告见 specs/rsc_impl_analysis_2026-09-21.md。

## 1. 背景与核心问题

当前 CGE 的基本思想是：对 Agent 轨迹中的某个行为 a_i，移除该行为产生的
evidence，构造反事实证据状态，并比较正确答案概率的变化：

Δ_i = S(G) − S(G∖E_i)

其中 G=完整轨迹获得的 KG evidence；E_i=行为 a_i 对应的 evidence block；
S(G)=在证据 G 下正确答案的支持分数（如 gold answer log-probability）。

原始 Leave-One-Out 的核心问题：**所有行为都相对于同一个完整轨迹 G 进行
删除**。若多个行为之间存在冗余或可替代信息（c_1 ≈ c_2），则
S(G−c_1)≈S(G) 且 S(G−c_2)≈S(G)，最终 Δ_{c_1}≈0、Δ_{c_2}≈0——两个本来
都合理的行为因为互相替代而同时得不到 credit。

即：**静态 Leave-One-Out 始终在包含大量冗余 evidence 的完整轨迹上评价
行为，产生 redundancy masking。**

## 2. 核心修改：Reverse Sequential Counterfactual

不再对所有行为独立 LOO，而是**按照行为真实执行顺序的逆序，从轨迹尾部
开始依次构造反事实**。关键区别：**每当一个行为被判定为冗余，就真正从当前
evidence state 中移除它，后续行为在更新后的状态上继续进行 counterfactual
evaluation**——counterfactual reference state 是动态变化的。

## 3-6. 单实体场景与动态反事实过程

轨迹 a_1→a_2→b_1→b_2→c_1→c_2→c_3，先结构裁决得 G^(0)，按
c_3,c_2,c_1,b_2,b_1,a_2,a_1 反向评价。当前 evidence state G^(k)，评价
a_i：G_cf^(i) = G^(k)∖E_i，Δ_i = S(G^(k)) − S(G_cf^(i))。

S 优先 S(G)=log P(y*|q,G)（log 而非 raw，减轻饱和）。

- 若 Δ_i > τ：Informative（保留，G^(k+1)=G^(k)）。
- 若 Δ_i ≤ τ：Redundant-valid（不是错误行为）——**真正移除**：
  G^(k+1) = G^(k)∖E_i，下一行为在新状态上评价。这是与普通 LOO 最核心
  的区别。

示例：G_0={c_1,c_2,c_3,…}，Δ_{c_3}≈0 → 删 c_3 得 G_1；Δ_{c_2}=S(G_1)−S(G_1−c_2)>τ → Informative；c_1 同样 → 最终 c_1,c_2=Informative、c_3=Redundant-valid。避免三者互相替代全部近零 credit。

## 6. 为什么倒序而不是正序

轨迹有 delayed credit。从前往后评价 a_1 时，下游 a_2..a_T 仍含大量重复
冗余 evidence，删除 a_1 后概率不降也无法区分"a_1 无价值"与"后面替代了
a_1"（downstream redundancy masking）。反序先清除下游冗余，评价早期行为
时后续 evidence 已收缩。

## 7. 仍属 Counterfactual

subtractive evidence-state counterfactual：intervention 对象是 E_i
（behavior-induced graph evidence）。论文表述建议 "We construct
counterfactual evidence states by removing behavior-induced graph evidence"，
不宣称 exact causal effect of the action（那意味着删 action 重跑环境）。

## 8. 结构裁决先于反事实

先利用 KG 结构移除：无法连接相关候选实体的探索块、与 fact/query
constraint 无关的 branch、明显错误 relation path、无法进入答案相关
retrieval pattern 的 evidence——直接标 Structural-invalid，不浪费 LLM
概率评估。

## 9. 三类行为标签

1. **Structural-invalid**：r<0。
2. **Redundant-valid**：结构正确但可被替代（Δ_i≤τ）——不是错误行为，
   r≈0 或小正值。
3. **Informative / Necessary-under-context**：Δ_i>τ，r>0。

## 10. 冗余与互补的自然处理

冗余对 c_1≈c_2：先评 c_2 → S(c_1,c_2)−S(c_1)≈0 → Redundant-valid 删；
再评 c_1 → S(c_1)−S(∅) 明显下降 → Informative。互补对：两者都保留，
complementarity 不被破坏。

## 11-15. 多实体：偏序 Dependency Graph，非全局时间倒序

多显式实体 e_1..e_M 各展开子图 G_1..G_M 时，**不能全局时间倒序**——跨
子图是并行条件不是因果序列。应 **Branch-wise Reverse Sequential
Counterfactual**：每个实体子图内部倒序（a^m_{T_m}→…→a^m_1），子图间保持
并行，最后 G* = Merge(G_1*,…,G_M*)。

原则（Cameron/DiCaprio 例）：G_Cameron 与 G_DiCaprio 是独立 constraint
branches，问题逻辑是 G_Cameron ∧ G_DiCaprio——不能因 P(y*|G_Cameron)
已高就把 G_DiCaprio 判错；跨 branch 概率删除只用于分析
（complementarity/redundancy/model shortcut），不直接作负 reward。

准确定义：**Reverse Dependency-Ordered Counterfactual Evaluation**。
单实体时 dependency order ≈ temporal order（表现为严格倒时序）；多实体
时 branch 内倒序、branch 间并行。

## 16. 伪代码（要点）

build_behavior_evidence_graph(trajectory) → split_by_entity_branch →
每 branch：structural_prune（invalid→负 credit）→ 对 valid 部分按
reverse dependency order：factual=S(current_graph)，cf=S(remove_evidence
(current_graph, action))，delta=factual−cf；delta≤τ→redundant_valid 且
current_graph=cf（**动态更新**），否则 informative 保留。最后
merge_branches + final_score。

## 17. score_fn

第一版 S(G)=log P(y*|q,G)；增强可用 normalized margin
log P(y*)−log P(y^-)（y^-=最强竞争答案）。保持简单先行。

## 18-19. 实现注意：删的是 evidence block 不是字符串

E_i = 行为级 evidence block（一条 relation/多个 triples/多个 candidates/
sequence-extension evidence）。trajectory 数据结构至少：
action_id, entity_branch_id, fact_id, timestamp, parent_action_id,
retrieval_relation, retrieved_entities, retrieved_triples,
evidence_block_id, dependency_depth。删除必须删完整 block，不能字符串级
删 prompt 行。子图结构显式保存 parent/dependency（entity_branch/parent/
depth），Reverse Order 依据 entity branch → dependency depth → 同链内
execution order，不是全局 timestamp。

## 20. 可选增强：迭代收缩到不动点（局部最小 sufficient evidence graph）
第一版只做 single reverse pass（控成本）。

## 21-22. 与 Static LOO 的区别 + 四组对照实验

Static LOO: Δ_i^LOO = S(G)−S(G−E_i)（同一 G）。
RSCC: Δ_i^RSC = S(G^(k))−S(G^(k)−E_i)（G^(k) 动态收缩）。
Static LOO measures marginal necessity under the full redundant trajectory;
RSCC measures conditional necessity under progressively contracted downstream
context。

必须实现四种对照：**Static LOO / Forward Sequential / Random Sequential /
Reverse Sequential**。核心验证：Reverse 是否减少早期有效行为被 downstream
redundancy masking。

## 23-25. Claim 与命名

Claim：利用 agentic KG reasoning 的 dependency order 反序评价
behavior-induced evidence；行为可被替代时先从参考状态移除再评价更早行为，
逐步消除后续冗余对早期 credit 的遮蔽；多实体按实体子图独立反向收缩再
融合。三核心组件：Structure-aware + Reverse sequential + Dynamic
counterfactual state。命名：**RSCC (Reverse Sequential Counterfactual
Credit)**。
