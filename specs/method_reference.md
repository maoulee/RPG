# SEQ-KGQA 方法参考（论文起草用速查）

> 只记录"现在是怎么做的"：机制 + 公式 + 代码位置。无解释性文字。
> 数字基线与实验结论见 `SESSION_MEMORY.md`。

## 1. 总体架构

```
Qwen3.5-9B (hybrid: 24 linear-attn + 8 full-attn, vocab 248K)
  + SEQ agent harness (in-process, 本地 RoG 子图 + Virtuoso 修补)
  + LoRA r64/α128 离线 GRPO 微调（可选）
流程: prelink(qentity 注入) → decompose(子图/fact 分解)
      → 每 fact: retrieve_relations(GTE 候选关系) → retrieve_subgraph(走查+证据树)
      → answer(entities / 分支引用)
协议: 纯文本 tool: 调用（flat / JSON 双解析），无 native tool-call
服务: vLLM (TP2, prefix caching, Mamba align, fp8 KV, thinking_token_budget)
      GTE :8003 (Qwen3-Embedding-0.6B, 关系/实体语义检索)
```

## 2. 子图探索（证据生产）

| 机制 | 内容 | 代码 |
|---|---|---|
| K-path 走查 | 单 BFS 多关系队列，模式数有界（beam 80、completed≤5000），**不约束模式内叶子数** | `kgqa/traversal/k_queue.py:k_queue_traverse` |
| 叶子全量枚举 (Option B) | witness 末跳的关联边**双向全量**进入证据（CVT 兄弟展开 `_expand_sibling_cvts` 的推广）；24 support-path 上限语义=路径形态多样性 | `kgqa/stages/formatting.py:build_pattern_evidence_triples` |
| candidates 富集 | lp.candidates ∪ triples 非CVT端点（无 50 上限） | 同上 |
| 证据渲染 | `h --rel--> t1\|t2\|...` 合并行；单行 >120 尾巴截断 + 分支引用提示 `#center::rel` | `kgqa/agent/seq_tools.py:_merge_edges` |
| CVT 记录渲染 | holder→title [from;to;juris]; measurement 按 (h,rel) 配对 date/value | `seq_tools.py:_render_records` |
| 零增益属性压缩 | 组内全同属性收进组头 `(all: k=v)`，from/to 永不隐藏 | 同上 |
| 方向规整 | 渲染前按原图方向翻转 | `seq_tools.py:_canonicalize_triples` |

## 3. 作答协议

```
answer: {entities: [...]}
  分支引用: "#center::relation"（'::' 分隔，'|' 与 flat 列表分隔符冲突）
           → _expand_branch_refs 展开 = 该 (center, rel) 全部本地边端点（非CVT）
  offpool:  证据外实体拒绝一次（带 pool 提示），第二次放行
  过早作答: seq_validate `reminded` 一次性拒绝，重试放行
  终局兜底: rescue_terminal_answer —— 末次 answer 调用 → ANSWER: 行 → 末次 checkpoint 绑定
代码: kgqa/agent/tools.py:_do_answer,_expand_branch_refs
      kgqa/agent/seq_harness.py:seq_validate
      kgqa/agent/seq_react_loop.py:SeqReactCase.rescue_terminal_answer
```

## 4. 拒绝/反馈规则（P1-P6）

1. `answer` 豁免 repeat 拒绝（幂等终止工具，重复=确认）
2. 每种拒绝一次性（reminded / offpool_retried）
3. 拒绝消息只指向可执行动作
4. max-rounds 兜底回收被流程拒绝的答案
5. 入口清洗 `strip_reasoning_leak`：vLLM 注入短语 + 游离 `</think>`（历史/绑定/解析之前）
6. `_do_answer` 实体值级再剥一次

`kgqa/core/utils.py:strip_reasoning_leak`, `kgqa/agent/seq_react_loop.py:process_turn`

## 5. 训练数据管线

### 5.1 Rollout（`kgqa/rl/seq_rollout.py`）
```
G=8, temp 0.8, top_p 0.8, top_k 20, presence 1.5
THINK_BUDGET 512, MAX_ROUNDS 12, CASE_BATCH 48 分阶段（增量落盘）
OfflineVLLM: prefix caching ON (Mamba align), fp8 KV
记录结构化字段: evidence_entities（ctx 级全量，含隐藏叶子+分支展开）
              pred_entities（answer 展开后）
```

### 5.2 IG pass（`kgqa/rl/seq_advantage.py:run_real`）
```
teacher-forcing 金标 logprob（OfflineVLLM.gold_logprob_batch）:
  V0  = logP(gold | 问题)                      p0 = e^{V0}
  VF  = logP(gold | 全证据)                     pF = e^{VF}
  Valone_s = logP(gold | 仅 sg s 证据)          fwd_s = e^{Valone} − p0  (前向增量)
  Vloo_s  = logP(gold | 去掉 sg s)              c_s = e^{VF} − e^{Vloo}  (LOO)
  Vyhat = logP(模型实际答案 | 全证据)
A_k = (f1 − mean_group(f1)) / std_group(f1)
```

### 5.3 v0 优势方案（`scripts/recompute_advantage_v0.py`）
```
轴1 探索/规划轮:   a_t = scale_t × A_exp
  R_exp = |gold ∩ evidence| / |gold|        (display 模式, 结构化字段)
        或 pF − p0                           (tf 模式, 旧数据/证据可见性饱和时)
  A_exp = R_exp − mean_group(R_exp)          ← 轨迹间差分（非步间差分）
  scale_t ∈ {0,1} = 1{G_t ∨ F_t ∨ L_t}       (二值 v0)
    G_t: 金标首次归属（该 sg 首先把某金标实体带入证据）
    F_t: fwd_t > 0.01（执行时增量 IG）
    L_t: c_t > 0.01（LOO 移除伤害答案概率）
  plan 轮: scale = 1{R_exp > 0}
  负轨迹中 scale=0 轮: a_t = −ε·|A_exp| (ε=0.05, 对抗零权重相对抬升)
  轮内无 ÷n，Σa_t 无守恒约束

轴2 答案轮:   a_ans = F1(pred_expanded, gold∩evidence) − mean_group(同式)
              gold∩evidence = ∅ → 0（不强化运气）
```
已知现象: 新 harness 下 display-recall 组内饱和（全组=1.0），tf 模式为主；
G/F/L 对"合取约束步"的覆盖靠 F（84% 被掩蔽步骤 fwd>0）。

## 6. 训练

### 6.1 标量路径（已验证）
```
scalar_adv = Σ turn_advantages → liger fused GRPO (beta=0, 无 ref/IS)
           ≡ 带符号加权的交叉熵 L = −Σ_i A_i·logπ(y_i)
代码: kgqa/rl/seq_train_grpo.py:_tokenize_seq
```

### 6.2 逐轮路径（判据实验 v8）
```
_tokenize_seq_perturn: 第 k 个 assistant 回复的 token 均匀携带 turn_advantages[k]
  span 对齐 = <|im_start|> 分块（#spans == #messages 校验，ADV_MISMATCH 丢弃）
  loss = per-stage 逐 token 加权对数似然（时间维分块投影, chunk 1024）
       ≡ 带符号逐轮 SFT（负权重压低错误轮）
代码: seq_train_grpo.py:_tokenize_seq_perturn + scripts/train_offline_grpo.py
      (_make_per_stage_collator, _compute_loss_per_stage)  --per-turn 开关
```

### 6.3 训练配置
```
ZeRO-2 (DDP 配置会破坏 liger 路径——_get_base_transformer 解包差异, 勿用)
Qwen3_5ForCausalLM + liger(RMSNorm+SwiGLU) + LoRA r64/α128 全投影层
lr 1e-5 cosine, warmup 3%, bf16, GC reentrant, batch 2×accum4×2GPU=16
group_by_length(构造后属性注入), adamw_bnb_8bit, --drop-zero-adv
fla/causal-conv1d 快速线性注意力 kernel（环境自带）
实测: 35.4s/step（scalar, vs 旧 45-50）; per-turn ~2.5x
```

## 7. 评测协议

```
scripts/run_seq_eval.py: HTTP batch 端口, 100 case, LLM_SEED 逐请求采样种子
结论规则: 3-seed 均值±极差; 配对 Δ + 95%CI; n=100 的 MDE≈±5pp(单seed)/±3pp(3seed)
      <3pp 单 seed 差异不作结论
```

## 8. 当前数字（2026-08-15）

| | CWQ100 | WebQSP100 |
|---|---|---|
| base (全 harness 修复后, 3-seed) | **0.8178** (0.808-0.828) | **0.8080** (0.782-0.823) |
| v7 LoRA (scalar) | 0.8050 | — |
| 数据修补贡献 | +3.0pp | ~0（WebQSP 无此缺口） |
| harness 修复贡献 | +3.0pp (CWQ配对) | 多答案层 +6.0pp |
| GRPO (v1/v2/v7 scalar) | ≈0（持平） | ≈0 |

误差归因 (CWQ base): ②关系选择 72.6% / ①意图噪声 26.4% / ③答案数量 0.9%；
②内 86-89% 跨 seed 翻转伴随关系选择差异。

## 9. 文件索引

| 部分 | 文件 |
|---|---|
| agent 主循环/批量 | `kgqa/agent/seq_react_loop.py` |
| 工具 dispatch/渲染 | `kgqa/agent/seq_tools.py` |
| answer/offpool/分支展开 | `kgqa/agent/tools.py` |
| 状态机/预算 | `kgqa/agent/seq_harness.py` |
| K-path 走查 | `kgqa/traversal/k_queue.py`, `frontier.py` |
| 证据构建(叶子全量) | `kgqa/stages/formatting.py` |
| 离线 vLLM (生成/logprob) | `kgqa/llm/offline_vllm.py` |
| HTTP 客户端(seed/清洗) | `kgqa/llm/client.py` |
| rollout | `kgqa/rl/seq_rollout.py` |
| IG + 旧分配 | `kgqa/rl/seq_advantage.py` |
| v0 优势重算 | `scripts/recompute_advantage_v0.py` |
| 信用分配机制自述(外部讨论版,无代码名词) | `specs/credit_assignment_mechanism.md` |
| 信用分配机制+代码映射 | `specs/credit_assignment_code.md` |
| 训练入口(scalar/per-turn) | `kgqa/rl/seq_train_grpo.py` |
| 通用 trainer | `scripts/train_offline_grpo.py` |
| case 选择 | `scripts/select_rollout_cases.py` |
| 数据修补 | `scripts/repair_v4.py`, `repair_subgraph_virtuoso.py` |
| eval | `scripts/run_seq_eval.py` |
