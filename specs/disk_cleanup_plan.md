# /zhaoshu 磁盘清理 & 回传计划 (v2)

**日期**: 2026-07-22（v2，基于架构调整决策）
**目的**: 为上传 Freebase 数据腾出空间（50G 压缩包 → 解压 130G → 共 180G；容器重启前可叠加容量，**只需给压缩包留 50G 上传空间**，做完删图谱）
**当前占用**: `/zhaoshu` 共 **97G**

## ⚡ 本版策略要点（用户 2026-07-22 决策）

1. **RL checkpoint 全删**（5.3G）—— 架构正在调整，旧 ckpt 不再需要，不回传
2. **阶段1 缓存清理** —— 执行
3. **模型权重暂不动** —— 等架构调整稳定后再考虑
4. **reports 深度甄别** —— 大量是过时探索/中间采样，核心只保留：最新架构相关分析、paper baseline、最佳实验结果
5. **核心代码 + 数据本地下载** —— 真正独有的、不可重建的

---

## 一、`/zhaoshu` 占用全貌（97G）

| 目录 | 大小 | 类别 | 处置 |
|---|---|---|---|
| `llm/Qwen3.*` | 49G | 公开模型权重 | ⏸️ 暂不动（架构调整后再说） |
| `subgraph/checkpoint/*` | 5.3G | RL LoRA ckpt ×8 | 🔴 **全删**（架构调整，不需要） |
| `subgraph/data/offline_grpo` | 4.4G | RL 训练数据 | 🟡 待定（可重跑生成） |
| `subgraph/data/{cwq,webqsp,cwq_processed}` | 1.1G | KGQA 原始数据 | 🟢 **回传本地** |
| `subgraph/reports/*` | 3.0G | 实验结果 | 🟢/🔴 **甄别**（见下） |
| `subgraph/{kgqa,scripts,specs,config}` | 小 | **核心代码** | 🟢 git tracked，本地 clone |
| `venvs/qwen35-train` | 5.3G | Python venv | 🔴 阶段1 删 |
| `kgc/*` | 8.5G | KGC 项目+数据集 | 🟡 待定 |
| `kg_llm/checkpoints` | 2.4G | 旧训练 ckpt | 🟡 待定 |
| `kg_llm/data/wikidata5m` | 3.0G | 大数据集 | 🟡 待定 |
| `node/v24.14.1` | 2.3G | Node 运行时 | 🔴 阶段1 删 |
| `Chenleyang` / `hwj` / `Wanghuanhuan` | 3.2G | **他人目录** | ⚠️ **只标记，不动** |
| `softpath/outputs` | 1.3G | NCRL 实验输出 | 🟢 建议回传 |
| `open-design/node_modules` | 1.1G | npm 依赖 | 🔴 阶段1 删 |
| `.conda-gcc` | 753M | conda 环境 | 🔴 阶段1 删 |
| `root/.claude` | 1.4G | Claude CLI 缓存 | 🔴 阶段1 删 |
| `webgpt` | 2.1G | 工具+数据 | 🟡 待定 |

---

## 二、`subgraph/reports/` 甄别（核心 vs 过时）

依据 SESSION_MEMORY / paper_handoff / 提交历史。**关键判断线：架构调整提交 `43bfa84`（K30 sub-question decompose，2026-07-19）之后的才算新架构相关。**

### 🟢 保留（核心实验数据）

| 目录 | 大小 | 最后修改 | 保留理由 |
|---|---|---|---|
| `cwq_full_test/` | **220M**（删轨迹后） | 05-10 | **全量 CWQ 测试结果**：8 chunks × `results.json`(220M, 结构化阶段结果+指标) **保留**；仅删 `trajectory_dump.jsonl`(862M) + `fail_traces.txt`(103M) 轨迹。results.json 已含完整 f1/阶段字段，不依赖轨迹 |
| `ab_rewrite_baseline/` | 50M | 07-19 | **K30/K15 AB 实验**，新架构 decompose 对照基线 |
| `decompose_audit/` | 32M | **07-20** | **最新架构分析**（`traj_100_constraint.jsonl`，新 decompose 审计） |
| `baselineA_400/` | 79M | 06-25 | **paper baseline**（v2 stage, 85.8% hit / 0.749 F1 @400，spec §0 引用） |
| `samp_cwq_full/` | 31M | 07-09 | **plan-failure 根因诊断**（paper 关键结论来源） |
| `samp_val_pool/` | 227K | 07-09 | 🔴 **删 batch 留诊断**：只保留 `plan_failure_diagnosis*.json` / `state.json`，删 `batch_*.jsonl`(672M, 可重跑) |
| `heldout_*` / `ab_*` / `abcd_*` / `test_multirun_*` | ~20M | 07-10~12 | 近期 AB / held-out / multirun 结果，小，保留 |

**reports 保留总计 ≈ 432M**（cwq_full_test 删轨迹 + samp_val_pool 删 batch 后）

### 🔴 可删（过时探索/中间采样/废弃 baseline + 大轨迹，~3.6G）

| 目录 | 大小 | 删除理由 |
|---|---|---|
| `cwq_full_test/` 轨迹部分 | **965M** | `trajectory_dump.jsonl`(862M) + `fail_traces.txt`(103M)，results.json 已含指标 |
| `webqsp_full_hint_v2/` | 297M | 05-22 旧 hint 实验，已被新架构取代 |
| `webqsp_full_test/` | 296M | 05-21 旧 full test（含 trajectory_dump 241M），已被 samp_cwq_full 取代 |
| `samp_val_b{1..9}` 系列 | ~95M | 07-06 早期分批采样，已被 samp_val_pool + samp_cwq_full 取代 |
| `samp_webqsp_full/` / `samp_cwq_b1/` | 24M | 早期采样 |
| `stage_*_greedy/` (6个) | ~100M | 07-09 stage pipeline 实验，已被 agent 架构取代 |
| `cwq_*_100/` / `webqsp_*_100/` 系列 | ~50M | 03~07月 早期 100-case 探索 |
| `samp_val_pool/batch_*.jsonl` | 672M | 中间采样，可重跑 |
| `cwq_case*/` `multi_*/` `*_smoke/` 等 | ~10M | 单 case 调试 / probe / smoke |

---

## 三、回传清单（🟢 必传 —— 独有、不可重建）

总计约 **5.4G**。原则：**代码留容器（轻）、数据回传本地（重）、模型暂不动**。

### Bundle A: subgraph 核心代码（git tracked，本地 clone）
```bash
# 在本地 PC 执行：
git clone <repo_url> subgraph
git checkout agent-toolcall
```
**⚠️ 必须先在容器内 commit/stash 未提交修改**（架构调整核心）：
- `kgqa/agent/*` (loop.py, react_loop.py, tools.py, loader.py, AGENTS.md)
- `scripts/*` 新增（method2_*, prefix_rollout, audit_*, rescore_* 等）
- `kgqa/stages/*`, `kgqa/llm/batch.py`

### Bundle B: subgraph 核心数据（1.1G）
```bash
# subgraph/data/cwq/             (254M)  CWQ 原始 train/val/test
# subgraph/data/webqsp/          (427M)  WebQSP 原始
# subgraph/data/cwq_processed/   (466M)  预处理 pkl + 元数据
# subgraph/data/cwq_sparql/      (3.0M)  SPARQL 标注
# subgraph/data/deploy_bundle/   (3.7M)  部署 bundle 源
# subgraph/data/relation_*.json  (~2M)   relation_ids / richtext
```

### Bundle C: subgraph 核心 reports（~432M）
```bash
# cwq_full_test/*/results.json   (220M)  全量测试结果（轨迹已删）
# ab_rewrite_baseline/           (50M)   新架构 K30/K15 baseline
# decompose_audit/               (32M)   最新 decompose 审计
# baselineA_400/                 (79M)   paper baseline
# samp_cwq_full/                 (31M)   plan-failure 诊断
# samp_val_pool/plan_failure_*.json (227K) 诊断文件
# heldout_* / ab_* / abcd_* / test_multirun_*  (~20M)
```

### Bundle D: 其他项目数据（数据回传，代码留容器，~3.9G）
```bash
# softpath/outputs/              (1.3G)  NCRL 实验输出（wn18rr/fb15k with_path）
# softpath/rules/                (23M)   生成的规则文件（fb15k237/wn18rr rules）
#   ↑ softpath 纯代码仅 410K，留容器；NCRL-main 206M 是第三方仓库，可重 clone
# kg_llm/checkpoints/            (2.4G)  sft(1.8G) + kge(638M) ckpt（如还要用）
#   ↑ kg_llm 代码 111 个 py，留容器
```

---

## 四、操作脚本

### 阶段 0：打包待回传（在容器内）
**`scripts/pack_for_local.sh`** — 打包 Bundle B/C/D 到 `/zhaoshu/_for_local/`

### 阶段 1：删除 RL checkpoint + 过时 reports + 缓存
- **`scripts/cleanup_rl_ckpts.sh`** — 删 `subgraph/checkpoint/*`（5.3G）
- **`scripts/cleanup_reports_stale.sh`** — 删过时 reports（~2.6G）
- **`scripts/cleanup_stage1_safe.sh`** — 删可重建缓存（~9G）

### 阶段 2：模型权重（⏸️ 暂不执行）
**`scripts/cleanup_stage2_models.sh`** — 架构调整稳定后再考虑

---

## 五、空间账

| 操作 | 释放 |
|---|---|
| 删 RL checkpoint | 5.3G |
| 删过时 reports（含 cwq_full_test 轨迹 + samp_val_pool batch） | ~3.6G |
| 阶段1 删缓存（venv/node/claude等） | ~9G |
| **合计（阶段1 全做）** | **~18G** |
| 阶段2 模型权重（暂缓） | (+49G 备用) |

**18G + 容器重启前叠加容量 ≫ 50G Freebase 压缩包需求。** 阶段1 足够，阶段2 留作余量。

> 📌 关键变化：cwq_full_test 现在只删轨迹（965M）保留 results（220M），比 v2 方案少删 220M，但 results 是全量测试的核心指标，值得保留。

---

## 六、🟡 待定项（传完 Freebase 后再决定）

- `subgraph/data/offline_grpo` (4.4G) — RL 训练数据，架构调整后可能不再需要，但可由 `sample_trajectories.py` 重跑。**建议先留着，等新架构定型再删。**
- `kgc/*` (8.5G) / `kg_llm/data/wikidata5m` (3.0G) — 标准数据集，可重下
- `kg_llm/checkpoints` (2.4G) — 旧 ckpt，看是否还要用
- `webgpt` (2.1G) — 工具，看是否还用
- `codex-backup` (386M) — 确认是否还需要

---

## 七、不动项（明确保留）

- `subgraph/` 主体代码（tracked）
- `Chenleyang/` `hwj/` `Wanghuanhuan/` —— **他人目录，只标记不动**
- `llm/Qwen*` —— 模型权重，暂不动
- `polyfill-glibc` `libxml2-2.9.12` —— 可能被系统依赖
