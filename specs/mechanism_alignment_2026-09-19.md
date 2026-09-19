# 游走机制对齐定稿（2026-09-19，用户裁定集 + 现状差距审计）

> 定位：游走-选择-渲染机制的唯一权威描述。实施按本文；历史迭代残留
> 标注为 ARCHIVED。前身审计：behavior_audit / 三次 render_diff 循环。

## 一、机制定稿（三层分立）

```
模式层（不变——已是主干）：
  CVT 抽象为超节点（关系压缩到超节点上）；
  枚举/排序/选择全在模式空间（关系集合操作，毫秒级）：
    derive（首调广撒网：深度 1-3、终点=提交关系族、cap 60）
    _patterns_from_layers（续调：declared 层链笛卡尔 + 可行性 + top-K=3）
    B 相选择（per center×terminal top-3，GTE 语义排，1-hop 全过）
  爆炸三层收口：模式选择 top-3 → 层链 top-K → （重建层实例 cap）
  链式接力为正式机制：h 为中心 ≤2 跳内以 r1 为末跳的路径确认 →
  终点实体接力 r2（同规则）→ 模式路径按长短+命中排序。首调整链枚举
  = 无树时的广撒网特殊形态。
  多中心 = 关系确定基准（非检索起点）：第二三轮是对 step 关系的
  修正与添加；游走永远从真实起点/根出发。

重建层（新——替代 beam 搜索）：
  沿每条选中模式路径确定性逐跳取边（邻接倒排，无搜索无 beam）；
  落点 CVT 时穿透其边续走（_trans_named_step 语义），CVT 节点
  保留在链上供属性内联；
  只保留贯通实例链（走完整条模式路径——h 的 r1-邻居中续不了 r2
  的 t 不算，"有些 t 不在路径上"）；
  搜索已完毕（模式层完成），重建不做搜索；
  实例 cap（洪泛控制，继承 budget 200/模式语义）。

渲染层（收口）：
  每个贯通实例链逐跳渲染三元组（同头多实例合并尾=压缩格式）；
  头/尾实体是 CVT 时展开内联属性（判别信息来源——判别器家族全在
  CVT 属性上）；
  只渲染路径上的边——块实体的非路径邻居边不渲染；
  预算=选择层控制（渲染只对实际渲染的模式计数，selected key 计 1，
  与 raw 变体数无关）；
  bridge=中跳衔接（h 的多 t 承担下一跳头实体职责），永远不是终点，
  不铸造渲染段。
```

## 二、现状差距（本次审计结论）

| # | 差距 | 现状锚点 | 处置 |
|---|---|---|---|
| 1 | merge 拍平丢弃模式→确认路径映射，渲染靠名字匹配，CVT 形式错配致异构多跳全灭 | seq_tools 4411-4428; seq_triples 名字匹配 | 重建器天然产 confirmed 归档，渲染直读 |
| 2 | 最后一步是 beam 搜索（logical_paths，beam=80+witness 收集）非重建 | logical_paths._hit_paths | 主干摘除（ARCHIVED），重建器替代 |
| 3 | 渲染含块实体全边（"FULL evidence"语义+环境尾注）——路径外边混入 | seq_triples env/块全边 | 只渲染 confirmed 链 |
| 4 | bridge 入 rel_names/_sub_sh → bridge direct 段 | seq_tools 3808-3811; seq_triples 49-52 | bridge 中跳化，出终点资格 |
| 5 | 预算前置花在永不匹配的 selected 上 | seq_triples 预填 | 后置：只计实际渲染 |
| 6 | PG 穷举补块（实例完备补丁，except 吞） | seq_tools 4437-4495 | 删除（用户裁定） |
| 7 | step→pe 管线 4 份重复 + 3 层 quota 重复 | 2370/2264/2333/2610 | 单管线（重建器本体）；其余 ARCHIVED |
| 8 | 死码：_admit_terms/_env_cap/treq["prior"]/_sg_served(零命中) | 各处 | 清理 |
| 9 | 实验 flag 默认关 ×5（PATTERN_WALK/PATTERN_PREFIX/DIRECT_FIRST/SUBTERM/EVIDENCE_LAYERS） | 各处 | ARCHIVED 标注 |

## 三、重放性能构成（审计结论）

重放跑完整 dispatch（A/B/C 三相）非"只渲染"：walk beam 搜索 ~400s +
GTE 真调用 ~150s + 16 轮批窗 ~200s。重建式落地后 walk 变确定性取边
（毫秒×实例数），重放应接近纯 IO 速度；GTE 跳过 flag（渲染对比场景）
可再省 GTE 段。

## 四、实施与验证（批准的计划）

按差距表 1-8 实施；验证：pytest → 36 条重放（速度+567 标本：异构多跳
回归、路径外边消失、模式数 ≤16）→ render_diff v3 → 48×3 对比 0.7177
（最终权威）。风险：beam witness 消失致判别变薄——CVT 内联属性为主
来源，判别器四家迷你+全量确认不回退。
