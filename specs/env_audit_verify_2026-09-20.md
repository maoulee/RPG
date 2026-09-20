# Codex 环境审计逐条验证（3×Explore 子智能体）— 2026-09-20

> 方法：三个只读探索代理并行到代码逐条核对（file:line + 代码摘录）。
> 结论：**16 项主张 15 项 CONFIRMED、1 项 PARTIAL**；4 处比原审计更严重，
> 2 处有减轻性细节。

## 判定表

| # | 主张 | 判定 | 关键证据 |
|---|---|---|---|
| 1 | PLAN EXTEND 两层矛盾 | **确认** | nudge（seq_tools 2888-2895）叫模型 extend "covers the same requirement"；gate（react 1318-1320 `rid not in _cov.values()`）结构性拒绝已覆盖 requirement——**照 nudge 做必被拒**。细节：同文件 2806-2809 另有一致版本（uncovered 才 extend），只有 multi_anchor nudge 自败 |
| 2 | restart 不完全重置 | **确认** | 16 个字段全部未清（subgraph_entities/all_candidates/_sg_served/anchor_seqs/memo/consumed_anchors/pattern_state/fid_pattern/_qsim_*/重试旗标/_fid_alias/_ma_gate_fired/_multi_tree_prompted）；_accumulate 跨轮持续增长池子 |
| 3 | _sg_served 只存 True | **确认** | 写入 `True`（seq_tools 5075-5079）；repeat 回复仅 note 无证据重放（4014-4032）；与 #2 组合=灾难（证据已被 restart 截断却让模型"act on previous evidence"） |
| 4 | closure 只认 empty/moot | **确认+更糟** | `_CKPT_CLOSE_RE`（react 47）仅 empty/moot；**未识别的关闭声明被通用 ack 静默确认为"Checkpoints recorded"（1525）**；纯度环提醒（1797-1803）让模型声明 `unresolved-after-repair`——**一个 regex 解析不了的状态词**（只有 harness 自己的程序化写入有效） |
| 5 | 多实体强制 OWN subgraph | **部分** | 两处文本存在（seq_tools 2912-2913 / react 1393-1402）；但强制力=一次性 answer 拦截（1751-1755，_ma_gate_fired 闩锁，明说"re-submit unchanged"可过+类型词豁免）——"reminder+一次性拦截"而非强制 |
| 6 | join path 全图搜索 | **确认** | `_search_join_paths`（react 752-870）：BFS max_hops=4+hub 过滤+GTE 排序，JOIN PATHS 注入 user 消息+完整路径写 trajectory"for credit adjudication" |
| 7 | plan 前 ranked relations 泄漏 | **确认** | prelink（react 718-728）每 q_entity 注入 **top-3 GTE 排序关系**进首条 user 消息（plan 之前）——与 1379 语义漂移直接相关（available KG relation → plan interpretation） |
| 8 | zh authoritative | **确认** | （本组 2×2 实验已实锤为 plan 漂移主因） |
| 9 | q_entity 泄漏 2% | **确认（核心）** | 注释存在（react 659-663）；q_entity=数据集元数据非问题面实体；prelink 直接 seed 进 subgraph_entities=**turn-0 即合法 center**（682-683）；"与答案相关"是推断非代码事实 |
| 10 | answer_type 硬契约 | **确认+更强** | ANSWER-TYPE CONTRACT（react 741-749）**从 all-retrieved 起每轮注入直到答案被接受**——比"answer 阶段追加"更强；plan 期错误被持续升级 |
| 11 | 二拒枚举全部绑定 | **确认** | `_basis` 遍历所有 fact 的所有变量（react 1649-1656，每变量[:4]）；VAR-MISMATCH 守卫几行之外就会读 answer_var——**数据可得，没过滤是选择** |
| 12 | 越池答案二次放行 | **确认** | 旗标烘进守卫条件（tools 2126-2140），二次同情况直接落 `llm_answer_preds` 被接受；注释明示刻意 |
| 13 | 无新证据 subset 改绑 | **确认（有减轻）** | freeze 分支恰在"无新证据"时接受收窄并覆写 fact_bindings+var_bindings（react 157-200）；减轻：值仍须来自该 fact 自己的子图证据（166-177 幻觉过滤）——但**选哪个子集纯凭模型**，ledger 被污染成立 |
| 14 | SYSTEM JOIN 用 checkpoint | **确认（全部三点）** | join 值来自模型声明（react 252-299）；CURATED 注释存在（289-293）；双向不 enforce——非空分支是字面 `pass` no-op |
| 15 | 纯度环三缺陷 | **确认（全部）** | off-by-one（代码 `>=4` 关闭 vs 消息"5 similar queries"）；key 仅 center（1773，无 fact_id）；pre-dispatch 执行**不可能**看到本次证据增量 |
| 16 | walk-nothing 宣称 fact 正确 | **确认** | "the fact is right" 原文在（seq_tools 5217-5218）；全库唯一 diagnosis 变体——空 walk 同样兼容 fact 本身错 |

## 与既有发现的合流

- #4 = 我的 mismatch-token 契约缺口（V2.2 审计）——现在知道**更糟**（静默 ack + 环境自己教模型写解析不了的词）。
- #8 = P5（zh 治理），2×2 实验已证明是 plan 漂移主因。
- #11 = P2（强制作答类型校验）的证据升级：绑定枚举全量+answer_var 过滤器就在旁边。
- #15 = P4（纯度环分级）；#16 给 P4 补充：工具反馈也在替模型做语义断言。
- #7/#9 与 1379 漂移机制同族：**环境的 pre-plan 注入在教模型"什么好检索"**。

## 修正后的统一原则（合并双方提案）

> **可由程序状态证明对错的 → hard enforce；需要理解问题语义才能判断的 → 最多提醒。**

三层重构（legality / progress / semantic-policy-回收到 prompt）与本会话
P1-P5 方向一致，合并为单一 roadmap 执行。

## 建议执行序（在 Codex P0/P1/P2 基础上按验证结果微调）

- **P0**（协议自败/污染类，先行）：#1 PLAN EXTEND 双合法原因
  （COVER_MISSING + ADD_ANCHOR_VIEW）；#2 restart 全量重置
  （reset_seq_episode_state 统一注册）；#4 closure 枚举
  （empty|moot|mismatch|exhausted + 停止教模型写解析不了的词）；
  #12 越池永不二次放行（sanitize→[]）；#8 zh 去权威/拆出主实验；
  #7 pre-plan 只给实体不给 ranked relations。
- **P1**：#10 answer_type 降为 self-check；#11 二拒只列 answer-var；
  #15 纯度环 fact_id+evidence-delta；#16 walk-zero 只报观察给分层诊断；
  #13 binding ledger 与 answer_selection 分离；#14 join 改用工具侧完整池。
- **P2**：#5 多实体 gate 软化措辞；#6 join-path rescue 拆 ablation。
- **保留**：exact-repeat、semantic idempotence（+restart 清+证据缓存）、
  CVT guard、set-valued variables、per-subgraph provenance。
