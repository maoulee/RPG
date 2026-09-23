# RSCC 人审重放 dump（轨迹块标记 + 倒序移除逐步概率）— 2026-09-22

对齐旧实现:证据按时间序拼接构成 prompt(score_layer_op_probs 的
Vseq/Vloo 同款,块=annotate_layer_ops 拆分);RSCC 移除=同一拼接序
里跳过被删块(保留块相对位置不变)。每块给旧标记(IG 级联 d/l/f/N/g/
lineage/cls + pathway 裁决/必要)与 RSCC 概率(p_ref→p_cf,ratio,
判据 ratio=p_cf/p_ref,<0.90=Informative 保留,≥0.90=移除)。



========== CASE WebQTrn-1731_4eea981607dbe17b040580ce4cd93ec4|s0 ==========
Q: What did Randy Jackson play in the Eclipse Tour?
gold=['Bass guitar', 'Vocals']  实际answer='Bass guitar | Vocals' f1=1.0
打分口径 v2: per-gold 序列 log-likelihood(token SUM, log 域); 判定 ∃gold: d_g≥0.0513(=5%下降) → Informative; d_g≤-0.0488 → harmful 档
p0(无证据, per-gold)=[-9.95 -10.38]
pF(全轨迹, per-gold)=[-2.66 -12.37]
通路独立 l [Randy Jackson] per-gold=[-3.74 -13.11]
通路独立 l [Eclipse Tour] per-gold=[-10.04 -13.11]

## 块 #0 [msg 5]  分支=randy jackson
调用命令:
```text
tool: retrieve_subgraph
center: Randy Jackson
relations: music.group_membership.role | music.performance_role.guest_performances | track_contribution.role
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Randy Jackson
▸ patterns: group_member.instruments_played | group_member.membership | group_membership.member | track_contribution.contributor | person.profession | friendship.participant ⭢ celebrity.friendship ⭢ person.profession | track_contribution.contributor ⭢ track_contribution.role ⭢ group_membership.role | friendship.participant ⭢ celebrity.friendship ⭢ person.profession ⭢ group_membership.role | group_membership.member ⭢ group_membership.role ⭢ instrument.variation ⭢ track_contribution.role | track_contribution.contributor ⭢ track_contribution.role ⭢ instrument.variation ⭢ group_membership.role | track_contribution.contributor ⭢ track_contribution.role ⭢ instrument.variation ⭢ track_contribution.role
── Randy Jackson ──
    --group_member.instruments_played--> Bass guitar | Keyboard
    --group_member.membership--> g.11b6btynmz | m.01vxjq8 [end: 1987-08:00; group: Journey; role: Bass guitar | Vocals; start: 1985-08:00] | m.01vxjqg [group: Verdine White & Randy Jackson] | m.040rysf [group: Breakfast Club; has_value: Period (end) | Period (start); role: Bass guitar] | m.043dm0_ [group: Methods of Mayhem] | m.0ggf17l [group: The Sign]
    --person.profession--> A&R executive | Actor | Bassist | Music Manager | Musician | Record producer | Singer | TV Personality | Television producer
    m.010mrzsl | m.010n9k6l | m.011wxrc3 --track_contribution.contributor--> Randy Jackson
    m.01vxjq8 --group_membership.member--> Randy Jackson
    m.065pn83 --friendship.participant--> Randy Jackson
── Guitar ──
    --instrument.variation--> Bass guitar
    m.010k33zq | m.010n247n | m.010nc7ct | m.010ncy4n | m.012m1vz9 | m.01tz9k6 --track_contribution.role--> Guitar
── Bass guitar ──
    m.010n9k6l | m.012m1vf1 | m.01vxjq8 | m.040rysf --track_contribution.role--> Bass guitar
── Record producer ──
    Mariah Carey --person.profession--> Record producer
    m.012m1vf1 --group_membership.role--> Record producer
    m.012m1vz9 --group_membership.role--> Record producer
── Jonathan Cain ──
    m.01tz9k6 --group_membership.member--> Jonathan Cain
── Rob Bacon ──
    m.010nc7ct --track_contribution.contributor--> Rob Bacon
── Mariah Carey ──
    --celebrity.friendship--> m.065pn83 [participant: Mariah Carey]
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'music.group_membership.role': {'direct': ['music.group_membership.role'], 'bridge': ['music.group_member.instruments_played', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor', 'people.person.profession']}, 'music.performance_role.guest_performances': {'direct': ['music.performance_role.guest_performances'], 'bridge': ['music.group_membership.member', 'people.person.profession']}, 'track_contribution.role': {'direct': ['music.track_contribution.role'], 'bridge': ['music.group_member.instruments_played', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.1999 l=0.1002 f=0.1999 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 12]  分支=eclipse tour
调用命令:
```text
tool: retrieve_subgraph
center: Eclipse Tour
relations: music.artist.concert_tours
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Eclipse Tour
▸ patterns: artist.concert_tours | concert_tour.artist ⭢ artist.concert_tours | album.supporting_tours ⭢ album.artist ⭢ artist.concert_tours | album.supporting_tours ⭢ artist.album ⭢ artist.concert_tours
── Eclipse Tour ──
    --concert_tour.artist--> Journey
    Journey --artist.concert_tours--> Eclipse Tour
    Eclipse --album.supporting_tours--> Eclipse Tour
── Journey ──
    --artist.album--> Eclipse
    --artist.concert_tours--> Escape Tour | Frontiers Tour | Raised on Radio Tour | Revelation Tour
    Eclipse --album.artist--> Journey
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'music.artist.concert_tours': {'direct': ['music.artist.concert_tours'], 'bridge': ['music.concert_tour.artist']}}
```
(送评归属文本: 8 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=-0.0277 l=-0.01264 f=-0.0005388 N=1.0 g=- lineage=✓ necessary=n/a
◆ RSCC[v2.1] per-gold 明细:
    Bass guitar                    logP(ref)=-10.04 → logP(cf)=-6.261  Δ=-3.777  drop=-4267.9% ‼
    Vocals                         logP(ref)=-13.11 → logP(cf)=-10.1  Δ=-3.018  drop=-1944.9% ‼
  max drop=-1945%  coverage=0 D_pos=0  label=harmful → 移除
◆ LOO:  d(per-gold)=[-0.87 -1.97]  D_max=-0.8699 cov=0
  [结构: necessary=n/a pathway=eclipse tour]

## 块 #2 [msg 16]  分支=eclipse tour
调用命令:
```text
tool: retrieve_subgraph
center: Eclipse Tour
relations: music.group_membership.member | music.musical_group.member
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Eclipse Tour  (sequence root; this layer applies to the frontier: Journey)
▸ patterns: concert_tour.artist | musical_group.member
── Eclipse Tour ──
    --concert_tour.artist--> Journey
── Journey ──
    --musical_group.member--> g.11b6bfd9cl | g.11b6btynmz | g.11b6bwf1m9 | m.01tf0q1 [has_no_value: Period (end); member: Neal Schon; role: Vocals] | m.01tz9k6 [has_no_value: Period (end); member: Jonathan Cain; role: Guitar | Keyboard] | m.01vxjq8 [end: 1987-08:00; member: Randy Jackson; role: Bass guitar | Vocals; start: 1985-08:00]
    Raised on Radio Tour --concert_tour.artist--> Journey
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'music.musical_group.member': {'direct': ['music.musical_group.member'], 'bridge': ['music.concert_tour.artist']}}
anchor_sequence: Eclipse Tour ⭢ concert_tour.artist | group_membership.member | musical_group.member (1)
layer_action: update layer 1 (replaced music.artist.concert_tours)
```
(送评归属文本: 4 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.0126 l=0.01539 f=0.1094 N=0.9 g=- lineage=- necessary=n/a
◆ RSCC[v2.1] per-gold 明细:
    Bass guitar                    logP(ref)=-10.04 → logP(cf)=-18.83  Δ=+8.791  drop=+100.0% ★
    Vocals                         logP(ref)=-13.11 → logP(cf)=-16.26  Δ=+3.150  drop=+95.7% ★
  max drop=99.98%  coverage=1 D_pos=5.971  label=informative → 保留
◆ LOO:  d(per-gold)=[+1.87 +1.17]  D_max=1.874 cov=1
  [结构: necessary=n/a pathway=eclipse tour]

── RSCC 通路隔离倒序收缩迹（每通路独立; d 为 per-gold nats）──
〔通路 Randy Jackson〕起始 l_alone(per-gold)=[-3.74 -13.11]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Eclipse Tour〕起始 l_alone(per-gold)=[-10.04 -13.11]
  块#2 结构=n/a(通路未达): d=[+8.79 +3.15] max-drop=99.98% cov=1 [informative] ⇒ Informative → 保留
  块#1 结构=n/a(通路未达): d=[-3.78 -3.02] max-drop=-1945% cov=0 [harmful] ⇒ harmful → 移除
  终态[Eclipse Tour] l(per-gold)=[-6.26 -10.10]
  双通道小结: 结构必要块=['0'] | 概率移除块=['1'] | 两通道无冲突

