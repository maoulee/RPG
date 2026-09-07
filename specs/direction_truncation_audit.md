# 方向与截断全链路审计（2026-08-19）

触发标本：Bernie Brewer（Option-B 扇出锚方向错）、Greeley（hop 门集合级误剪）、
r267 错误集复查。用户裁定：这类潜在 bug 较多，需要对照原始设计做一次系统审计，
而非继续打地鼠。

## 0. 设计不变式（审计基准，用户口述）

1. **无向游走**：`KGQA_DIRECTED_TRAVERSAL=0`（默认），边可从任一侧进入。
2. **同路径不回环 = 边级约束**：同一条边不可在同一路径复用；已知逆对
   （contains/containedby）不可重建已建立的边。**节点经不同关系重访合法**。
3. **CVT 透明延展**：CVT 无自身身份，进出皆可穿透，入口/出口对称。
4. **出口方向约束只存在于模式路径裁决层**：末跳必须骑选中关系
   （`_hop_ok`），游走与枚举本身不做方向假设。

## 1. 审计范围

游走（logical_paths `_hit_paths` / k_queue / RPE）→ 伴生收割
（`_collect_hr_frontier` / `_last_step_candidates`）→ 压缩物化
（compress_paths / materialize）→ 证据（formatting.build_pattern_evidence_triples）
→ 展示（seq_tools `_canonicalize_triples` / `_render_records` / `_chain_is_cyclic`）
→ 池（`_reach2_relids`）。

## 2. 判定总表

| # | 站点 | 类 | 判定 | 说明 |
|---|------|----|------|------|
| A1 | `_hit_paths` CASE A：选中关系 1-hop 命中后 `continue`，不穿命名节点延伸 | 截断 | RISK·开放 | 见 §3.1（方向运气） |
| A2 | CASE A 的 CVT 延展 | 方向 | OK | adj 无向，对称 |
| A3 | CASE B：仅首跳关系 ∉ 选中集时启用 | 截断 | RISK·开放 | 见 §3.1 |
| A4 | CASE C：仅 nb1-CVT（nb2-CVT `continue`） | 截断 | **RISK** | end→命名→CVT→target 形状不可达；与 CVT 透明哲学不对称（CVT 在第 2 位不透明）。注释自认 kept narrow |
| A5 | 边级防回环（`e in used_edges`） | 回环 | OK | 正是设计语义 |
| A6 | `_prune_states` max_states=1200，tiebreak 含 `nodes[-1]` 实体表序 | 截断 | **RISK** | 任意序静默丢态（方向中性） |
| B1 | `_collect_hr_frontier`：`(h_id,r_id) in hr_pairs` 用路径序匹配 | 方向 | **BUG 级** | 逆向遍历跳永不命中 → 逆向跳的兄弟尾零枚举（正向跳有）。当前仅喂 cs.all_subgraph_nodes（诊断/边界），影响中低，但属机制缺口 |
| B2 | `_last_step_candidates` | 方向 | OK | 节点集操作，无向 |
| B3 | k_queue / RPE 的 adj | 方向 | OK | 双侧索引 + DIRECTED 开关 |
| C1 | compress_paths `_has_non_cvt_loop`：非 CVT 节点重访→整条路径丢弃 | 回环 | **BUG 级（偏离设计）** | 设计是边级；节点级丢弃比设计严。SEQ 单步（深度≤3）几乎不踩，多步/legacy 流会静默丢循环 witness |
| C2 | pattern key=(rel_chain, endpoint)，readable 一律 `-->` | 方向 | RISK（旧通道） | 同边两方向同 key 合并 OK；箭头谎言仅在 readable/tree 旧渲染通道，retrieve_subgraph 现走 `_canonicalize_triples` |
| C3 | trailing-CVT 只保留 1 跳尾巴 | 截断 | OK | 有意图的经济截断 |
| C4 | `cands[:20]`（字母序）、raw_paths[:200] | 截断 | **RISK** | 字母序任意；>20 叶 pattern 候选被砍，gold 排序无保证 |
| D1 | hop 门 per-relation（本日修复） | 方向 | OK | Greeley 标本 |
| D2 | support/Option-B `_true_edge` 顺向 + 扇出锚真实边头（本日修复） | 方向 | OK | Bernie 标本 |
| D3 | `_expand_sibling_cvts`：`edge_h != prev_idx` 仅正向父边 | 方向 | **BUG 级** | CVT 兄弟枚举仅当 prev 是边头；prev 作为尾（CVT --r--> prev）时无兄弟。与不变式 3 不对称 |
| D4 | CVT BRIDGE 显式构造（`_cvt = _et if _eh==anchor else _eh`） | 方向 | OK | 双向找 CVT，对称 |
| D5 | 预算叠加：support 24 / grouped 120 / _TOP_PATTERNS 5 / candidates[:60] / TREE 200 | 截断 | RISK | 多层截断有告知文本；最坏叠加 5×120 行 |
| E1 | `_canonicalize_triples` | 方向 | OK | 双向查表，前向优先；CVT 保序有理（CVT 是其出边的天然源头） |
| E2 | `_chain_is_cyclic` + `_INVERSE_PAIR` | 回环 | OK（小缺口） | 边级+逆对正合设计；逆对表手工 6 对，未知逆对（spouse 等）不抑制→重复显示，低害 |
| E3 | `_render_path_tree`（旧 stage7 通道） | 方向 | RISK | 路径序箭头；确认未被 retrieve_subgraph 使用，归渲染重写批次 |
| F1 | `_reach2_relids` / `_anchor_outgoing_rel_ids` / `_expand` | 方向 | OK | h/t 双侧、CVT 透明 BFS |

## 3. 开放裁决点（需要用户裁定，不擅动）

### 3.1 方向运气（A1+A3 联合）——已裁决实施（2026-08-19，见 SESSION_MEMORY 同日条目：原设计恢复）

Greeley 的 `school_type` 2-hop 之所以被游走发现，是因为图里**恰好同时存在**
`Greeley --contains--> Aims`（选中，CASE A 截断）与
`Aims --containedby--> Greeley`（未选中，CASE B 放行）两条方向边，witness
碰巧走了后者。若数据只有单方向边，该 2-hop 载荷关系在游走层即丢失
（证据层无从补救——没有 witness 就没有 pattern）。

修法候选：CASE A 命中后**也**允许穿命名节点做第二跳（首跳∈选中 + 末跳∈选中的链）。
但 Nordics 数据存在 `Nordic --contains--> Scandinavia --contains--> Sweden/Norway/Denmark`
同关系链，而证据层 hop 门对"中跳∈选中"是放行的（`if r_ in _sel_ids: continue`）
→ 直接开启会**重新放进已裁决剪除的回指绕路**。安全开启的前提是 hop 门新增一条：
**中跳关系 == 末跳关系 且 末跳关系在中心有直连 → 拒绝同关系链**（同关系链只在
该关系无直连时合法，即 Greeley 形状 contains→school_type；Nordics 形状
contains→contains 因 contains 有直连被拒）。这是新裁决，待批。

### 3.2 A4（CASE C 的 nb2-CVT 形状）

`center --命名-- CVT --target--> X` 目前不可走（CASE C 只认 nb1-CVT）。
真实形状示例：`city --location--> CVT --governing_official--> person` 少见但存在。
开启需防 CVT→CVT 爆炸（现有 CASE C 已防）。低优先，等标本。

### 3.3 C1（节点级回环）

改 `_has_non_cvt_loop` 为边级（复用 `_chain_is_cyclic` 语义）即回归设计。
SEQ 单步流影响极小，改动廉价，可与 P0 批一起。

## 4. P0 修复清单（机制性方向缺口，建议本批）

1. **B1** `_collect_hr_frontier`：hr_pairs 匹配前先做方向归一（对每跳查真实
   (h,r) 方向，两侧都试）。
2. **D3** `_expand_sibling_cvts`：父边匹配放宽为方向无关（prev 是头或尾皆可，
   兄弟=同 (prev, rel) 对的另一端为 CVT 的边）。
3. **C1** compress_paths 回环判据边级化。

三处均为"方向无关化"纯收敛修复，不改变任何已裁决的剪除语义，fixture 门
（Nordic/Ethiopia/Greeley/Bernie 四案）+ 全量回归即可验证。

## 5. P2（截断经济性，归渲染重写批次）

A6 tiebreak 任意序、C4 字母序 [:20]、D5 预算叠加、E3 旧树通道箭头。
统一在渲染重写（specs/rendering_mechanism_design.md）的三经济律下重设计，
不逐点补丁。
