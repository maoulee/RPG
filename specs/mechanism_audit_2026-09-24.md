# 机制深度审计 — 根源分析与清理方案 — 2026-09-24
（材料：mechanism_inventory_2026-09-24.md 60 机制盘点 / code_map_for_review_2026-09-24.md /
audit_report_2026-09-23.md 修复链 / 本段 16 修复 commit 史）

## 一、为什么这么多 bug——三个结构性根源（与盘点发现互证）

### 根源 1：隐式契约的层间漂移（16 bug 中 ≥8 个）
层间传递三种形态，假设写在注释里而非数据结构里：
- 键形态（center/root/fid/canonical fid）→ 树键归一 bug(a07add4)、rescue 池键 bug(88c7407)
- 边形态（pattern hops / full_edges / walked seq）→ 残段(1ffe41e)、终跳边(caea2b4)
- 实体形态（named/CVT/id/literal）→ CVT 起点侧、纯字面值终跳、answer 收割 list-当-dict(58d246a)
盘点互证：root 键解析现有**两条路径**（seq_tools 4233/4614）漏一处即复发；谓词碎片化
（CVT 检测 4 份、值检测 3 份**不等价**、短名键宽 rows=last-1 vs 其余=last-2——rows 的去重
键会重新合并 triples 层刻意分开的关系）。

### 根源 2：设计外补丁的累积（cap/折叠/车道）
原始设计（5 月 k_queue + 裁定链）的答案是**选择层收紧**（模式选择 per-terminal topk）；
实际演化在每个 flooding 事件当层打 cap——盘点实证：**同一 section 叠 7 层配额**
（derive 60→B相3/terminal→confirmed per-key 3→ADMIT 3/terminal+24 总→_TOP_PATTERNS 5
→行预算 200→块预算 10/40/6），任何一层独立调松不可见。1812 三重堵死（根折叠→GROUP_CAP
→车道拒 CVT 尾）是叠加必然：d9a7175 只修了第三重。另发现 legacy 车道在 "(empty)" 时
**整条重新接管**（含旧 cap 集），死代码（_env_cap、SEQ_BRIDGE_TERMINAL）仍在。

### 根源 3：同一语义多处实现
- per-terminal ≤3 有**三个不等价作用域**实现（(center,term)/全局 term/per selected key）
- "已交付"判定**四处**（层3 delta 与 v38 edge_shown 共用 fact 键但空渲染回退又反转其结论）
- 单亲 DAG 假设承载 576/1812/1392 三轮补丁（终点重发现+末跳物化渗入两分支）

## 二、清理方案（供裁定，按依赖序）

### C1 谓词与键的单一事实源（先做，无行为变化的收敛）
- CVT/值/短名判定收敛为模块级一组函数（实体四类 named/CVT/id/literal 的显式分类器）；
  短名统一 last-2（rows 的 last-1 修齐——注意它当前把刻意分开的关系重新合并，修齐即行为修正）。
- root 解析收敛为唯一函数（prepare/execute 两处调用点改引）。
- fact 键（_edge_fact_key）唯一化，delta/edge_shown/回退共用同一判定，回退不再反转结论。

### C2 cap 收敛到选择层（设计原则贯彻：选择层决定走什么，walk/render 零决策）
- 保留：B 相语义选择 per-terminal quota（设计内）、derive 枚举天花板（工程护栏，防爆）。
- 删除/降级为纯显示压缩：ADMIT_TOTAL/ADMIT_PER_TERM、_TOP_PATTERNS、_GROUP_CAP/
  40/6 块预算、行预算 200、层叉积≤24、family[:10]/桥[:6]、cont_frontier[:12]。
- 原则：**信息丢失型 cap 必须只存在于选择层；渲染层的 cap 只许视觉折叠（合并行），
  不许丢边**。补渲染层"预算内放不下时合并为紧凑行而非丢弃"的机制。

### C3 车道体系简化
- rows 的 blocks/context-tail 多车道 → 单通道模式驱动（pattern 的 hops/attrs 忠实呈现）；
  车道准入的形态假设（centers 在/root 折叠后）随 C1/C2 消解。
- legacy 车道（"(empty)" 重新接管）退役路径：显式开关 + 删除死代码。

### C4 根折叠改显式 root 传递
- _root_of 折叠改为 treq 显式携带 (root, centers[]) 结构，下游不再从 center 反推；
  块优先级按"本调用实际走的树"而非 center 数量。

### 验证策略（不跑批循环）
- 每步 C 后：离线重放器套件（tmp/replay_537/1392/1812 已有 3 个标本）回归 +
  pytest 153 + 单案探针抽查；C1-C4 全部完成后跑一轮 48×3 终验（对照 0.667/75.0）。

## 三、Codex 远程审计发现并入（2026-09-24，基准 06ef8fc）

已复现断点（与三根源对照）：
- [根源3] 单亲 DAG：两路径汇合同一实体第二条丢失；两 CVT 指向同一实体只留第一
- [根源1] "三跳成功"链无第三跳关系（边数校验把中间 CVT 额外边算入未拦）
- [根源1] step 覆盖分数写入键≠读取键；入边"返回全部"展开后返回相反侧实体
- [根源1] 折叠 CVT 模式时跳过另一组实例
- [根源2] 多中心一个无邻边→派生返回类型不一致→外层异常清空全部中心→NO_EVIDENCE
- [根源2] 第 11 实体数值被显示预算丢弃但已入证据累计→重查提示"已在上下文"
  （幂等缓存与渲染丢失的矛盾——"怎么查都显示不出来"）
- [根源2] 提示语承诺"同一关系证据完整展示" vs 渲染按模式数/块数/属性值截断

## 四、最终清理纲领（用户拍板 2026-09-24）

**数据通道统一**：设计本质 = 模式层游走 → 记录模式路径 → 模式路径还原实体证据，
全程参变量（键/边/实体形态/谓词）一致。
**折叠白名单**（仅两处）：
1. 模式数量的选择（选择层：粗排=长短+step命中 → top-20 GTE 细排 → per-terminal 取舍）
2. 超级叶子节点（同 h+r 的海量 t 合并/截断，视觉折叠不丢可达性）
其余一切 cap/折叠/车道全部移除或降级为纯视觉折叠（不许丢边）。
执行序不变：C1（变量统一）→ C2（cap 收敛）→ C3（车道简化）→ C4（显式 root）。
