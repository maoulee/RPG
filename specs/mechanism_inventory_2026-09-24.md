# 机制穷举盘点 — walk/pattern/render 四层管线（2026-09-24）

分支 `audit/gpt6-2026-09-23` 上的只读盘点。范围：`kgqa/agent/` 的
rr → `_sg_prepare`（关系扩展）→ `_derive_multistep_seq`（模式派生）→
`_rebuild_paths`/`_rebuild_pe_list`（链重建）→ `collect_pattern_triples`/
`seq_rows.render_rows`/`render_v38`（渲染）全链路上所有**限额 / 折叠 / 截断 /
合并 / 折叠键**机制。每个机制给：位置、作用、引入 commit（`git log -S` 溯源，
`%h %ad` + 动机）、分类标签。**只盘点不评判**，清理方案由主线做。

分类标签：
- **[设计内]** — 用户裁定链可溯源（commit/注释里有明确 user ruling，且语义
  属于管线骨架：step-coverage、长度优先、per-terminal topk、collapse 键等）。
- **[工程护栏]** — 防爆/降级/成本边界（hub 防爆、内存上限、失败降级），
  不承载选择语义。
- **[设计外补丁]** — 原始设计（2026-05 k_queue 单 BFS+有序覆盖、零状态零
  配额 → 2026-09-11 realignment 的模式骨架）没有、后期为某个标本/预算打
  补丁引入的**语义改变**（行块配额、总 section 预算、树根折叠的副作用等）。

锚点史：`64eea93` 2026-05-25（k_queue 初版）→ `891f618` 2026-09-11
（realignment：模式优先）→ `fe905d1` 2026-09-12（两层渲染拆分）→
`1751eb1` 2026-09-19（重建 lane 取代 beam）→ 2026-09-19..24（16 个 bug
修复波，多数在与本清单里的设计外机制错配）。

---

## 1. 层 0 — 候选关系检索 rr（`retrieve_relations`，seq_tools 2981–3393）

| 位置 | 机制 | 作用 | 引入（commit / 动机） | 分类 |
|---|---|---|---|---|
| seq_tools.py:3146 | `top_k=30 + (30 if _slots>0 else 0)` | union-rank GTE 调用取 top-30 喂 cands；桥槽开启时加 30 行"分数窗"只为给桥候选打分 | `0f6fa6b` 2026-09-23：21_ 标本——office_holder #38 / jurisdiction_of_office #51 全在 top-30 切线下，首屏整族缺席 | [工程护栏]（切线本身）+ 保底槽见下 |
| seq_tools.py:3161 | `len(cands) < 30` | union 池最终候选截 30 | 同上 lineage（union-rank 改造 `048b837` 前 per-entity top-15） | [设计外补丁]（首屏菜单预算） |
| seq_tools.py:3312–3314 | 平铺菜单 `[:15]` | candidate_relations 平铺列表截 15 | `93de7f0` 2026-09-09（V21 多实体工作流恢复 + attribute-first 排序） | [设计外补丁] |
| seq_tools.py:3061–3100, 3143, 3320–3327 | `SEQ_RR_BRIDGE_SLOTS=3` 保底槽 | 池中触及 center 一跳 CVT 的关系，按 GTE 尾分取 top-3，**追加在 15-cut 之后**不挤占排名位 | `0f6fa6b` 2026-09-23：同 21_ 标本（GTE 系统性埋葬 CVT 中介关系；扩 top-15→20 无效） | [设计外补丁]（对 GTE 排序失灵的结构性补偿） |
| seq_tools.py:3194–3198 | `SEQ_RR_GLOBAL_MERGE=1` + `SEQ_RR_MERGE_CAP=80` | 二次属性+关系 re-rank 的输入池：整 union 截 80（关则 `[:15]`） | `048b837` 2026-09-14：deflator 标本——cands 按实体序拼接，`[:15]` 是第一个实体的簇，晚到实体的 #1（Monaco gdp_deflator_change，union 位 ~29）进不了 re-rank | [设计外补丁]（对实体序截断的补丁） |
| seq_tools.py:3260, 3289 | `_ATTR_GROUP_THRESHOLD=5` | 每个 typed 组显示成员截 5 | `734c2bf` 2026-09-09（attribute-grouped 候选，user design 2026-09-08） | [工程护栏]（菜单密度） |
| seq_tools.py:3300–3303 | `len(lines) >= 12` | grouped 菜单总行数截 12 | `734c2bf`/`93de7f0` 2026-09-09 同期 | [工程护栏] |
| seq_harness.py:410–436 | rr per-center 预算 3 | 同一 center 的 retrieve_relations 调用 >3 次即拒绝（附 submission-first 指令） | `9bef817` 2026-09-22 B1：2576-s2 在一个 center 上烧 4+ 次相同 rr（确定性调用） | [工程护栏]（调用经济） |

## 2. 层 1 — 关系扩展 `_sg_prepare`（seq_tools 3686–4279）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_tools.py:3858 | 家族展开 direct `[:10]` | bare/typed 家族名在 center 2-hop 池内匹配的 direct 成员截 10 | 家族展开 lineage（user design 2026-09-08，unified expansion 2026-09-09） | [设计内]（展开本体）+ 截 10 [工程护栏] |
| seq_tools.py:3906, 3925 | 桥集 `len(_bids) >= 6`、桥 echo `[:6]` | center→carrier 桥关系扫描截 6 个 | CVT-bridge ruling 2026-09-09（position rule） | [工程护栏] |
| seq_tools.py:3893 | `SEQ_DIRECT_FIRST=0`（默认关） | center 已直连家族时跳过桥（去噪） | A/B 2026-09-10：清洁渲染但 -4.4pp，桥走的 penetration 是判别证据 → 门控关 | [设计外补丁]（已退役为 A/B 记录） |
| seq_tools.py:3931–3941 | 桥不入 rel_idxs | 桥只作 mseq 模式 mid-segment；`SEQ_BRIDGE_TERMINAL` 注入删除 | `7d8ee88` 2026-09-23：重建时代 lane-2 把注入桥当 frontier 一跳终点，逆关系 id 重 admit 已交付事实（1731） | [设计内]（realignment 裁定） |
| seq_tools.py:3997–4019 | pattern family = 提交关系名解析集 | exact → direct 桶 → 短名等价；**桥永不做 pattern 终点** | `fa30c8d` 2026-09-22：567——2 提交关系膨胀成 7 关系池，桥成了终点 → 60 枚举 / 20+ 渲染 | [设计内]（design realignment 裁定） |
| seq_tools.py:4041–4080 | **树根折叠** `_root_of` | center ∈ 某锚树（root/completions/roster/?var）→ 记 root 映射；**多个 center 折叠到同一 root 时 `centers` 被替换为 root 列表**，`_cont_compare=True` | `fdb7c3f` 2026-09-14：SEQ_REL_SEQ 默认开——typed roster/?var 展开全算树继续，从 root 整链重走 | [设计内]（SEQ_REL_SEQ user design 2026-09-15）**但 centers 替换是设计外副作用**：提交的 center 名单从此不在 treq 里（1812：21 center 折叠后，rows 层 `centers` 集合只剩 root，块优先级失锚） |
| seq_tools.py:4157–4159 | **`cont_frontier` 截 `[:12]`** | 续走 frontier（PRE-update 末层 completions 减 anchor）截 12 个成员作 plain-step 起点 | frontier 本体 `311ffe0` 2026-09-15（1278d3da per-binding rows 恢复）；截 12 在 `90a219a` 2026-09-20 chain-tree 已存在 | [工程护栏]（步数预算；>12 成员的 roster 丢弃尾巴） |
| seq_tools.py:3606–3607 | **层深 cap=3**（`depth_cap`） | `_classify_seq_submit`：层数已达 3 时新 frontier 关系标记 depth_cap 丢弃（注释："depth cap = derive's"，与派生 1..3 对齐） | `37a0a93` 2026-09-14（SEQ_REL_SEQ 初版，门默认关） | [设计内]（与 1..3-hop 枚举对齐）+ 同语义双执行点（见 §9.8） |
| seq_tools.py:3652–3660 | 层叉积截 ≤24 | `_patterns_from_layers`：声名层叉积超 24 时从最宽层逐个裁剪 | relseq lineage（`37a0a93`/`534d55a` 2026-09-14/15）；docstring 自述"只限组合数，语义过滤是 B 相配额" | [工程护栏] |
| seq_tools.py:3679 | `_K_CHAINS = SEQ_CHAIN_TOPK=3` | 声明链 cross-product 只留 top-3（短者优先，确定性） | `534d55a` 2026-09-15：L1(3)×L2(3)=9 section 爆炸（24353bbc 9→6 section） | [设计内]（user ruling 2026-09-15，K=3 对齐 per-terminal 配额） |
| seq_tools.py:4180–4210 | **`_sg_served` 语义幂等**（`SEQ_SEM_IDEMPOTENT=1`） | 键 = 排序后的 (center idx 集, rel idx 集)；重复调用直接回 note（不重放证据） | `9150a85` 2026-09-15（trajectory review：模型换 4 种表面形重打同一 walk）；Wave-2 缓存 `2eff65a` 2026-09-20（`_SG_SERVED_CAP=4000`，seq_tools:5363）；键序修复 `9bef817` 2026-09-22（str vs int 键，缓存结构性死锁 7 天） | [工程护栏]（调用去重；语义键建立在 root 折叠之后，表面形变化被折叠放大命中） |
| seq_tools.py:346 | `SEQ_WALLEXTRA_CAP=6` | `?var` 展开附带的 wandered-candidate 只取最近 6 个 | `d9be8e8` 2026-09-10：ledger 单调增长，晚回合 ?var 重走 30–50 个 center（slot 2343/run） | [工程护栏]（walk 成本） |
| seq_tools.py:3952–3957 | `consumed_anchors` | 已解析 center 记账（answer-time gate 消费） | user ruling 2026-09-01 | [设计内]（非限额，列出备查） |
| seq_tools.py:4262–4264 | 派生总是跑 + `topk=0 if _sem else 3` | 语义模式下派生不裁（交给 B 相），关语义则 length-first top-3 | `891f618` 2026-09-11 realignment；语义默认开裁定 2026-09-12 | [设计内] |

## 3. 层 2 — 模式派生（`_derive_multistep_seq` seq_tools 4282–4424 + B 相选择 4789–4881）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_tools.py:4338–4400 | 枚举深度 1..3 | 纯关系序列枚举（direct、(r1,fam)、(r1,r2,fam)），same-rel out-and-back 跳过 | user ruling 2026-09-13（any-hop 改造） | [设计内] |
| seq_tools.py:4421–4422 | **`_cap = max(topk, 0) or 60` 枚举天花板** | 语义模式（topk=0）候选池截 60，按 (len, tuple) | `1c126bd` 2026-09-19 A2：567——B 相选择异常被吞后全枚举走了渲染（4 提交关系 39 section） | [工程护栏]（选择失败降级边界） |
| seq_tools.py:4837–4857 | **B 相 per-terminal 配额 `n >= 3`** | 排序 key `(-coverage, len, gte_rank, name)`，配额按 (center, terminal-rel) 各 ≤3；1-hop direct 一等公民无配额 | 配额本体 `1bd5255` 2026-09-13（Charlie-Hunnam：per-center 配额让一个关系的模式挤掉另一个）；排序三段演化：step-coverage `bde6591` 2026-09-22、length-first `6e3e222` 2026-09-23（1379：GTE 序让 3 个题词 3-hop 绕行占满配额，唯一带 Priest 的 2-hop 出局） | [设计内]（三条 user ruling 可溯源） |
| seq_tools.py:4864–4874 | 选择失败 fallback top-3 | 语义选择异常时退回 length-first top-3 | `1c126bd` 2026-09-19（同上，异常吞掉后枚举无界） | [工程护栏] |
| seq_tools.py:4405–4410 | step-coverage 协方差图 | 命中锚树步关系集的模式优先（数步不数实体） | `bde6591` 2026-09-22（user design spec 2026-09-22） | [设计内] |
| seq_tools.py:4306–4335 | hop1 CVT 透明（一层，named-only） | center 一跳的 CVT 邻居贡献其全部 named 邻居（双向） | The-Ledge 标本（rev 方向 gold 支持计 0）；perf 重写 2026-09-17 | [设计内]（透明遍历语义） |
| seq_tools.py:4244–4250 | bridge-legal 免费派生回退 | 层判 infeasible 的提交关系并进 `_derive_multistep_seq(fam=infeasible 集)`（depth-2 枚举即桥接语义） | `9b12d35` 2026-09-23：21_——层可行性只认 1-hop 直连时 gpsh 模式整个缺席（f1 0.33→1.00） | [设计内]（user 裁定 2026-09-23：层关系允许"两跳内、提交关系收尾"） |

## 4. 层 3 — 链重建（`_rebuild_paths` 4438–4573 / `_rebuild_pe_list` 4576–4714）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_tools.py:4435, 4523–4524 | **`_REBUILD_BUDGET=400`** | 每跳层宽洪泛控制：`nxt` 超 400 截断（sorted 前 400） | `1751eb1` 2026-09-19（重建 lane 初版，"budget flood control (hub safety)"） | [工程护栏]（hub 防爆原型） |
| seq_tools.py:4529 | `sorted(level)[:budget]` | 回溯终点数同 400 预算 | 同上 | [工程护栏] |
| seq_tools.py:4451（单亲 DAG） | `parents` 单亲假设 | 每节点唯一 (prev, rel, passthru)；早跳已挂亲的节点默认不能再当终点 | 重建 lane 初版结构 | [设计内]（重建确定性）**单亲假设是 576/1812/1392 三连修的共同根因载体** |
| seq_tools.py:4461, 4488–4518 | 终点重发现（last-hop re-discovery） | 末跳允许已挂亲节点入终点层（`nxt.add(w)`），`term_edge` 记发现边 | 2026-09-21 audit ③（576/1812：18/23 roster 恰好丢被逆桥预挂亲的成员） | [设计外补丁]（对单亲 DAG 的语义修补） |
| seq_tools.py:4546–4559 | 末跳物化（materialization） | 链短于模式跳数且发现边自链尾发出时，补挂 submitted-rel 终跳边 | `caea2b4` 2026-09-24（Eleanor-1392：campus 自环让 hop-2 "成功"却无 campuses 边入链，渲染层 full-depth 检查丢弃） | [设计外补丁] |
| seq_tools.py:4562–4566 | **`_last_pat` 模式跳切分** | pattern hops 止于最后一条非 passthrough 边；`edges`=模式跳（license 要求 submitted 收尾），`full_edges`=含 CVT passthrough 全集 | `e9a10fd`（edges/full_edges 拆分）；统一组装 `601552b` 2026-09-21 | [设计内]（path-level admission 裁定 2026-09-12） |
| seq_tools.py:4603–4607 | **渲染 delta + fact 键** | `_shown_facts` = 方向归一 + 逆折叠（`_ctx_inverse_rels`/`_edge_fact_key`，seq_tools:784–840）的已积累事实；全旧链丢 | 渲染 delta user ruling 2026-09-20（取代 2026-08-20 全量重渲染）；fact 键 `7d8ee88` 2026-09-23（1731：同事实以逆关系 id 重入算"新"） | [设计内]（裁定可溯源） |
| seq_tools.py:4626–4636 | `_delta_new` | 丢掉"每条边都已展示"的链 | 同上 | [设计内] |
| seq_tools.py:4692–4711 | **空渲染回退** `_raw_fallback` | delta 吃光全部链时，重显第一条（打 `_repeat_evidence` 标 + UNCHANGED EVIDENCE note） | `1dd58f7` 2026-09-21：全旧调用渲染空 → 模型证据饿死进 reasoning/re-ask 循环（NO_EVIDENCE 5→0）；trivial lane 扩展 `601552b` | [设计外补丁]（与 delta 方向相反的补偿，见 §9.3） |
| seq_tools.py:4610–4617 | `_seen_roots` root 去重 | 折叠到同 root 的重复 center 只走一次 | chain-tree lineage | [设计内]（tree-keyed 裁定 2026-09-23） |
| seq_tools.py:4681–4685 | trivial fallback | 派生为空时提交关系本身作 root 锚 1-hop 模式（lane-2 删除后的统一路径） | `601552b`/`7d8ee88`/`a07add4` 2026-09-21..24 | [设计内]（统一裁定） |
| seq_tools.py:2374 | `max_grouped_lines=120` | 旧 walk lane（`SEQ_REBUILD=0`）的 evidence 行预算 | legacy | [工程护栏]（仅legacy 生效） |

## 5. 层 4 — 渲染

### 5.1 `collect_pattern_triples`（seq_triples.py，确认 lane 的准入）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_triples.py:23–33 | **`_collapse_rt` 折叠键** | 连续重复关系折叠（CVT mid 两边同关系：walked (r,r,f) ↔ key (r,f)）；"模式身份 = 去重关系序列" | `b75645f` 2026-09-15（user ruling 2026-09-15：CVT 遍历是展开细节不是模式跳）；实际路径接地 `56481cf` 同日 | [设计内] |
| seq_triples.py:65–70 | `_pkey` 排序键 | (提交终点优先, center 锚定, 长度, 字典序) —— "ORDER walked patterns, never cut" | `fe905d1` 2026-09-12 两层拆分 | [设计内] |
| seq_triples.py:73 | `_env_cap = 2` | **死变量**：`env_triples` 恒为空（260 行），此 cap 无消费者 | `9d53b94` 2026-09-19 清空 env 时遗留 | 死代码 |
| seq_triples.py:105–109, 186–189 | **`ADMIT_PER_TERM=3` 全局 per-terminal 预算**（含 selected 预填，预填本身也截 3） | B 相配额是 per-(center,terminal)，多 center 叠加 → 显示层按 terminal 全局再限 ≤3 | `1c126bd` 2026-09-19 A2（Colorado-River：多 center 3×N 叠加） | [设计外补丁]（对 B 相配额作用域错配的显示层再限；数值承接设计"direct + ≤3/terminal"） |
| seq_triples.py:149, 162–163 | **`ADMIT_TOTAL=24` 总 section 预算** | 多 center × 多 key 的 section 总数 ≤24 | `a95ec8a` 2026-09-20：Tempus-Unbound——8 terminal × N center = 125 section | [设计外补丁]（总显示预算，原始设计无总预算概念） |
| seq_triples.py:150–166 | `_a_seen` collapse 键去重 + `_key_count` per confirmed key ≤3 | 同折叠键只显一个代表；每个 selected key 的 raw 代表 ≤3（重建 lane 的 per-key 预算） | `1c126bd`/`a95ec8a` 2026-09-19/20 | [设计外补丁]（第三处 per-terminal 语义实现，作用域 = per selected key） |
| seq_triples.py:141 | **full-depth 检查 `len(_rel_t) >= len(_names)`** | 链边序列短于模式跳数 = 展开残骸（567：hop-1-only 链铸出裸标签）；**长于跳数保留**（537：mid-chain CVT passthrough 是合法桥接实例） | 短丢弃 `1ffe41e` 2026-09-23；长保留 `eb604a5` 2026-09-24（此前的等值检查把 537 的续渲染清零） | [设计内]（两步裁定均可溯源） |
| seq_triples.py:193–196 | 1-hop submitted-direct 通道 | 折叠后单关系且短名在提交序里的 raw tuple 直接入选 | `fe905d1` lineage | [设计内] |
| seq_triples.py:260–265 | `env_triples = []` | walked-but-unselected 边渲染零（无环境回退；键保留为接口兼容） | `9d53b94` 2026-09-19（user ruling：渲染层不做显示决策） | [设计内] |
| seq_triples.py:223–235 | section 域 attr 排除（typed） | mid 的 attr 折叠排除只在该 hop 实际渲染 CVT→named 边时生效 | `24353bbc` 修复 2026-09-15；typed 化 2026-09-21（537：named→CVT 单跳模式把自己的答案面排除掉） | [设计内] |

### 5.2 `render_rows`（seq_rows.py，行块车道体系）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_rows.py:17–21 | `_TAIL_CAP=40 / _HEAD_CAP=12 / _VAL_CAP=6 / _MULTI_MIN=3` | 出边尾合并截 40（+`#h::rel` 补全指令）、入边头合并截 12、值截 6、≥3 才合并 | `821b8f6`/`d3fd748` 2026-09-15/16（entity-block 设计）；补全指令 `1c126bd` A3 2026-09-19 | [工程护栏]（行长）+ 补全逃生口 [设计内] |
| seq_rows.py:20, 137 | **`_GROUP_CAP=10` 行块配额** | 实体块候选打分（center 优先 → CVT 连接 → 度数 → 字典序）后取前 10 做块主 | `d3fd748` 2026-09-16（entity-block v2）；块主机制 821b8f6 2026-09-15 | [设计外补丁]（渲染预算；车道布局是 user design 2026-09-16，**10 这个数是管线外加的配额**——1812 三重堵死的第一重） |
| seq_rows.py:92–109 | 车道体系：`cvt_owner` / `val_by_mid` 判别值车道 | 四类端点分流：named 出/入边成块；CVT 归属 owner；CVT→值边走 owner 块下的判别值行 | 判别值车道 2026-09-21（audit ③ 626：date/number 边无车道，模型弃答"无日期证据"）；入边 CVT 头补括号 `caea2b4` 2026-09-24（Eleanor-1392） | [设计外补丁]（车道按**值形状**判定，非声明类型——user design 的实现选择） |
| seq_rows.py:223–226 | **context-tail 车道拒 CVT 裸尾** | 未入块边的收尾车道：`not _cvt(t) or (t in cvt_kv and cvt_kv[t])`——CVT 尾必须带 walked attrs 才收 | 241 标本（CVT 头有 named 端点先放行）；**CVT-tailed 带 attrs 放行 `d9a7175` 2026-09-24**（1812：纯字面终跳 `Barbados --size_of_armed_forces--> g.xxx [number: 610]` 三重堵死的第三重修复） | [设计外补丁]（两轮打补丁的车道准入条件） |
| seq_rows.py:229 | `ctx[:_GROUP_CAP * 3]` | context-tail 输入截 30 条边 | `d3fd748` 2026-09-16 | [工程护栏] |
| seq_rows.py:42–45 | 无 center 回显 | store["centers"]（=root 名单）不回显（call 命令已含 center） | `883370b` 2026-09-24（user correction：重复而非长度问题，撤掉 5 条截断） | [设计内] |

### 5.3 `render_v38_ack`（seq_render_v38.py；multistep 空时走 5.1+5.2，否则旧车道）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| v38:136–151 | 路径数 >400 的 perf 守卫 | composite-first 片段抑制退化为后缀删除 | composite-first `1278d3da` 修复 2026-09-15 | [工程护栏] |
| v38:69–75 | `_edge_shown`（prior facts） | 边级先验去重：方向归一+逆折叠 fact 键对 `treq["prior"]` 查过 | `7d8ee88` 2026-09-23 | [设计内]（**与层 3 `_delta_new` 同键两层实现**，见 §9.2） |
| v38:108–114 | 同关系 out-and-back 抑制（要求节点回归） | r-then-反方向且回到访问过节点才删（CVT 桥合法走 r-then-f） | `b75645f` 2026-09-15 | [设计内] |
| v38:310 | `_K = SEQ_CVT_ATTR_TOPK=5` | 每 CVT 属性键 top-K（GTE 排序，超 cap 才启用；命中提交组件优先） | `eb6df5c` 2026-09-08（top-3）；`b884f77` 2026-09-11（3→5：initial_release_date #3 被切）；per-CVT 化 2026-09-12（Eleanor：institution #7/143 被全局门抹空） | [设计内]（user design 2026-09-08 pillar 4b 演化） |
| v38:431, 519 | `_CVT_COMPRESS_MIN=4` | ≥4 个 CVT 尾触发压缩摘要 | CVT-tail 压缩 user approval 2026-09-09 | [设计内] |
| v38:476, 485 | `_vcap_fam=SEQ_CVT_VALCAP=40` / 次键 8 | 家族键（匹配提交关系末段）值截 40，次键 8 | `b884f77` 2026-09-11（567/25：平铺 8 值 cap 恰切家族键答案面） | [设计内] |
| v38:566–579 | 行长 1200/600 字符折叠 | 超长合并行保留头部记录、余部折 attr 对 | structure-preserving fold 2026-09-03 | [工程护栏] |
| v38:694, 700 | `_ENV_ROWS_PER_REL=6` | 环境段每关系行数截 6 | `a1c2535` 2026-09-12（env capped 2 起家，后调 6；mid-hop 可见性 2026-09-12 Belgium 链路断裂修复） | [工程护栏] |
| v38:630–631 | roster `ns[:40]` | 段尾 roster 截 40（与 VALCAP=40 对齐的 roster 平价） | dda5d50-era 2026-09-07 | [工程护栏] |
| v38:175 | `SEQ_TIER_ANCHOR=0`（默认关） | tier-1 只认 center 锚链 | A/B -4.4pp（pathcons 0.6539/0.6661 vs 0.6978）→ 门控关 | [设计外补丁]（退役 A/B 记录） |
| v38:674 | `SEQ_BRIDGE_LABEL=0`（默认关） | 桥段落 bridge context 标签 | A/B hit 82.6→79.2 → 门控关 | [设计外补丁]（退役） |
| seq_tools.py:5419, 5115–5143 | **`_TOP_PATTERNS=5`** + 喂养保障 cap `top_n + 2*len(sel)` | 每 center 收集 pattern 截 5；带 center 锚 1-hop 提交关系见证的 pattern 超额保留（每关系 fwd+rev 各 1） | `b27320f` 2026-08-08（"excess patterns are noise"）；喂养保障 2026-08-26 walk-starvation 审计 | [设计外补丁]（finalize 收集预算，早于模式框架） |
| seq_tools.py:5750–5754 | `_TREE_LINE_BUDGET=200` | 总渲染行数截 200（+N truncated 行） | `58a3068` 2026-08-06 | [工程护栏] |
| seq_tools.py:919, 916 | `source [:15]` / `by_rel [:60]` | layer_evidence 语义层切层（`SEQ_EVIDENCE_LAYERS=0` 默认关） | V4 2026-08-24；两轮 cohort -4pp → 默认关 | [设计外补丁]（退役 A/B） |
| seq_tools.py:704, 737–780, 1535–1703 | **`_MERGE_TAIL_CAP=120`** | 旧 dense 车道（`_merge_edges`/`_format_*`/记录渲染）每行尾/头截 120 + branch ref 广告 | `dda5d50` 2026-09-07（WIP 大提交；V3 2026-08-24 dense 设计） | [工程护栏]（仅 v38 返回 "(empty)" 的 fallback 链路激活） |
| seq_tools.py:1017, 1298 | `_SHAPE_INSTANCE_CAP=3000` | 旧 evidence_sections 每 shape 实例枚举截 3000 | dda5d50-era | [工程护栏]（legacy） |
| seq_render_v36.py:36–48 | v36 `enum(cap=300)` | v36 渲染器每跳枚举截 300 | dda5d50-era | [工程护栏]（legacy A/B 车道） |

## 6. 调用层闸门（seq_harness，供完整性）

| 位置 | 机制 | 作用 | 引入 | 分类 |
|---|---|---|---|---|
| seq_harness.py:438–459 | sg per-center 预算 4 | 按声明起始实体计 retrieve_subgraph，>4 拒绝该 center（567：28-film 判别在旧 3×facts-per-sg 下饿死，cap 曾发 15 次） | user ruling 2026-09-20 | [工程护栏] |
| seq_harness.py:410–436 | rr per-center 预算 3 | 见 §1 | `9bef817` 2026-09-22 | [工程护栏] |

## 7. SEQ_* 环境开关全家

**默认开（代码默认 =1/正值）**：`SEQ_REL_SEQ`(1) `SEQ_REBUILD`(1)
`SEQ_PAT_SEMANTIC`(1) `SEQ_SEM_IDEMPOTENT`(1) `SEQ_LAYER_OPS`(1)
`SEQ_RR_UNION_RANK`(1) `SEQ_RR_GLOBAL_MERGE`(1) `SEQ_RR_BRIDGE_SLOTS`(3)
`SEQ_LICENSE_FILTER`(1) `SEQ_GHOST_EDGES`(1) `SEQ_CHAIN_TOPK`(3)
`SEQ_CVT_ATTR_TOPK`(5) `SEQ_CVT_VALCAP`(40) `SEQ_CVT_STYLE`(inline)
`SEQ_WALLEXTRA_CAP`(6) `SEQ_BUBBLE`(1) `SEQ_WIDE_COMMIT`(1)
`SEQ_POOL_VALUE_STUB`(1) `SEQ_RR_MERGE_CAP`(80，仅 GLOBAL_MERGE 下生效)。

**默认关（=0/空）**：`SEQ_MULTISTEP`(0——**但站立 rollout env 显式 =1**)
`SEQ_PATTERN_WALK`(0) `SEQ_PATTERN_PREFIX`(0) `SEQ_DIRECT_FIRST`(0)
`SEQ_TIER_ANCHOR`(0) `SEQ_SUBTERM`(0) `SEQ_EVIDENCE_LAYERS`(0)
`SEQ_DEBUG_CHAIN`(0) `SEQ_BRIDGE_LABEL`(0) `SEQ_FRONTIER_RENDER_K`(0)
渲染门 `SEQ_RENDER_V2/V35/V36/V37/V38`(空 → legacy V3.3；站立 env =V38)
`SEQ_PROMPT`(空；站立 =V23)。

**站立 rollout env**（SESSION_MEMORY 489–490 行）：
`SEQ_PROMPT=V23 SEQ_MULTISTEP=1 SEQ_RENDER_V38=1 SEQ_LICENSE_FILTER=1
SEQ_GHOST_EDGES=1 SPLIT=test_v4`。

**已作废**：`SEQ_BRIDGE_TERMINAL`（2026-09-23 `7d8ee88` 删消费方，env 不再读）。
调试：`SEQ_DEBUG_TREE`/`SEQ_DEBUG_WALK`/`SEQ_GHOST_DEBUG`/`SEQ_ZH_QUESTION`
（zh 已移出站立 env）。

## 8. 层间隐式契约表

| 边界 | 下游的输入假设 | 上游实际产出 | 错配史/风险 |
|---|---|---|---|
| prepare→execute/rebuild | `treq["centers"]` = 走路起点；`multistep`/`confirmed`/`cont_frontier`/`root_of` 键 = center idx | **centers 已被 root 折叠替换**（4073–4080）：键实际是 root idx；frontier center 只有经 `root_of.get(_ci,_ci)` 解析才命中 | `a07add4` 2026-09-24 前沿 center 掉出两 lookup、落 per-center 免费派生（537/241 execute 截断）。消费方现在有两条解析路径（4233、4614），漏一处即复发 |
| prepare→triples/rows | `store["centers"]` 是"本调用的 center"，rows 块打分 `e in centers` 优先 | 是 **root 名单**——模型提交的 center（typed roster 成员）不在集合里 | 1812 第一重：owner 失块优先级 → 掉出行块预算 |
| rebuild→render | paths.relations = 模式跳（submitted 收尾）；triples = full_edges（含 passthrough） | `_last_pat` 切分保证前者；但链边数 vs 模式名跳数在 CVT 双写/中链桥下**不相等** | full-depth 检查两连修（`1ffe41e`/`eb604a5`）：等值假设先杀残骸后又杀合法桥，现语义 = `>=` |
| v38→triples | `kept` 的 relsn 是"实际走过关系序列"（含 CVT 双写），与 selected 键经 `_collapse_rt` 对齐 | pattern hops 的实际 relations 确实含 CVT 双写（label 注释 240–242 明确保留） | 折叠键对齐是唯一桥梁；一侧改键宽即静默失配（见下条） |
| triples→rows | hops 键 `rel_short`（**last-2** typed）；rows 内部去重键 `_short_rel`（**last-1 小写**） | 同一关系两个键宽 | rows 的 last-1 键会把 triples 刻意分开的关系重新合并（division/facility/league 的 teams 正是 v38 改 last-2 的原因——rows 层未同步） |
| 全链 | CVT 判定 = `s[:2] in ("m.","g.") and len>4` | 4 份拷贝：`is_cvt_like`(traversal.cvt)、`_cvt_like_name`(seq_tools:3476)、`_cvt`(seq_triples:14 / seq_rows:24 / v38:34) | 当前等价；**id 节点（m./g. 前缀的非 CVT）与事件 CVT 同判**（`_trans_named_step` 注释明示），值型终跳 g.xxx 走 CVT 车道而非值车道 |
| 全链 | 值判定 | 3 份**不等价**实现：`_looks_like_value`(seq_tools:194，≥50% 数字或 UTC)、`_is_value`(seq_rows:29，≤14 字符+数字+无字母)、`_VAL_RE`(v38:26，日期/数字正则) | 同一字符串三处判定可不同（"610"全中；"1975-06"中两处；长 ID 只中 seq_tools）→ 车道分流不一致 |
| execute→prepare 状态 | `_sg_served` 键 = (center-idx 集, rel-idx 集) | 键建立在 root 折叠**之后**（4180），mark 在 finalize（5406） | 折叠把不同表面形收敛到同键（增益）；但 mark 存的是 root 键，若未来折叠策略变，缓存语义漂移 |
| frontier 契约 | `cont_frontier[root]` = 前 12 个末层 completions | prepare 里截 12；execute `_fr_of.get(_ci)` 以（已被替换的）centers 取 | >12 成员 roster 的 plain-step 只覆盖前 12（排序序），尾部成员的直连边只有模式链可承载 |

## 9. 同一语义多处实现 / 互相打架清单

1. **同一最终对象（一条渲染 section）上叠 7 层配额**：
   derive 天花板 60（4421）→ B 相 per-(center,terminal) ≤3（4854）→
   confirmed per-key ≤3（seq_triples:162）→ ADMIT per-terminal ≤3 含预填
   （seq_triples:105/187）→ ADMIT_TOTAL=24（149）→ `_TOP_PATTERNS=5` +
   喂养余量（5419/5129）→ `_TREE_LINE_BUDGET=200`（5750）→ 行层
   `_GROUP_CAP=10`/`_TAIL_CAP=40`/`_VAL_CAP=6`。任何一层独立调松都不可见。
2. **"已交付"判定四处、两处同键**：层 3 `_delta_new`（fact 键，链级）与
   v38 `_edge_shown`（**同一个** `_edge_fact_key`+`_ctx_inverse_rels`，边级）
   —— 同键两层串联；再上 `_sg_served`（语义键，调用级）与 finalize 后
   `accumulated_triples`（跨调用积累）。空渲染回退（`1dd58f7`）又**故意
   反转** delta 的结论把证据重显——同一对象上"去重"与"防饿死"方向相反。
3. **per-terminal ≤3 三处实现、三个作用域**：B 相按 (center, terminal)；
   triples 预填按 terminal 全局；confirmed lane 按 selected key。多 center
   场景三者叠乘后与设计计数（direct+3/terminal）的关系只在注释里成立。
4. **值形状检测 3 份不等价**（见 §8）；**CVT 检测 4 份拷贝**；**关系短名
   两种键宽**（last-1 vs last-2）跨层不齐。
5. **桥语义活在 3 处 + 1 处退役**：rr 保底槽（`0f6fa6b`，首屏前置）、
   sg expansion 桥 echo（审计显示，不入 rel_idxs）、derive 的 bridge-legal
   回退（`9b12d35`）；`SEQ_BRIDGE_TERMINAL` 已删消费方但 env 名仍散见于
   SESSION_MEMORY 记载。
6. **root 折叠 vs 多 center compare 契约**：折叠把 9-center roster 折成
   1 个 root，compare 框架只剩 `_cont_compare` note 文本承载
   （1278d3da 曾整案丢失）；rows 层的 `centers` 集合优先级随之失锚（1812）。
7. **死代码/半退役**：seq_triples:73 `_env_cap=2`（无消费者）；
   `env_triples` 恒空但 rows 仍保留消费循环（61–65）；`SEQ_BRIDGE_TERMINAL`
   作废；v35/v36/v37/v2 渲染车道 + `_MERGE_TAIL_CAP`/`_SHAPE_INSTANCE_CAP`
   仅在 v38 判 "(empty)" 的 fallback 链激活——**旧 cap 集合在主车道判空时
   重新接管语义**。
8. **depth cap=3 双执行点**：`_classify_seq_submit:3606`（层状态）与
   derive 1..3 枚举（4338）——注释声明有意对齐（"depth cap = derive's"），
   属同一语义的两处强制，改动需同步。
9. **单亲 DAG 假设 vs 终点重发现/末跳物化**：`_rebuild_paths` 的
   `parents` 单亲结构是重建确定性的核心，但 576/1812（2026-09-21）与
   Eleanor-1392（`caea2b4` 2026-09-24）两轮补丁都在给"早挂亲节点不能再
   当终点"这一假设打洞——`term_edge` 特例已渗入两个分支（4488–4518、
   4546–4559），同一"链完整性"语义散在发现与组装两端。
10. **frontier 三重不同截断**：rr frontier 池（`_rr_prepare` 3046–3056，
    不截）、`cont_frontier[:12]`（4157，步数）、rows context-tail
    `[:_GROUP_CAP*3]`（seq_rows:229，边数）——同一"frontier/剩余"概念
    三个数量级不同的边界。
11. **行块配额 × 树根折叠 × 车道拒 CVT 尾（1812 实锤组合）**：
    root 折叠使提交 center 失去块优先级（§8 行 2）→ 21 center 填满 10 块
    预算 → 纯字面终跳（CVT 尾带值）被 context-tail 的 `not _cvt(t)` 拒收
    → submitted 关系的终跳全链无车道。`d9a7175` 只修了第三重（带 attrs
    放行），前两重仍在。
12. **`_select_patterns_for_render` 喂养保障 vs `_pe_filter`**：finalize
    先超配额保留 center 直连 pattern（5115），再由 `_pe_filter`（5441，
    `SEQ_SUBTERM=0` 默认关）可能整条滤空——保障与过滤互不知情（当前
    因 SUBTERM 默认关而休眠）。

---
*盘点方法：全量 `grep` + 逐段精读 + `git log -S <常量>` 溯源（`--date=short`）；
commit 动机取自 commit message 与代码内注释段。行号均指当前
`audit/gpt6-2026-09-23` HEAD（1219a7c）。*
