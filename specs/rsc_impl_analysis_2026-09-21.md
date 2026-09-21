# RSCC 实现分析报告（四代理综合）— 2026-09-21

素材：specs/rsc_rsc_spec_2026-09-21.md（机制原稿）+ 四个并行分析代理
（数据结构 / 打分器 / 结构裁决与依赖序 / 融合架构与实验设计）对现有
管线的只读审计。数据基础：reports/v23_unified_48x3.json（144 轨迹，
与 v23_envfix 同 schema，分析管线零改动可读）。

## 0. 结论速览

1. **第一版做分析端**：新脚本 `scripts/rscc_credit.py` + 复用
   annotate_layer_ops / score_layer_op_probs / dump_traj_full 三件套；
   训练端 GRPO 杠杆在该栈七连平（lever CLOSED），不值得先动。
2. **S() 零新数学**：RSCC 的 S(G)=log P(y*|q,G) 与现有 V=log-mean-exp
   （per-entity cap-8、长度去偏、seed 1234+traj_idx）完全同构，直接复用
   （scripts/score_layer_op_probs.py:88-94,141-211；源头
   kgqa/rl/seq_advantage.py:371-467）。
3. **成本可承受**：倒序链式复用后每 branch 只需 T+1 次状态评分（非 2T）；
   四臂对照 144 轨迹 ≈ 5-7k 次评分，8 线程 **1-2 小时**。
4. **最大风险是打分噪声而非机制**：echo 批次效应实测最大差 0.409
   （远大于 τ），必须四臂同批发射 + 双 τ 报告 + 噪声带判据。
5. **三处跨代理分歧已裁定**（见 §5）。

## 1. 数据结构（代理①）：§18-19 字段映射

**现状**：rollout 落盘只有 trajectory 文本（扁平 key:value 渲染，非
JSON）+ case 级压扁 evidence_entities；**全部 ctx 账本随对象丢弃**
（seq_rollout.py:346-359 是唯一出口，无 ctx dump）。三重渲染截断
（_TREE_LINE_BUDGET=200 行 / tail 合并 / display-license 过滤）使
文本块 ⊂ 真实交付证据。

**零改动离线重建路径**（第一版采用）：解析 plan 文本（sgN.anchor 行，
seq_harness.py:69-96 解析器可离线复用）→ 顺序扫描 assistant 的 sg 调用
（center/relations/sg 字段）与配对 tool 消息（fact_id/anchor_sequence/
layer_action/triples 渲染块）→ checkpoint 声明（_CKPT_RE 家族）给
fact→绑定。

**偏序三键的现有代理**（全部文本层可组）：
- entity_branch_id = **sg 树 id（锚树），不是 fid**——anchor_seqs 以锚
  实体为 key 做树延续（seq_tools.py:3881-3907），35/144 条轨迹含 ≥2
  树，多实体 branch 真实存在；fid 命名空间与树命名空间混杂必须经
  fact_key_map 归一（seq_harness.py:62-96）。
- dependency_depth = anchor_sequence 行的 ⭢ 分段序号（root=0，extend
  加层，update:k 替换第 k 层；构造 seq_tools.py:3994-3999）。
- 同链执行序 = trajectory 消息下标。

**第二版升级（最小改动，两处）**：①首选改 `_sg_finalize` 的 `_res`
（seq_tools.py:5555-5605）——加 `triples_raw`（post-filter all_triples
cap 500）/ `candidates_raw` / `layers`（root+depth+layer_relsets+action
序列化，同时解决 parent/depth）/ `fact_key`，自动随 trajectory 落盘；
②seq_rollout out.append 加 `ctx_ledger` dump（fact_evidence/
fact_candidate_pool/fact_bindings/fact_vars/closed_facts/anchor_seqs/
consumed_anchors/fid_pattern，set→list）。

## 2. 打分器（代理②）：S() 复用与成本

- **复用清单**：gold_logprob（HTTP echo，marker "\n\nAnswer: "，从尾
  向前找 boundary、丢最后 1 个生成 token——score_layer_op_probs.py:61-85）；
  per-entity V=log-mean-exp（:141-211）；rules_prefix 截 8000；
  evidence_text 剥指令行 + trunc 15 行。
- **echo 陷阱（必须尊重）**：echo/prompt_logprobs 在
  max_num_batched_tokens>2048 的服务器会 OOM 杀引擎（fp32 全词表
  log_softmax，2026-09-17 事故 3.42GiB ask）；**长 prompt 永远走
  /generative_scoring chain 路径**（informat_tf_calib.py:342-393，
  与 echo bit-identical 且 budget 免疫）。第一版 15 行截断使 prompt
  有界（2-3K token），echo 可用；证据状态加大即切 chain。
- **评分次数精确公式**：倒序第 k 步的 factual 可复用上一步结果
  （Informative→参考态不变；Redundant→参考态=上一步 cf），故每 branch
  **T_v+1 次状态评分**（naive 2T 是不做链式缓存）；四臂 ≈ 4T_v+3。
  branch 内因动态依赖天然串行，144 条轨迹间并行，8 线程足够。
- **τ 标定（log 域参照实测）**：真 Informative 簇 0.11-1.43 nats
  （567_df97 mod4=0.11 最弱）；冗余/噪声簇 |Δ|≤0.07；co-batch 噪声底
  0.037。**建议 τ_log=0.10-0.15 nats**；标定程序=同配置重复打分实测
  漂移 → 已确认 redundant_dup 样本 95 分位加 margin → τ 敏感性扫描 →
  边界带重打分。
- **多 branch 语义**：某 branch 反向收缩时**其他 branch 证据固定全量
  作上下文**（避免处理顺序引入次序依赖，Cameron/DiCaprio 原则）；
  merge 后可加一次跨 branch 对照分（只作分析不作负 reward）。

## 3. 结构裁决与依赖序（代理③）

- **L1 不是 Structural-invalid 的家**——它是"结构必要∨台阶"的正向
  裁决。真正的结构负裁决散在三处：pathway `unreached`（展示边上
  anchor↔gold 不通，annotate_layer_ops.py:418-425）、pathway
  `redundant`（core-path 签名重复）、`harmful-break`（φ 电位不再下降
  后首个不推进 op，:506-580，现仅 MISS 案例标）。
- **复用而非重写**：mark_necessity（:341-453）就是 structural_prune
  的同构物（按 pathway 分组+组内静态删边+组间签名去重）；补两点：
  unreached+零引用+零台阶三条件合取才判 invalid（567-s0 忠实性教训）；
  harmful-break 放开为通用结构负裁决候选。redundant_irr **不映射**
  （已裁定系统性误标，动态删除直接替代它）。
- **替代对互顶（626）天然解除**：倒序先删一个，另一个的 Δ 显现。
  保留 g（金标首达）作 Informative 的 OR 臂，**废弃 f 臂**（伪装的
  答案相关性）。
- **空交付块（1731）单开"证伪"记账通道**：删空块 S 不变是同义反复，
  不给负类；记 `Redundant-valid(Δ=0) + falsification=fid:closed_reason`
  （closed_facts 账本已有结构化载体），训练信号给 0。
- **四臂=同一引擎纯顺序参数化**：Vloo 循环即 Static LOO、Vseq 即
  Forward 边际（注意 Forward Sequential counterfactual ≠ d，d 只加
  不删，需把 RSCC 循环 order 参数设正序）；唯一引擎改动=预枚举批量
  改逐步提交（参考态依赖前序判决）。**Static LOO 组应与现网
  layer_op_probs_2026-09-17.json 完全复现**——现成的回归校验。

## 4. 融合架构（代理④）：六阶段流水线

`scripts/rscc_credit.py`：
- **Stage 0** 装载+切块+通路标注（复用 annotate/mark_necessity/
  mark_break_points，纯 CPU <2 分钟）。
- **Stage 1** behavior→evidence-block（§1 的零改动重建路径）。
- **Stage 2** branch 划分与偏序（sg 树 → 层深 → 执行序）。
- **Stage 3** 结构裁决（零 LLM 成本；L1 必要∨台阶短路 Informative）。
- **Stage 4** 倒序动态反事实核心循环（§2 打分器；单遍先行，不迭代
  到不动点）。
- **Stage 5** 输出：JSON（全 144×4 臂 per-block credit，键 str 化、
  4 位有效数字）+ ◆ 行 dump（四臂对照列，prob_audit_trajs 惯例）。
- **Stage 6** `--arm rscc|loo|fwd|rand|all`（rand 3 seed 取均值，
  随机化域跑"branch 间随机/branch 内倒序"与"全随机"两档，分离
  "倒序"与"依赖序"两个因子）。

**训练端将来接口（P3，先裁定后动）**：RSCC credit → turn_advantages
复用 build_turn_advantages 守恒除法；Σa_t=A_k 的守恒约束需显式做
零头分配（被删块的 credit 差额归属"冗余信息"）。

## 5. 跨代理分歧裁定（三处）

| 分歧 | 代理② | 代理③④ | 裁定 |
|---|---|---|---|
| τ 域 | log 域 0.10-0.15 nats | 概率域 TAU=0.005（v15 惯例） | **双域双报**：主判概率域（与 v15/layer_op_probs 可比、微概率下 log 差恒>τ 的教训），log 域 Δ 落盘；结论须在 τ=0.005/0.05 与 τ_log=0.10 两档下同号 |
| 打分路径 | chain 默认（budget 免疫） | echo（15 行截断 prompt 有界） | 第一版 15 行截断 → echo 可用；证据状态加大或服务重启后 budget 不明 → 切 chain；**四臂无论如何同 run 同批** |
| 块边界口径 | —（未涉） | display 口径（§6.14/6.20 "judgments use what the model actually saw"） | **第一版 display 口径是设计正确**（模型从看到的东西作答，credit 评的就是它）；`_res` 加 triples_raw 是第二版"完整交付语义"升级，不是第一版缺口 |

## 6. 实验方案（四组对照，§22）

- **对象**：v23_unified_48x3 全 144 轨迹 × 4 臂（rand +3 seed）。
- **指标**：
  - M1 早期行为 credit 恢复（前 1/3 块 gold-pattern 行为的 Δ，
    RSCC vs LOO 配对）+ masking 率 P(Δ_LOO≤τ ∧ Δ_RSCC>τ)；
  - M2 gold 块被标 Redundant 的比例（redundancy-masked 率）；
  - M3 **626 替代对互顶解除**（LOO 双负/双零 → RSCC 一 Inf 一 Red）；
  - M4 与 v1.5 级联标签一致率（>80%，分歧应集中在已知误标类）；
  - M5 收缩有效性（被删块在 rand 臂下删除会伤 Δ）。
- **成本**：5-7k 次评分 ≈ 1-2 小时；P0 结构表（半天）→ P1 标本 13
  条单臂（一晚）→ P2 四臂全量（一晚）→ P3 训练端（用户裁定后）。
- **失败判据**：M1 无差（|ΔΔ|<0.05 噪声带内）；626 不解除；rand≈rscc
  （一致率>90%）；删块伤分；M4 一致率低且方向随机。

## 7. 风险清单（合并去重）

R1 echo OOM（15 行截断+必要时 chain）；R2 批次非确定性（最大 0.409，
四臂同批发射+5-prompt 双发校准+噪声带单独报）；R3 τ 低于噪声带（双 τ
两档同号才下结论）；R4 生成 token 混入（保留 len-1 截断）；R5 json 键
str 化；R6 精度抹零（.4g 全程）；R7 **删块位置效应**（固定拼接序
=(branch first_idx, 块 idx)，删除=跳过不补位，四臂同序，G* 同序）；
R8 Δ 概率域；R9 per-entity 不退回整串；R10 跨 server 漂移 ~0.3 ln
（同 run 完成）；R11 answer-stage miss 分层呈现；R12 unreached 判
invalid 三条件合取；R13 重放 pool 序（第一版不触 replay）。

## 8. 待用户裁定项

1. 第一版按上述设计动工与否（P0→P2）。
2. 空交付块"证伪通道"记 0 分（非负类）是否接受。
3. 训练端接入（P3）暂缓是否接受（GRPO lever CLOSED 的历史结论）。
4. `_res` 加 triples_raw 等字段（第二版升级）现在顺手做还是等第一版
   结论——建议等（第一版 display 口径自足，且不动 rollout 主线）。
