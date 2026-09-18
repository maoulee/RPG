# 存疑标记清单（2026-09-18，供人工逐条评估）

来源: 13 条已打分轨迹（specs/layer_op_probs_2026-09-17.json）× 审计发现的分歧点。
信号缩写: N=新颖性(展示边首现占比) f=前向独立 d=顺序增量 l=移除伤害 g=金标首达
lin=台阶(后续调用中心来自本块) cls=概率档。判断为**我的建议**，最终以你评估为准。

## A 类：redundant_irr 误标有价值探索（4 例——我认为全部错标）

### A1. WebQTrn-567_11fd-s0 mod1 — 首次查发行日期被标"冗余无关"
- 行为: `center=?film | relations=film.release_date_s | film_regional_release_date...`
  返回 Ron Howard 各电影的发行日期块
- 信号: **N=0.90** f=−0.0016 g=0 lin=0 → cls=redundant_irr
- 判断: **错标**。全新关系族首次探查（N=0.90 自己就说明 90% 边是新
  的），f≈0 的真因是日期被渲染成 m.xxx CVT id（打分器和模型都读不出
  值）——这是**渲染层问题记到了行为头上**。正确读法: 有价值探索+
  环境渲染缺陷。

### A2. WebQTrn-1731-s0 mod3 — track 级保险探查被标 irr
- 行为: `center=Eclipse Tour | relations=artist.track | performance_role.guest_performances`
  （?instrument 已绑定后，探查曲目级署名——不同假设层级）
- 信号: N=0.65 f=−0.0018 → redundant_irr
- 判断: **错标（无害探索）**。没有任何重复发生；答案此时已对。
  f≈0 只证明"没带来增量概率"，不证明"冗余"。建议增设
  "exploration-harmless"（探索-无害）档而非记负。

### A3. WebQTrn-2576-s0 mod2 — 错误假设下的连贯步骤被标 irr
- 行为: `center=United Kingdom | relations=location.location.containedby`
  （绑定国家+时区后查所在大洲——UK 路线假设的下一步）
- 信号: N=0.82 f=−0.0001 → redundant_irr
- 判断: **错标（假设错≠调用冗余）**。gold 走 Falkland→Americas 路线，
  UK 路线整个是错假设，但该调用在假设内完全连贯且全部新边。f 把
  "顶层假设错"记到"这个调用冗余"。注: mod0（Falkland 首查,g=1,d=+.04）
  已正确拿 effective——假设错的责任已在源头记录。

### A4. WebQTest-1379-s0 mod3 — 方向对但关系选反的探索被标 irr
- 行为: `center=Franz Liszt | relations=people.profession.people_with_this_profession`
- 信号: N=0.48 f≈0 → redundant_irr
- 判断: **错标（有价值未遂）**。gold "Priest" 是职业节点——问题的
  正确方向就是 profession！模型选了 `people_with_this_profession`
  （此职业有哪些人——反向），从 Liszt 出发查不到；正向
  `people.person.profession` 才会命中。探索方向正确、关系方向反了。
  这恰是最该被信用体系鼓励的"接近正确的未遂"。

## B 类：redundant_dup 判定正确（2 例对照——标记体系在这类可靠）

### B1. WebQTest-1379-s1 mod4 — restart 后 ?org 同关系集重取
- 行为: `center=?org | relations=organization_membership.organization | ...` N=**0.00**
- 判断: **标记对**（真冗余）。根因: NONE-verdict restart 丢弃全部先验
  证据，模型被迫全链重做——冗余由**环境设计**造成，不是模型重复癖。
  修复应在 restart 证据保留，不在标注。

### B2. WebQTest-1379-s1 mod5 — Franz Liszt 同关系集重取
- 同 B1（N=0.00，restart 后重取 mod0 的关系）。标记对。

## C 类：effective 存疑（概率信号负但被 L1/g 短路，3 例）

### C1. WebQTrn-567_df97-s0 mod0（[5]）— 含金噪声块
- 行为: `center=Ron Howard | relations=director.film | directed_by | produced_by...`
  返回 99 部电影（gold Village of the Giants 文本在内）
- 信号: N=1.0 **g=1（首现金标）lin=1（台阶）** 但 **d=−.004 f=−.004
  l=−.028（移除反升）** → effective
- 判断: **存疑，需复合标签**。三概率信号全负（99 部电影的噪声在
  概率上压过了含金文本），但 g/台阶/必要各自独立成立。单标签
  "effective" 丢失 l=−.028 的发现。建议: effective + noise-negative
  限定符（提示渲染裁剪该块受益——P2 的 SEQ_FRONTIER_RENDER_K 正对此）。

### C2. WebQTest-1797-s1 mod0 — 巨中心把概率拖到 p0 之下，L1 短路救回
- 行为: `center=Siege of Vicksburg | relations=combatants | participated_in_conflicts...`
- 信号: N=1.0 **f=−.0847 d=−.0847**（本块把 gold 概率从 p0=.151 拖到
  .066）l=+.005 微正 → effective（必要∨台阶短路）
- 判断: **标记错（应为 harmful 剖面）**。harmful 三条件 d<−τ ∧ g=0 ∧
  f≤τ **全部满足**，但级联顺序 L1 在 L2 前短路——同一行为在结构
  必要时永远逃过有害判定。级联需要冲突标记而非短路。

### C3. WebQTest-1797-s1 mod1 — 20 实体巨中心第二块
- 行为: `center=Carter L. Stevenson | David Farragut | ...（20 参战者）|
  relations=place_of_death | interred_here...`
- 信号: N=0.76 **f=−.1204 d=−.0262** 但 **g=1**（首现金标 Pemberton）
  → effective
- 判断: **存疑**。含金（首现 gold）与巨中心淹没（f 最负的块）并存；
  pF(.035)<p0(.151) 主要由此两块造成。与 C1 同型：单标签不够，
  需 effective + drowning 限定。

## D 类：lineage 台阶链通向 unreached（1379-s0 mods 0-2）

- 行为: mods0-2（Freemasonry→founders→religion 三次扩展）全 lin=1，
  f≈0，通路 unreached（Priest 边从未出现）→ 全 effective
- 判断: **语义漏洞**。台阶只测"被后续复用"，不测"链是否终止于
  gold"——一条永久迷失的游走，多数块拿 effective，只有末块
  （lin=0）拿 irr。建议: lineage 在通路 unreached 时降级为
  stepping-unreached（半额或标记），避免失败链全绿。

## 汇总建议（待你裁定）

| 类 | 例数 | 建议改判 |
|---|---|---|
| A（irr 误标探索） | 4 | → exploration-harmless / valuable-unlucky（去掉 f 门槛或改 N 单判） |
| B（dup 正确） | 2 | 维持；根因修 restart 证据保留 |
| C（噪声/短路 effective） | 3 | → 复合标签 effective+noise-negative；级联改冲突标记（L1 命中时仍记录 L2 harmful 剖面） |
| D（台阶到 unreached） | 3 块 | → lineage 在 unreached 通路降级 |

核心规律（供裁定参考）: **dup 靠 N 可靠；irr 的 f 门槛是伪装的答案
相关性（A 类全部 N≥0.48 仍被罚）；L1/g 短路掩盖概率负信号（C 类）**。
