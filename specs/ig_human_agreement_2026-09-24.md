# IG(RSCC v3) vs 人类审阅者一致性研究 — 2026-09-24

数据源：`specs/rscc_v34ig_dump_2026-09-22.md`（16012 行，48 问 × 3 seed = 144 段轨迹）；
机器判决结构化数据取自 `specs/rscc_v34ig_2026-09-22.json`。

## 1. 方法

1. **抽样**：从 144 段中按 f1 分层选 12 段（4 高 f1=1.0、4 中 f1∈[0.333,0.667]、
   4 低 f1=0.0），同时要求覆盖 RSCC 四类判决（informative / harmful /
   redundant / 弃权保留）。12 段共 40 个块，其中结构保护块 10 个（不进对照），
   **非结构块 30 个**进入人机对照。
2. **盲审**：对每段生成"盲视图"（脚本剥离 p0/pF/通路概率/L 锚/Δp/R/label/
   收缩迹，仅保留 Q、gold、实际答案 f1、每块的调用命令 + 完整工具结果 +
   送评归属行），按块顺序阅读，独立给四档判定：
   informative（证据直接支撑答案推导）/ harmful（引入干扰或歧义）/
   redundant（与已有证据重复或与问题无关）/ uncertain（人拿不准），
   每块记一句理由。判定全部完成之后才回看 RSCC 数字。
3. **对照**：人档 vs RSCC 原 label（informative/harmful/redundant）与
   实际处置（保留/移除/弃权保留），统计一致率并列分歧清单。

已知口径差（dump 实现与判据文本不一致，对照时以 dump 为准）：
- v3 文本说 harmful=Δp≤−5pp，但 v34ig 实际在 Δp=−0.48pp 也判 harmful→移除
  （1731|s0 块#1）；
- v3 文本说 redundant→保留，但 v34ig 对可测的 redundant 块执行**移除**
  （576|s0 块#1/#3、567|s2 块#3、2152|s0 块#2），仅 L<0.02 弃权时才保留；
- L<0.02 或 L≤0（通路独立反而降概/通路未达 gold）→ R 记不可靠，仅剩
  Δp≥5pp 强效一条路可判 informative（harmful 方向无此豁免）。

## 2. 12 case 清单

| # | case（短 id + seed） | Q（缩写） | gold | f1 | 非结构块 |
|---|---|---|---|---|---|
| 1 | WebQTrn-1731…\|s0 | Randy Jackson 在 Eclipse Tour 演什么 | Bass guitar, Vocals | 1.0 | 3 |
| 2 | WebQTest-1379…\|s2 | Liszt 何职业使他领导宗教组织 | Priest | 1.0 | 2 |
| 3 | WebQTest-1171…\|s1 | 75th Ranger 团里给 Darth Vader 配音者 | James Earl Jones | 1.0 | 2 |
| 4 | WebQTest-1797…\|s0 | Vicksburg 参战者中谁最早去世 | John C. Pemberton | 1.0 | 2 |
| 5 | WebQTest-576…\|s0 | 中美七国谁区号最大 | Panama | 0.5 | 6 |
| 6 | WebQTrn-124_6655…\|s0 | Jolie 执导的 drama 电影 | ITLOBH, Unbroken | 0.667 | 1 |
| 7 | WebQTrn-2576…\|s0 | Falkland 所属(ETZ)国在哪个大洲 | Americas | 0.667 | 2 |
| 8 | WebQTrn-25_7cec…\|s0 | Lautner 主演的获奖提名 Meyer 改编电影 | New Moon | 0.333 | 2 |
| 9 | WebQTrn-567_df97…\|s2 | Ron Howard 的神童题材电影 | Village of the Giants | 0.0 | 3 |
| 10 | WebQTrn-2152…\|s0 | AL West 哪队成立最晚 | Anaheim Angels | 0.0 | 2 |
| 11 | WebQTrn-452_343e…\|s0 | CO2=0.111… 且是 Lala Anthony 家乡 | Brooklyn | 0.0 | 4 |
| 12 | WebQTrn-493…\|s0 | Belgium 在 GMT 时区的哪里 | Europe | 0.0 | 1 |

## 3. 逐块对照表（30 块）

人=human 档；R=RSCC 原 label；处置=保留/移除/弃权；Δp=per-gold maxΔp（pp）；
R 值=最大有效 R；一致=原 label 与人档完全一致。

| case | 块 | msg | 人 | R | 处置 | Δp(pp) | R值 | L锚 | 一致 |
|---|---|---|---|---|---|---|---|---|---|
| 1731\|s0 | 1 | 10 | informative | harmful | 移除 | −0.48 | −3.25 | 0.034 | ✗ |
| 1731\|s0 | 2 | 18 | informative | informative | 保留 | +4.10 | 1.20 | 0.034 | ✓ |
| 1731\|s0 | 3 | 30 | redundant | redundant | 弃权 | −0.41 | – | 0.007 | ✓ |
| 1379\|s2 | 1 | 12 | redundant | redundant | 弃权 | −0.01 | – | 0.000 | ✓ |
| 1379\|s2 | 2 | 17 | redundant | harmful | 移除 | −5.75 | −0.81 | 0.071 | ✗ |
| 1171\|s1 | 0 | 5 | harmful | harmful | 弃权(留) | −25.59 | – | −0.25 | ✓ |
| 1171\|s1 | 1 | 10 | informative | informative | 保留 | +31.26 | 1.00 | 0.31 | ✓ |
| 1797\|s0 | 0 | 5 | informative | informative | 保留 | +24.72 | 1.00 | 0.25 | ✓ |
| 1797\|s0 | 1 | 13 | informative | informative | 保留 | +51.31 | 1.00 | 0.51 | ✓ |
| 576\|s0 | 1 | 9 | redundant | redundant | 移除 | +0.87 | 0.11 | 0.077 | ✓ |
| 576\|s0 | 2 | 13 | redundant | informative | 保留 | +1.31 | 0.17 | 0.077 | ✗ |
| 576\|s0 | 3 | 17 | redundant | redundant | 移除 | −3.35 | −0.43 | 0.077 | ✓ |
| 576\|s0 | 4 | 23 | redundant | redundant | 弃权 | +0.00 | – | 0.011 | ✓ |
| 576\|s0 | 5 | 28 | redundant | redundant | 弃权 | −0.00 | – | 0.011 | ✓ |
| 576\|s0 | 6 | 32 | redundant | redundant | 弃权 | −0.00 | – | 0.011 | ✓ |
| 124_6655\|s0 | 1 | 10 | harmful | harmful | 弃权(留) | −4.63 | – | 0.16* | ✓ |
| 2576\|s0 | 1 | 11 | informative | informative | 保留 | +16.21 | 1.46 | 0.11 | ✓ |
| 2576\|s0 | 2 | 15 | redundant | harmful | 移除 | −5.11 | −0.46 | 0.11 | ✗ |
| 25_7cec\|s0 | 1 | 13 | redundant | informative | 保留 | +5.16 | – | −0.17 | ✗ |
| 25_7cec\|s0 | 2 | 19 | redundant | informative | 保留 | +5.89 | – | −0.17 | ✗ |
| 567_df97\|s2 | 0 | 5 | uncertain | redundant | 弃权 | −0.74 | – | 0.007 | ✗ |
| 567_df97\|s2 | 2 | 17 | redundant | harmful | 移除 | −6.61 | −0.11 | 0.62 | ✗ |
| 567_df97\|s2 | 3 | 25 | informative | redundant | 移除 | +2.05 | 0.03 | 0.62 | ✗ |
| 2152\|s0 | 2 | 17 | redundant | redundant | 移除 | +4.36 | 0.09 | 0.50 | ✓ |
| 2152\|s0 | 3 | 21 | informative | informative | 保留 | +39.97 | 0.80 | 0.50 | ✓ |
| 452_343e\|s0 | 0 | 11 | redundant | redundant | 弃权 | −0.01 | – | 0.000 | ✓ |
| 452_343e\|s0 | 2 | 19 | redundant | redundant | 弃权 | −0.03 | – | 0.000 | ✓ |
| 452_343e\|s0 | 3 | 23 | redundant | redundant | 弃权 | +0.58 | – | 0.006 | ✓ |
| 452_343e\|s0 | 4 | 29 | redundant | redundant | 弃权 | −0.01 | – | 0.000 | ✓ |
| 493\|s0 | 1 | 12 | informative | redundant | 弃权 | +1.47 | – | 0.0145 | ✗ |

\* 124_6655 块#1 通路 L 对两 gold 分别为 −0.046/−0.162（均负→通道不可靠）。

人档理由摘录（每块一句，按表序）：
- 1731B1：Eclipse Tour→Journey 是解题必需的中间链路（tour→band）。
- 1731B2：Journey 成员表里 Randy Jackson role=Bass guitar|Vocals，直接支撑 gold。
- 1731B3：查的是其他成员（Cain/Schon）的乐器，与问题无关。
- 1379B1：书目/题献证据，与"职业/宗教组织"无关。
- 1379B2：religion=Catholicism、Freemasonry 相邻但非职业，无增量（轻度干扰）。
- 1171B0：返回 Matt Sloan/Reiner Schöne 两个错误配音候选，纯干扰。
- 1171B1：75th RR servicemembers 直接列出 gold（James Earl Jones）。
- 1797B0：给出 Vicksburg 全部参战者候选集（含 gold Pemberton）。
- 1797B1：拿到 Pemberton 死亡日期 1881，是"最早去世"的决定属性。
- 576B1–B6：全程没查 calling code；旅行社/语言/时区/人口均为无关游走（B2 只是
  重复确认国家列表）。
- 124B1：Drama 片单不含两部 gold，反而引入 Gia 等非执导片干扰。
- 2576B1：Europe/Americas 时区关联支撑 gold 链路。
- 2576B2：重复 #0 的 containedby 信息＋大量国家名单噪声。
- 25_7cecB1/B2：系列结构边（prequel/series）不提供 Meyer 作者判据，不能筛选
  出唯一 gold。
- 567B0：Howard 执导片单是 join 的一侧候选池，但 gold 不在其中（"did"≠directed），
  拿不准 → uncertain。
- 567B2：重复 #1 的同一条 subject 边。
- 567B3：Village of the Giants starring→Ron Howard [character: Genius]，是
  gold 与问题实体的直接 join 边。
- 2152B2：team_stats CVT 引用无日期可读，重复 #1。
- 2152B3：Anaheim Angels founded 1997，唯一可比成立日期。
- 452B0/B2/B3/B4：查 Carmelo 兄弟/出生地/地理编码，既非 Lala 家乡也无 CO2。
- 493B1：Europe 的时区表含 GMT，把问题里的 GMT 与 gold（Europe）关联起来。

## 4. 统计

- **原 label 四档严格一致：20/30 = 66.7%**。
- 仅看 RSCC 有实际判决的 17 块（非弃权）：一致 9/17 = **52.9%**。
- 弃权 13 块中，其携带的原 label 碰巧与人档相同 11 块（9 redundant + 2 harmful），
  不同 2 块（493B1 informative、567B0 uncertain）。
- **动作层（留/删）一致：22/30 = 73.3%**——但完全由"双方都保留"构成：
  - RSCC 移除的 8 块，人审**一块都不赞同删**（1 块人判 informative、7 块人判
    仅 redundant）；
  - 人审要删的 2 块（1171B0、124B1，Δp=−25.6/−15.3pp）反而因 L 锚不可靠被
    弃权保留。
- 按 f1 分带一致率（原 label）：高 7/9（78%）、中 7/11（64%）、低 6/10（60%），
  概率通道在高分 case 上并未更贴合人审。
- 按 RSCC label 的人审"查准率"：informative 6/9（67%）、harmful 2/6（33%）、
  redundant 12/15（80%）、弃权→其中 9/13 为人审 redundant（弃权大体无害）。

## 5. 分歧清单（10 例原 label 分歧 + 2 例动作分歧）

| 块 | 人 | RSCC | 数字 | 可能原因 |
|---|---|---|---|---|
| 1731\|s0 B1 | informative | harmful(移除) | Δp=−0.48pp, R=−3.25 | 桥接边（tour→band）价值由其他块承担概率，删除后 P(gold) 变化在噪声内；且 −0.48pp 远低于判据文本的 −5pp，v34ig 的 harmful 实现过松 |
| 1379\|s2 B2 | redundant | harmful(移除) | Δp=−5.75pp | Freemasonry 等成员信息确实稀释 P(Priest)，但人认为属"无增量"而非干扰；−5pp 线刚过即删 |
| 576\|s0 B2 | redundant | informative(保留) | Δp=+1.31pp, R=0.17 | 分享通道无 Δp 下限：1.3pp 噪声 + R 刚过 0.10 即判 informative；内容只是重复国家列表 |
| 25_7cec B1 | redundant | informative(保留) | Δp=+5.16pp, R=– | 强效阈值在负 L（通路独立降概）的退化通道上触发；系列结构边放大了答案集合（过生成）却被读作"信息增益" |
| 25_7cec B2 | redundant | informative(保留) | Δp=+5.89pp, R=– | 同上，3 行新边（Eclipse→系列）被强效阈值放大 |
| 567_df97 B0 | uncertain | redundant(弃权) | Δp=−0.74pp, L=0.007 | join 一侧候选池但不含 gold；人诚实拿不准，机器按"无概率增量"归 redundant |
| 567_df97 B2 | redundant | harmful(移除) | Δp=−6.61pp, R=−0.11 | 重复渲染同一 subject 边反而压低 P(gold)（拼接上下文变长/重排），被当作有害；人视为纯重复 |
| 567_df97 B3 | informative | redundant(移除) | Δp=+2.05pp, R=0.03 | 关键 join 边（film↔actor）的概率增益被更早的块#1(+57pp) 抢走，R=0.03<0.10 被滤掉——概率通道测不出 join 价值 |
| 493\|s0 B1 | informative | redundant(弃权) | Δp=+1.47pp, L=0.0145 | L 锚 0.0145 差 0.005 未过 0.02 → 弃权；GMT↔Europe 关联实为问题核心 |
| （动作分歧）1171\|s1 B0 | harmful | harmful→弃权保留 | Δp=−25.59pp | 负 L（通路未达 gold）→ R 不可靠 → 弃权；大负 Δp 的方向性信息被弃权规则吞掉 |
| （动作分歧）124_6655 B0 B1 | harmful | harmful→弃权保留 | Δp=−4.63/−15.28pp | 同上：通路 L 为负即弃权，明确干扰证据被保留 |

## 6. 结论与建议

**结论**
1. 总体原 label 一致率 66.7%，但结构不均衡：RSCC-redundant 与人审最合（80%），
   RSCC-harmful 与人审最不合（33%，6 例中人只认 2 例）；弃权通道 13 例里 9 例
   本来就是人审 redundant（弃权基本等于"看不见"，代价可接受但收益也小）。
2. 分歧最多的一类是**"人判 informative、RSCC 测不出"**（3 例：1731B1、567B3、
   493B1）：块的贡献是问题实体与答案子图之间的**连接边**，gold 概率由别的块
   承担，leave-one-out 的 Δp 天然趋零。其次是**"人判 redundant、RSCC 判
   informative"**（3 例，全部由强效 5pp 或分享 0.10 在边缘 Δp 上触发）和
   **"人判 redundant、RSCC 判 harmful"**（3 例，Δp 落在 −5~−7pp 刚过线区）。
3. 判据各部分在分歧中的表现：
   - 强效 0.05：在 L 为负的退化通路上 2 次把 redundant 抬成 informative
     （25_7cec）；在 −5pp 附近的 borderline 负 Δp 3 次触发人不同意的移除。
   - 分享 0.10：无 Δp 下限导致 1.3pp 噪声判 informative（576B2）；同时 0.10
     门槛把真 join 边滤成 redundant（567B3, R=0.03）。
   - L 锚 0.02：挡住了 1 个 informative（L=0.0145）和 2 个大负 Δp 的 harmful
     （−25.6/−15.3pp 因负 L 弃权保留）；其余 9 次弃权发生在人审 redundant 上，
     无害但也无信息。
   - 实现 vs 文本：harmful 实际在 −0.48pp 就触发、redundant 实际被执行移除，
     均与 v3 判据文本不符，是移除侧分歧的直接来源。

**判据调整建议**
1. **移除动作与 label 解耦并收紧 harmful**：harmful→移除 要求 Δp≤−5pp 且
   （cov>0 或 |R|≥0.5）；可测的 redundant 只降权不删块（本次 4 例
   redundant-移除人审全反对，且删掉的 567B3 是必要 join 边）。同时把实现
   对齐判据文本（−0.48pp 不应判 harmful）。
2. **给"连接边"结构通道投票权**：把结构必要从"删除后 lineage 断链"扩为
   "删除后问题锚实体与 gold 子图不连通"（1731B1 的 tour→band、567B3 的
   film↔actor、493B1 的 GMT↔Europe 都会被此规则保下），或在概率删除前做
   一次 Q-anchor↔gold 连通性检查。
3. **弃权规则保留方向性 + 分享通道加 Δp 下限**：L<0.02（含负 L）但
   |Δp|≥5pp 时仍输出方向标签而非纯弃权（挽回 1171B0/124B1 两个明确干扰块）；
   分享通道 informative 加 Δp≥2pp 下限（消除 576B2 式 1.3pp 噪声）；
   可考虑把 L 锚阈值降到 0.01（493B1 L=0.0145 仅差 0.005）。

（审计性质：只读评估 + 本报告，未改任何流水线代码。）
