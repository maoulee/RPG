# KG 智能体轨迹的信用分配：机制与核心代码

> 问题：多轮 KGQA 轨迹（plan → k×[retrieve_relations → retrieve_subgraph] → answer）
> 只有轨迹级结果奖励（F1）。需要把信用分配到**每一轮行为**，且：
> (a) 同样的探索行为不因最终答案运气而得到不同信用；
> (b) 冗余探索无信用、有害探索受抑、关键探索拿满；
> (c) 轮数增加不稀释每轮信用。

---

## 0. 方案总览（四层）

```
① 信号层   teacher-forcing 金标概率: V0/VF/Valone/Vloo → c_i(LOO), fwd_i(前向增量)
② 轨迹层   R_exp = 证据质量, A_exp = R_exp − mean_group(R_exp)   [轨迹间差分]
③ 轮层     a_t = scale_t × A_exp,  scale ∈ {0,1} = 1{G ∨ F ∨ L}
           答案轮独立: a_ans = F1(pred, gold∩evidence) − mean_group(·)
④ 梯度层   第 k 个 assistant 回复的 token 均匀携带 a_k:
           L = −Σ_t a_t·logπ(y_t)   （带符号逐轮 SFT / per-token 加权策略梯度）
```

---

## 1. 信号层：teacher-forcing 信息增益（`kgqa/rl/seq_advantage.py:run_real`）

```python
# 对每条轨迹构造 (prefix, gold) 对，冻结 base 上 batch 求 logP(gold | prefix)
all_pairs.append((f"Question: {q}", gold));            pair_meta.append((i, "V0", None))    # 无证据
all_pairs.append((evidence_full, gold));               pair_meta.append((i, "VF", None))    # 全证据
for sg in sgs:                                            # 每个 sg：
    all_pairs.append((evidence_sg_alone, gold))           # Valone → fwd_i = e^{Valone} − p0
    all_pairs.append((evidence_without_sg, gold))         # Vloo  → c_i   = e^{VF} − e^{Vloo}
all_pairs.append((evidence_full, model_answer))           # Vyhat

# teacher-forcing 实现 (kgqa/llm/offline_vllm.py):
sp = SamplingParams(max_tokens=1, prompt_logprobs=0, temperature=0)
outputs = self.llm.generate(prompts, sp)   # prompt-only logprob, 无生成
# gold 段 token 的平均 logprob → V 值

# 组内中心化 (轨迹级结果):
A_k = (f1 − mean_group(f1)) / std_group(f1)
```

**两个信号的正交分工**（v5 数据实测，4152 轨迹）：

| 信号 | 测什么 | 盲区 |
|---|---|---|
| `c_i`（LOO） | 移除该 sg 对答案概率的伤害 | 冗余互相备份时全零（金标携带 sg 的 58% 被掩蔽） |
| `fwd_i`（前向） | 执行时刻的增量信息 | — 被掩蔽步骤 84% 靠它恢复（合取约束步） |
| `G`（金标归属） | 谁**首次**把金标带入证据 | 约束步（不带金标实体）看不见 |

---

## 2. 轨迹层 + 轮层：两轴优势分配（`scripts/recompute_advantage_v0.py` 核心逻辑）

```python
# ── 轨迹层：探索轴（证据质量，组内差分） ─────────────────────────
if args.r_exp_mode == "tf":          # 旧数据 / 证据可见性饱和时
    r_exp = pF - p0                  # teacher-forcing 增益（逐实体均值语义）
else:                                # display: 结构化证据字段
    r_exp = |gold ∩ evidence| / |gold|
a_exp = r_exp - mean_group(r_exp)    # ← 轨迹间差分，非步间差分

# ── 轮层：scale 门控（二值 v0） ──────────────────────────────────
# G: 金标首次归属 —— 按 sg 出现顺序, 首次带入某金标实体者得
attributed = set(); g_first = defaultdict(float)
for s in sg_order:                              # 轨迹内 sg 时序
    new_gold = [gm for gm in range(len(gold))
                if gm not in attributed and fuzzy_in(gold[gm], ev_by_sg[s])]
    for gm in new_gold: attributed.add(gm)
    g_first[s] = len(new_gold) / len(gold)

# 每轮: scale = 1{G ∨ F ∨ L} —— 任一信号有值即"这步有价值"
val  = (g_first.get(sg, 0) > 0                  # G 金标归属
        or fwd.get(sg, 0) > 0.01                # F 前向增量
        or loo.get(sg, 0)  > 0.01)              # L LOO 伤害
scale = 1.0 if val else 0.0
# plan 轮: scale = 1{r_exp > 0}

# ── 合成（无 ÷n 稀释, 无 Σ 守恒） ────────────────────────────────
if blk == "answer":
    turn_advs[k] = a_ans                       # 答案轴独立（见下）
else:
    adv = scale * a_exp
    if scale == 0 and a_exp < 0:
        adv = -eps * abs(a_exp)                # ε=0.05: 负轨迹中零权重轮的相对抬升对抗

# ── 答案轴：基于证据可达金标的 F1（不强化运气） ──────────────────
gold_e = [g for g in gold if fuzzy_in(g, evidence)]   # 证据可达金标
f_ans  = f1(pred_expanded, gold_e) if gold_e else 0.0  # 分支引用已展开
a_ans  = f_ans - mean_group(f_ans)
```

**关键设计决定（与实测依据）**：

### 不变性保证（解耦的构造性性质）

```
G1 探索不变性: 组内相同的关系选择行为 → 严格相同的探索轮信用，与各自最终答案无关
   （原始问题: imp×A_k 耦合下, 相同探索因答案运气拿到 ±不同信用;
     实证 165 条好探索+坏答案轨迹 95% 被错误压制 → 解耦后 66-70% 翻正）
G2 答案归因:   同证据下不同答案 → 不同答案轮信用（不同动作不同账）
G3 轴零耦合:   答案优势永不落在探索轮, 反之亦然
```

| 决定 | 依据 |
|---|---|
| 两轴解耦（答案结果不进探索信用） | G1：相同行为必须相同信用——耦合方案 95% 错误压制好探索 |
| 轨迹间差分而非步间 ΔΦ | 步间差分有概率尺度畸变（0.01→0.10 与 0.90→0.99 不同权），且路径依赖 |
| scale 独立绝对值（非 softmax/和一） | 轮数增加不稀释；4 关键步各拿满=正确（都做了有价值的事） |
| 负轨迹零权重轮加 −ε | 概率归一化下，零梯度在负轨迹中等价于相对抬升该行为 |
| `gold∩evidence=∅ → a_ans=0` | 无证据支撑的正确答案=运气，不强化（实测 2% 轨迹） |
| TF 用 pF−p0 而非裸 pF | 多实体联合概率压缩伪影（441 条"坏探索"中 94% 为测量假象） |

---

## 3. 梯度层 A：逐轮信用 → token 级权重（`kgqa/rl/seq_train_grpo.py`）

```python
def _tokenize_seq_perturn(tokenizer, messages, turn_advantages, max_length):
    """第 k 个 assistant 回复的 token 均匀携带 turn_advantages[k]（per-reply 设计）。
    span 对齐: 每个 Qwen chat turn 恰好一个 <|im_start|>…<|im_end|> 块,
    #spans == #messages, 与 messages 1:1 对齐。"""
    ids = tokenizer.apply_chat_template(messages, tokenize=True,
                                        add_generation_prompt=False)
    if isinstance(ids, list) and ids and isinstance(ids[0], list):
        ids = ids[0]
    if isinstance(ids, list) and ids and hasattr(ids[0], "ids"):
        ids = list(ids[0].ids)
    ids = list(ids)
    if len(ids) > max_length:
        return None
    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    starts = [i for i, t in enumerate(ids) if t == im_start]
    spans = [(starts[k], starts[k + 1] if k + 1 < len(starts) else len(ids))
             for k in range(len(starts))]
    if len(spans) != len(messages):
        return "MISMATCH"
    asst_idxs = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    if len(asst_idxs) != len(turn_advantages):
        return "ADV_MISMATCH"
    labels, per_tok = [-100] * len(ids), [0.0] * len(ids)
    for k, mi in enumerate(asst_idxs):           # ← 逐轮信用落在该轮 token span 上
        s, e = spans[mi]
        adv = float(turn_advantages[k])
        for t in range(s, e):
            labels[t] = ids[t]                   # 只训 assistant token
            per_tok[t] = adv                     # 回复内均匀（per-reply 统一优势）
    return {"input_ids": ids, "labels": labels, "per_token_advantage": per_tok}
```

---

## 4. 梯度层 B：逐 token 加权损失（`scripts/train_offline_grpo.py`）

```python
def _compute_loss_per_stage(self, model, input_ids, attention_mask, labels,
                            per_token_advantage):
    """L = -mean_{t ∈ completion}( per_token_adv[t] · logprob(token_t) )
    带符号: a_t>0 抬升该回复, a_t<0 压低, a_t=0 不动。
    backbone 前向一次; logits 按时间维分块投影（峰值 B×chunk×V, 非 B×T×V）。"""
    base = _get_base_transformer(model)
    out = base.model(input_ids=input_ids, attention_mask=attention_mask)
    hidden = out.last_hidden_state                       # (B, T, H)
    shift_hidden = hidden[:, :-1, :].contiguous()        # (B, T-1, H)
    shift_labels = labels[:, 1:].contiguous()            # (B, T-1)
    shift_adv = per_token_advantage[:, 1:].contiguous()  # (B, T-1) 与 shift 对齐
    mask = (shift_labels != -100).to(hidden.dtype)       # 仅 assistant token
    safe = shift_labels.clamp(min=0)

    lm_head, chunk = base.lm_head, max(1, self.per_stage_chunk)
    logp_chunks = []
    for st in range(0, shift_hidden.shape[1], chunk):
        en = min(st + chunk, shift_hidden.shape[1])
        logits = lm_head(shift_hidden[:, st:en, :])              # (B, c, V)
        lsm = torch.log_softmax(logits.float(), dim=-1)
        logp_chunks.append(
            lsm.gather(-1, safe[:, st:en].unsqueeze(-1)).squeeze(-1))
    logp = torch.cat(logp_chunks, dim=1)

    contrib = -(shift_adv * logp) * mask                # ← 信用在这里进入梯度
    return contrib.sum() / mask.sum().clamp(min=1.0)   # 逐 token 归一（天然抗长度膨胀）
```

**与标量 GRPO 的等价关系**：离线 GRPO（beta=0、无 ref、无重要性采样）的
limer fused loss 恒等于 `L = −Σ_i A_i·logπ(y_i)`，即**带符号加权 SFT**。
标量路径把 Σa_t 求和（轮结构坍缩）；逐轮路径保留 a_t（本方案）。

---

## 5. Rollout 侧的结构化字段（`kgqa/rl/seq_rollout.py`，供 ②③ 层消费）

```python
# 证据 = ctx 级全量（含渲染截断的隐藏叶子 + 分支引用展开），非显示文本解析
at = getattr(rc.ctx, "accumulated_triples", None) or set()
ev_ents = {str(h) for h, r_, t in at} | {str(t) for h, r_, t in at}
ev_ents.update(str(c) for c in (getattr(rc.ctx, "all_candidates", None) or []))
out.append({..., "evidence_entities": sorted(ev_ents),
            "pred_entities": list(getattr(rc.ctx, "llm_answer_preds", None) or [])})
```

---

## 6. 验证数字（为什么是这些设计）

| 实验 | 结果 | 支撑的设计点 |
|---|---|---|
| 旧方案信用分布 | 答案轮占赢家信用 93.9%（中位） | 两轴解耦的动机 |
| 好探索+坏答案 165 条 | 95% 被旧方案压制 → 新方案 69% 翻正 | 探索/结果解耦 |
| 坏探索+好答案 441 条 | 旧方案白拿信用 → 89% 压低 | a_ans 用 gold∩evidence |
| 金标携带 sg 交叉表 | 58% 被 LOO 掩蔽，84% 靠 fwd 恢复 | G∨F∨L 三信号门控 |
| corr(证据增益, 结果奖励) | 0.104（正交） | 结果奖励不能教探索 |
| 组内 turn 模式差异 | 362/364 case（99%） | 逐轮信用有可学结构 |
| v7 scalar（Σa_t 坍缩） | 与 base 持平（3-seed） | 标量坍缩 → 必须逐轮进梯度 |
| **v8 per-turn（终局）** | 0.8128 vs base 0.8178，Δ−0.5pp CI[−4.0,+3.0]；vs v7 +0.78pp（噪声内）；跨 seed 方差未收 | 逐轮信用数学上实现且数据侧验证（99% 组内有轮级模式差异），但 9B+LoRA+1epoch 规模下三种形态（scalar/逐轮）均持平 → 训练侧杠杆关闭；有效杠杆为数据修补(+3pp)与 harness(+3pp) |
