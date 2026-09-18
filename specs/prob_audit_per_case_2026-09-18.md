# 概率审计报告（2026-09-18）：逐轨迹 p0/pF + 逐行为概率明细

用途: 核查冗余判定（dup/irr）是否正确标注。13 条已打分轨迹全量列出。
信号: p0=未检索直答概率 / pF=全证据概率 / Δ=pF−p0（检索概率优势，与答案对错脱钩）/
每个行为: N=新颖性(展示边首现占比) f=前向独立(p_alone−p0) d=顺序增量(概率域)
l=移除伤害(pF−p⁻) g=金标首达 lin=台阶(后续调用中心来自本块) p⁻=移除本块后概率
p_alone=仅本块概率。cls=v1.5 级联分档。
**总分布: effective 33 / redundant_irr 5 / redundant_dup 3**

---

## 1. WebQTest-1379 s0 — f1=0.00 pred=NONE 【检索负优势，全链迷失】
p0=1.74e-05 → pF=9.52e-06 (Δ=−7.9e-06, 0.55x)
问题方向: Priest=职业节点，正确关系是 people.person.profession——全程未查到。
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | −0 | −0 | −0 | 0 | 1 | Liszt × organization_membership.member/member_of → Freemasonry |
| 1 | effective | 0.61 | −0 | −0 | +0 | 0 | 1 | Liszt × organization.founders → Liszt Academy |
| 2 | effective | 0.52 | −0 | +0 | +0 | 0 | 1 | Liszt × religion+founders → Catholicism |
| 3 | **redundant_irr** | 0.48 | −0 | +0 | +0 | 0 | 0 | Liszt × profession.people_with_this_profession → Virtuoso |
**审计注**: mods0-2 靠台阶(lin=1)在 p≈0 时判 effective——"迷失链全绿"漏洞的标本。
mod3 方向正确（profession 族）但选了反向关系（people_WITH_this_profession 从
Liszt 出发查不到）→ 标 irr。**建议裁定: 探索方向正确记 valuable-unlucky**。

## 2. WebQTest-1379 s1 — f1=0.00 pred=Freemasonry 【restart 全链重做】
p0=1.74e-05 → pF=2.26e-06 (0.13x)
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | −0 | −0 | −0 | 0 | 1 | Liszt × founders → Freemasonry |
| 1 | effective | 0.60 | −0 | −0 | −0 | 0 | 1 | Freemasonry+Academy × members/employment_tenure |
| 2 | effective | 0.14 | −0 | +0 | +0 | 0 | 1 | Freemasonry+Academy × members/member(≈mod1 复查) |
| 3 | effective | 0.72 | −0 | +0 | +0 | 0 | 1 | Freemasonry × organization_type → Classical music |
| 4 | **redundant_dup** | **0.00** | −0 | −0 | −0 | 0 | 0 | ?org × membership.organization（同集重取）|
| 5 | **redundant_dup** | **0.00** | +0 | +0 | +0 | 0 | 0 | Liszt × founders（mod0 同集重取）|
**审计注**: 两个 dup 标记**正确**（N=0.00 零新边）。根因=NONE-verdict restart
丢弃先验证据强迫全链重做——环境设计问题非模型重复癖。

## 3. WebQTest-1797 s1 — f1=0.00 pred=U.S. Grant 【证据降级：巨中心】
p0=0.1513 → pF=0.0351 (**Δ=−0.116**, 0.23x——本 case 检索是负贡献)
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | **−0.085** | **−0.085** | +0.005 | 0 | 1 | Vicksburg × combatants → 20 参战者 |
| 1 | effective | 0.76 | **−0.120** | −0.026 | −0.012 | **1** | 1 | 20 人巨中心 × place_of_death（gold Pemberton 首现于此）|
| 2 | **redundant_irr** | 0.30 | −0.120 | −0.004 | −0.004 | 0 | 0 | 同 20 人 × cause_of_death（查死因，问题只要最早死亡日期）|
**审计注**: mod0 是 **harmful 三条件全满足**（d<−τ∧g=0∧f≤τ）却被"必要∨台阶"
短路救成 effective——级联顺序掩盖概率负信号。mod2 查 cause_of_death 是问题
不需要的维度（要 date）→ irr 标记**正确**（真冗余维度）。

## 4. WebQTrn-567_11fd s0 — f1=0.00 pred=Cocoon 【日期渲染成 m.xxx id】
p0=0.0018 → pF=0.0003 (0.17x)
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | −0.001 | −0.001 | +0.000 | 1 | 1 | Ron Howard × director.film/directed_by → 电影列表（gold The Journey 在内）|
| 1 | **redundant_irr** | **0.90** | −0.002 | −0.000 | −0.000 | 0 | 0 | ?film × **release_date_s**（首查日期！返回 m.xxx CVT 无法读值）|
| 2 | redundant_dup | 0.18 | −0.002 | −0.000 | −0.000 | 0 | 0 | （derive path）同题收窄重试 |
**审计注**: **最明显误标**。mod1 是全新关系族首次探查（N=0.90 自证），
f≈0 真因是环境把日期渲染成 m.xxx id——渲染缺陷记到行为头上。mod2 收窄
重试合法（learned dates 需要 named 形式）。两个都建议改判。

## 5. WebQTrn-567_df97 s0 — f1=0.00 pred=A Beautiful Mind 【检索赢答案输】
p0=0.0115 → pF=**0.6286** (**+0.617, 54.7x**)
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | −0.004 | −0.004 | **−0.028** | 1 | 1 | Ron Howard × director/producer → 99 电影（含 gold 文本）|
| 1 | effective | 0.87 | −0.005 | +0.000 | −0.017 | 0 | 1 | 8 电影巨中心 × film_subjects |
| 2 | effective | 0.18 | −0.006 | +0.000 | +0.014 | 0 | 1 | A Beautiful Mind × film_subjects（收窄）|
| 3 | effective | 0.64 | −0.004 | −0.001 | **−0.048** | 0 | 1 | ABM × story_by → 编剧层（噪声）|
| 4 | effective | 1.00 | **+0.732** | **+0.707** | +0.086 | 0 | 1 | **Child prodigy × film_subjects → gold！** |
| 5 | effective | 0.38 | +0.679 | −0.072 | −0.088 | 0 | 0 | Village of the Giants × director（验证步）|
**审计注**: 检索优势 54.7x 但答错——答案层用参数知识否决图证据。
mod0 三信号全负（l=−.028 移除反升）靠 g/台阶判 effective；mod5 事后
验证步 l=−.088（砍掉它概率反升 8.8pp）仍 effective。**含金噪声与
验证步的复合标签是缺口**。

## 6. WebQTrn-2784 s2 — f1=0.00 pred=None 【检索赢答案输：拒答死锁】
p0=0.0317 → pF=**0.5484** (**+0.517, 17.3x**)
| mod | cls | N | f | d | l | g | lin | 调用 |
|---|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | +0.443 | +0.446 | +0.177 | 1 | 1 | Tupac+Petruccelli × actor.film/starring（gold 首位绑定）|
| 1 | effective | 0.33 | +0.302 | +0.070 | +0.023 | 0 | 0 | 6×m.xxx id × directed_by |
| 2 | effective | 0.01 | +0.418 | +0.017 | −0.004 | 0 | 0 | Petruccelli × directed_by |
**审计注**: 检索 17.3x 但答案层对着打印的 bindings 连续 answer NONE 8 次
到预算死。三个模块标记**全部正确**——问题纯在答案层。

## 7. WebQTrn-21 s0 — f1=1.00 【双赢基线】
p0=0.3486 → pF=0.8635 (+0.515, 2.5x)
mod0: effective N=1.00 f=+0.094 d=+0.078（birr→Ethiopia）
mod1: effective N=0.93 f=+0.501 d=+0.437 l=+0.458 g=1（Ethiopia × positions → gold）
**审计注**: 全部标记正确，教科书链。

## 8. WebQTrn-2209 s0 — f1=0.111 【多 gold，部分选对】
p0=0.042 → pF=0.314 (+0.272, 7.5x)
mod0: effective N=1.00 f=+0.012（Stevens × head_coach → 球队）
mod1: effective N=0.94 f=+0.252 d=+0.258 l=+0.260 g=1（球队 × championships → 17 gold）
**审计注**: 标记正确。f1 低是答案层只选 1/17（时间判别器缺失）。

## 9. WebQTrn-1731 s0 — f1=1.00 【pF 低但答对：gold 藏 CVT 属性】
p0=0.0030 → pF=0.1789 (+0.176, 59.1x)
| mod | cls | N | f | d | l | g | lin |
|---|---|---|---|---|---|---|---|
| 0 | effective | **0.00** | −0.002 | −0.002 | **+0.097** | 0 | 1 | Randy Jackson × concert_tours（**空交付块**！）|
| 1 | effective | 1.00 | +0.148 | +0.246 | +0.047 | 1 | 1 | Eclipse Tour × tours/group → Vocals/Bass guitar |
| 2 | effective | 0.78 | +0.100 | −0.066 | −0.025 | 0 | 0 | Jackson × instruments_played → 乐器 |
| 3 | **redundant_irr** | 0.65 | −0.002 | −0.004 | +0.000 | 0 | 0 | Eclipse Tour × track/guest_performances（track 级署名探查）|
**审计注**: **mod0 是重要异常**——交付块为空（N=0.00）、l=+0.097 反而
全场最高！空块为什么移除伤害最大？因为它的文本（plan 分解上下文）承载
了锚定信息。**空交付块进模块序列是打分框架的边界 case**（它其实是
"空结果也有信息"——告诉模型这条关系不存在）。mod3 标记 irr 过严
（同 A2：无害探查，答案已对）。

## 10. WebQTrn-2784 s0 — f1=1.00 【同 s2 证据，答案层选对对照】
p0=0.0317 → pF=0.5126 (+0.481, 16.2x)
mod0: effective N=1.00 f=+0.648 l=**−0.046** g=1（gold 首位）
mod1: effective N=0.70 f=+0.567 d=**−0.166** l=**−0.167**（derive 重走，砍掉反升 16.7pp）
**审计注**: mod1 概率全负但仍 effective（f 救）——与 s2 对比：同证据
不同采样，答案层一个对一个拒绝。**CASE-B 抛硬币的对照组**。

## 11. WebQTest-626 s0 — f1=1.00 【三段链全 effective】
p0=0.0227 → pF=0.4065 (+0.384, 18.0x)
mod0: N=1.00 f=+0.618 d=+0.619 g=1（Tempus Unbound × universe）
mod1: N=0.89 f=+0.427 d=+0.018 l=−0.076（?setting × containedby）
mod2: N=0.98 f=+0.291 d=**−0.259** l=**−0.254**（Missouri River × partially_contains → Kansas）
**审计注**: mod2 的 d/l 大负是**替代对语义的教科书**——它和 mod1 是
两条到 Kansas 的通路，LOO 互顶（砍一条另一条顶上）。全标 effective
正确（§10.8 替代对故意满额），但**信贷量未再裁决**（备份=一半？）。

## 12. WebQTrn-2576 s0 — f1=0.00 pred=Western Europe 【错假设链】
p0=1.2e-04 → pF=0.0070 (+0.007, 57.8x——绝对值仍低)
| mod | cls | N | f | d | l | g | lin |
|---|---|---|---|---|---|---|---|
| 0 | effective | 1.00 | +0.040 | +0.040 | +0.003 | 1 | 1 | Falkland × containedby → **Americas（gold 方向！）**|
| 1 | effective | 0.93 | +0.009 | **−0.029** | −0.012 | 0 | 1 | UK × time_zones（岔向 Europe）|
| 2 | **redundant_irr** | 0.82 | −0.000 | −0.004 | −0.004 | 0 | 0 | UK × containedby → Western Europe（错误假设的下一步）|
**审计注**: mod0 已把 gold（Americas）摆上台面（g=1），mod1 起岔向 UK
路线最终答 Western Europe。mod2 在错误假设内连贯且全新边（N=0.82）——
**假设错记到调用头上**的又一例（同 A3）。

---

## 冗余判定核查结论（dup/irr 共 8 个，对 3 错 5）

| 标记 | 例 | 判定 | 依据 |
|---|---|---|---|
| redundant_dup ×3 | 1379-s1 mod4/5, 567_11fd mod2 | **全对** | N=0.00-0.18 零/微新边，真重复 |
| redundant_irr ×5 | 1379-s0 mod3, 567_11fd mod1, 1731 mod3, 2576 mod2, 1797-s1 mod2 | **对 1 错 4** | 1797 mod2 查问题不需要的维度=真冗余✓；其余四个是 N=0.48-0.90 的新颖探索（方向对/渲染缺陷/无害保险/错误假设内连贯）|

**系统性结论**: dup 靠 N 可靠；irr 的 `N≥0.2 ∧ f≤0.005` 门槛把
"新颖但未移动 gold 概率"的探索全部打入冗余——与"行为评估与答案
脱钩"原则冲突。修法建议（待裁定）: irr 需加"表面变体"条件
（与已服务调用同 resolved 关系集），仅 N 高 f 低不再构成 irr；
新增 exploration-harmless 档承接 A 类。

## effective 侧的两个结构性发现（附带）

1. **空交付块异常**（1731 mod0）: N=0.00、交付块空、却 l=+0.097 全场
   最高——空结果本身携带"此路不通"信息，进模块序列的打分语义需单独定义。
2. **替代对 LOO 互顶**（626 mod1/mod2）: d/l 双大负是替代对的签名而非
   冗余——与 567 mod5（真验证步，l=−0.088 无替代对象）需要区分，
   现有级联都记 effective 但语义不同。
