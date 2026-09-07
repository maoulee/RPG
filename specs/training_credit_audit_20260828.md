# 信用分配机制审计 + 金标概率 teacher-forcing 拼接设计(2026-08-28)

输入:用户与 GPT 的两项训练工作方案(工作一 = 行为级信用分配;
工作二 = OPSD 在策略自蒸馏)。本文 ① 审计本仓库**现有**信用分配机制
的计算(seq_advantage.py + offline_vllm.py + seq_train_grpo.py 链路),
② 给出对文档计算公式的修正意见(基于本仓库已付出的标定代价),
③ 设计我们环境下的 teacher-forcing 金标概率拼接(对应用户问题:
"论文拼 `<think>Now there's enough information…</think><answer>GT</answer>`
再算 GT logprobs,我们要基于工具提交协议")。

---

## 一、现有信用分配机制:计算链全景

```
seq_rollout.py:253          reward = f1 + 0.1·format_ok + 0.1·efficient   (轨迹级标量,仅记录)
seq_advantage.py run_real
  :360-369   A_k = GroupNorm(F1)         同题 K 采样组内 z-score
  :237-255   extract_subgraphs           从轨迹 tool 消息正则抽 fact_id + triples 块(每 SG 截 15 行)
  :398-417   V0 / Vseq / Vloo / Valone / Vyhat   五类 (prefix, gold) 打分对
  offline_vllm.py:226-246  gold_logprob_batch
             prompt = "Question: {q}\n\nEvidence:\n{triples}" + "\n\nAnswer: " + gold
             = 裸 completion 文本(无 chat template / 无 system / 无 <think>)
             取 gold token 的 mean logprob
  :377-387   多实体金标逐实体打分,概率域 log-mean-exp 汇聚,实体截 8
  :37-101    alloc_advantages  两级守恒:info 块 vs answer;info 内 plan=ρ_plan(0.2),SG 组按
             r_i = max(L_i⁺, ρ·F_i⁺) 分摊(LOO 信用 L、forward 救援 F);Σa_t = A_k
  :166-206   build_turn_advantages  块优势按块内 assistant turn 数均分(turn 级守恒)
seq_train_grpo.py           per-turn advantage 加权 policy gradient(liger 标量 / 逐 token 两路径)
```

## 二、审计发现

### A. 已被本仓库自己的标定否决 / 修正过的部分(最重要的输入)

SESSION_MEMORY 记录的完整代价历史:

1. **v9 标定(08-15)**:`corr(pF, 实际 F1) ≈ 0.02-0.05`。exact-token
   teacher-forcing 看不见模糊匹配正确性(同义/部分列表)→ **pF 作为
   轨迹价值基线被否决**,答案轴退回组均值 F1。教训原文:"frozen-model
   exact-token TF is too strict a reader to serve as V̂"。
2. **distractor-competition 陷阱(v10.2,08-15)**:LOO 负值大量出现在
   gold-bearing SG 上 —— 引入竞争候选吸走概率质量 ≠ 信息伤害。
   惩罚已限制到 non-gold-bearing SG(真噪声),gold-bearing 落回
   effective/full-credit 分支。触发条件 = Δp<−0.005 ∪ LOO<−0.005
   (41% 多 SG 的 sg LOO 为负,LOO 比 Δp 多抓 285 个)。
3. **域不一致陷阱**:单 SG credits 是 log 域(vF−v0),多 SG 是概率域
   (pF−p_loo)—— 任何跨粒度的统一阈值都会错。
4. **终审:连续 7 轮训练 parity-or-worse**(v2/v7/v8/v12/v13/v14/
   v2h)。v2h 已用这套 IG 信用分配 + 新栈数据(2268 轨迹,2256 训练
   记录),r267 上 **0.7544→0.7281(−2.6pp)**。

**含义**:文档工作一的因果链(行为→ΔG→ΔI→优势→更新)在本仓库已
完整实现过一轮,没有产生学习增益。工作一若只重跑 GRPO,历史强烈
预示 parity。工作一的真正价值是给工作二供**行为标签**(教师轨迹
净化),这与文档 §4.3 的推荐顺序一致,应照办。

### B. 拼接格式与策略分布失配(现有实现的答案,用户问题的核心)

现状拼接是**裸 completion 文本**:

```
Question: {q}\n\nEvidence:\n{≤15行/SG的triples}\n\nAnswer: {gold}
```

- 不走 chat template、无 V21 系统提示、无多轮轨迹、无 `<think>`;
- 策略 rollout 时答题的真实分布是:chat 模板 + V21 全文系统提示 +
  完整多轮轨迹 + ANSWER_ANALYSIS→ANSWER_READY 两段协议,提交
  `tool: answer\nentities: X`;
- 因此 pF 测的不是"agent 在该证据下生成金标的概率",而是"9B 模型
  在从未见过的裸格式下续接金标的概率"。作为 V0/VF/LOO 之间的**相对**
  比较,格式偏置部分抵消(各变体同格式);但绝对阈值("pF<0.2 =
  shortcut")、跨问题比较、以及 corr(pF,F1) 都是格式敏感的 —— v9
  的 0.02-0.05 正是格式失配 + exact-token 严格性的综合读数。
- 结论:用户提议的"拼到真实会话前缀再算"方向正确,是对现有测量
  的**修错**,不是新增装饰。

### C. 与当前栈的具体漂移清单

| # | 位置 | 问题 |
|---|---|---|
| C1 | seq_advantage.py:142 | `SEQ_AGENTS_MD` 指向旧版 `SEQ_AGENTS.md`;线上是 `SEQ_AGENTS_V21.md`(且 live loop 不截断读入,RL 路径 sys_cap=8000 还在截)。训练/推理系统提示不一致 = 分布漂移 |
| C2 | seq_advantage.py:565 | `simulate()` 崩溃:`alloc_advantages` 已无 conn 参数、输出键已改版,SCENARIOS/docstring 仍是旧的连通性门控设计;且 tests/ 零覆盖(run_real/reallocate 调用签名正确,真实路径不受影响) |
| C3 | MAX_SG_LINES=15 / max_model_len=4096 | 按旧渲染调参。V3.4 单次 ack 可达 200 行(_TREE_LINE_BUDGET)+ checkpoint + candidates;15 行截断使 IG 看到的证据 ≪ 模型看到的证据 → pF 系统性偏低、"冗余"判定(移除后不变)在证据本被截断时会误判 |
| C4 | extract_subgraphs 首个 fact_id 去重 | 同 fid 多次检索(EXTEND/补采)只保留**第一次**渲染;V2.1 的 fact_evidence 是 UNION 语义(注册域 = 原始 ∪ 新检索),IG 抽取是 FIRST 语义,丢后续扩展 |
| C5 | build_turn_advantages | retrieve_relations turn 归给"下一个 retrieve_subgraph 的 sg"—— 一个 GTE 调用服务多个后续 SG 时信用归属是近似;V2.1 一个 retrieve_subgraph call 可带多 center、cover 多 fact,SG 粒度 ≠ 行为粒度 |
| C6 | _has_mid | gold 全为 mid 的 case 整条丢弃(v2h:12/15207 pairs;小但要知情) |
| C7 | _connected | object-membership 而非多跳可达(注释自认 codex P0-4);现在有更好来源:rollout 已记录 evidence_entities / pred_entities(structured fields,ctx 级全量含隐藏叶/展开) |

### D. 值得保留的资产

- 每实体打分 + 概率域 LME 汇聚(长度去偏,已标定);
- Vyhat(actor 实际答案支持度)= 文档"答案阶段独立优势"的基础;
- Valone forward 救援(France 案例);
- 两级守恒 + turn 级守恒的分配代数(Σa_t = A_k,span 对齐已验证);
- v10.2 行为分类矩阵 + gold-bearing 豁免 = 文档 §2.5 的类别学,
  且已修掉 distractor-competition 偏差。

## 三、对文档工作一计算公式的修正意见(基于上述代价)

1. `s_ret = log p(y*|q,P,R,G)` 绝对值不可用(corr 0.02-0.05)。
   必须:(a) 组内相对化;(b) 减记忆基线 p0;(c) in-format 测量
   (§四)。文档 α·s_ret+β·s_struct−γ·c 未定归一化 —— 建议直接继承
   v10.2 结构:轨迹分用 F1 组归一;pF/Δp 只做 within-trajectory
   分配权重与行为分类。
2. ΔI 的 distractor-competition 偏差:文档 §2.4/§2.5 没有这个豁免
   类别。需补:gold-bearing 行为的 LOO 负值记 0(不惩罚),只有
   non-gold-bearing 行为的负 ΔI 才进"有害"。
3. 行为级反事实的状态依赖:移除 call t 后,后续 call 的 center 可能
   来自该 call 的绑定 —— G^{-t} 有可执行性问题。两条可计算路线见 §四.6
   (冻结前缀手术 vs 环境重放)。
4. Plan 聚合(§2.6 选项 2)的"语义等价"判据不要退化为文本相似:
   用 plan 的 R* 需求集合 + sgN.fM.covers 结构签名。
5. 单/多行为粒度的分数域必须统一(概率域),阈值只在一域内定。

## 四、teacher-forcing 拼接设计(我们环境的答案提交协议版)

论文做法:每轮结束拼
`<think>Now there's enough information to answer</think><answer>GT</answer>`,
重进 policy LLM 算 GT token logprobs。
我们的答案不是裸 `<answer>`,而是两段协议:ANALYSIS(PROVISIONAL_FINAL)
→ harness 注入 `ANSWER_READY signal` → READY(`FINAL_BINDINGS:` +
`tool: answer` + `entities:`)。

### 4.1 推荐拼接(in-format READY continuation)

```
[截至此锚点的完整 messages —— 与 rollout 完全同源]
{"role": "tool",      "content": "ANSWER_READY signal"}     ← 逐字复制 harness 注入文本
{"role": "assistant", "content":
   "FINAL_BINDINGS:\n{var} = {gold}\n\ntool: answer\nentities: {gold}"}
```

只对 `entities: ` 之后的 gold token 计 logprob。

设计裁决与理由:

1. **同源序列化**:必须走 rollout 同一条序列化路径(build_messages
   已有;system 换 V21 全文不截断;reasoning 字段重建
   `<think>\n…\n</think>`,build_train_test 已验证 im_start span 对齐)。
   裸文本拼接(现状)是格式失配的根源。
2. **bridge 选 harness ack 而不是论文的 think 句**:两段协议天然有
   更好的桥 —— `ANSWER_READY signal` 是 harness 真实会注入的文本,
   测得的恰好是 p(agent 在被要求提交时交出金标 | 当前证据),正是
   s_ret 想要的条件,零虚构文本。消融位:①固定 think 桥;
   ②PROVISIONAL_FINAL 变体(测 ANALYSIS 期支持度,即证据能否支持
   "识别出"答案而不仅是"复述")。
3. **多实体金标**:逐实体分别拼 `entities: {e}` 打分再 LME 汇聚,
   避免列表顺序/分隔符的 token 噪声(继承 v9 的每实体语义)。
4. **gold 的 surface form 先过 normalize 通道**:exact-token 严格性的
   一半残留在拼写 —— 用 evidence_entities 中命中 gold 的规范形(若有)
   作为 teacher-force 字符串,无命中才用原始 gold。否则打的是
   "拼写概率"不是"答案概率"。
5. **归一化**:mean-per-token(v9 已证测量本就长度归一,残余 -0.2
   长度相关是多实体金标固有不可预测性);跨问题比较必须组内相对化
   + 减 V0。
6. **逐锚点打点 + LOO 的两条路线**:
   - **冻结前缀手术(便宜,工作一用)**:prefix 到 call t 的 ack 为止,
     把该 ack 的 `triples:` 块替换为手术版(去掉该 call 新增边/候选)
     或 `(empty)`,**后续轮次观测原样保留**(不重渲染)。测的是
     "后续推理链文本不变时,该 call 新增信息的边际贡献"—— 与文档
     G^{-t} 最接近的可计算近似,无状态依赖问题;作为分配权重足够。
   - **环境重放(贵,工作二教师净化用)**:perf 工作留下的 replay
     基础设施可复用;删除行为后重放,后续 ack 全部重渲染 —— 这才是
     文档 §3.6 要求的"可执行轨迹"验证。两阶段分工:工作一手术、
     工作二重放。
   - 锚点集合(非逐轮,控成本):V0 / plan ack 后 / 每个
     retrieve_subgraph ack 后 / 最终 —— 每轨迹 ~4-7 个锚点已覆盖
     行为分类所需。
7. **打分不经过 react loop**:纯构造 messages + 单次 forward,
   STAGE GATE / COMMIT / 拒绝阶梯不触发;但必须逐字复制 harness 会
   注入的 ack 文本(它们是条件分布的一部分,轨迹记录里都有原文)。
8. **工程载体**:继续 in-process OfflineVLLM(rollout 释放 GPU 后离线
   批),复用 gold_logprob_batch 接口、换拼接构造器 + max_model_len
   提到 ≥32k(V3.4 前缀 10-30k token)。逐 case 连续发射吃 prefix
   caching。粗算:267×3 轨迹 × ~5 锚点 × ~15k tok prefill ≈ 60M tok,
   prompt_logprobs 拖慢后 ~5k tok/s → **2-3 GPU·h**,可行。

### 4.2 与两项工作的落位

- **工作一先行,但产物是"行为评估器"而不是又一轮 GRPO**(7 轮
  parity 的历史):冻结前缀手术 + in-format TF + gold-bearing 豁免,
  输出必要/冗余/有害/局部有效未被使用 标签,人工抽验(文档 §7
  要求的审计集)。第一用途 = 工作二的教师净化,第二用途才是优势分配。
- **工作二是未做过的新杠杆**:稠密分布监督 vs 标量优势,与
  "49% 错误在 answer-selection"的诊断吻合 —— 方差稳定正是把概率
  质量搬到正确替代 token 上,标量优势结构上做不到。工程上教师
  top-k 分布可从 vLLM prompt_logprobs 拿;forward-KL 蒸馏需要 logits
  级 trainer(TRL GKD 类),比标量 trainer 重,是主要新增成本。
- 顺序按文档 §4.3:工作一的评估器冻结后开工作二。

## 六、2026-08-28 用户三项调整:裁决 + 审计 + 标定实验

### 6.1 调整一:打分源 = 思考 + 答案提交工具(裁决,已实现)

续接文本 = **已打开的 think 块内拼固定桥句,然后 FINAL_BINDINGS +
`tool: answer` 提交**。三个实测模板事实(标定脚本落地依据):

- Qwen3.5 chat template **丢弃** assistant 消息的 `reasoning` 字段 →
  rollout 服务器历史 = content only → 打分前缀同源 = 同样只用 content
  (训练路径 build_messages 重插 <think> 是梯度重建,另一回事);
- `add_generation_prompt=True` 的渲染以 `<|im_start|>assistant\n<think>\n`
  结尾 → 续接文本直接拼在 think 块内部(论文技巧的精确形状,零
  虚构、零模板重排);
- **抄写泄漏陷阱(冒烟实测)**:若对 `entities:` 行打分而
  FINAL_BINDINGS 行已先写出 gold,测的是"抄写两行前内容的保真度",
  概率恒 ≈1.0(冒烟全部 -0.0)。**打分段 = FINAL_BINDINGS 行里的首次
  gold 出现**;`entities:` 行保留作协议真实感,不打分。

修正后的冒烟数值已有合理分布:f1=0 记录 p0_info=−4.18 → pF_info=−2.69
(证据确实抬概率);f1=1 的记忆型问题恒 ≈0(参数记忆天花板,pF−p0
才是证据信号)。

### 6.2 调整二:轨迹间优势池化(审计)

用户方案:行为分类(轨迹内 LOO/结构信号得出)× 优势等级(组统计查表):

| 行为类 | 优势来源 |
|---|---|
| 有效(effective) | 组内最高轨迹优势 A_max |
| 有害(harmful) | 组内最低轨迹优势 A_min |
| 无效/冗余(redundant) | 组内中位数,或 ½·A_min |

这个"分类在轨迹内、等级在轨迹间"的因式分解是合理的:有效行为不受
宿主轨迹平庸拖累(直击 7 轮 parity 的"误伤"假说),且**不要求行为跨
轨迹同一性**(分类来自本轨迹 LOO,等级来自组分布,无需对齐)。

审计意见(4 点,均为旋钮非结构缺陷):

1. **冗余定价的极性耦合**:v10.2 用户裁决曾是"浪费统一定价
   (−λ_red 0.08),同类同价,不随其他行为浮动"。½·A_min 把冗余的
   代价耦合到组内最差轨迹的幅度:难组(A_max≈+0.5, A_min≈−1.7)下
   冗余 −0.85/turn ≫ 有效 +0.5 → 系统性压制检索。建议对称截断:
   redundant = −min(½|A_min|, |A_max|),或维持绝对 λ_red。
2. **正梯度质量失控**:守恒(Σa_t = A_k)被放弃后,一条 4-有效行为
   轨迹的正质量 = 4×A_max(旧方案 ≈1×A_k)。建议二选一:逐轨迹把
   Σa⁺ 重标到 ≤C·A_max(C≈1.5),或维持原样但配 advantage clip ±2
   + 降学习率。
3. **全败组的救援缺口**:组内全部失败(std≈0 → A≈0)时有效行为拿
   ≈0 —— 而"证据充分但答错"(轨迹四,32 个 gold-in-ckpt 案例)正
   落在这里。v10.2 已有对应机制(A<0 时 +min(Δp,0.15) measured-gain
   rescue),**新方案必须保留**:全败组中 pF−p0 达标的有效行为给
   绝对小_floor,而不是 0。
4. **全胜组无信号**:全部成功时 A≈0,一致好行为不被强化(GRPO 零
   方差组的固有局限)。可选:组内 F1 全 1 时有效行为给绝对小 ε;
   或接受。

### 6.3 调整三:模块级移除 + 全量加载(已实现)

LOO 粒度 = 一次 retrieve_subgraph 调用(模块)。手术规则与泄漏通道
(用户"前缀信息可能影响信用分配"的担忧,实测确认,前两条必须手术):

- **通道 1(致命,已手术)**:assistant 轮里的 checkpoint 声明行
  `[sgN.fM ✓] ?var = [v1|v2…]` 携带绑定值 —— 单绑定问题上**它就是
  答案本身**(标本 record 0 实证)。移除模块时剥离其后所有该 fact 的
  checkpoint 行。
- **通道 2(已手术)**:EVIDENCE COMMIT 消息的 `CANDIDATES (?var)`
  行复述绑定 → 剥离受影响 var 的行。
- **通道 3(残留,接受并测量)**:后续子图 ack 重渲染重叠边
  (2026-08-20/25 用户裁决:跨调用去重禁止,子图重渲染全部自己证据)
  → 移除的信息部分回流,ΔI 偏向 0,**误判冗余是主要失败模式**。
  以 re-mention rate 量化(冒烟标本 0.25-0.48!)。打分脚本按模块
  报告该比率,行为分类阈值时知情。
- 通道 4(轻微):后续 ack 的 candidate provenance 标签指向已移除
  子图(悬空引用)—— 留置。
- rr ack 候选关系列表保留(弱答案信号,且移除会破坏后续调用合法性)。
- **全量加载**:打分用完整 ack 文本 + V21 系统提示全文,无 15 行
  截断(修审计 C1/C3);IG 看到的证据 = 模型看到的证据。

### 6.4 问题一答复:vLLM 直接给概率(是)

- **常驻服务器路径(已验证可用)**:`POST /v1/completions`
  `{prompt, echo:true, logprobs:1, max_tokens:1, temperature:0}` →
  响应含逐位置 `prompt_logprobs`(实测含实际 token 的 logprob,即使
  不在 top-k)。**零卸载/重载** —— rollout 后直接对 :8000 打分。
  两个实测陷阱:`prompt_token_ids` 字段可能为 None → 客户端自己
  re-encode 对齐;chat template 由 CPU tokenizer 完成
  (apply_chat_template),不加载模型权重。
- **in-process 路径**:OfflineVLLM.logprob_batch(prompt_logprobs=0)
  同能力,IG 批量场景沿用。
- 打分负载 = 纯 prefill(prompt_logprobs),与生成解码不冲突,但与
  rollout 共享 GPU —— 大批量打分排在 rollout 间隙。

### 6.5 标定实验(informat_tf_calib.py,已完成,2026-08-28)

`scripts/informat_tf_calib.py`(one-off,已入 .gitignore):120 条分层
样本(perf/zero/mid 各 1/3)+ 40 条 LOO 手术,1517 个打分请求,11 分钟,
输出 `tmp/informat_tf_calib.json`。三臂:info(同源前缀 + think 桥 +
FINAL_BINDINGS/tool:answer 续接)/ bare_full(旧裸格式全量)/
bare_t15(旧格式 + 15 行截断,复刻 seq_advantage 现状)。

**结果 —— 阴性,格式不是瓶颈:**

| 判据 | info | bare_full | bare_t15 |
|---|---|---|---|
| corr(pF, F1) 全样本 | +0.251 | +0.276 | +0.325 |
| corr(pF, F1) hard(f1<1,n=80) | +0.139 | +0.136 | +0.184 |
| corr(pF−p0, F1) 全样本 | **−0.037** | +0.085 | +0.192 |
| corr(pF−p0, F1) hard | **+0.011** | +0.111 | +0.198 |

- **p0_info(记忆基线,无证据)是全样本最强单预测子:ρ=+0.299**
  —— F1 方差大头是题目难度/参数记忆,不是边际证据质量(hard 子集
  p0 掉到 +0.100 证实)。
- in-format 臂的**增益相关 ≈ 0**:同源前缀把"证据"和"这条 run 自己
  的噪声"(错误绑定声明、死胡同 center、后续调用的干扰)耦合进条件
  —— 测的是"模型能否在这次混乱 run 后答对",不是"证据是否充分"。
  裸文本臂恰好把 run 噪声剥掉了。
- LOO:gold-bearing 模块 LOO<0 率 info 38.3% vs bare 33.3%
  (distractor-competition 两格式都在,**豁免规则必须保留**);
  re-mention 泄漏均值 0.23(通道 3 的量化)。
- 相对 v9(0.02-0.05)的提升(→0.13-0.33)来自全量渲染 + per-entity
  + gold surface form 归一,不是格式。
- 次要:bare 臂 n=101 vs info 109(8 条超长 Evidence 拼接失败)。

**判定与落位(三次独立标定一致:v9 旧栈、本次三臂):**

1. log p(gold|·) 家族(任何格式)不升级为轨迹分 —— 轨迹优势继续用
   F1 组归一;TF 概率只做轨迹内行为分类(ΔI)+ 教师净化排序。
   行为分类处格式差异在噪声内(33% vs 38%),选便宜的一路。
2. 调整一的 in-format 续接机制**保留**(机制正确、span 验证、数值
   合理):它仍是 Vyhat(学生实际答案支持度)、充分性时间序列、
   工作二任何 in-context 测量的基座;只是不作为 s_ret 轨迹分。
3. 对工作二的定向含义:凡是"答案概率当分数/奖励"的蒸馏变体继承
   这个弱点;学生 token 位置上的分布 KL 监督不受影响(测量的不是
   金标后缀概率)。

### 6.6 补充测量(2026-08-28 晚,冗余判定的量化)

- **思考字段定论(模板源码)**:Qwen3.5 chat template 的历史渲染只认
  `reasoning_content` 键名;我们回传的是 `reasoning` → 名字不匹配被丢。
  且即使键名正确,模板仅对"最后一条 user 查询之后"的 assistant 轮渲染
  思考(ns.last_query_index),我们的多轮流每轮后跟 tool ack → 全部
  历史 assistant 轮被薄思考化(空 think 块,模板设计)。响应侧 reasoning
  返回与客户端捕获均正常。⇒ rollout 从未把思考放进历史,标定的
  content-only 前缀是同源的,结论不受影响。
- **概率天花板是冗余判定的主要敌人**:83% 记录 p0_info>0.6(模型无
  证据即 >60% 信心),仅 9% 记录 p0<0.2 有分类余量。修复选项:
  分类改 log-odds 域 / 低 p0 难例门控 / ΔI 除以 (1−p0)。
- **精确重复调用罕见**:801 记录 1736 次 sg 调用,3% 记录含完全重复
  (center,relations) 重调,1% 调用 → 重复对错位问题降优先级。
- 生产分类器默认走裸文本臂(更便宜、与 run 噪声解耦);in-format
  机制保留给 Vyhat/充分性时序/工作二。

### 6.7 工具轨迹臂 + 结构必要性门(2026-08-28 深夜,用户调整 #3 落地)

`scripts/tooltrace_calib.py`(one-off):打分上下文 = plan 调用块 + 工具
调用命令 + 真实工具 ack(assistant 思考/正文/checkpoint、COMMIT/harness
消息全部排除 —— 对话层泄漏通道构造性消失);裸式 `Answer:` 尾。同一样
本同种子,770 jobs / 175s(比 info 臂快 4 倍)。结构门 = 无向可达性
(解析 ack 实例行;剥离 note 散文与 node1/node2 模板行;`--rel-->`/
`--[rel]-->`/`→`/反向箭头全格式分割;括号 CVT 属性取值入节点;
`?var` 占位符剔除防虚假桥接)。

**结果:**

- 工具轨迹臂 corr(pF,F1)=+0.215,gain +0.043 —— 与 info(+0.251)/
  bare(+0.276) 同噪声带。第三次确认:**格式不是瓶颈**。
- **结构门:80 个 LOO 模块中 25% 结构必要(零 GPU);ΔI 判冗余的
  27 个模块里 6 个(22%)被结构门翻案为必要** —— 直接修复误判冗余
  失败模式;另有 13/80 全图即 gold 不可达(解析极限/gold 不在证据),
  门保持沉默回退 ΔI。交叉:bare 判冗余但结构必要的 7/65(11%)。
- 顺序判据(用户的"第 k 个子图加进来概率没动=冗余")与 LOO 一致率
  38/43(88%)—— 两者互为确认,不一致的 12% 标记 ambiguous。
- **跨格式 ΔI 相关性低**(trace vs bare +0.248,vs info +0.153)——
  概率分类本身有格式依赖噪声,单靠 ΔI 不可靠,联合判据必要。

**合成:三级行为分类器(裁决案)**

```
L0 结构门(免费,25% 覆盖):移除后 anchor→gold 无向可达断裂 ⟹ effective
L1 概率判据(工具轨迹上下文):ΔI=pF−p_loo>θ ⟹ effective;
   |ΔI|≤θ ⟹ redundant;ΔI<0 且 non-gold-bearing ⟹ harmful
L2 顺序确认:Δp_k 与 LOO 不一致(12%)⟹ ambiguous,降权/不进训练
豁免与门控:gold-bearing 永不 harmful;低 p0 难例门控或 log-odds 域
   (83% 记录 p0>0.6 的天花板)
```

## 七、待用户裁决(更新)
1. 拼接 bridge 用 harness `ANSWER_READY signal`(推荐)还是论文式
   think 句,还是两者做消融?
2. 工作一的 LOO 先做冻结前缀手术(推荐)还是直接上环境重放?
3. 是否同意"工作一不再单独训练 GRPO,产物仅供审计 + 工作二净化"?

---

### 6.8 跨轨迹结构判定 + 纯 LOO 稳定性(2026-08-28 夜,scripts/xtrack_struct_analysis.py)

- **纯 LOO 判定稳定性(警示的定量形态)**:同一模块的 LOO 判定
  (θ=±0.005,冗余/有效/有害)在 trace/bare/info 三种上下文间一致率仅
  **63-65%**(结构门开与否几乎不变——门覆盖的模块本来就两侧一致)。
  含义:LOO 可作核心判据,但携带 ~1/3 的上下文噪声。缓解:结构门定锚
  (25%)+ 死区加宽只训高置信 + 或三上下文多数投票。**顺序/信息增益
  判据可去**(与 LOO 一致率 88%,信息增量小——用户裁决方向正确)。
- **不连通轨迹的跨轨迹判定(Q1)**:机制走通——91% 的 case 有 ≥1 条
  连通轨迹可作参照;56 条不连通轨迹的 on-path 率区间
  **[16%(并集最短路径参照,下界).. 86%(连通轨迹任意模块边集,上界)]**
  —— 参照定义是设计杠杆:正确中间态 = 每条连通轨迹**沿自身路径**的
  模块序列(前缀模块不被绕过)。警示:不同 plan 结构下(梁启超式
  2-fact vs 3-fact 分解)结构重叠天然保守。解析器把少数答对的轨迹
  误标为不连通(gold 形态失配,WebQTrn-857 s0 f1=1.0)。
- **参照推理轨迹(Q3,工作二教师骨架)**:可行且已演示——连通+正确
  轨迹的必要模块链 = 净化骨架(标本:Ramble Elementary → Bill Clinton
  两模块链);进教师库前按文档 §3.6 走环境重放验证;同一参照也是 Q1
  不连通轨迹的判定标尺。多路径保留(文档 §3.7)= 每条连通轨迹一个
  骨架,不取全局唯一。

### 6.9 单独证据测试 + 黄金路径参照(2026-08-29 用户裁决,scripts/golden_path_analysis.py)

**裁决内容**:① LOO 移除的块单独与答案判定(旧 V_alone 语义,测内在
信息量);② 参照不取最短路径 —— 在连通轨迹中优先选 F1 正确、on-path
模块最多、off-path(冗余代理)最少的轨迹,其自身实现的 anchor→gold
路径 = 核心路径,不连通轨迹按覆盖几成计分。

**单独×边际 2×2(80 个 LOO 模块,alone_gain = p_alone − p0):**

| | alone⁺(内在有信息) | alone⁻ |
|---|---|---|
| **LOO⁺(边际有贡献)** | core 19 (24%) | bridge 3 (4%) |
| **LOO≈0** | **duplicate 43 (54%)** | noise 15 (19%) |

- duplicate 是主体:模块自己带金标信息,但移除后概率不动 —— 与
  重渲染回流(0.23)和平行检索一致;真噪声仅 19%;桥接模块稀少。
  训练定价:core→A_max,duplicate/noise→冗余价,bridge→有效
  (结构门也常覆盖)。
- **黄金路径**:243/267 case 可选(202 个 F1 正确);标本链
  Brad Stevens→Boston Celtics(2 模块,2 跳)。
- **不连通轨迹覆盖双峰**:n=57,mean 0.26-0.28,median 0.00,
  ≥50% 覆盖 39-42%,max 1.00 —— 判定很锐:要么同轨(可部分挽回,
  模块级 partial credit = 命中核心路径的模块),要么一开始就跑偏
  (58%,零命中)。该参照同时是工作二的教师骨架。

### 6.10 结构增量消歧 + 分叉判定 + 教师库 + 信用干跑(2026-08-29,scripts/credit_dryrun.py)

四项裁决落地(离线,全模块 1735 个):

1. **结构增量消歧 duplicate**:模块边集相对轨迹先前累积边集的
   new_frac —— 首次呈现且在路径上 = eff_first(45%);第二次出现 =
   red_repeat(8%)。加上 off-path 新结构 = red_unused(31%,最大冗余桶)。
2. **分叉判定**:不连通轨迹对黄金路径 —— 命中前缀 = eff_golden_partial
   (25 模块);分叉模块 = harm_divergence(9);分叉后 = red_after_div(53);
   零命中 = harm_div0(34,plan/首决策责任)。无黄金参照 = no_ref(9%)。
3. **教师库**:243/267 case,plan+保留模块的 (call,result) 纯工具轨迹,
   平均保留 1.2/3.2 模块。**警示:净化激进** —— 1 跳问题的路径只含
   1 模块,被丢模块可能携带答案选择所需的候选上下文;教师构造时
   保留阈值应放宽(on-path ∪ gold-bearing),且必须过环境重放验证。
4. **信用干跑(池化:eff→A_max,harm→A_min,red→clamped ½A_min)**:
   类别均值 eff +0.40~+0.59 / harm −0.61~−0.79 / red −0.26~−0.30 ——
   排序形状正是目标。**最大发现:123/267(46%)case 为全胜组
   (A≈0)→ 有效模块拿到的 A_max=0,零正信号**;all-fail 17 组同理。
   ⇒ 训练批次必须选难例组(错误 cohort/方差组),或给全胜组有效行为
   绝对 ε floor。rescue 效应 9%(72/808 有效模块住在低于中位 A 的
   轨迹里,现在照样拿 A_max)。数据 tmp/credit_dryrun.json。

### 6.11 约束模块找回(2026-08-29 用户抓漏,scripts/constraint_recover.py)

用户判断:1.2 模块的平均保留把**约束检索模块**扔了 —— 答案早命中、
后续检索判别条件的合取型问题。两个信号验证:

- **LOO 验证(用户判据:移除后概率下降)**:off-path 模块中 7/34
  (21%)是 LOO⁺ —— 结构路径漏掉、但移除确实降低金标概率的约束证据。
  (对照:on-path LOO≈0 占 39% —— 回流压缩,与前期一致。)
- **plan 事实归属(协议信号,零 GPU)**:red_unused 且绑定变量 ≠
  answer var 的模块 = 约束模块,找回 **223 个**(标本:Winged Monkey
  →?film 而答案变量 ?actor;Belgium→?time_zone 而答案 ?location)。

**教师库新保留规则**:kept = eff_first ∪ (red_unused ∧ (fact_var≠
answer_var ∨ gold-bearing ∨ LOO⁺))。保留均值 1.07→1.38(729 条轨迹),
且 223 个模块在信用侧从冗余价移到 A_max(约束验证是有效行为)。
数据 tmp/constraint_recover.json。

### 6.12 统一综合判定器(2026-08-29 用户裁决:多指标综合,不单测,scripts/unified_classifier.py)

**投票表(权重 = 本会话标定的可靠性)**:

| 指示 | 权重 | 依据 |
|---|---|---|
| 结构必要性门 | +1.0 | 确定性;翻案 22% ΔI-冗余 |
| 首载体(on-path ∧ new_frac≥.3) | +0.8 | 漏 21% 约束 → 有豁免通道 |
| 约束(绑定 var ≠ answer var) | +0.8 | 223 个找回 |
| LOO⁺(dI>θ) | +0.5 | 判定跨格式一致率仅 63-65% |
| 单独信息⁺(alone_gain>θ) | +0.4 | duplicate 偏多(54%) |
| 重复呈现(new_frac<.3) | −0.6 | 第二次出现 |
| 未使用探索(off-path ∧ 新 ∧ 非约束) | −0.4 | 21% 是 LOO⁺ 约束 → 弱负 |
| 黄金路径分叉/零命中 | −0.8 | 跨轨迹结构判定 |
| LOO⁻(dI<−θ 且 ¬gold-bearing) | −0.5 | gold-bearing = 有害否决 |
| gold-bearing | 否决权 | 33-38% LOO<0 是候选竞争 |

类判定:score≥+0.5→有效;≤−0.5(未被否决)→有害;中间→冗余;
**弃权**:总票质量<0.5(单一弱指示不许定案——用户裁决)或
|score|/总质量<0.7(强冲突)。

**结果(1735 模块)**:有效 59% / 冗余 7% / 有害 4% / **弃权 30%**
(517 个——主要是只有单条 unused 信号的模块,定义为"需概率层确认"
队列:补 LOO+单独打分后可解,仍冲突则不进训练)。置信度均值 0.86,
86% 模块 conf≥0.9。

**留一验证的结构性解读**:与 LOO 判定的原始一致率 32%,但混淆矩阵
显示分歧集中在 融合=有效 × LOO=冗余(28/50)——恰是结构门已证明
LOO 错误(重渲染回流+概率天花板压缩 ΔI→0)的格子。即:确定性层与
噪声层的分歧正好发生在噪声层已知失效的地方;结构票赢平局,LOO 只
在结构弃权处补位。判定顺序:结构融合定案 → 弃权者进概率层 →
仍冲突 → 丢弃。数据 tmp/unified_class.json。

---

## 八、设计哲学:模块有效性的统一理论(2026-08-29 用户裁决)

### 8.1 本体论:有效性是什么

一个模块 = 一次带可执行后果的检索行为,后果 = ΔG(新增证据子图)。
"有效性"不可直接观测;可观测的是它在**四个正交轴上的投影**:

| 轴 | 回答的问题 | 指示 | 已标定的失效模式 |
|---|---|---|---|
| 反事实轴 | 移除它,答案支持会塌吗(必要性) | LOO、结构必要性门 | 回流 0.23;天花板 83% 记录 p0>0.6;候选竞争 33-38% |
| 信息轴 | 它自己带答案相关信息吗(内容充分性) | 单独测试、gold-bearing | informative ≠ needed(duplicate 54%) |
| 组合轴 | 它在 anchor→gold 组合里承重吗 | 路径归属、结构增量、黄金路径 | 约束盲区(off-path 的 21% 是约束) |
| 意图轴 | plan 给它分配了什么角色 | 事实归属、绑定变量≠答案变量 | 依赖模型自 declare,误declare 传染 |

**核心命题**:任何单轴都只是含噪投影;轴间失效模式机制不同且互不
相关 —— 这就是融合的方差下降来源,也是"不单测"裁决的理论根据。

### 8.2 认识论:融合的规则

1. **权重 = 标定可靠性**(gate 1.0 > 结构/意图 0.8 > LOO 0.5 > 单独
   0.4);确定性轴赢平局,但其盲区(约束)恰好由意图轴覆盖 —— 轴间
   互补是设计出来的,不是碰巧。
2. **机制性偏差用否决权,不用软融合**:gold-bearing 的 LOO<0 是竞争
   效应(系统性),加权平均消不掉,只能否决。
3. **弃权是一等公民**:单一弱指示(票质量<0.5)或强冲突(|score|/
   质量<0.7)→ 不定案、不进训练。**训练信号的干净性 > 覆盖率**。

### 8.3 三条操作律

- **定案律**:综合判定,证据不足不定案。
- **参照律**:轨迹内不可判定的(不连通),由同题池的结构共识
  (黄金路径)判定 —— 群体是个体的参照系。
- **解耦律**:分类(行为是什么)与等级(值多少分)正交 —— 等级查
  组统计表(有效→A_max/有害→A_min/冗余→½A_min),不改变分类本身。

### 8.4 对照需求的自审

| 需求(本会话逐条提出) | 机制 | 状态 |
|---|---|---|
| 好行为不被差轨迹拖累 | 池化 A_max(rescue 9%) | ✓ |
| 约束检索不被净化扔掉 | 意图轴(223 找回,LOO 21% 验证) | ✓ |
| 重复行为受罚 | 结构增量(第二次出现) | ✓ |
| 有害可定位 | 黄金路径分叉点 | ✓ |
| 不训噪声 | 弃权(30% 待概率层) | ✓ |
| 教师净化 | 保留规则 on-path∪约束 | ✓(待重放) |
| 答案选择层(49% 错误) | **不在模块分类器管辖** —— ANALYSIS/READY 轮的信用仍走答案轴 F1,哲学边界须明示 | 边界 |
| 无参照的 9% | no_ref,不可判 | 已知缺口 |
| 意图轴的误 declare | 未交叉校验(covers 结构可校) | 待办 |
| 教师库可执行性 | 环境重放验证 | 待办 |

### 8.5 可证伪预言(下阶段验收判据)

哲学必须可检验。若融合判定正确,则:
1. 高置信(conf≥0.9)有效模块的训练增益 > 低置信者;
2. 弃权队列(单 unused 信号为主)补概率层后应大量落冗余;
3. 约束模块计 A_max 后,**合取型问题**(梁启超类)的组内方差应下降;
4. 若用单轴替换融合(消融),误伤率(rescue 计数)与弃权纯净度应变差。

### 6.13 轨迹-信号一致性人工审计(2026-08-29,scripts/specimen_audit.py)

9 标本人工判读(每类抽样,读问题/plan/调用/ack/后续动作/答案):

- **eff 3/3 正确**:两跳链首载体、约束中间跳(绑 ?composer/?tour 而答案
  是 ?guitar/?instrument)均与轨迹故事一致。
- **harm 2/2 正确**:标本 6 = s1 在第二跳选了 appointments/inauguration
  关系(丢了 FDR 的 from-date)→ 候选集错 → 全错 —— 正是"第二跳偏离";
  标本 7 = 未声明绑定就调用的 error turn(harm 语义成立:耗轮+程序错)。
- **red/repeat 2/2 均翻案或存疑 → 挖出两个解析失效模式**:
  ① 显示经济(V3.4):`?x/?y` 占位符尾、`[19 records]` 折叠、多头行
  产生空/假团边 → 判别模块(日期判别)误判 repeat。**已修**:结构图
  补 candidates + checkpoint 绑定值两通道,占位符尾行跳过。修复后
  该标本正确翻案为 eff/constraint;整体分布 eff 59→68%、弃权 30→25%、
  置信均值 0.75→0.94。
  ② **枢纽膨胀(未修,已定方案)**:锚点模块走查邻域爆炸(标本:
  图像节点模块 1307 边)把下游语义模块的边全部包含 → new_frac 假低。
  修复:增量比较改**行级三元组**(同 center+同关系+同行才算重复),
  并加 checkpoint 闭合状态通道(`[fid ✗ empty]` = 零产出 → 冗余)。

### 九、训练端优化审计(2026-08-29)

代码事实(train_offline_grpo.py:326 OfflineGRPOTrainer + seq_train_grpo.py):
- 损失 = −E[A·mean_completion logπ](scalar liger)或
  −Σ(a_t·logp_t)/Σmask(per-turn 分块路径);
- **无重要性比率**(liger 调用不传 old_per_token_logps)、**无裁剪**、
  **无 KL**(beta=0, use_ref_model=False);默认 epochs=1, LoRA r64。

**判定:θ=θ_old 首过时与 GRPO 一步梯度严格等价**(组归一基线同 GRPO
的 Â 构造;比率=1 时裁剪不活跃)。因此"训练无提升"不是优化器 bug
——7 轮 parity 的主因在信号侧(统一轨迹优势 + pF 组件噪声),本次
会话已重造。与真 GRPO 的三个偏差,按风险排序:
1. **负优势无刹车**:A<0 无比率裁剪地压低模型自己 token 的 logprob,
   接近 unlikelihood;池化后 harm 低至 A_min≈−1.4,是失稳首选位置。
   GRPO 会在 ρ<1−ε 处停手。
2. **epoch>1 / 迭代轮次 = 静默 off-policy**:无比率修正的加权 MLE。
   规则:严格 epochs=1;迭代轮次(--init-adapter)必须重采 rollout。
3. **per-turn 路径的分母是全 batch assistant token 数** + 守恒破坏后
   样本级梯度量 ∝ n_eff×A_max → 装 Σa⁺ 封顶(≈1.5×A_max)。
可选升级:rollout 后用 echo+logprobs 机器补 π_old 逐 token logprobs
入库,per-turn 分块路径加 ρ-clip —— 离线精确 GRPO,零新基建。

### 6.14 展示语义裁决(2026-08-29 用户:只判定实际展示的内容)

**判定基准 = 模型实际看到的轨迹文本**:显示的行、显示的
`candidates:` 列表、模型自己声明的 checkpoint;隐藏叶、裁剪内容、
底层全图、ctx 累积三元组一律不进结构判定。落地三件事:

1. **行级增量**(parse_rows):展示行为增量单位,计数后缀剥离
   ("17 instances" 与 "19 instances" 重渲染视为同行);成对团边增量
   废弃(枢纽膨胀根因)。
2. **闭合状态通道**:`[fid ✗ empty]`(模型自 declare、harness 认可)
   = 零产出 → closure 票(−0.6)。
3. **gold 展示过滤**:gold surface form 必须在展示文本中出现过。

**数字变化(三轮)**:边级→+通道→行级展示:
eff 59→68→**65%**,red 7→5→**4%**,harm 4→3→**4%**,
abstain 30→25→**27%**,conf .75→.94→**.92**。

**标本复核**:日期判别 → eff/constraint ✓(稳定);Kirk 补救重探 →
red/closure+repeat ✓(✗ empty 佐证);Lautner 电影 → abstain/unused
(枢纽膨胀消除;@5 的展示 candidates 已含金标 → 1 跳路径成立,@9 的
完整重呈现按展示语义计 unused,交概率层定夺——裁决的自洽后果)。

**训练批次前置项更新**:① 弃权 27% 补概率层;② 全胜组裁决;③
π_old logprobs + ρ-clip;④ 教师库重放验证。

### 6.15 弃权队列的消解(2026-08-29 用户再框架:增益有无是二分的,弃权≠判定)

**用户判断证实**:弃权不是行为类别,是"未测量"队列。成因:466 个弃权
中 309(66%)是"单 unused 弱信号、概率层未测",59 无参照,~97 弱冲突。

**补测**(scripts/abstain_resolve.py,1816 个去重打分请求,8.5 分钟):
- 修复一个静默 bug:gold 与前导空格合并为单 BPE token(" Belize")时
  字符切点坍缩 → span 为空 → 110 个 dI=None。score() 改 offset-mapping
  span → **不可解归零**。
- 队列裁决:eff 218(47%)/ harm 22 / red 11;剩 215 个融合仍弃权,
  拆解 = noise 44 + 近平局 66 + **competition-corrupted 105**。

**标本(WebQTrn-2209,Brad Stevens)——纯概率裁决的陷阱实证**:
mod@10(凯尔特人→17 个总冠军,checkpoint 含全部金标)dI=−0.064、
alone=+0.589。纯二分规则(有增益=有效,无/负=冗余/有害)判它有害;
真相:信息经 mod@15 重渲染回流 + 移除带走 17 个竞争年份压低概率。
**队列里 32%(147 个)会被纯概率规则误判有害** —— 否决权
(gold-bearing/alone⁺)正是挡这个的。

**终态分类(1735 模块,弃权归零)**:

| 类 | 数量 | 定价 |
|---|---|---|
| eff | 1350(78%) | A_max |
| red(noise+近平局) | 197(11%) | ½A_min |
| **untrainable(corrupted)** | 105(6%) | 不进训练(两轴不可调和) |
| harm | 86(5%) | A_min |

6% 的 corrupted 残余是诚实的:回流+竞争把概率读数污染到无法裁决,
任何强行定价都是错标 —— 哲学的"干净性 > 覆盖率"在此收口。

### 6.16 竞争污染的三重成因与消解(2026-08-29,scripts/pair_loo.py)

用户假设:竞争污染 = **成对联合贡献**(两模块各有新增结构,单个不
胜出,合在一起胜出)。成对 LOO 检验(移除 m+最大行重叠搭档 j):

1. **joint_eff 10/27(37%,可测对)——假设证实**:标本 WebQTrn-567
   m@16:dI=−0.055(单独移除反升)、dI_pair=**+0.369**(成对移除塌)
   → 联合有效。边际 LOO 对互补贡献结构性失明,成对检验补上。
2. **记忆天花板(Brad Stevens 家族)**:连成对移除都不掉(dI_pair
   −0.022)——题目被参数记忆覆盖(p0 高),概率轴在这类问题上
   **测不出"需要"**。消解:轨迹内承载规则 —— 模块 checkpoint 声明
   ≥1 金标 ∧ 轨迹 f1>0.5(成功的 run 确实用它承载了答案)→ eff。
   哲学收口:概率轴测"给定记忆是否需要",轨迹轴测"成功 run 是否
   使用";记忆型问题上二者分歧时,**使用胜出**(强化成功 run 的行为)。
3. 78 个无行重叠搭档(污染源不是重渲染兄弟)——被承载规则覆盖。

**105 → joint 10 + carrier 64 + 真不可裁 31。终态:eff 1424(82%)/
red 197(11%)/harm 86(5%)/不训 31(1.8%)。**

### 6.17 用户人工审计 #1 的四条裁决落地(2026-08-29)

标本 WebQTrn-2209 s0(Brad Stevens)人工审计产出四条机制级裁决:

1. **根基:环境反馈内容是核心**——工具调用是设想,模型声明(含
   checkpoint)可能有偏差;增量/重叠/信息判定全部以 ack 内容为基准。
2. **绑定所有权**:checkpoint 绑定属于**首次产出该事实的检索**;
   重声明不产生新边(否则重声明制造假 1 跳捷径,把真正的承载者挤出
   路径——本标本实测:@16 重声明曾让 @15 抢走 sg2 的 brad→finals 边,
   on_mod 只剩 {15},@10 被判 unused)。
3. **必要性门全模块化**:移除后 anchor→gold 无向可达断裂 ⟹ 有效,
   不再限于 GPU 打分子集。本标本 @10 必要性命中(票 necessary+first)。
4. **信息级增量**:增量单位 = 逐对链接 (h, 关系|属性键, t) ——箭头链
   笛卡尔拆平 + 括号属性抽成 (属主,键,值) 对,使 "X --team--> m
   [team=Boston]" 与 "X --team--> m --team--> Boston" 归一为同一信息。
   本标本 @15 对 @5 的纯重呈现(关系名消歧后缀/链形/分组差异掩盖)
   正确落入 repeat → 冗余。
5. 附带语义修正:**纯冗余票不得判有害**(harm 需要有害意图票
   div/loo_neg;单条 repeat −0.6 越过 harm 阈值曾把冗余误判有害)
   ——有害类 65→21,冗余 72→109。

**标本终态:@5 eff / @10 eff(necessary) / @15 red(repeat)= 人工裁决
逐模块一致。** 整体:eff 67% / red 6% / harm 1% / 弃权 26%(下游
消解链条重跑中)。rr+sg 同判一个完整检索单元:分类以 sg ack 为单元,
信用映射时 rr turn 继承同单元类别(build_turn_advantages 已然)。

**下游链条重跑后的终态(裁决落地后)**:队列消解 eff 216 中,
竞争污染 105 → joint 8 + carrier 66 + 真不可裁 31;非污染弃权 111 →
noise/近平局 → 冗余。**终态:eff 1430(82%)/ red 231(13%)/
harm 43(2.5%)/ 不可训 31(1.8%)。** 与 §6.16 相比:有害类大幅收缩
(86→43,纯冗余误判被语义修正挡掉),冗余扩张(109→231)。

### 6.18 增量来源改判:环境真实 ΔG(2026-08-29 用户裁决五)

**裁决**:信息级增量不解析渲染回复,而是取环境实际返回的图三元组
——不受显示层(折叠/消歧/分组)与答案文本影响。

**实现**(scripts/replay_delta_g.py):重放 801 记录全部 1736 次 sg
调用(plan 经 _parse_flat + dispatch 重放以注册锚点,checkpoint 经
_update_var_bindings 合并,跨记录同轮并发走 walk 池),逐调用快照
ctx.accumulated_triples 差分。覆盖 **1704/1736(98%)**;键 = ack 下标
(初版 call/ack 错位已修)。ΔG 本身即环境级增量(累积层跨调用去重内
含):**|ΔG|≤3 ⟺ repeat,零解析机械判据**(文本解析仅作 2% 回退)。

**标本 #1 环境级证实**:@5 ΔG=18(eff)/ @10 ΔG=51(eff+necessary)/
**@15 ΔG=3 → repeat**——重走查对累积图只新增 3 条三元组,环境自己
证明"无额外信息"(用户裁决的直接验证)。

**整体变化**:eff 67→62% / **red 6→15%** / harm 1% / abstain 25→21%。
冗余大幅显形:显示层让重呈现看起来"新"(渲染差异),环境的跨调用
去重按图内容判重——文本层系统性低估冗余。

### 6.19 用户全类别审计 #2(2026-08-29)——六条发现

**判定修正(已落地)**:
- **#16 harm→eff**:链必要性票(chain,权重 1.0)——后续调用的 center
  由本模块 ΔG 引入 ⟹ 结构不可分(标本:@5 产出 Mosque,是下一调用的
  起点;移除则连通性崩塌)。整体:harm 23→19,eff→65%。
- **#17 不可裁→冗余**:约束失配的小检索(|ΔG|≤10 ∧ 竞争污染)归冗余
  ——证据粒度失配(日期非 1 月 1 日)不是模型行为错误。
- **#5 eff 确认**(约束真有效,失败在答案层)。

**工作流缺口(存档待办,prompt/harness 轨)**:CVT 绑定被剥离后,
模型未重新声明 checkpoint 就直接重试 rr(死循环入口)——§7.5 指引
没有教"如何用括号属性值重声明"的具体操作。

**渲染缺陷(存档待办,V3.4 轨)**:① 候选列表未按关系归类(平铺 60
个实体,模型无法按关系语义过滤——layer_evidence 的 per-relation
分组已有实验实现);② 两跳行缺顶层关系头(如 gnis_feature_id 的
模式路径分组缺失,模型无法评估);③ 每关系 top-3 模式截断过紧,
超出的关系模式信息丢失。

### 6.20 用户审计 #3:结构层全面切环境图(2026-08-29 深夜)

**裁决**:结构连通性/必要性/路径归属必须基于**实际连接的图谱信息**
(重放 ΔG 的累积并集),不再用 ack 文本解析;模型声明(含 ✗empty)
服从环境。落地五项:

1. **环境图结构层**:own-path/necessity/golden-path/coverage 全部改为
   累积 ΔG 无向图,边归属 = 首次引入模块(_env_path/_env_onpath_owners)。
2. **全最短路归属并集**:边在任意最短路上即计入 on_mod —— 单条 BFS
   会被空洞枢纽路线劫持(标本:tupac—USA—juice 挤掉 tupac—表演记录
   —juice)。距离双向 BFS 判据 d_s[u]+1+d_t[v]=D。
3. **闭合票服从环境**:[fid ✗ empty] 仅当 |ΔG|≤3 才计(声明可能有偏,
   #17@9 声明空但 ΔG=76 → 不计)。
4. **约束票需产出被使用**(chain 或后续引用)——未被使用的约束追逐
   (#17@15 日期非 1 月 1 日的失配检索)归冗余。
5. **零信号 = 冗余**(tot=0 → red,不再弃权)。

**标本验证(与人工裁决逐模块一致)**:located-ID @7 eff/@11 eff/
@14 red;#17 @5 eff/@9 eff/@15 red。整体:eff 60%/red 26%/abstain 13%/
harm 1%。撤回 §6.19 的"top-3 截断过紧"存档项(展示本允许超过 3,
观察有误)。

### 6.21 起点+关系覆盖信号(2026-08-29 深夜2,用户裁决六)

用户澄清:最短路径 = **整个累积增量图**上的多跳 BFS(表演记录被挤
正是全图 BFS 让空洞枢纽赢——全最短路并集已修);并提出更简单的
补充信号:**(起点, 所用关系) 覆盖** —— 模块的 center+relations 对
黄金路线某步的 (起点, 关系集) 高概率覆盖(center 命中 ∧ 关系覆盖
≥0.5)且核心关系完整 ⟹ 有效。调用参数经重放执行 = 环境背书。

落地为 sig 票(+0.8)。分布:eff 64%/red 24%/abstain 11%/harm 1%。
核心机制维持:实际图结构变量为中心,解析文本仅回退。

### 6.22 三类闭合(2026-08-29 终)

分类器层的弃权是**消解前队列**(组成:132 单 unused 未测概率 + 47 真
近平局 + 8 单 alone)。链条(abstain_resolve → pair_loo → carrier/小ΔG)
重跑后:**终态 = eff 1247(72%)/ red 457(26%)/ harm 21(1.2%)/
untrainable 10(0.6%)**,弃权归零。10 个残余为竞争污染(成对不塌、
非承载、|ΔG|>10),依"干净性>覆盖率"裁决保持不训。

### 6.23 用户审计 #4 的渲染/harness 发现(2026-08-29,存档渲染轨)

标本 WebQTrn-25_892f s1(Taylor Lautner tvrage 家族):
1. **多中心行截断**:seq_tools.py:1435 —— 模式路径行的 center 列表
   硬编码只显示前 4 个 + "…(+N centers)";模型传 ?movie(展开 20 部
   电影)后看不到自己的 center 全集,无法评估覆盖。
2. **PLAN EXTEND 拒绝后无变量注册指引**:模型扩展用 ?var 做 anchor
   被拒("D1 not in original contract"),但第一条 fact 未注册变量的
   情况下,拒绝信息没告诉它先注册/绑定 anchor 变量。
3. **模式路径以 film 为末跳的分组不一致**:同关系末跳的路径超过 3
   条未按关系分组收敛(与 6.19 ②③ 同族的分组一致性问题)。

### 6.24 渲染重构规格(用户裁决七,2026-08-29 夜 — 下一阶段工作纲领)

**渲染结构(两部分)**:
1. 最上层 = **工具检索请求的关系**(调用 relations: 列表)——每个请求
   关系一个顶层组;
2. 组内 = 关系模式,按**路径长度升序**;该组聚合所有命中该关系的
   路径(含以其为末跳/中间跳的)。

**中间变量替代机制修复**:多 center 头应显示 fact 声明的 ?var
(seq_tools.py:1432 `if var_label` 的来源目前仅取调用参数里的 ?var;
模型传字面 center 列表时失效 → 回退用 checkpoint 声明的 fact 变量;
center 全量不截断 —— :1435 的 heads[:4] 撤销,变量标签优先)。

**walk 层疑问(存档待查)**:`--language--> English <--primary_language--
Mei Mei --genre--> Drama` 为 3 跳且中间无 CVT 节点仍被命中 —— 模式链
枚举是否未按 CVT 门控。

**判定修正(已落地)**:零信号 ∧ |ΔG|>10 → 不落冗余,交概率层
(用户标本:约束检查模块 |ΔG|=85 有真实信息增益,不该 red)。
渲染/harness 轨累积 6 条(§6.23)+ 本渲染规格。

### 6.25 增量语义终裁(用户裁决八,2026-08-29):路径相关增量

**ΔG 只看与答案路径相关的部分**:模块增量 = 其 ΔG 边与
anchor→gold 全最短路边集的交集(起点→终点的信息增益);
**触及金标邻域的边 = 最强正信号**(gold_adj 票 +0.8,命中 1268 模块);
原始体量(枢纽膨胀的贪婪走查)不参与判定。sig 票需以
路径相关新信息为前提(重复执行同签名不算)。冗余判据随之精化:
dg_rel≤1 ⟺ repeat。零信号护栏同步改用 dg_rel。

**链条后终态:eff 1420(82%)/ red 259(15%)/ abstain 35(2%,概率
队列)/ harm 21(1%)。** 标本:布拉德 @5 eff/@10 eff(gold_adj)/
@15 red ✓。

### 6.26 判定器 v2 设计定稿(2026-08-30,用户裁决九至十一)

**裁决九·判定单元 = 事实块**:单个事实(f1/f2)可能需要一个关系检索
+ 多个子图检索——以**事实为核心**分组 (rr + sg*) 为一个判定块;
rr 与 sg 是同一动作的两半,失败一起归因(rr 关系选择错误 = 块的
关键决策错误)。sig 票的动作签名(center+relations)天然跨 rr+sg。

**裁决十·打分机制 = 结构层重放**:概率层不重放完整对话,用
**问题 + plan + 工具调用(± 移除)** 的结构轨迹做 teacher-forcing
(即已验证的 tool-trace 臂,快 4 倍且与 run 噪声解耦)。

**裁决十一·判定逻辑(两级增量 + 概率反馈)**:
```
结构增量(原始 ΔG)≠ 0   = 基础前提(证据存在)
路径相关增量 == 0       = 重复 ⟹ 冗余(概率/LOO 读数是重复的伪影,只作次级)
断链 / 链必要性          ⟹ 有效且必须(结构独立定案)
连通后的继续探索:
    基础(ΔG≠0) ∧ 移除后答案概率下降 ⟹ 有效(结构=证据存在,概率=是否被需要)
    基础(ΔG≠0) ∧ 移除后概率不降     ⟹ 冗余(探索了无用信息,路径已有)
有害 = 块的关键决策错误(rr 关系选择分叉/黄金路径分叉)∨ 移除后概率升高
      (金标否决仍挡竞争伪影)
```
即:**结构回答"有没有证据",概率回答"证据是否被需要"**;
重复由路径相关增量直接判定,不劳概率。

**实现要点(v2 重构)**:按 fact 分组模块(fact 归属已由 R2 所有权/
checkpoint 提供)→ 块级判定走布尔格(audit §规范化程序)→ 概率层
用 tool-trace 结构重放打分 → 全链条干净重跑 + 标本回归
(Brad Stevens 三模块、#16、#17、located-ID)。

### 6.27 判定器 v2 落地与终态(2026-08-30)

scripts/classifier_v2.py:事实块分组(rr+sg* 按事实合并,1631 块)+
裁决十一布尔规则 + 块级概率打分(结构层重放,3357 请求/1002s)。
**判定修正**:div("非最短路而他块在路")降级为标记不作判据——它把
合法的连通后探索打成有害(21%);有害只由"移除后概率升高 ∧ 非金标"
决定,与黄金路径分叉(v1 语义)留待跨轨迹参照接入后合并。

**v2 终态:eff 1005(62%)/ red 594(36%)/ harm 32(2%)**;
div=True 的 477 块去问概率后:red 329 / eff 130 / harm 18 —— 连通后
探索的主体是冗余,少数有效(约束验证),极少有害。
审计包 tmp/v2_review.md;数据 tmp/classifier_v2.json。
提速结论:瓶颈=prefill 计算(~15-25k tok/s),非调度;批量端点
(prompt 数组)已验证可用;后续杠杆=单金标+打分截断(~4-5min/轮)。

### 6.28 审计包全细节版 + 批量端点(2026-08-30)

- **审计包修复**(scripts/v2_dump.py → tmp/v2_review.md):每块含 rr+sg
  调用与返回头 8 行、ΔG 实际新增边(前 10 条)、全部读数——用户标本
  (Filaret)可审:sg1.f1 = 领导记录→乌克兰(nec),sg2.f1 = 语言集
  (ΔG=32 含金标);错答在官方 vs 主要语言的判别层。
- **批量端点接入**(classifier_v2):prompt 数组 ×16/请求 ×4 并发,
  客户端 offset-mapping 抽取。后续轮次叠加单金标+打分截断。
- **渲染密度标本入档(并入 §6.24 重构 fixture)**:Missouri River —
  ① 35 实体尾全列举单行;② 近逆重复块(partially_containedby vs
  partially_contains 展示同一批 m.xxx);③ CVT 属性括号在首次展示后
  裸 id 引用仍重复完整括号。

## 附录: 渲染演化完整记录(2026-08-31 终)

六版渲染 fastcheck(10标本 TEMP=0.3):
基线 0.5111 → v1 +7.2 → v4 +1.9 → SAPS +2.5 → v3.6统一trie −14.6
→ **V3.6c 候选+模式分组 0.6534(+14.2pp)最佳**

V3.6c = 用户候选中心设计 + 模式分组(保留关系名) + SAPS 树连接符
+ CVT 内联属性 + L1 一致压缩 + 零丢失(尾行全名/折叠枝全实体)
+ 候选标记◂(仅真叶子) + 头一次性。

统一 trie 失败的教训: 跨模式合并丢每跳关系语义(致命)。
候选中心范式的正确实现 = 模式分组内做候选标注,不是打破模式分组。
