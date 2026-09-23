# RSCC 人审重放 dump（轨迹块标记 + 倒序移除逐步概率）— 2026-09-22

对齐旧实现:证据按时间序拼接构成 prompt(score_layer_op_probs 的
Vseq/Vloo 同款,块=annotate_layer_ops 拆分);RSCC 移除=同一拼接序
里跳过被删块(保留块相对位置不变)。每块给旧标记(IG 级联 d/l/f/N/g/
lineage/cls + pathway 裁决/必要)与 RSCC 概率(p_ref→p_cf,ratio,
判据 ratio=p_cf/p_ref,<0.90=Informative 保留,≥0.90=移除)。



========== CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5|s0 ==========
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27, 1993?
gold=['Priest']  实际answer='Priest' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.00]
pF(全轨迹, per-gold)=[+0.12]
通路独立 p [Franz Liszt] per-gold=[+0.00]  lift锚 L=[-0.00]
通路独立 p [Life of Franz Liszt] per-gold=[+0.04]  lift锚 L=[+0.04]
通路独立 p [Freemasonry] per-gold=[+0.00]  lift锚 L=[-0.00]

## 块 #0 [msg 5]  分支=franz liszt
调用命令:
```text
tool: retrieve_subgraph
center: Franz Liszt
relations: profession.people_with_this_profession | person.profession
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Franz Liszt
▸ patterns: fictional_character.based_on | fictional_character.occupation | topic.image ⭢ person.children ⭢ person.profession | topic.image ⭢ person.profession ⭢ profession.people_with_this_profession
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    --fictional_character.occupation--> Composer | Pianist
    Life of Franz Liszt --topic.image--> Franz Liszt
── Virtuoso ──
    --profession.people_with_this_profession--> Arcadi Volodos | Lance Dossor | Marc-André Hamelin | Mark Gasser | Niccolò Paganini | Osman Zeki Üngör | Pablo de Sarasate | Paolo Girolamo Besozzi | Sigismond Thalberg
    Life of Franz Liszt --person.profession--> Virtuoso
── Life of Franz Liszt ──
    --person.children--> Daniel Liszt
── Daniel Liszt ──
    --person.profession--> Pianist
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'profession.people_with_this_profession': {'direct': ['people.profession.people_with_this_profession'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'person.profession': {'direct': ['people.person.profession'], 'bridge': ['fictional_universe.fictional_character.based_on', 'fictional_universe.fictional_character.occupation']}}
```
(送评归属文本: 11 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=-1.233e-05 l=-0.000804 f=-1.223e-05 N=1.0 g=- lineage=✓ necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 11]  分支=franz liszt
调用命令:
```text
tool: retrieve_subgraph
center: Life of Franz Liszt
relations: religion.religious_leadership_title.leaders | organization.organization_membership.organization | organization.organization_member.member_of
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Franz Liszt  (sequence root; this layer applies to the frontier: Composer | Life of Franz Liszt | Pianist)
▸ patterns: fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | organization_member.member_of | person.profession
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --person.profession--> Composer | Film Score Composer | Pianist | Priest
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Composer ──
    Aaron Copland | Albert Roussel | Alexander Borodin | Amadeu Vives i Roig | André Jolivet | Anton Bruckner | Antonio Salieri | Antonio Vivaldi | Antonín Dvořák | Arcangelo Corelli | Arnold Schoenberg | Benjamin Britten …(+95) (to answer with ALL of them, include "#Aaron Copland::profession" as one answer entity) --person.profession--> Composer
── Pianist ──
    Aaron Copland | Benjamin Britten | Billy Joel | Béla Bartók | Camille Saint-Saëns | Carl Czerny | Charles-Valentin Alkan | Clara Schumann | Claude Debussy | César Franck | Daniel Liszt | Dmitri Shostakovich …(+33) (to answer with ALL of them, include "#Aaron Copland::profession" as one answer entity) --person.profession--> Pianist
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'religion.religious_leadership_title.leaders': {'direct': ['religion.religious_leadership_title.leaders'], 'bridge': ['people.person.profession']}, 'organization.organization_membership.organization': {'direct': ['organization.organization_membership.organization'], 'bridge': ['organization.organization_membership.member']}}
anchor_sequence: Franz Liszt ⭢ fictional_character.based_on | fictional_character.occupation | person.profession | profession.people_with_this_profession (3) ⭢ organization_member.member_of | organization_membership.member (0)
layer_action: extend
```
(送评归属文本: 9 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.0006216 l=0.0003733 f=0.001236 N=0.935 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #2 [msg 15]  分支=franz liszt
调用命令:
```text
tool: retrieve_subgraph
center: Freemasonry
relations: organization.organization_membership.member | people.person.profession | business.employment_tenure.person
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Franz Liszt  (sequence root; this layer applies to the frontier: Freemasonry)
▸ patterns: organization_membership.organization
── Freemasonry ──
    m.0cr70y2 --organization_membership.organization--> Freemasonry
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['organization.organization_membership.organization']}, 'people.person.profession': {'direct': ['people.person.profession'], 'bridge': ['organization.organization_membership.organization']}, 'business.employment_tenure.person': {'direct': ['business.employment_tenure.person'], 'bridge': ['organization.organization_membership.organization']}}
anchor_sequence: Franz Liszt ⭢ fictional_character.based_on | fictional_character.occupation | person.profession | profession.people_with_this_profession (3) ⭢ employment_tenure.person | organization_member.member_of | organization_membership.member (1) ⭢ organization_membership.organization (0)
layer_action: extend
```
(送评归属文本: 2 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=redundant_irr d=-0.000386 l=-4.249e-05 f=-1.276e-05 N=1.0 g=- lineage=- necessary=no
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Priest                         p(ref)=4.082e-07 → p(cf)=0.0001082  Δp=-0.01pp  R=不可靠  
  max Δp=-0.01078pp  coverage=0 D_pos=0pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[+1.32]  max=1.318pp
  [结构: necessary=no pathway=franz liszt]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Franz Liszt〕起始 p_alone(per-gold)=[+0.00]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Life of Franz Liszt〕起始 p_alone(per-gold)=[+0.04]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Freemasonry〕起始 p_alone(per-gold)=[+0.00]
  块#2 结构必要=否: Δp=[-0.01]pp R=[-] maxΔp=-0.01078pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTest-1797_2fb9e2823ccf35d2103fa8846d6f2ca8|s1 ==========
Q: Of the people who fought in the Battle of Vicksburg, who has the earliest date of death?
gold=['John C. Pemberton']  实际answer='John C. Pemberton' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.18]
pF(全轨迹, per-gold)=[+0.79]
通路独立 p [Siege of Vicksburg] per-gold=[+0.41]  lift锚 L=[+0.23]
通路独立 p [Carter L. Stevenson] per-gold=[+0.74]  lift锚 L=[+0.56]

## 块 #0 [msg 5]  分支=siege of vicksburg
调用命令:
```text
tool: retrieve_subgraph
center: Siege of Vicksburg
relations: military_conflict.combatants | military_person.participated_in_conflicts | military_combatant.military_commanders | event.entity_involved
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Siege of Vicksburg
▸ patterns: event.entity_involved | military_command.military_conflict | military_conflict.combatants | military_conflict.commanders | military_conflict.military_personnel_involved | military_person.participated_in_conflicts | event.included_in_event | event.entity_involved ⭢ military_person.participated_in_conflicts | event.included_in_event ⭢ military_conflict.combatants | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ event.entity_involved | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_person.participated_in_conflicts | military_unit.conflicts_participated_in ⭢ battle.military_units_involved_in_this_conflict ⭢ event.entity_involved | military_unit.conflicts_participated_in ⭢ battle.military_units_involved_in_this_conflict ⭢ military_person.participated_in_conflicts | military_command.military_conflict ⭢ military_command.military_combatant ⭢ military_combatant.military_commanders | military_conflict.combatants ⭢ military_combatant_group.combatants ⭢ event.entity_involved | military_conflict.combatants ⭢ military_combatant_group.combatants ⭢ military_combatant.military_commanders | military_conflict.commanders ⭢ military_command.military_combatant ⭢ military_combatant.military_commanders | military_conflict.commanders ⭢ military_command.military_commander ⭢ military_person.participated_in_conflicts | military_conflict.commanders ⭢ military_commander.military_commands ⭢ military_person.participated_in_conflicts
── Siege of Vicksburg ──
    --military_conflict.combatants--> m.049y2pc [combatants: Confederate States of America] | m.04fvcs7 [combatants: Union]
    --military_conflict.commanders--> m.049y2lz [military_combatant: Union; military_commander: Ulysses S. Grant] | m.049y2m5 [military_combatant: Confederate States of America; military_commander: John C. Pemberton]
    --event.entity_involved--> Confederate States of America | John C. Pemberton | Ulysses S. Grant | Union | United States of America
    --event.included_in_event--> American Civil War | Grant's Operations Against Vicksburg
    --military_conflict.military_personnel_involved--> Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | William D. Turner | William F. Draper
    --battle.military_units_involved_in_this_conflict--> 17th Louisiana Infantry Regiment | 22nd Louisiana Infantry Regiment | 31st Louisiana Infantry Regiment | 3rd Louisiana Infantry Regiment
    17th Louisiana Infantry Regiment | 22nd Louisiana Infantry Regiment | 31st Louisiana Infantry Regiment | 3rd Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Siege of Vicksburg
    m.049y2lz --military_command.military_conflict--> Siege of Vicksburg
    m.049y2m5 --military_command.military_conflict--> Siege of Vicksburg
    Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner …(+1) (to answer with ALL of them, include "#Carter L. Stevenson::participated_in_conflicts" as one answer entity) --military_person.participated_in_conflicts--> Siege of Vicksburg
── Confederate States of America ──
    --military_combatant.military_commanders--> m.048z_8v [military_commander: Robert E. Lee] | m.049y2vg [military_combatant: Confederate States of America; military_commander: P. G. T. Beauregard] | m.049y34w [military_combatant: Confederate States of America] | m.049yl34 [military_combatant: Confederate States of America] | m.049ylkz [military_commander: Joseph E. Johnston] | m.0dl56tp [military_combatant: Confederate States of America; military_commander: Robert E. Lee] | m.049y2m5 [military_combatant: Confederate States of America; military_commander: John C. Pemberton]
    m.049y2pc --military_combatant_group.combatants--> Confederate States of America
    American Civil War | Atlanta Campaign | Battle of Arkansas Post | Battle of Big Black River Bridge | Battle of Chickasaw Bayou | Battle of Fort Donelson | Battle of Fort Henry | Battle of Globe Tavern | Battle of Goodrich's Landing | Battle of Grand Gulf | Battle of Helena | Battle of Iuka …(+18) (to answer with ALL of them, include "#American Civil War::entity_involved" as one answer entity) --event.entity_involved--> Confederate States of America
    m.049y2m5 --military_command.military_combatant--> Confederate States of America
── Ulysses S. Grant ──
    --military_person.participated_in_conflicts--> American Civil War | Appomattox Campaign | Battle of Chapultepec | Battle of Fort Donelson | Battle of Molino del Rey | Battle of Monterrey | Battle of Palo Alto | Battle of Resaca de la Palma | Battle of Shiloh | Chattanooga Campaign | Overland Campaign | Siege of Petersburg | Siege of Veracruz
    Battle of Port Gibson --event.entity_involved--> Ulysses S. Grant
    m.049y2lz --military_command.military_commander--> Ulysses S. Grant
── Union ──
    --military_combatant.military_commanders--> m.049yl2q [military_commander: James B. McPherson; military_conflict: Battle of Atlanta] | m.04yvs96 [military_combatant: Union; military_commander: Ulysses S. Grant] | m.049y2lz [military_combatant: Union; military_commander: Ulysses S. Grant]
    m.04fvcs7 --military_combatant_group.combatants--> Union
    Battle of Atlanta | Battle of Champion Hill | Battle of Chancellorsville | Battle of Chickasaw Bayou --event.entity_involved--> Union
    m.049y2lz --military_command.military_combatant--> Union
── American Civil War ──
    --military_conflict.combatants--> m.03z965k [combatants: Union] | m.03z98d_ [combatants: Confederate States of America]
── Battle of Shiloh ──
    --military_conflict.commanders--> m.049y2vg [military_combatant: Confederate States of America; military_commander: P. G. T. Beauregard]
── Overland Campaign ──
    --military_conflict.commanders--> m.0dl56tp [military_combatant: Confederate States of America; military_commander: Robert E. Lee]
── Battle of Atlanta ──
    m.049yl34 --military_command.military_conflict--> Battle of Atlanta
── Battle of Chancellorsville ──
    --military_conflict.commanders--> m.049y34w [military_combatant: Confederate States of America]
── Battle of Fort Henry ──
    m.04yvs96 --military_command.military_conflict--> Battle of Fort Henry
    17th Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Battle of Chickasaw Bayou
    22nd Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Capture of New Orleans
    31st Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Battle of Port Gibson
    3rd Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Battle of Pea Ridge
    Battle of Chickasaw Bayou --event.entity_involved--> John C. Pemberton | United States of America
    Battle of Chickasaw Bayou --battle.military_units_involved_in_this_conflict--> 17th Louisiana Infantry Regiment
    Battle of Pea Ridge --battle.military_units_involved_in_this_conflict--> 3rd Louisiana Infantry Regiment
    Battle of Port Gibson --event.entity_involved--> John S. Bowen
    Battle of Port Gibson --battle.military_units_involved_in_this_conflict--> 31st Louisiana Infantry Regiment
    Capture of New Orleans --event.entity_involved--> David Farragut
    Capture of New Orleans --battle.military_units_involved_in_this_conflict--> 22nd Louisiana Infantry Regiment
    John C. Pemberton --military_person.participated_in_conflicts--> Mexican–American War
    John S. Bowen --military_person.participated_in_conflicts--> Battle of Port Gibson
    Peter Joseph Osterhaus --military_person.participated_in_conflicts--> Battle of Pea Ridge
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'military_conflict.combatants': {'direct': ['military.military_conflict.combatants'], 'bridge': ['time.event.included_in_event']}, 'military_person.participated_in_conflicts': {'direct': ['military.military_person.participated_in_conflicts'], 'bridge': ['base.culturalevent.event.entity_involved', 'military.military_command.military_conflict', 'military.military_conflict.commanders', 'military.military_conflict.military_personnel_involved', 'time.event.included_in_event']}, 'military_combatant.military_commanders': {'direct': ['military.military_combatant.military_commanders'], 'bridge': ['base.culturalevent.event.entity_involved', 'military.military_combatant_group.conflict', 'military.military_command.military_conflict', 'military.military_conflict.combatants', 'military.military_conflict.commanders']}, 'event.entity_involved': {'direct': ['base.culturalevent.event.entity_involved'], 'bridge': ['military.military_combatant_group.conflict', 'military.military_command.military_conflict', 'military.military_conflict.commanders', 'military.military_conflict.military_personnel_involved', 'military.military_person.participated_in_conflicts']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.4192 l=-0.06964 f=0.4159 N=1.0 g=★ lineage=✓ necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 15]  分支=siege of vicksburg
调用命令:
```text
tool: retrieve_subgraph
center: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | William D. Turner | Ulysses S. Grant | John C. Pemberton
relations: deceased_person.date_of_death
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Siege of Vicksburg  (sequence root; this layer applies to the frontier: American Civil War | Carter L. Stevenson | Confederate States of America | David Farragut | Grant's Operations Against Vicksburg | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John C. Pemberton | John S. Bowen | Peter Joseph Osterhaus)
▸ patterns: event.entity_involved ⭢ topic.image | event.entity_involved ⭢ deceased_person.date_of_death | military_combatant_group.conflict ⭢ military_combatant_group.combatants ⭢ topic.image | topic.image | deceased_person.date_of_death
── Siege of Vicksburg ──
    --event.entity_involved--> Confederate States of America | John C. Pemberton | Ulysses S. Grant | Union
    m.049y2pc --military_combatant_group.conflict--> Siege of Vicksburg
    m.04fvcs7 --military_combatant_group.conflict--> Siege of Vicksburg
── Union ──
    --topic.image--> USA Map 1864 including Civil War Divisions | United States 1860-1870
    m.04fvcs7 --military_combatant_group.combatants--> Union
── Confederate States of America ──
    --topic.image--> CSAlocation
    m.049y2pc --military_combatant_group.combatants--> Confederate States of America
── American Civil War ──
    --topic.image--> American Civil War Montage 2 | Civil War - Gettysburg | Savannah Immortal City by Barry Sheehy Cindy Wallace Vaughnette Goode Walker.jpg
── John C. Pemberton ──
    --deceased_person.date_of_death--> 1881-07-13-08:00
    --topic.image--> JCPembertonBLY
── Ulysses S. Grant ──
    --topic.image--> GrantBirthplace | Ulysses Grant 1870-1880
── David Farragut ──
    --topic.image--> Admiral David Farragut | Admiral David Farragut (1801–1870) - collodion, LC-BH82-4054 restored
    Carter L. Stevenson --topic.image--> CLStevenson
    James B. McPherson --topic.image--> Brady-GeneralMcPherson
    John S. Bowen --topic.image--> GenJohnBowen
    Peter Joseph Osterhaus --topic.image--> Peter J Osterhaus
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'deceased_person.date_of_death': {'direct': ['people.deceased_person.date_of_death'], 'bridge': ['common.topic.image']}}
anchor_sequence: Siege of Vicksburg ⭢ event.entity_involved | military_combatant.military_commanders | military_combatant_group.conflict | military_command.military_conflict | military_conflict.combatants | military_conflict.commanders | military_conflict.military_personnel_involved | military_person.participated_in_conflicts | event.included_in_event (19) ⭢ topic.image | deceased_person.date_of_death (0)
layer_action: extend
```
(送评归属文本: 13 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.2103 l=0.2082 f=0.6903 N=0.75 g=- lineage=- necessary=no
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    John C. Pemberton              p(ref)=0.7392 → p(cf)=0.1762  Δp=+56.31pp  R=+1.01 ★
  max Δp=56.31pp  coverage=1 D_pos=56.31pp  label=informative → 保留
◆ LOO:  Δp(per-gold,pp)=[+39.46]  max=39.46pp
  [结构: necessary=no pathway=siege of vicksburg]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Siege of Vicksburg〕起始 p_alone(per-gold)=[+0.41]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Carter L. Stevenson〕起始 p_alone(per-gold)=[+0.74]
  块#1 结构必要=否: Δp=[+56.31]pp R=[+1.01] maxΔp=56.31pp cov=1 [informative] ⇒ Informative → 保留
  双通道小结: 结构必要块=['0'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-567_11fd073d11dbb5448b6e6ef3f85999f1|s0 ==========
Q: What Ron Howard film was released first?
gold=['The Journey']  实际answer="Angels & Demons | Backdraft | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | The Dark Tower | The Dilemma | The Lost Symbol | The Paper | Beyond the Mat | Changeling | Clean and Sober | Closet Land | Cowboys & Aliens | Curious George 2: Follow That Monkey! | Inside Deep Throat | Inventing the Abbotts | J. Edgar | Katy Perry: Part of Me | Problem Child | Restless | Sky High | The 'Burbs | The Alamo | The Chamber | The Good Lie" f1=0.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.00]
pF(全轨迹, per-gold)=[+0.00]
通路独立 p [Ron Howard] per-gold=[+0.00]  lift锚 L=[-0.00]
通路独立 p [?film] per-gold=[+0.00]  lift锚 L=[-0.00]

## 块 #0 [msg 5]  分支=ron howard
调用命令:
```text
tool: retrieve_subgraph
center: Ron Howard
relations: film.director.film
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Ron Howard
▸ patterns: award_honor.award_winner | award_nominee.award_nominations | director.film | producer.film | producer.films_executive_produced | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.executive_produced_by ⭢ director.film | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.produced_by ⭢ director.film
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dorothea Gillim | Ellen Cockrill | Jon Shapiro; ceremony: 41st Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.05bkr1w [award: Academy Award for Best Director; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05bm2lq [award: Academy Award for Best Picture; award_nominee: Brian Grazer | Eric Fellner; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.07zqyp3 [award: BAFTA Award for Best Direction; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.07zqyxh [award: BAFTA Award for Best Direction; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lbx1t [award: BAFTA Award for Best Film; award_nominee: Brian Grazer; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lby3g [award: BAFTA Award for Best Film; award_nominee: Brian Grazer | Eric Fellner | Tim Bevan; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.090dj60 [ceremony: 34th Golden Globe Awards; nominated_for: The Shootist] | m.095h15z [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 53rd Golden Globe Awards; nominated_for: Apollo 13] | m.095h1h2 [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 59th Golden Globe Awards; nominated_for: A Beautiful Mind] | m.095h1tj [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 66th Golden Globe Awards; nominated_for: Frost/Nixon] | m.09k3n_p [award: Critics' Choice Movie Award for Best Director; ceremony: 11th Critics' Choice Awards; nominated_for: Cinderella Man] | m.09k3nwh [award: Critics' Choice Movie Award for Best Director; ceremony: 14th Critics' Choice Awards; nominated_for: Frost/Nixon] | m.09sc2mb [ceremony: 61st Directors Guild of America Awards; nominated_for: Frost/Nixon] | m.09tjrrf [award: Satellite Award for Best Director; ceremony: 13th Satellite Awards; nominated_for: Frost/Nixon] | m.09z78wm [award: Golden Raspberry Award for Worst Director; ceremony: 27th Golden Raspberry Awards; nominated_for: The Da Vinci Code] | m.0b6b38g [ceremony: 38th Directors Guild of America Awards; nominated_for: Cocoon] | m.0gkjjsg [award: Saturn Award for Best Director; nominated_for: Splash] | m.0glkp4v [award: Golden Bear; nominated_for: The Missing] | m.0k1j58y [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Dorothea Gillim | Ellen Cockrill; ceremony: 39th Daytime Emmy Awards; nominated_for: Curious George] | m.0lmtm8f [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Dorothea Gillim | Ellen Cockrill; ceremony: 38th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0lv467q [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Brian Grazer | Chuck Tatham | David Nevins | Dean Lorey | John Amodeo | Mitchell Hurwitz; ceremony: 58th Primetime Emmy Awards; nominated_for: Arrested Development] | m.0lv4ffs [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Barbie Adler | Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo; ceremony: 57th Primetime Emmy Awards; nominated_for: Arrested Development] | m.0m0bwv0 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Ellen Cockrill | Jacqui Deegan; ceremony: 36th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0m_1x_7 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dean Criswell | Ellen Cockrill | Frank Marino; ceremony: 34th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0my74fy [award: PGA Television Producer of the Year Award in Episodic; award_nominee: Brian Grazer | Rob Scheidlinger | Ron Howard | Thomas Schlamme | Tony Krantz; ceremony: Producers Guild of America Awards 1999; nominated_for: Sports Night] | m.0n4htv8 [award_nominee: Brian Grazer | Chuck Martin | David Nevins | John Levenstein | Mitchell Hurwitz | Richard A. Rosenstock; ceremony: Producers Guild of America Awards 2004; nominated_for: Arrested Development] | m.0n4kzq9 [award_nominee: Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo | Mitchell Hurwitz; ceremony: Producers Guild of America Awards 2005; nominated_for: Arrested Development] | m.0n4psbw [award_nominee: Brian Grazer | David Nevins | Dean Lorey | Jim Vallely | John Amodeo | Mitchell Hurwitz; ceremony: Producers Guild of America Awards 2006; nominated_for: Arrested Development] | m.0n4t7bh [award_nominee: Brian Grazer | Eric Fellner; ceremony: Producers Guild of America Awards 2008; nominated_for: Frost/Nixon] | m.0nbbh6b [award: Australian Film Institute Award for Best Foreign Film; award_nominee: Brian Grazer; ceremony: 44th Australian Film Institute Awards; nominated_for: A Beautiful Mind] | m.0svn6jn [award_nominee: Al Jean | Bill Freiberger | Brian Grazer | David Ichioka | Donald R. Beck | Eddie Murphy; ceremony: 51st Primetime Emmy Awards; nominated_for: The PJs] | m.0v4_x4x [award: Primetime Emmy Award for Outstanding Children's Program; award_nominee: Herbert Wright | Rance Howard; ceremony: 34th Primetime Emmy Awards; nominated_for: Through the Magic Pyramid] | m.0ycq_cj [award: Hugo Award for Best Dramatic Presentation; award_nominee: Jeffrey Kluger | Jim Lovell | Ron Howard | William Broyles, Jr.; ceremony: 1996 Hugo Awards; nominated_for: Apollo 13] | m.0yfbbn9 [award: Hugo Award for Best Dramatic Presentation; award_nominee: George Lucas | Ron Howard; ceremony: 1989 Hugo Awards; nominated_for: Willow] | m.0yj9zzq [award: Hugo Award for Best Dramatic Presentation; award_nominee: David Saperstein | Tom Benedek; ceremony: 1986 Hugo Awards; nominated_for: Cocoon] | m.0z62fp3 [award: Best Sports Movie ESPY Award; ceremony: 2005 ESPY Awards; nominated_for: Cinderella Man] | m.0zgtpgn [award_nominee: David Cross | Henry Winkler | Isla Fisher | Jason Bateman | Jeffrey Tambor | Jessica Walter; ceremony: 20th Screen Actors Guild Awards; nominated_for: Arrested Development] | m.0zgztlt [award: Golden Globe Award for Best Motion Picture – Drama; ceremony: 71st Golden Globe Awards; nominated_for: Rush] | m.0zrlfxd [award: Satellite Award for Best Director; ceremony: 18th Satellite Awards; nominated_for: Rush] …(+2) (to answer with ALL of them, include "#Ron Howard::award_nominations" as one answer entity)
    --producer.film--> Angels & Demons | Backdraft | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | The Dark Tower | The Dilemma | The Lost Symbol | The Paper | Beyond the Mat | Changeling | Clean and Sober | Closet Land | Cowboys & Aliens | Curious George 2: Follow That Monkey! | Inside Deep Throat | Inventing the Abbotts | J. Edgar | Katy Perry: Part of Me | Problem Child | Restless | Sky High | The 'Burbs | The Alamo | The Chamber | The Good Lie
    --producer.films_executive_produced--> Leo and Loree
    m.03mlppw | m.03mlsw7 | m.04kcph9 | m.08pc389 | m.09dyy55 | m.09dyymh | m.09k3ns1 | m.0jyzxxs | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0mzc0vk …(+4) (to answer with ALL of them, include "#m.03mlppw::award_winner" as one answer entity) --award_honor.award_winner--> Ron Howard
── Aaron Sorkin ──
    --award_nominee.award_nominations--> m.0my74fy [award: PGA Television Producer of the Year Award in Episodic; award_nominee: Brian Grazer | Rob Scheidlinger | Ron Howard | Thomas Schlamme | Tony Krantz; ceremony: Producers Guild of America Awards 1999; nominated_for: Sports Night]
── Al Reinert ──
    --award_nominee.award_nominations--> m.0ycq_cj [award: Hugo Award for Best Dramatic Presentation; award_nominee: Jeffrey Kluger | Jim Lovell | Ron Howard | William Broyles, Jr.; ceremony: 1996 Hugo Awards; nominated_for: Apollo 13]
── Alia Shawkat ──
    --award_nominee.award_nominations--> m.0zgtpgn [award_nominee: David Cross | Henry Winkler | Isla Fisher | Jason Bateman | Jeffrey Tambor | Jessica Walter; ceremony: 20th Screen Actors Guild Awards; nominated_for: Arrested Development]
── Barbie Adler ──
    m.04kcph9 --award_honor.award_winner--> Barbie Adler
── Bob Dolman ──
    --award_nominee.award_nominations--> m.0yfbbn9 [award: Hugo Award for Best Dramatic Presentation; award_nominee: George Lucas | Ron Howard; ceremony: 1989 Hugo Awards; nominated_for: Willow]
── Brad Copeland ──
    --award_nominee.award_nominations--> m.0lv4ffs [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Barbie Adler | Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo; ceremony: 57th Primetime Emmy Awards; nominated_for: Arrested Development]
── Bruce Akiyama ──
    --award_nominee.award_nominations--> m.0m_1x_7 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dean Criswell | Ellen Cockrill | Frank Marino; ceremony: 34th Daytime Creative Arts Emmy Awards; nominated_for: Curious George]
── Bruce Richmond ──
    m.0mvjqsr --award_honor.award_winner--> Bruce Richmond
── Carol Greenwald ──
    m.0lts_jr --award_honor.award_winner--> Carol Greenwald
    Barry W. Blaustein --director.film--> Beyond the Mat
    Beyond the Mat --film.produced_by--> Brian Grazer
    Changeling --film.produced_by--> Brian Grazer
    Clint Eastwood --director.film--> Changeling
    Closet Land --film.executive_produced_by--> Brian Grazer
    Mark Romanek --director.film--> The Lost Symbol
    Radha Bharadwaj --director.film--> Closet Land
    The Lost Symbol --film.produced_by--> Brian Grazer
    m.04kcph9 --award_honor.award_winner--> Mitchell Hurwitz | Richard A. Rosenstock
    m.0lts_jr --award_honor.award_winner--> David Wilcox | Ellen Cockrill | Matthew Baughman
    m.0mvjqsr --award_honor.award_winner--> John P. Melfi | Michael Bostick | Tom Hanks | Tony To
    m.0mwh6d0 --award_honor.award_winner--> Patty Jausoro
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.director.film': {'direct': ['film.director.film'], 'bridge': ['award.award_honor.award_winner', 'award.award_nominee.award_nominations', 'award.award_winner.awards_won', 'film.producer.film', 'film.producer.films_executive_produced']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=-0.0004679 l=0.0002958 f=-0.0004679 N=1.0 g=- lineage=✓ necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    The Journey                    p(ref)=0.0004302 → p(cf)=0.002517  Δp=-0.21pp  R=不可靠  
  max Δp=-0.2087pp  coverage=0 D_pos=0pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[-0.01]  max=-0.007192pp
  [结构: necessary=n/a pathway=ron howard]

## 块 #1 [msg 10]  分支=ron howard
调用命令:
```text
tool: retrieve_subgraph
center: ?film
relations: film.film.release_date_s
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: 11th Critics' Choice Awards | 13th Satellite Awards | 14th Critics' Choice Awards | 18th Satellite Awards | 1986 Hugo Awards | 1989 Hugo Awards | 1996 Hugo Awards | 2005 ESPY Awards | 20th Screen Actors Guild Awards | 21st People's Choice Awards | 27th Golden Raspberry Awards | 34th Daytime Creative Arts Emmy Awards)
▸ patterns: award_honor.award_winner
── Ron Howard ──
    m.0jyzxxs --award_honor.award_winner--> Ron Howard
note: UNCHANGED EVIDENCE (repeat): these relations produced no NEW edges since your previous subgraph — the same evidence is displayed again so it stays in context. ACT on it (checkpoint / answer / move to the next fact); re-retrieving will return the same. SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.film.release_date_s': {'direct': ['film.film.release_date_s'], 'bridge': ['common.topic.image', 'film.film.soundtrack', 'music.soundtrack.film']}}
anchor_sequence: Ron Howard ⭢ award_honor.award_winner | award_nominee.award_nominations | award_winner.awards_won | director.film | producer.film | producer.films_executive_produced (236) ⭢ topic.image | film.release_date_s | film.soundtrack | soundtrack.film (0)
layer_action: extend
```
(送评归属文本: 1 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=redundant_dup d=-0.0002236 l=-0.0002574 f=-0.0009565 N=0.0 g=- lineage=- necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    The Journey                    p(ref)=0.0002216 → p(cf)=0.002452  Δp=-0.22pp  R=不可靠  
  max Δp=-0.2231pp  coverage=0 D_pos=0pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[-0.04]  max=-0.03515pp
  [结构: necessary=n/a pathway=ron howard]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Ron Howard〕起始 p_alone(per-gold)=[+0.00]
  块#0 结构=n/a(通路未达): Δp=[-0.21]pp R=[-] maxΔp=-0.2087pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
〔通路 ?film〕起始 p_alone(per-gold)=[+0.00]
  块#1 结构=n/a(通路未达): Δp=[-0.22]pp R=[-] maxΔp=-0.2231pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
  双通道小结: 结构必要块=无 | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-567_df97b91c1a9dfe15bdad689feb59f791|s0 ==========
Q: What is the movie about a child prodigy that Ron Howard did?
gold=['Village of the Giants']  实际answer='NONE' f1=0.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.02]
pF(全轨迹, per-gold)=[+0.62]
通路独立 p [Ron Howard] per-gold=[+0.01]  lift锚 L=[-0.01]
通路独立 p [Child prodigy] per-gold=[+0.73]  lift锚 L=[+0.71]

## 块 #0 [msg 5]  分支=ron howard
调用命令:
```text
tool: retrieve_subgraph
center: Ron Howard
relations: film.director.film | film.film.directed_by
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Ron Howard
▸ patterns: award_honor.award_winner | award_nominee.award_nominations | director.film | film.directed_by | producer.film | producer.films_executive_produced | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.executive_produced_by ⭢ director.film | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.executive_produced_by ⭢ film.directed_by | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.produced_by ⭢ director.film | award_honor.award_winner ⭢ award_winner.awards_won ⭢ film.produced_by ⭢ film.directed_by
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dorothea Gillim | Ellen Cockrill | Jon Shapiro; ceremony: 41st Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.05bkr1w [award: Academy Award for Best Director; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05bm2lq [award: Academy Award for Best Picture; award_nominee: Brian Grazer | Eric Fellner; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.07zqyp3 [award: BAFTA Award for Best Direction; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.07zqyxh [award: BAFTA Award for Best Direction; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lbx1t [award: BAFTA Award for Best Film; award_nominee: Brian Grazer; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lby3g [award: BAFTA Award for Best Film; award_nominee: Brian Grazer | Eric Fellner | Tim Bevan; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.090dj60 [ceremony: 34th Golden Globe Awards; nominated_for: The Shootist] | m.095h15z [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 53rd Golden Globe Awards; nominated_for: Apollo 13] | m.095h1h2 [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 59th Golden Globe Awards; nominated_for: A Beautiful Mind] | m.095h1tj [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 66th Golden Globe Awards; nominated_for: Frost/Nixon] | m.09k3n_p [award: Critics' Choice Movie Award for Best Director; ceremony: 11th Critics' Choice Awards; nominated_for: Cinderella Man] | m.09k3nwh [award: Critics' Choice Movie Award for Best Director; ceremony: 14th Critics' Choice Awards; nominated_for: Frost/Nixon] | m.09sc2mb [ceremony: 61st Directors Guild of America Awards; nominated_for: Frost/Nixon] | m.09tjrrf [award: Satellite Award for Best Director; ceremony: 13th Satellite Awards; nominated_for: Frost/Nixon] | m.09z78wm [award: Golden Raspberry Award for Worst Director; ceremony: 27th Golden Raspberry Awards; nominated_for: The Da Vinci Code] | m.0b6b38g [ceremony: 38th Directors Guild of America Awards; nominated_for: Cocoon] | m.0gkjjsg [award: Saturn Award for Best Director; nominated_for: Splash] | m.0glkp4v [award: Golden Bear; nominated_for: The Missing] | m.0k1j58y [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Dorothea Gillim | Ellen Cockrill; ceremony: 39th Daytime Emmy Awards; nominated_for: Curious George] | m.0lmtm8f [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Dorothea Gillim | Ellen Cockrill; ceremony: 38th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0lv467q [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Brian Grazer | Chuck Tatham | David Nevins | Dean Lorey | John Amodeo | Mitchell Hurwitz; ceremony: 58th Primetime Emmy Awards; nominated_for: Arrested Development] | m.0lv4ffs [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Barbie Adler | Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo; ceremony: 57th Primetime Emmy Awards; nominated_for: Arrested Development] | m.0m0bwv0 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | David Wilcox | Ellen Cockrill | Jacqui Deegan; ceremony: 36th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0m_1x_7 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dean Criswell | Ellen Cockrill | Frank Marino; ceremony: 34th Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.0my74fy [award: PGA Television Producer of the Year Award in Episodic; award_nominee: Brian Grazer | Rob Scheidlinger | Ron Howard | Thomas Schlamme | Tony Krantz; ceremony: Producers Guild of America Awards 1999; nominated_for: Sports Night] | m.0n4htv8 [award_nominee: Brian Grazer | Chuck Martin | David Nevins | John Levenstein | Mitchell Hurwitz | Richard A. Rosenstock; ceremony: Producers Guild of America Awards 2004; nominated_for: Arrested Development] | m.0n4kzq9 [award_nominee: Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo | Mitchell Hurwitz; ceremony: Producers Guild of America Awards 2005; nominated_for: Arrested Development] | m.0n4psbw [award_nominee: Brian Grazer | David Nevins | Dean Lorey | Jim Vallely | John Amodeo | Mitchell Hurwitz; ceremony: Producers Guild of America Awards 2006; nominated_for: Arrested Development] | m.0n4t7bh [award_nominee: Brian Grazer | Eric Fellner; ceremony: Producers Guild of America Awards 2008; nominated_for: Frost/Nixon] | m.0nbbh6b [award: Australian Film Institute Award for Best Foreign Film; award_nominee: Brian Grazer; ceremony: 44th Australian Film Institute Awards; nominated_for: A Beautiful Mind] | m.0svn6jn [award_nominee: Al Jean | Bill Freiberger | Brian Grazer | David Ichioka | Donald R. Beck | Eddie Murphy; ceremony: 51st Primetime Emmy Awards; nominated_for: The PJs] | m.0v4_x4x [award: Primetime Emmy Award for Outstanding Children's Program; award_nominee: Herbert Wright | Rance Howard; ceremony: 34th Primetime Emmy Awards; nominated_for: Through the Magic Pyramid] | m.0ycq_cj [award: Hugo Award for Best Dramatic Presentation; award_nominee: Jeffrey Kluger | Jim Lovell | Ron Howard | William Broyles, Jr.; ceremony: 1996 Hugo Awards; nominated_for: Apollo 13] | m.0yfbbn9 [award: Hugo Award for Best Dramatic Presentation; award_nominee: George Lucas | Ron Howard; ceremony: 1989 Hugo Awards; nominated_for: Willow] | m.0yj9zzq [award: Hugo Award for Best Dramatic Presentation; award_nominee: David Saperstein | Tom Benedek; ceremony: 1986 Hugo Awards; nominated_for: Cocoon] | m.0z62fp3 [award: Best Sports Movie ESPY Award; ceremony: 2005 ESPY Awards; nominated_for: Cinderella Man] | m.0zgtpgn [award_nominee: David Cross | Henry Winkler | Isla Fisher | Jason Bateman | Jeffrey Tambor | Jessica Walter; ceremony: 20th Screen Actors Guild Awards; nominated_for: Arrested Development] | m.0zgztlt [award: Golden Globe Award for Best Motion Picture – Drama; ceremony: 71st Golden Globe Awards; nominated_for: Rush] | m.0zrlfxd [award: Satellite Award for Best Director; ceremony: 18th Satellite Awards; nominated_for: Rush] …(+2) (to answer with ALL of them, include "#Ron Howard::award_nominations" as one answer entity)
    --producer.film--> Angels & Demons | Backdraft | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | The Dark Tower | The Dilemma | The Lost Symbol | The Paper | Beyond the Mat | Changeling | Clean and Sober | Closet Land | Cowboys & Aliens | Curious George 2: Follow That Monkey! | Inside Deep Throat | Inventing the Abbotts | J. Edgar | Katy Perry: Part of Me | Problem Child | Restless | Sky High | The 'Burbs | The Alamo | The Chamber | The Good Lie
    --producer.films_executive_produced--> Leo and Loree
    m.03mlppw | m.03mlsw7 | m.04kcph9 | m.08pc389 | m.09dyy55 | m.09dyymh | m.09k3ns1 | m.0jyzxxs | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0mzc0vk …(+4) (to answer with ALL of them, include "#m.03mlppw::award_winner" as one answer entity) --award_honor.award_winner--> Ron Howard
    A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto …(+17) (to answer with ALL of them, include "#A Beautiful Mind::directed_by" as one answer entity) --film.directed_by--> Ron Howard
── Aaron Sorkin ──
    --award_nominee.award_nominations--> m.0my74fy [award: PGA Television Producer of the Year Award in Episodic; award_nominee: Brian Grazer | Rob Scheidlinger | Ron Howard | Thomas Schlamme | Tony Krantz; ceremony: Producers Guild of America Awards 1999; nominated_for: Sports Night]
── Al Reinert ──
    --award_nominee.award_nominations--> m.0ycq_cj [award: Hugo Award for Best Dramatic Presentation; award_nominee: Jeffrey Kluger | Jim Lovell | Ron Howard | William Broyles, Jr.; ceremony: 1996 Hugo Awards; nominated_for: Apollo 13]
── Alia Shawkat ──
    --award_nominee.award_nominations--> m.0zgtpgn [award_nominee: David Cross | Henry Winkler | Isla Fisher | Jason Bateman | Jeffrey Tambor | Jessica Walter; ceremony: 20th Screen Actors Guild Awards; nominated_for: Arrested Development]
── Barbie Adler ──
    m.04kcph9 --award_honor.award_winner--> Barbie Adler
── Bob Dolman ──
    --award_nominee.award_nominations--> m.0yfbbn9 [award: Hugo Award for Best Dramatic Presentation; award_nominee: George Lucas | Ron Howard; ceremony: 1989 Hugo Awards; nominated_for: Willow]
── Brad Copeland ──
    --award_nominee.award_nominations--> m.0lv4ffs [award: Primetime Emmy Award for Outstanding Comedy Series; award_nominee: Barbie Adler | Brian Grazer | Chuck Martin | David Nevins | Jim Vallely | John Amodeo; ceremony: 57th Primetime Emmy Awards; nominated_for: Arrested Development]
── Bruce Akiyama ──
    --award_nominee.award_nominations--> m.0m_1x_7 [award_nominee: Brian Grazer | Carol Greenwald | David Kirschner | Dean Criswell | Ellen Cockrill | Frank Marino; ceremony: 34th Daytime Creative Arts Emmy Awards; nominated_for: Curious George]
── Bruce Richmond ──
    m.0mvjqsr --award_honor.award_winner--> Bruce Richmond
── Carol Greenwald ──
    m.0lts_jr --award_honor.award_winner--> Carol Greenwald
    Barry W. Blaustein --director.film--> Beyond the Mat
    Beyond the Mat --film.directed_by--> Barry W. Blaustein
    Beyond the Mat --film.produced_by--> Brian Grazer
    Changeling --film.directed_by--> Clint Eastwood
    Changeling --film.produced_by--> Brian Grazer
    Clint Eastwood --director.film--> Changeling
    Closet Land --film.directed_by--> Radha Bharadwaj
    Closet Land --film.executive_produced_by--> Brian Grazer
    Mark Romanek --director.film--> The Lost Symbol
    Radha Bharadwaj --director.film--> Closet Land
    The Lost Symbol --film.directed_by--> Mark Romanek
    The Lost Symbol --film.produced_by--> Brian Grazer
    m.04kcph9 --award_honor.award_winner--> Mitchell Hurwitz | Richard A. Rosenstock
    m.0lts_jr --award_honor.award_winner--> David Wilcox | Ellen Cockrill | Matthew Baughman
    m.0mvjqsr --award_honor.award_winner--> John P. Melfi | Michael Bostick | Tom Hanks | Tony To
    m.0mwh6d0 --award_honor.award_winner--> Patty Jausoro
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.director.film': {'direct': ['film.director.film'], 'bridge': ['award.award_honor.award_winner', 'award.award_nominee.award_nominations', 'award.award_winner.awards_won', 'film.producer.film', 'film.producer.films_executive_produced']}, 'film.film.directed_by': {'direct': ['film.film.directed_by'], 'bridge': ['award.award_honor.award_winner', 'award.award_nominee.award_nominations', 'award.award_winner.awards_won', 'film.director.film', 'film.producer.film', 'film.producer.films_executive_produced']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=harmful d=-0.00861 l=-0.25 f=-0.008533 N=1.0 g=- lineage=- necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Village of the Giants          p(ref)=0.006272 → p(cf)=0.01683  Δp=-1.06pp  R=不可靠  
  max Δp=-1.056pp  coverage=0 D_pos=0pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[-11.61]  max=-11.61pp
  [结构: necessary=n/a pathway=ron howard]

## 块 #1 [msg 9]  分支=child prodigy
调用命令:
```text
tool: retrieve_subgraph
center: Child prodigy
relations: film.film_subject.films | film.film_genre.films_in_this_genre
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Child prodigy
▸ patterns: film_subject.films | film.subjects ⭢ film_genre.films_in_this_genre
── Child prodigy ──
    --film_subject.films--> Village of the Giants
    Village of the Giants --film.subjects--> Child prodigy
── Village of the Giants ──
    Juvenile Delinquency Film --film_genre.films_in_this_genre--> Village of the Giants
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.film_genre.films_in_this_genre': {'direct': ['film.film_genre.films_in_this_genre'], 'bridge': ['film.film_subject.films']}}
```
(送评归属文本: 5 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.5591 l=0.5518 f=0.7932 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Ron Howard〕起始 p_alone(per-gold)=[+0.01]
  块#0 结构=n/a(通路未达): Δp=[-1.06]pp R=[-] maxΔp=-1.056pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
〔通路 Child prodigy〕起始 p_alone(per-gold)=[+0.73]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  双通道小结: 结构必要块=['1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec|s2 ==========
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?
gold=['Poetic Justice']  实际answer='Poetic Justice' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.04]
pF(全轨迹, per-gold)=[+0.44]
通路独立 p [Tupac Shakur] per-gold=[+0.38]  lift锚 L=[+0.34]
通路独立 p [Kirk M. Petruccelli] per-gold=[+0.25]  lift锚 L=[+0.21]

## 块 #0 [msg 5]  分支=tupac shakur
调用命令:
```text
tool: retrieve_subgraph
center: Tupac Shakur
relations: film.actor.film | film.person_or_entity_appearing_in_film.films | film.performance.film
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Tupac Shakur
▸ patterns: award_nomination.award_nominee | actor.film | person_or_entity_appearing_in_film.films | producer.releases_produced | producer.releases_produced ⭢ performance.film | producer.tracks_produced ⭢ recording.releases ⭢ performance.film | recording.producer ⭢ recording.releases ⭢ performance.film
── Tupac Shakur ──
    --actor.film--> m.02vb3h0 [character: Lucky; film: Poetic Justice] | m.02vcpnk [character: Tank; film: Bullet] | m.02vcykh [character: Digital Underground member; film: Nothing but Trouble] | m.0j_81z [character: Bishop; film: Juice] | m.0js_kj [character: Birdie; film: Above the Rim] | m.0jyn86 [character: Det. Rodriguez; film: Gang Related] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore; film: Gridlock'd] | m.0pcn9p9 [character: Sniper; film: Murder Was the Case]
    --person_or_entity_appearing_in_film.films--> m.0cg09kz [film: Tupac: Resurrection] | m.0cg53k6 [film: Tupac Shakur: Thug Angel: The Life of an Outlaw; type_of_appearance: Him/Herself] | m.0crz6dl [film: Biggie & Tupac] | m.0cs3gpc [film: Thug Immortal: The Tupac Shakur Story] | m.0cs6p06 [film: Tupac: So Many Years, So Many Tears] | m.0csbsmb [film: Tupac Vs.] | m.0cscmvw [film: Hip Hop Story: Tha Movie] | m.0cskjp_ [film: Welcome to Death Row] | m.0cv_t55 [film: Tupac Shakur: Before I Wake] | m.0gm2nfd [film: Tupac: Uncensored and Uncut: The Lost Prison Tapes] | m.0jmyz7_ [film: Dead Homiez] | m.0jmyz7d [film: Tupac: Assassination] | m.0jmyz7m [film: Beef] | m.0jmyz7t [film: Freestyle: The Art of Rhyme] | m.0jmyz86 [film: Apprenticeship of Tupac Shakur] | m.0jmyz8d [film: Tha Westside] | m.0jmyz8n [film: R.I.P.: Shades of Hip Hop] | m.0jmyz8w [film: Best of the Source Awards: Vol. 1] | m.0jmyz91 [film: Death Row Uncut] | m.0jmyz96 [film: Digital Underground: Raw and Uncut] | m.0jmyz9c [film: Most Famous Hits: Hip Hop Story - The Movie Soundtrack] | m.0jmyz9j [film: R.I.P. II: Eyes on Hip Hop] | m.0pbjvw9 [film: Hip Hop Time Capsule: The Best of RETV 1993; type_of_appearance: Him/Herself] | m.0vxfjxm [film: Tupac: Live at the House of Blues; type_of_appearance: Archive Footage]
    --producer.releases_produced--> 15 Years on Death Row | Death Row: The Singles Collection | Gang Related | Poetic Justice | Still I Rise | Strictly 4 My N.I.G.G.A.Z... | Supercop | The Don Killuminati: The 7 Day Theory | West Side | オール・アイズ・オン・ミー
    --producer.tracks_produced--> Made Niggaz
    m.0_tln3r | m.0j_l784 | m.0j_l78n | m.0j_l7hc | m.0j_pbc9 | m.0lyw79d | m.0m0q4k7 | m.0m3g28_ | m.0mv8gv3 | m.0mw779x | m.0ndlnz1 | m.0nf_zwj …(+7) (to answer with ALL of them, include "#m.0_tln3r::award_nominee" as one answer entity) --award_nomination.award_nominee--> Tupac Shakur
    Made Niggaz --recording.producer--> Tupac Shakur
── Gang Related ──
    m.0jyn86 --performance.film--> Gang Related
    Made Niggaz --recording.releases--> Gang Related
── Poetic Justice ──
    m.02vb3h0 --performance.film--> Poetic Justice
    m.02vckpm --performance.film--> Poetic Justice
── Janet Jackson ──
    --actor.film--> m.02vckpm [film: Poetic Justice]
── K-Ci & JoJo ──
    m.0j_l78n --award_nomination.award_nominee--> K-Ci & JoJo
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.actor.film': {'direct': ['film.actor.film'], 'bridge': ['fictional_universe.person_in_fiction.representations_in_fiction']}, 'film.person_or_entity_appearing_in_film.films': {'direct': ['film.person_or_entity_appearing_in_film.films'], 'bridge': ['fictional_universe.person_in_fiction.representations_in_fiction']}, 'film.performance.film': {'direct': ['film.performance.film'], 'bridge': ['award.award_nomination.award_nominee', 'film.actor.film', 'film.performance.actor', 'music.producer.releases_produced']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.6003 l=0.3038 f=0.6003 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 9]  分支=kirk m petruccelli
调用命令:
```text
tool: retrieve_subgraph
center: Kirk M. Petruccelli
relations: film.director.film | film.film.directed_by
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Kirk M. Petruccelli
▸ patterns: award_nominee.award_nominations | film.film_art_direction_by | film.film_production_design_by | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film.directed_by
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Anaconda | Blade | Bullhead | Fantastic Four: Rise of the Silver Surfer | Ghost Rider | Killing Season | Lara Croft Tomb Raider: The Cradle of Life | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Incredible Hulk …(+8) (to answer with ALL of them, include "#3 Ninjas::film_production_design_by" as one answer entity) --film.film_production_design_by--> Kirk M. Petruccelli
── Barry Chusid ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
── 3 Ninjas ──
    --film.directed_by--> Jon Turteltaub
    Jon Turteltaub --director.film--> 3 Ninjas
── Bullhead ──
    --film.directed_by--> Ken Twohy
    Ken Twohy --director.film--> Bullhead
── Ghost Rider ──
    --film.directed_by--> Mark Steven Johnson
    Mark Steven Johnson --director.film--> Ghost Rider
── Lara Croft: Tomb Raider ──
    --film.directed_by--> Simon West
    Simon West --director.film--> Lara Croft: Tomb Raider
── Murder in the First ──
    --film.directed_by--> Marc Rocco
    Marc Rocco --director.film--> Murder in the First
── Mystery Men ──
    --film.directed_by--> Kinka Usher
    Kinka Usher --director.film--> Mystery Men
── The Last Castle ──
    --film.directed_by--> Rod Lurie
    Rod Lurie --director.film--> The Last Castle
── The Librarian: Quest for the Spear ──
    --film.directed_by--> Peter Winther
    Peter Winther --director.film--> The Librarian: Quest for the Spear
    Josef Rusnak --director.film--> The Thirteenth Floor
    Roland Emmerich --director.film--> The Patriot
    The Patriot --film.directed_by--> Roland Emmerich
    The Thirteenth Floor --film.directed_by--> Josef Rusnak
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.director.film': {'direct': ['film.director.film'], 'bridge': ['award.award_nominee.award_nominations', 'film.film.film_production_design_by', 'film.film_art_director.films_art_directed', 'film.film_production_designer.films_production_designed']}, 'film.film.directed_by': {'direct': ['film.film.directed_by'], 'bridge': ['award.award_nominee.award_nominations', 'film.film.film_art_direction_by', 'film.film.film_production_design_by', 'film.film_art_director.films_art_directed', 'film.film_production_designer.films_production_designed']}}
```
(送评归属文本: 14 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.0803 l=0.07999 f=0.3768 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Tupac Shakur〕起始 p_alone(per-gold)=[+0.38]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Kirk M. Petruccelli〕起始 p_alone(per-gold)=[+0.25]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a|s0 ==========
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?
gold=['Hailemariam Desalegn']  实际answer='Haile Selassie | Hailemariam Desalegn' f1=0.667
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.44]
pF(全轨迹, per-gold)=[+0.83]
通路独立 p [Ethiopian birr] per-gold=[+0.12]  lift锚 L=[-0.31]
通路独立 p [Ethiopia] per-gold=[+0.74]  lift锚 L=[+0.30]

## 块 #0 [msg 5]  分支=ethiopian birr
调用命令:
```text
tool: retrieve_subgraph
center: Ethiopian birr
relations: location.country.currency_used | finance.currency.countries_used
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Ethiopian birr
▸ patterns: currency.countries_used | country.currency_used
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
    Ethiopia --country.currency_used--> Ethiopian birr
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
```
(送评归属文本: 3 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.2176 l=0.009404 f=0.2176 N=1.0 g=- lineage=✓ necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Hailemariam Desalegn           p(ref)=0.123 → p(cf)=0.4359  Δp=-31.28pp  R=不可靠 ‼
  max Δp=-31.28pp  coverage=0 D_pos=0pp  label=harmful → 保留
◆ LOO:  Δp(per-gold,pp)=[+9.82]  max=9.82pp
  [结构: necessary=n/a pathway=ethiopian birr]

## 块 #1 [msg 9]  分支=ethiopian birr
调用命令:
```text
tool: retrieve_subgraph
center: Ethiopia
relations: government.government.government_for | government.politician.government_positions_held
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Ethiopian birr  (sequence root; this layer applies to the frontier: Ethiopia)
▸ patterns: currency.countries_used ⭢ government.government_for | currency.countries_used ⭢ government_position_held.jurisdiction_of_office | currency.countries_used ⭢ governmental_jurisdiction.governing_officials | government.government_for | government_position_held.jurisdiction_of_office | person.nationality
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
── Ethiopia ──
    --governmental_jurisdiction.governing_officials--> m.010g4gn8 [basic_title: Prime minister] | m.010pzwzw [office_holder: Haile Selassie] | m.0kmspfs [governmental_body: House of Peoples' Representatives] | m.0l0j4x3 | m.0n1nqyj [basic_title: Prime minister; from: 2012-09-21-08:00; has_no_value: To; office_holder: Hailemariam Desalegn; office_position_or_title: Prime Minister of Ethiopia]
    Government of Ethiopia --government.government_for--> Ethiopia
    m.010g4gn8 | m.010pzwzw | m.0kmspfs | m.0l0j4x3 | m.0n1nqyj --government_position_held.jurisdiction_of_office--> Ethiopia
    Baeda Maryam I | Demetros | Gebre Krestos | Gigar | Tekle Giyorgis I | Tekle Haymanot II --person.nationality--> Ethiopia
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'government.politician.government_positions_held': {'direct': ['government.politician.government_positions_held'], 'bridge': ['government.government_position_held.jurisdiction_of_office', 'government.governmental_jurisdiction.governing_officials', 'people.person.nationality']}}
anchor_sequence: Ethiopian birr ⭢ currency.countries_used | country.currency_used (1) ⭢ government.government_for | government_position_held.jurisdiction_of_office | governmental_jurisdiction.governing_officials | person.nationality (0)
layer_action: extend
```
(送评归属文本: 6 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.1368 l=0.1368 f=0.345 N=0.944 g=★ lineage=- necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Hailemariam Desalegn           p(ref)=0.7408 → p(cf)=0.4362  Δp=+30.46pp  R=+1.00 ★
  max Δp=30.46pp  coverage=1 D_pos=30.46pp  label=informative → 保留
◆ LOO:  Δp(per-gold,pp)=[+70.40]  max=70.4pp
  [结构: necessary=n/a pathway=ethiopian birr]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Ethiopian birr〕起始 p_alone(per-gold)=[+0.12]
  块#0 结构=n/a(通路未达): Δp=[-31.28]pp R=[-] maxΔp=-31.28pp cov=0 [harmful] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
〔通路 Ethiopia〕起始 p_alone(per-gold)=[+0.74]
  块#1 结构=n/a(通路未达): Δp=[+30.46]pp R=[+1.00] maxΔp=30.46pp cov=1 [informative] ⇒ Informative → 保留
  双通道小结: 结构必要块=无 | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-2209_c1374f388d9cc7a78365860c91218362|s0 ==========
Q: What year did the basketball team coached by Brad Stevens win the championship?
gold=['2008 NBA Finals', '1969 NBA Finals', '1986 NBA Finals', '1984 NBA Finals', '1981 NBA Finals', '1976 NBA Finals', '1974 NBA Finals', '1968 NBA Finals']  实际answer='2008' f1=0.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.07 +0.07 +0.07 +0.06 +0.06 +0.06 +0.06 +0.06 +0.06 +0.06 +0.07 +0.07 +0.08 +0.08 +0.09 +0.09 +0.16]
pF(全轨迹, per-gold)=[+0.44 +0.48 +0.49 +0.40 +0.25 +0.44 +0.26 +0.23 +0.24 +0.48 +0.31 +0.21 +0.29 +0.36 +0.39 +0.42 +0.52]
通路独立 p [Brad Stevens] per-gold=[+0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.05 +0.04 +0.09]  lift锚 L=[-0.03 -0.03 -0.03 -0.02 -0.02 -0.02 -0.02 -0.02 -0.02 -0.02 -0.03 -0.03 -0.04 -0.04 -0.04 -0.04 -0.07]
通路独立 p [Butler Bulldogs men's ba] per-gold=[+0.68 +0.35 +0.34 +0.41 +0.32 +0.29 +0.34 +0.31 +0.39 +0.36 +0.45 +0.35 +0.36 +0.40 +0.54 +0.54 +0.71]  lift锚 L=[+0.61 +0.29 +0.27 +0.35 +0.26 +0.24 +0.28 +0.26 +0.33 +0.30 +0.37 +0.28 +0.28 +0.33 +0.45 +0.45 +0.55]
通路独立 p [1957 NBA Finals] per-gold=[+0.43 +0.56 +0.55 +0.42 +0.26 +0.50 +0.26 +0.21 +0.21 +0.63 +0.30 +0.22 +0.30 +0.36 +0.39 +0.37 +0.51]  lift锚 L=[+0.36 +0.49 +0.49 +0.36 +0.21 +0.44 +0.20 +0.16 +0.15 +0.57 +0.23 +0.15 +0.22 +0.28 +0.31 +0.29 +0.35]

## 块 #0 [msg 5]  分支=brad stevens
调用命令:
```text
tool: retrieve_subgraph
center: Brad Stevens
relations: sport.team_coaches | sports_team_coach.teams_coached | basketball_team.head_coach | sports_team.coaches
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Brad Stevens
▸ patterns: basketball_coach.previous_teams | basketball_coach.team | basketball_team.head_coach | sport.team_coaches | sports_team_coach.teams_coached | basketball_coach.team ⭢ sports_team.coaches | basketball_team.head_coach ⭢ sports_team.coaches | sports_team_coach.sports_coached ⭢ sport.team_coaches | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ basketball_team.head_coach | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ sports_team.coaches | topic.notable_types ⭢ person.profession ⭢ sports_team_coach.teams_coached | sport.team_coaches ⭢ sports_team_coach.sports_coached ⭢ sports_team_coach.teams_coached | sports_team_coach.sports_coached ⭢ sport.team_coaches ⭢ sports_team_coach.teams_coached | sports_team_coach.teams_coached ⭢ sports_team_coach_tenure.team ⭢ basketball_team.head_coach | sports_team_coach_tenure.coach ⭢ sports_team_coach_tenure.team ⭢ basketball_team.head_coach | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ basketball_coach.team ⭢ sport.team_coaches | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ basketball_team.head_coach ⭢ sport.team_coaches | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ sports_team.sport ⭢ sport.team_coaches | basketball_historical_coach_position.coach
── Brad Stevens ──
    --topic.notable_types--> Basketball Coach
    --basketball_coach.previous_teams--> m.0wfd2k7 [team: Butler Bulldogs men's basketball]
    --sports_team_coach.sports_coached--> Basketball
    --basketball_coach.team--> Boston Celtics
    --sports_team_coach.teams_coached--> m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics] | m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball]
    m.0w48285 --sports_team_coach_tenure.coach--> Brad Stevens
    m.0wfd2k7 --basketball_historical_coach_position.coach--> Brad Stevens
    Boston Celtics --basketball_team.head_coach--> Brad Stevens
    Basketball --sport.team_coaches--> Brad Stevens
── Butler Bulldogs men's basketball ──
    --sports_team.coaches--> m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball] | m.0w4828t [coach: Brad Stevens; position: Head coach]
    --basketball_team.head_coach--> Brandon Miller
    --sports_team.sport--> Basketball
    Brandon Miller | m.0w48285 | m.0wfd2k7 --basketball_coach.team--> Butler Bulldogs men's basketball
── Boston Celtics ──
    --sports_team.coaches--> m.0w1g5hx [position: Coach] | m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics]
── Geno Auriemma ──
    --person.profession--> Basketball Coach
    --sports_team_coach.sports_coached--> Basketball
    --sports_team_coach.teams_coached--> m.0y98dfs [has_no_value: To; position: Basketball Coach]
    Basketball --sport.team_coaches--> Geno Auriemma
── Basketball ──
    --sport.team_coaches--> Billy Donovan | Billy Wright | Brandon Miller | Carl Roth | Derek Fisher | Don Meyer | Earl Scott | Enoch J. Mills | Ettore Messina | Frank Haith | Frank Summers | Frank Vogel | Fred Hengeveld | Gene Keady | Gregg Popovich | Jarron Collins | Jason Kidd | Jesse Mermuys | Jim Boeheim | Jim Calhoun | John Floyd | June Olkowski | Larry Drew | Marty Fletcher | Matt Johnson | Mike Maker | Mike Montgomery | Ned Thompson | Pat Kelsey | Pat Summitt | Rick Barnes | Robert Morris | Sam Jones | Tay Baker | Tom Izzo | Tony Miller
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'sport.team_coaches': {'direct': ['sports.sport.team_coaches'], 'bridge': []}, 'sports_team_coach.teams_coached': {'direct': ['sports.sports_team_coach.teams_coached'], 'bridge': []}, 'basketball_team.head_coach': {'direct': ['basketball.basketball_team.head_coach'], 'bridge': ['basketball.basketball_coach.previous_teams', 'sports.sports_team_coach.teams_coached', 'sports.sports_team_coach_tenure.coach']}, 'sports_team.coaches': {'direct': ['sports.sports_team.coaches'], 'bridge': ['basketball.basketball_coach.previous_teams', 'basketball.basketball_coach.team', 'sports.sports_team_coach.teams_coached', 'sports.sports_team_coach_tenure.coach']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.05397 l=0.02214 f=0.05406 N=1.0 g=- lineage=✓ necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 9]  分支=brad stevens
调用命令:
```text
tool: retrieve_subgraph
center: Butler Bulldogs men's basketball | Boston Celtics
relations: sports.sports_team.championships | sports.sports_championship_event.champion
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Brad Stevens  (sequence root; this layer applies to the frontier: Assistant Coach | Basketball | Boston Celtics | Butler Bulldogs men's basketball | Head coach | To)
▸ patterns: basketball_coach.team ⭢ sports_championship_event.champion | basketball_coach.team ⭢ sports_team.championships | basketball_team.head_coach ⭢ sports_championship_event.champion | sports_championship_event.champion
── Brad Stevens ──
    --basketball_coach.team--> Boston Celtics
    Boston Celtics --basketball_team.head_coach--> Brad Stevens
── Boston Celtics ──
    --sports_team.championships--> 1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals | 1976 NBA Finals | 1981 NBA Finals | 1984 NBA Finals | 1986 NBA Finals | 2008 NBA Finals
    1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals …(+5) (to answer with ALL of them, include "#1957 NBA Finals::champion" as one answer entity) --sports_championship_event.champion--> Boston Celtics
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
anchor_sequence: Brad Stevens ⭢ basketball_coach.previous_teams | basketball_coach.team | basketball_team.head_coach | sport.team_coaches | sports_team.coaches | sports_team_coach.teams_coached | sports_team_coach_tenure.coach (6) ⭢ sports_championship_event.champion | sports_team.championships (0)
layer_action: extend
```
(送评归属文本: 4 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.1863 l=-0.01298 f=0.2197 N=0.935 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #2 [msg 13]  分支=brad stevens
调用命令:
```text
tool: retrieve_subgraph
center: 1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals | 1976 NBA Finals | 1981 NBA Finals | 1984 NBA Finals | 1986 NBA Finals | 2008 NBA Finals
relations: time.event.start_date
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Brad Stevens  (sequence root; this layer applies to the frontier: 1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals)
▸ patterns: basketball_coach.team ⭢ sports_championship_event.champion ⭢ event.start_date | basketball_coach.team ⭢ sports_team.championships ⭢ event.start_date | event.start_date | object.name
── Brad Stevens ──
    --basketball_coach.team--> Boston Celtics
── Boston Celtics ──
    --sports_team.championships--> 1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals | 1976 NBA Finals | 1981 NBA Finals | 1984 NBA Finals | 1986 NBA Finals | 2008 NBA Finals
    1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals …(+5) (to answer with ALL of them, include "#1957 NBA Finals::champion" as one answer entity) --sports_championship_event.champion--> Boston Celtics
── 1959 NBA Finals ──
    --object.name--> 1968 NBA Finals
    --event.start_date--> 1968-04-21-08:00
    1960 NBA Finals --object.name--> 1959 NBA Finals
── 1960 NBA Finals ──
    --event.start_date--> 1959-04-04-08:00
    1976 NBA Finals --object.name--> 1960 NBA Finals
── 1961 NBA Finals ──
    --object.name--> 1963 NBA Finals
    --event.start_date--> 1963-04-14-08:00
    2008 NBA Finals --object.name--> 1961 NBA Finals
── 1962 NBA Finals ──
    --object.name--> 1981 NBA Finals
    --event.start_date--> 1981-05-05-08:00
    1974 NBA Finals --object.name--> 1962 NBA Finals
── 1963 NBA Finals ──
    --object.name--> 1965 NBA Finals
    --event.start_date--> 1965-04-18-08:00
── 1964 NBA Finals ──
    --object.name--> 1974 NBA Finals
    --event.start_date--> 1974-04-28-08:00
    1981 NBA Finals --object.name--> 1964 NBA Finals
── 1965 NBA Finals ──
    --object.name--> 1986 NBA Finals
    --event.start_date--> 1986-05-26-08:00
── 1966 NBA Finals ──
    --object.name--> 2008 NBA Finals
    --event.start_date--> 2008-08:00
    1984 NBA Finals --object.name--> 1966 NBA Finals
    1957 NBA Finals --event.start_date--> 1957-03-30-08:00
    1968 NBA Finals --object.name--> 1969 NBA Finals
    1968 NBA Finals --event.start_date--> 1969-04-23-08:00
    1969 NBA Finals --object.name--> 1976 NBA Finals
    1969 NBA Finals --event.start_date--> 1976-05-23-08:00
    1974 NBA Finals --event.start_date--> 1962-04-07-08:00
    1976 NBA Finals --event.start_date--> 1960-03-27-08:00
    1981 NBA Finals --event.start_date--> 1964-04-18-08:00
    1984 NBA Finals --event.start_date--> 1966-04-17-08:00
    1986 NBA Finals --event.start_date--> 1984-05-27-08:00
    2008 NBA Finals --event.start_date--> 1961-04-02-08:00
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'time.event.start_date': {'direct': ['time.event.start_date'], 'bridge': ['type.object.name']}}
anchor_sequence: Brad Stevens ⭢ basketball_coach.previous_teams | basketball_coach.team | basketball_team.head_coach | sport.team_coaches | sports_team.coaches | sports_team_coach.teams_coached | sports_team_coach_tenure.coach (6) ⭢ sports_championship_event.champion | sports_team.championships (17) ⭢ event.start_date | object.name (0)
layer_action: extend
```
(送评归属文本: 12 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.08703 l=0.09537 f=0.3166 N=0.516 g=- lineage=- necessary=no
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    1957 NBA Finals                p(ref)=0.4288 → p(cf)=0.07246  Δp=+35.63pp  R=+0.99 ★
    1959 NBA Finals                p(ref)=0.5621 → p(cf)=0.06859  Δp=+49.35pp  R=+1.00 ★
    1960 NBA Finals                p(ref)=0.5536 → p(cf)=0.06946  Δp=+48.41pp  R=+1.00 ★
    1961 NBA Finals                p(ref)=0.4218 → p(cf)=0.06007  Δp=+36.18pp  R=+1.00 ★
    1962 NBA Finals                p(ref)=0.2636 → p(cf)=0.05843  Δp=+20.52pp  R=+0.99 ★
    1963 NBA Finals                p(ref)=0.4978 → p(cf)=0.05992  Δp=+43.79pp  R=+1.00 ★
    1964 NBA Finals                p(ref)=0.2607 → p(cf)=0.05914  Δp=+20.15pp  R=+0.99 ★
    1965 NBA Finals                p(ref)=0.214 → p(cf)=0.05785  Δp=+15.61pp  R=+1.00 ★
    1966 NBA Finals                p(ref)=0.2085 → p(cf)=0.06207  Δp=+14.64pp  R=+1.00 ★
    1968 NBA Finals                p(ref)=0.6295 → p(cf)=0.06424  Δp=+56.53pp  R=+1.00 ★
    1969 NBA Finals                p(ref)=0.3035 → p(cf)=0.07254  Δp=+23.10pp  R=+1.00 ★
    1974 NBA Finals                p(ref)=0.2226 → p(cf)=0.07246  Δp=+15.01pp  R=+0.99 ★
    1976 NBA Finals                p(ref)=0.3005 → p(cf)=0.07839  Δp=+22.21pp  R=+1.00 ★
    1981 NBA Finals                p(ref)=0.3603 → p(cf)=0.07521  Δp=+28.51pp  R=+1.00 ★
    1984 NBA Finals                p(ref)=0.3928 → p(cf)=0.08339  Δp=+30.94pp  R=+1.01 ★
    1986 NBA Finals                p(ref)=0.3734 → p(cf)=0.08805  Δp=+28.54pp  R=+1.00 ★
    2008 NBA Finals                p(ref)=0.5062 → p(cf)=0.1547  Δp=+35.14pp  R=+1.01 ★
  max Δp=56.53pp  coverage=1 D_pos=30.84pp  label=informative → 保留
◆ LOO:  Δp(per-gold,pp)=[-12.96 +16.66 +18.72 +3.49 -5.37 +16.81 -7.97 -8.46 -11.01 +13.79 -13.96 -3.28 +2.48 -1.31 -5.12 -4.37 -23.94]  max=18.72pp
  [结构: necessary=no pathway=brad stevens]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Brad Stevens〕起始 p_alone(per-gold)=[+0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.04 +0.05 +0.04 +0.09]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Butler Bulldogs men's ba〕起始 p_alone(per-gold)=[+0.68 +0.35 +0.34 +0.41 +0.32 +0.29 +0.34 +0.31 +0.39 +0.36 +0.45 +0.35 +0.36 +0.40 +0.54 +0.54 +0.71]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 1957 NBA Finals〕起始 p_alone(per-gold)=[+0.43 +0.56 +0.55 +0.42 +0.26 +0.50 +0.26 +0.21 +0.21 +0.63 +0.30 +0.22 +0.30 +0.36 +0.39 +0.37 +0.51]
  块#2 结构必要=否: Δp=[+35.63 +49.35 +48.41 +36.18 +20.52 +43.79 +20.15 +15.61 +14.64 +56.53 +23.10 +15.01 +22.21 +28.51 +30.94 +28.54 +35.14]pp R=[+0.99 +1.00 +1.00 +1.00 +0.99 +1.00 +0.99 +1.00 +1.00 +1.00 +1.00 +0.99 +1.00 +1.00 +1.01 +1.00 +1.01] maxΔp=56.53pp cov=1 [informative] ⇒ Informative → 保留
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-2316_b8e16d5f4985c5ab2a3c75e7bc8c9e1a|s0 ==========
Q: Who is the illustrator of the book Feu de joie and the person who influenced Jackson Pollock's work?
gold=['Pablo Picasso']  实际answer='Pablo Picasso' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.01]
pF(全轨迹, per-gold)=[+0.37]
通路独立 p [Feu de joie] per-gold=[+0.45]  lift锚 L=[+0.44]
通路独立 p [Jackson Pollock] per-gold=[+0.12]  lift锚 L=[+0.11]

## 块 #0 [msg 5]  分支=feu de joie
调用命令:
```text
tool: retrieve_subgraph
center: Feu de joie
relations: book.illustrator.books_illustrated | book.book.interior_illustrations_by
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Feu de joie
▸ patterns: book.interior_illustrations_by | illustrator.books_illustrated | book.interior_illustrations_by ⭢ influence_node.influenced ⭢ illustrator.books_illustrated | illustrator.books_illustrated ⭢ influence_node.influenced_by ⭢ book.interior_illustrations_by | school_or_movement.associated_works ⭢ written_work.school_or_movement ⭢ book.interior_illustrations_by | school_or_movement.associated_works ⭢ art_period_movement.associated_artists ⭢ illustrator.books_illustrated | school_or_movement.associated_works ⭢ visual_artist.associated_periods_or_movements ⭢ book.interior_illustrations_by | school_or_movement.associated_works ⭢ visual_artist.associated_periods_or_movements ⭢ illustrator.books_illustrated
── Feu de joie ──
    --book.interior_illustrations_by--> Pablo Picasso
    Dada --school_or_movement.associated_works--> Feu de joie
    Pablo Picasso --illustrator.books_illustrated--> Feu de joie
── Dada ──
    --art_period_movement.associated_artists--> Hans Arp | Joan Mir | Max Ernst
    Hans Arp | Joan Mir | Max Ernst --visual_artist.associated_periods_or_movements--> Dada
    Cinéma calendrier du coeur abstrait. maisons --written_work.school_or_movement--> Dada
    L'antitête, vol. III: Le Désespéranto --written_work.school_or_movement--> Dada
── Hans Arp ──
    --illustrator.books_illustrated--> Cinéma calendrier du coeur abstrait. maisons | Vingt-cinq poèmes | Vingt-cinq-et-un poèmes
    Cinéma calendrier du coeur abstrait. maisons | Vingt-cinq poèmes | Vingt-cinq-et-un poèmes --book.interior_illustrations_by--> Hans Arp
── Joan Mir ──
    --illustrator.books_illustrated--> L'antitête, vol. III: Le Désespéranto
    --influence_node.influenced_by--> Pablo Picasso
    Pablo Picasso --influence_node.influenced--> Joan Mir
    L'antitête, vol. III: Le Désespéranto --book.interior_illustrations_by--> Joan Mir
── Max Ernst ──
    --illustrator.books_illustrated--> L'antitête, vol. I: Monsieur Aa l'Antiphilosophe
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'book.illustrator.books_illustrated': {'direct': ['book.illustrator.books_illustrated'], 'bridge': ['book.book.interior_illustrations_by']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.2524 l=0.3335 f=0.2558 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 10]  分支=jackson pollock
调用命令:
```text
tool: retrieve_subgraph
center: Jackson Pollock
relations: influence.influence_node.influenced_by | base.inspiration.inspiration.inspired_by
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Jackson Pollock
▸ patterns: influence_node.influenced | influence_node.influenced_by | influence_node.peers | marriage.spouse | person.ethnicity | person.nationality | exhibition.subjects ⭢ exhibition_subject.exhibitions_created_about_this_subject ⭢ influence_node.influenced_by | exhibition_subject.exhibitions_created_about_this_subject ⭢ exhibition.subjects ⭢ influence_node.influenced_by | artwork.artist ⭢ visual_artist.artworks ⭢ influence_node.influenced_by | client.related_patron ⭢ patron.related_client ⭢ person.nationality ⭢ inspiration.inspired_by | patron_client_relationship.client ⭢ patron.related_client ⭢ person.nationality ⭢ inspiration.inspired_by | peer_relationship.peers ⭢ peer_relationship.peers ⭢ person.nationality ⭢ inspiration.inspired_by
── Jackson Pollock ──
    --person.ethnicity--> Americans
    --exhibition_subject.exhibitions_created_about_this_subject--> Action/Abstraction: Pollock, de Kooning, and American Art, 1940-1976
    --influence_node.influenced--> Allan Kaprow | Chuck Connelly | Cleve Gray | Frank Stella | Helen Frankenthaler | Ho Ho Ying | Jan-Hein Arens | Jeanine Heller | Kenneth Noland | Merlin Carpenter | Morris Louis | Robert Ryman | Ronnie Landfield | Roy Ascott
    --influence_node.influenced_by--> Carl Jung | Joan Mir | John D. Graham | Mark Tobey | Max Ernst | Pablo Picasso | Thomas Hart Benton
    --person.nationality--> United States of America
    --influence_node.peers--> m.03ysr_r [peers: Willem de Kooning]
    --client.related_patron--> m.0c1pjwj [patron: Peggy Guggenheim]
    Untitled --artwork.artist--> Jackson Pollock
    m.0c1pjwj --patron_client_relationship.client--> Jackson Pollock
    Carl Jung | Joan Mir | John D. Graham | Mark Tobey | Max Ernst | Pablo Picasso | Thomas Hart Benton --influence_node.influenced--> Jackson Pollock
    Allan Kaprow | Chuck Connelly | Cleve Gray | Frank Stella | Helen Frankenthaler | Ho Ho Ying | Jan-Hein Arens | Jeanine Heller | Kenneth Noland | Merlin Carpenter | Morris Louis | Robert Ryman …(+2) (to answer with ALL of them, include "#Allan Kaprow::influenced_by" as one answer entity) --influence_node.influenced_by--> Jackson Pollock
    m.03ysr_r --peer_relationship.peers--> Jackson Pollock
    m.025dmkz --marriage.spouse--> Jackson Pollock
    Action/Abstraction: Pollock, de Kooning, and American Art, 1940-1976 --exhibition.subjects--> Jackson Pollock
── Willem de Kooning ──
    --exhibition_subject.exhibitions_created_about_this_subject--> Action/Abstraction: Pollock, de Kooning, and American Art, 1940-1976
    --influence_node.influenced_by--> Allan Kaprow | John D. Graham | Josef Albers | Louise Nevelson | Vincent van Gogh
    --person.nationality--> United States of America
    Chuck Connelly | Franz Kline | Jasper Johns | Robert Ryman | Ronnie Landfield --influence_node.influenced_by--> Willem de Kooning
    m.03ysr_r --peer_relationship.peers--> Willem de Kooning
    Action/Abstraction: Pollock, de Kooning, and American Art, 1940-1976 --exhibition.subjects--> Willem de Kooning
── Lee Krasner ──
    m.025dmkz --marriage.spouse--> Lee Krasner
── Robert Ryman ──
    --visual_artist.artworks--> Untitled
    --influence_node.influenced_by--> Barnett Newman | Clyfford Still | Mark Rothko
── Morris Louis ──
    --visual_artist.artworks--> Untitled
    --influence_node.influenced_by--> Clement Greenberg | Helen Frankenthaler
    Kenneth Noland --influence_node.influenced_by--> Morris Louis
── United States of America ──
    \"History dressed up in the glow of love’s kiss turned grief into beauty.\" --inspiration.inspired_by--> United States of America
    Peggy Guggenheim --person.nationality--> United States of America
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'influence.influence_node.influenced_by': {'direct': ['influence.influence_node.influenced_by'], 'bridge': ['influence.influence_node.influenced', 'influence.influence_node.peers', 'people.marriage.spouse']}, 'base.inspiration.inspiration.inspired_by': {'direct': ['base.inspiration.inspiration.inspired_by'], 'bridge': ['people.person.ethnicity', 'people.person.nationality']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.07902 l=0.07902 f=-0.001673 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Feu de joie〕起始 p_alone(per-gold)=[+0.45]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Jackson Pollock〕起始 p_alone(per-gold)=[+0.12]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-1731_4eea981607dbe17b040580ce4cd93ec4|s0 ==========
Q: What did Randy Jackson play in the Eclipse Tour?
gold=['Bass guitar', 'Vocals']  实际answer='Bass guitar | Vocals' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.01 +0.01]
pF(全轨迹, per-gold)=[+0.29 +0.00]
通路独立 p [Randy Jackson] per-gold=[+0.16 +0.00]  lift锚 L=[+0.15 -0.00]
通路独立 p [Eclipse Tour] per-gold=[+0.01 +0.00]  lift锚 L=[-0.00 -0.00]

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
◆ 旧标记: cls=effective d=0.1999 l=0.09055 f=0.2023 N=1.0 g=★ lineage=- necessary=yes
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
◆ 旧标记: cls=effective d=-0.0277 l=-0.009226 f=-0.0005323 N=1.0 g=- lineage=✓ necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Bass guitar                    p(ref)=0.005463 → p(cf)=0.04404  Δp=-3.86pp  R=不可靠  
    Vocals                         p(ref)=0.00133 → p(cf)=0.006178  Δp=-0.48pp  R=不可靠  
  max Δp=-0.4848pp  coverage=0 D_pos=0pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[-10.08 -0.42]  max=-0.4203pp
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
◆ 旧标记: cls=effective d=0.0126 l=0.006461 f=0.1094 N=0.9 g=- lineage=- necessary=n/a
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Bass guitar                    p(ref)=0.005463 → p(cf)=8.648e-05  Δp=+0.54pp  R=不可靠  
    Vocals                         p(ref)=0.00133 → p(cf)=0.0002941  Δp=+0.10pp  R=不可靠  
  max Δp=0.5377pp  coverage=0 D_pos=0.3206pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[+18.24 +0.07]  max=18.24pp
  [结构: necessary=n/a pathway=eclipse tour]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Randy Jackson〕起始 p_alone(per-gold)=[+0.16 +0.00]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Eclipse Tour〕起始 p_alone(per-gold)=[+0.01 +0.00]
  块#2 结构=n/a(通路未达): Δp=[+0.54 +0.10]pp R=[- -] maxΔp=0.5377pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
  块#1 结构=n/a(通路未达): Δp=[-3.86 -0.48]pp R=[- -] maxΔp=-0.4848pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
  双通道小结: 结构必要块=['0'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec|s0 ==========
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?
gold=['Poetic Justice']  实际answer='NONE' f1=0.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.04]
pF(全轨迹, per-gold)=[+0.43]
通路独立 p [Tupac Shakur] per-gold=[+0.32]  lift锚 L=[+0.28]
通路独立 p [Kirk M. Petruccelli] per-gold=[+0.25]  lift锚 L=[+0.21]

## 块 #0 [msg 5]  分支=tupac shakur
调用命令:
```text
tool: retrieve_subgraph
center: Tupac Shakur
relations: film_character.portrayed_in_films | film.person_or_entity_appearing_in_film.films | film.actor.film | film.performance.film
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Tupac Shakur
▸ patterns: award_nomination.award_nominee | actor.film | performance.actor | person_or_entity_appearing_in_film.films | producer.releases_produced | producer.releases_produced ⭢ performance.film | producer.tracks_produced ⭢ recording.releases ⭢ performance.film | recording.producer ⭢ recording.releases ⭢ performance.film
── Tupac Shakur ──
    --actor.film--> m.02vb3h0 [character: Lucky; film: Poetic Justice] | m.02vcpnk [character: Tank; film: Bullet] | m.02vcykh [character: Digital Underground member; film: Nothing but Trouble] | m.0j_81z [character: Bishop; film: Juice] | m.0js_kj [character: Birdie; film: Above the Rim] | m.0jyn86 [character: Det. Rodriguez; film: Gang Related] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore; film: Gridlock'd] | m.0pcn9p9 [character: Sniper; film: Murder Was the Case]
    --person_or_entity_appearing_in_film.films--> m.0cg09kz [film: Tupac: Resurrection] | m.0cg53k6 [film: Tupac Shakur: Thug Angel: The Life of an Outlaw; type_of_appearance: Him/Herself] | m.0crz6dl [film: Biggie & Tupac] | m.0cs3gpc [film: Thug Immortal: The Tupac Shakur Story] | m.0cs6p06 [film: Tupac: So Many Years, So Many Tears] | m.0csbsmb [film: Tupac Vs.] | m.0cscmvw [film: Hip Hop Story: Tha Movie] | m.0cskjp_ [film: Welcome to Death Row] | m.0cv_t55 [film: Tupac Shakur: Before I Wake] | m.0gm2nfd [film: Tupac: Uncensored and Uncut: The Lost Prison Tapes] | m.0jmyz7_ [film: Dead Homiez] | m.0jmyz7d [film: Tupac: Assassination] | m.0jmyz7m [film: Beef] | m.0jmyz7t [film: Freestyle: The Art of Rhyme] | m.0jmyz86 [film: Apprenticeship of Tupac Shakur] | m.0jmyz8d [film: Tha Westside] | m.0jmyz8n [film: R.I.P.: Shades of Hip Hop] | m.0jmyz8w [film: Best of the Source Awards: Vol. 1] | m.0jmyz91 [film: Death Row Uncut] | m.0jmyz96 [film: Digital Underground: Raw and Uncut] | m.0jmyz9c [film: Most Famous Hits: Hip Hop Story - The Movie Soundtrack] | m.0jmyz9j [film: R.I.P. II: Eyes on Hip Hop] | m.0pbjvw9 [film: Hip Hop Time Capsule: The Best of RETV 1993; type_of_appearance: Him/Herself] | m.0vxfjxm [film: Tupac: Live at the House of Blues; type_of_appearance: Archive Footage]
    --producer.releases_produced--> 15 Years on Death Row | Death Row: The Singles Collection | Gang Related | Poetic Justice | Still I Rise | Strictly 4 My N.I.G.G.A.Z... | Supercop | The Don Killuminati: The 7 Day Theory | West Side | オール・アイズ・オン・ミー
    --producer.tracks_produced--> Made Niggaz
    m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 --performance.actor--> Tupac Shakur
    m.0_tln3r | m.0j_l784 | m.0j_l78n | m.0j_l7hc | m.0j_pbc9 | m.0lyw79d | m.0m0q4k7 | m.0m3g28_ | m.0mv8gv3 | m.0mw779x | m.0ndlnz1 | m.0nf_zwj …(+7) (to answer with ALL of them, include "#m.0_tln3r::award_nominee" as one answer entity) --award_nomination.award_nominee--> Tupac Shakur
    Made Niggaz --recording.producer--> Tupac Shakur
── Gang Related ──
    m.0jyn86 --performance.film--> Gang Related
    Made Niggaz --recording.releases--> Gang Related
── Poetic Justice ──
    m.02vb3h0 --performance.film--> Poetic Justice
    m.02vckpm --performance.film--> Poetic Justice
── Janet Jackson ──
    --actor.film--> m.02vckpm [film: Poetic Justice]
── K-Ci & JoJo ──
    m.0j_l78n --award_nomination.award_nominee--> K-Ci & JoJo
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film_character.portrayed_in_films': {'direct': ['film.film_character.portrayed_in_films'], 'bridge': ['fictional_universe.person_in_fiction.representations_in_fiction', 'film.actor.film', 'film.performance.actor']}, 'film.person_or_entity_appearing_in_film.films': {'direct': ['film.person_or_entity_appearing_in_film.films'], 'bridge': ['fictional_universe.person_in_fiction.representations_in_fiction']}, 'film.actor.film': {'direct': ['film.actor.film'], 'bridge': ['fictional_universe.person_in_fiction.representations_in_fiction']}, 'film.performance.film': {'direct': ['film.performance.film'], 'bridge': ['award.award_nomination.award_nominee', 'film.actor.film', 'film.performance.actor', 'music.producer.releases_produced']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.5426 l=0.3131 f=0.5426 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 10]  分支=kirk m petruccelli
调用命令:
```text
tool: retrieve_subgraph
center: Kirk M. Petruccelli
relations: film.director.film | film.film.directed_by
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Kirk M. Petruccelli
▸ patterns: award_nominee.award_nominations | film.film_art_direction_by | film.film_production_design_by | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film.directed_by
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Anaconda | Blade | Bullhead | Fantastic Four: Rise of the Silver Surfer | Ghost Rider | Killing Season | Lara Croft Tomb Raider: The Cradle of Life | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Incredible Hulk …(+8) (to answer with ALL of them, include "#3 Ninjas::film_production_design_by" as one answer entity) --film.film_production_design_by--> Kirk M. Petruccelli
── Barry Chusid ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
── 3 Ninjas ──
    --film.directed_by--> Jon Turteltaub
    Jon Turteltaub --director.film--> 3 Ninjas
── Bullhead ──
    --film.directed_by--> Ken Twohy
    Ken Twohy --director.film--> Bullhead
── Ghost Rider ──
    --film.directed_by--> Mark Steven Johnson
    Mark Steven Johnson --director.film--> Ghost Rider
── Lara Croft: Tomb Raider ──
    --film.directed_by--> Simon West
    Simon West --director.film--> Lara Croft: Tomb Raider
── Murder in the First ──
    --film.directed_by--> Marc Rocco
    Marc Rocco --director.film--> Murder in the First
── Mystery Men ──
    --film.directed_by--> Kinka Usher
    Kinka Usher --director.film--> Mystery Men
── The Last Castle ──
    --film.directed_by--> Rod Lurie
    Rod Lurie --director.film--> The Last Castle
── The Librarian: Quest for the Spear ──
    --film.directed_by--> Peter Winther
    Peter Winther --director.film--> The Librarian: Quest for the Spear
    Josef Rusnak --director.film--> The Thirteenth Floor
    Roland Emmerich --director.film--> The Patriot
    The Patriot --film.directed_by--> Roland Emmerich
    The Thirteenth Floor --film.directed_by--> Josef Rusnak
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'film.director.film': {'direct': ['film.director.film'], 'bridge': ['award.award_nominee.award_nominations', 'film.film.film_production_design_by', 'film.film_art_director.films_art_directed', 'film.film_production_designer.films_production_designed']}, 'film.film.directed_by': {'direct': ['film.film.directed_by'], 'bridge': ['award.award_nominee.award_nominations', 'film.film.film_art_direction_by', 'film.film.film_production_design_by', 'film.film_art_director.films_art_directed', 'film.film_production_designer.films_production_designed']}}
```
(送评归属文本: 14 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.162 l=0.1528 f=0.3771 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Tupac Shakur〕起始 p_alone(per-gold)=[+0.32]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Kirk M. Petruccelli〕起始 p_alone(per-gold)=[+0.25]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTest-626_01ad90831a03b6c5ef17898ccd80a639|s0 ==========
Q: What setting of the fictional universe Tempus Unbound is bisected by the Missouri River?
gold=['Kansas']  实际answer='Kansas' f1=1.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.01]
pF(全轨迹, per-gold)=[+0.21]
通路独立 p [Tempus Unbound] per-gold=[+0.26]  lift锚 L=[+0.24]
通路独立 p [Missouri River] per-gold=[+0.25]  lift锚 L=[+0.23]

## 块 #0 [msg 5]  分支=tempus unbound
调用命令:
```text
tool: retrieve_subgraph
center: Tempus Unbound
relations: fictional_universe.work_of_fiction.setting | fictional_universe.fictional_setting.universe | fictional_universe.fictional_setting.contained_by
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Tempus Unbound
▸ patterns: location_in_fiction.works_set_here | military_command_in_fiction.mentioned_in_works | written_work.next_in_series | fictional_character.appears_in_these_fictional_universes | fictional_setting.universe | fictional_setting.works_set_here | fictional_universe.works_set_here | work_of_fiction.setting | fictional_character.appears_in_these_fictional_universes ⭢ work_of_fiction.setting | fictional_object.featured_in_fictional_universe ⭢ work_of_fiction.setting | fictional_setting.universe ⭢ fictional_setting.contained_by | fictional_universe.fictional_objects ⭢ fictional_setting.contained_by | fictional_universe.fictional_objects ⭢ fictional_setting.universe | fictional_universe.literary_series_set_here ⭢ work_of_fiction.setting | fictional_universe.locations ⭢ fictional_setting.contained_by | fictional_universe.locations ⭢ fictional_setting.universe | work_of_fiction.setting ⭢ fictional_setting.universe
── Tempus Unbound ──
    --fictional_universe.fictional_objects--> Lemurian citadel | Lemurian windows into any place or time
    --fictional_universe.literary_series_set_here--> The Sacred Band
    --fictional_universe.locations--> Lemuria | Kansas
    --work_of_fiction.setting--> Beyond Sanctuary | Citadel of Lemuria | Kansas | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Long Island | Manhattan | Mari, Syria | Meridian | New York | Pinnacle House | Sandia
    Arnaud | Askelon of Meridian | Chiara, Evening Star | Critias | Director Dick | Faun | Gayle | Jerry, called Stinger | Kama | Mano | Niko | Rath …(+3) (to answer with ALL of them, include "#Arnaud::appears_in_these_fictional_universes" as one answer entity) --fictional_character.appears_in_these_fictional_universes--> Tempus Unbound
    Lemurian citadel --fictional_object.featured_in_fictional_universe--> Tempus Unbound
    m.0dfy90l --military_command_in_fiction.mentioned_in_works--> Tempus Unbound
    City at the Edge of Time --written_work.next_in_series--> Tempus Unbound
    Kansas | Lemuria | Long Island | New York City --fictional_setting.universe--> Tempus Unbound
    Beyond Sanctuary | Citadel | Citadel of Lemuria | Egypt | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Manhattan | Mari, Syria | Meridian | New York | Pinnacle House …(+5) (to answer with ALL of them, include "#Beyond Sanctuary::works_set_here" as one answer entity) --location_in_fiction.works_set_here--> Tempus Unbound
── The Sacred Band ──
    --work_of_fiction.setting--> Abarsis Valley | Abarsis's Overlook | Bandara | Bandaran island chain | Battleplain of Chaeronea | Beyond Overlook | Beyond Sanctuary | Chaeronea | Citadel of Lemuria | Downwind | Free Nisibis | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Meridian battleplain | Mygdonia | Nisibis | Peace Falls | Pinnacle House | Rankan Mageguild | Ratfall | Sanctuary | Stepsons' barracks | The Misty Isles | Theban Cadmea | Tyse | liminal | warrior-monk academy
    m.0dfy90l --military_command_in_fiction.mentioned_in_works--> The Sacred Band
── Lemuria ──
    --fictional_setting.contained_by--> Beyond Sanctuary | Sea at the edge of time | Storm Seed | liminal
    --fictional_setting.universe--> Sacred Band of Stepsons | Thieves' World fictional shared universe
    Citadel of Lemuria | Lemurian citadel | Lemurian windows into any place or time | Mari, Syria | Pinnacle House | warrior-monk academy --fictional_setting.contained_by--> Lemuria
── Lemurian citadel ──
    --fictional_setting.contained_by--> Lemurian city-state | Storm Seed
    --fictional_setting.universe--> The Sacred Band of Stepsons universe
    Pinnacle House --fictional_setting.contained_by--> Lemurian citadel
    Storm Seed --work_of_fiction.setting--> Lemurian citadel
── Lemurian windows into any place or time ──
    --fictional_setting.contained_by--> Citadel of Lemuria | Sea at the edge of time
    --fictional_setting.universe--> Thieves' World fictional shared universe
── Beyond Sanctuary ──
    --fictional_setting.universe--> The Sacred Band of Stepsons universe | Thieves' World fictional shared universe
── Pinnacle House ──
    Faun --work_of_fiction.setting--> Pinnacle House
── Faun ──
    --work_of_fiction.setting--> Desert | Sandia
── Kansas ──
    --fictional_setting.universe--> The Sacred Band of Stepsons universe
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'fictional_universe.work_of_fiction.setting': {'direct': ['fictional_universe.work_of_fiction.setting'], 'bridge': ['base.militaryinfiction.location_in_fiction.works_set_here', 'book.written_work.next_in_series', 'fictional_universe.fictional_character.appears_in_these_fictional_universes', 'fictional_universe.fictional_setting.works_set_here', 'fictional_universe.fictional_universe.works_set_here']}, 'fictional_universe.fictional_setting.universe': {'direct': ['fictional_universe.fictional_setting.universe'], 'bridge': ['base.militaryinfiction.location_in_fiction.works_set_here', 'book.written_work.next_in_series', 'fictional_universe.fictional_setting.works_set_here', 'fictional_universe.fictional_universe.works_set_here', 'fictional_universe.work_of_fiction.setting']}, 'fictional_universe.fictional_setting.contained_by': {'direct': ['fictional_universe.fictional_setting.contained_by'], 'bridge': ['base.militaryinfiction.location_in_fiction.works_set_here', 'base.militaryinfiction.military_command_in_fiction.mentioned_in_works', 'book.written_work.next_in_series', 'fictional_universe.fictional_setting.works_set_here', 'fictional_universe.work_of_fiction.setting']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.3357 l=0.142 f=0.3357 N=1.0 g=★ lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 10]  分支=missouri river
调用命令:
```text
tool: retrieve_subgraph
center: Missouri River
relations: location.partiallycontains | location.location.contains_major_portion_of | location.location.containedby
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Missouri River
▸ patterns: body_of_water.bridges | river.mouth | location.containedby | location.partially_contained_by | travel_destination.tourist_attractions | river.basin_countries ⭢ location.contains_major_portion_of | river.mouth ⭢ location.containedby | river.origin ⭢ location.containedby | river.basin_countries ⭢ location_in_fiction.contained_by ⭢ location.partiallycontains | river.basin_countries ⭢ location_in_fiction.contains ⭢ location.containedby | river.basin_countries ⭢ location_in_fiction.contains ⭢ location.partiallycontains | river.basin_countries ⭢ administrative_division.first_level_division_of ⭢ location.partiallycontains
── Missouri River ──
    --river.basin_countries--> United States of America
    --body_of_water.bridges--> ASB Bridge | Ak-Sar-Ben Bridge | Amelia Earhart Memorial Bridge | Bellevue Bridge | Blair Bridge | Blanchette Memorial Bridge | Bob Kerrey Pedestrian Bridge | Boonslick Bridge | Broadway Bridge | Burt County Missouri River Bridge | Centennial Bridge | Chouteau Bridge | Christopher S. Bond Bridge | Daniel Boone Bridge | Discovery Bridge | Fairfax Bridge | Hannibal Bridge | Hardy Bridge | Heart of America Bridge | Hermann Bridge | Illinois Central Missouri River Bridge | Lewis Bridge | Liberty Bend Bridge | Meridian Highway Bridge | Miami Bridge | Mormon Bridge | Nebraska City Bridge | Old St. Charles Bridge | Paseo Bridge | Platte Purchase Bridge | Plattsmouth Bridge | Pony Express Bridge | Second Hannibal Bridge | Siouxland Veterans Memorial Bridge | Snowden Bridge | Union Pacific Missouri River Bridge | Vermillion–Newcastle Bridge | Veterans Memorial Bridge | Wabash Bridge
    --location.containedby--> North America | United States of America
    --river.mouth--> Mississippi River
    --river.origin--> Brower's Spring
    --location.partially_contained_by--> m.0wg900g [partially_contained_by: Missouri] | m.0wg906w [partially_contained_by: Iowa] | m.0wg90jv [partially_contained_by: Montana] | m.0wg90lw [partially_contained_by: Nebraska] | m.0wg90p7 [partially_contained_by: South Dakota] | m.0wg90rv [partially_contained_by: North Dakota] | m.0wg90t8 [partially_contained_by: Kansas]
    --travel_destination.tourist_attractions--> Glacier National Park | Lewis and Clark National Historic Trail
    Big Sioux River | Blue River | Grand River | James River | Kansas River | Little Missouri River | Platte River | White River | Yellowstone River --river.mouth--> Missouri River
    Bismarck --travel_destination.tourist_attractions--> Missouri River
── Kansas ──
    --location_in_fiction.contained_by--> United States of America
    --location.containedby--> Contiguous United States | Midwestern United States | West North Central States
    --administrative_division.first_level_division_of--> United States of America
    --location.partiallycontains--> m.0wg90t8 [partially_contained_by: Kansas] | m.0wg90tf [partially_contains: Arkansas River] | m.0wg90tm [partially_contained_by: Kansas] | m.0wg90ts [partially_contained_by: Kansas] | m.0wg90ty [partially_contains: Cimarron River] | m.0wg90v2 [partially_contains: Ozarks] | m.0wg90vm [partially_contained_by: Kansas] | m.0wg90w4 [partially_contains: Marmaton River] | m.0wg90wp [partially_contained_by: Kansas] | m.0wg90ww [partially_contains: Spring River] | m.0wg90x0 [partially_contains: Salt Fork Arkansas River] | m.0wg90x5 [partially_contains: Big Blue River] | m.0wg90xb [partially_contains: Blue River] | m.0wg90xh [partially_contains: Little Osage River] | m.0wg90xn [partially_contained_by: Kansas] | m.0wjpmb0 [partially_contained_by: Kansas]
    Atchison County | Chautauqua County | Cheyenne County | Clark County | Clay County | Cloud County | Coffey County | Comanche County | Crawford County | Decatur County | Dickinson County | Doniphan County …(+66) (to answer with ALL of them, include "#Atchison County::containedby" as one answer entity) --location.containedby--> Kansas
    United States of America --location_in_fiction.contains--> Kansas
── Iowa ──
    --administrative_division.first_level_division_of--> United States of America
    --location.partiallycontains--> m.0wg906q [partially_contains: Mississippi River]
── Arikaree River ──
    --location.partially_contained_by--> m.0wg90xn [partially_contained_by: Kansas]
── Marais des Cygnes River ──
    --location.partially_contained_by--> m.0wg90vm [partially_contained_by: Kansas]
── Neosho River ──
    --location.partially_contained_by--> m.0wjpmb0 [partially_contained_by: Kansas]
── Republican River ──
    --location.partially_contained_by--> m.0wg90tm [partially_contained_by: Kansas]
── Smoky Hill River ──
    --location.partially_contained_by--> m.0wg90ts [partially_contained_by: Kansas]
── Verdigris River ──
    --location.partially_contained_by--> m.0wg90wp [partially_contained_by: Kansas]
── United States of America ──
    Big Sioux River --location.containedby--> United States of America
    North America --location.contains_major_portion_of--> United States of America
    Big Sioux River --location.containedby--> North America
    Brower's Spring --location.containedby--> Centennial Mountains | Montana
    Lower Mississippi River --location.containedby--> Mississippi River
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'location.partiallycontains': {'direct': ['location.location.partiallycontains'], 'bridge': ['location.location.partially_contained_by', 'location.location.partially_containedby', 'location.location.partially_contains', 'location.partial_containment_relationship.partially_contains']}, 'location.location.contains_major_portion_of': {'direct': ['location.location.contains_major_portion_of'], 'bridge': ['location.location.containedby']}, 'location.location.containedby': {'direct': ['location.location.containedby'], 'bridge': ['geography.body_of_water.bridges', 'geography.river.mouth', 'location.location.partially_containedby', 'location.partial_containment_relationship.partially_contains', 'transportation.bridge.body_of_water_spanned', 'travel.travel_destination.tourist_attractions']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.07733 l=0.03564 f=0.2291 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Tempus Unbound〕起始 p_alone(per-gold)=[+0.26]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Missouri River〕起始 p_alone(per-gold)=[+0.25]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-2576_872253e47dd6ddaa213ff31eeda8783b|s0 ==========
Q: What continent is the country in the Eastern Time Zone that Falkland Island belong to located in?
gold=['Americas']  实际answer='NONE' f1=0.0
打分口径 v3: p_g=exp(mean token logprob)=归一化答案支持概率; 判定 ∃g:[Δp≥0.05(强效) 或 (Δp>0.01 且 R=Δp/L>0.1)]; L=通路固定锚(pF−p0); L<0.02=该 gold 概率通道不可靠
p0(无证据, per-gold)=[+0.00]
pF(全轨迹, per-gold)=[+0.00]
通路独立 p [Falkland Islands] per-gold=[+0.00]  lift锚 L=[+0.00]
通路独立 p [Eastern Time Zone] per-gold=[+0.00]  lift锚 L=[+0.00]
通路独立 p [United Kingdom, with Dep] per-gold=[+0.01]  lift锚 L=[+0.01]

## 块 #0 [msg 5]  分支=falkland islands
调用命令:
```text
tool: retrieve_subgraph
center: Falkland Islands
relations: sovereign_domain.sovereign_state | location.containedby
sg: sg1
```
工具结果(完整,未截断):
```text
fact_id: sg1
triples:
entities: Falkland Islands
▸ patterns: island_group.islands_in_group | government_position_held.jurisdiction_of_office | administrative_division.first_level_division_of | location.containedby | island.island_group ⭢ location.containedby | location.containedby ⭢ sovereign_domain.sovereign_state | administrative_area.administrative_children ⭢ sovereign_domain.sovereign_state ⭢ location.containedby | administrative_area.administrative_parent ⭢ sovereign_domain.sovereign_state ⭢ location.containedby
── Falkland Islands ──
    --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    --location.containedby--> Americas | Atlantic Ocean | South America | United Kingdom, with Dependencies and Territories
    --administrative_division.first_level_division_of--> United Kingdom, with Dependencies and Territories
    --island_group.islands_in_group--> East Falkland | Lively Island | New Island | Pebble Island | Saunders Island, Falkland Islands | South Georgia and the South Sandwich Islands | West Falkland
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> Falkland Islands
    Port Stanley Airport --location.containedby--> Falkland Islands
    East Falkland --island.island_group--> Falkland Islands
    South Georgia and the South Sandwich Islands --island.island_group--> Falkland Islands
    m.010wxphf | m.010wxs9y | m.09jy10q | m.0zbfy6d --government_position_held.jurisdiction_of_office--> Falkland Islands
── United Kingdom, with Dependencies and Territories ──
    --sovereign_domain.sovereign_state--> United Kingdom
    South Georgia and the South Sandwich Islands --location.containedby--> United Kingdom, with Dependencies and Territories
── East Falkland ──
    --location.containedby--> Atlantic Ocean
    Stanley --location.containedby--> East Falkland
── South Georgia and the South Sandwich Islands ──
    --location.containedby--> Americas
── United Kingdom ──
    --location.containedby--> Western Europe
    Guernsey --location.containedby--> United Kingdom
    Wales --location.containedby--> United Kingdom
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'sovereign_domain.sovereign_state': {'direct': ['base.aareas.schema.earth.sovereign_domain.sovereign_state'], 'bridge': ['location.administrative_division.first_level_division_of']}, 'location.containedby': {'direct': ['location.location.containedby'], 'bridge': ['geography.island_group.islands_in_group', 'government.government_position_held.jurisdiction_of_office', 'location.administrative_division.country', 'location.administrative_division_capital_relationship.administrative_division', 'location.location.contains']}}
```
(送评归属文本: 15 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.008539 l=-0.01665 f=0.008539 N=1.0 g=★ lineage=✓ necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #1 [msg 9]  分支=eastern time zone
调用命令:
```text
tool: retrieve_subgraph
center: Eastern Time Zone
relations: time_zone.locations_in_this_time_zone | location.location.time_zones
sg: sg2
```
工具结果(完整,未截断):
```text
fact_id: sg2
triples:
entities: Eastern Time Zone
▸ patterns: location.time_zones | image.appears_in_topic_gallery ⭢ topic.image ⭢ location.time_zones | topic.image ⭢ image.appears_in_topic_gallery ⭢ location.time_zones | location.time_zones ⭢ continents.countries_within ⭢ time_zone.locations_in_this_time_zone | location.time_zones ⭢ countries.continent ⭢ time_zone.locations_in_this_time_zone | time_zone.day_dst_begins ⭢ time_zone.day_dst_ends ⭢ location.time_zones | time_zone.day_dst_begins ⭢ time_zone.day_dst_ends ⭢ time_zone.locations_in_this_time_zone
── Eastern Time Zone ──
    --time_zone.day_dst_begins--> Second Sunday in March
    --topic.image--> Timezoneswest
    Timezoneswest --image.appears_in_topic_gallery--> Eastern Time Zone
    Americas | Bahamas | Canada | Latin America | Long Beach Island | Lucayan Archipelago | North America | United States of America --location.time_zones--> Eastern Time Zone
── Atlantic Time Zone ──
    --topic.image--> Timezoneswest
    Timezoneswest --image.appears_in_topic_gallery--> Atlantic Time Zone
    Aruba | Bermuda | Bonaire | British Virgin Islands | Canada | Curaçao | Dominican Republic | Greater Antilles | Greenland | Kingdom of the Netherlands | Leeward Islands | Netherlands …(+7) (to answer with ALL of them, include "#Aruba::time_zones" as one answer entity) --location.time_zones--> Atlantic Time Zone
── Timezoneswest ──
    --image.appears_in_topic_gallery--> Alaska Time Zone | Central Time Zone | Samoa Time Zone
    Alaska Time Zone | Central Time Zone | Samoa Time Zone --topic.image--> Timezoneswest
── Uruguay Time Zone ──
    --time_zone.day_dst_ends--> Second Sunday in March
    --time_zone.locations_in_this_time_zone--> Americas | South America | Uruguay
    Americas | South America | Uruguay --location.time_zones--> Uruguay Time Zone
── Central Time Zone ──
    Belize | Guatemala | Honduras | Latin America --location.time_zones--> Central Time Zone
── Alaska Time Zone ──
    Americas | North America | United States of America --location.time_zones--> Alaska Time Zone
── North America ──
    --continents.countries_within--> Antigua and Barbuda
    Antigua and Barbuda --countries.continent--> North America
── Antigua and Barbuda ──
    Eastern Caribbean Time Zone --time_zone.locations_in_this_time_zone--> Antigua and Barbuda
── Samoa Time Zone ──
    American Samoa --location.time_zones--> Samoa Time Zone
note: Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'time_zone.locations_in_this_time_zone': {'direct': ['time.time_zone.locations_in_this_time_zone'], 'bridge': ['location.location.time_zones']}}
```
(送评归属文本: 14 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=-0.003714 l=-0.0001118 f=0.007733 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

## 块 #2 [msg 13]  分支=falkland islands
调用命令:
```text
tool: retrieve_subgraph
center: United Kingdom, with Dependencies and Territories
relations: base.locations.planets.countries_within | location.location.contains
sg: sg3
```
工具结果(完整,未截断):
```text
fact_id: sg3
triples:
entities: Falkland Islands  (sequence root; this layer applies to the frontier: Americas | Appointed By (if Position is Appointed) | Atlantic Ocean | Basic title | Chief Executive of the Falkland Islands | Chief executive | Colin Roberts | East Falkland | Elizabeth II | From | Governor | Governor of the Falkland Islands)
▸ patterns: location.containedby | island_group.islands_in_group ⭢ administrative_area.administrative_children | island_group.islands_in_group ⭢ administrative_area.administrative_parent | location.contains | location.partially_contains
── Falkland Islands ──
    --location.containedby--> Americas | Atlantic Ocean
    --island_group.islands_in_group--> South Georgia and the South Sandwich Islands
── Atlantic Ocean ──
    --location.containedby--> World Ocean
    --location.contains--> Bailey | Bermuda Triangle | Boa Vista | Brava | Faial Island | Flores Island | Fogo | Gough Island | Graciosa | Maio, Cape Verde | Nightingale Island | North Atlantic Gyre | Pico Island | Rocas Atoll | Sal | Santiago | Santo Antão, Cape Verde | Sole | Southeast Iceland | Stóra Dímun | São Vicente | Texas Tower 4 | Western Approaches | Wreck of the  RMS Titanic
    --location.partially_contains--> Portugal | Spain | United Kingdom, with Dependencies and Territories
    Anguilla | Argentine Sea | Ascension Island | Azores | Bay of Biscay | Bermuda | Bouvet Island | British Isles | Canary Islands | Caribbean Sea | Celtic Sea | Corvo Island …(+29) (to answer with ALL of them, include "#Anguilla::containedby" as one answer entity) --location.containedby--> Atlantic Ocean
── Americas ──
    --location.containedby--> Western Hemisphere
    Anguilla | Antigua and Barbuda | Argentina | Aruba | Bahamas | Barbados | Belize | Bermuda | Bolivia | Bonaire | Brazil | British Virgin Islands …(+50) (to answer with ALL of them, include "#Anguilla::containedby" as one answer entity) --location.containedby--> Americas
── South Georgia and the South Sandwich Islands ──
    --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> South Georgia and the South Sandwich Islands
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and declare the values the evidence supports (any non-empty count). Final discrimination happens at answer analysis. Mid-chain entities are HOPS, not answers. Evidence blocks group triples by entity: 'h --rel--> t1 | t2' merges tails, 'h1 | h2 --rel--> t' merges heads. m.xxx/g.xxx are EVENT nodes — NEVER answer or bind them; use their named ATTRIBUTES (actor, character, office holder, jurisdiction), shown inline in brackets. Discriminator attributes (dates, incumbent) appear as their own edges — compare them to pick. Pick the next center FROM these triples.
relation_expansion: {'base.locations.planets.countries_within': {'direct': ['base.locations.planets.countries_within'], 'bridge': ['base.aareas.schema.administrative_area.administrative_parent']}, 'location.location.contains': {'direct': ['location.location.contains'], 'bridge': ['base.aareas.schema.administrative_area.administrative_children', 'base.aareas.schema.administrative_area.administrative_parent', 'location.country.administrative_divisions', 'location.location.containedby', 'location.location.partially_contained_by', 'location.location.partially_contains']}}
anchor_sequence: Falkland Islands ⭢ sovereign_domain.sovereign_state | island_group.islands_in_group | government_position_held.jurisdiction_of_office | administrative_division.country | administrative_division.first_level_division_of | administrative_division_capital_relationship.administrative_division | location.containedby | location.contains (32) ⭢ administrative_area.administrative_children | administrative_area.administrative_parent | country.administrative_divisions | location.partially_contained_by | location.partially_contains (0)
layer_action: extend
```
(送评归属文本: 12 行 = 本块独有新边; 其余行为上一轮已走路径的重渲染,已按三元组归属移除)
◆ 旧标记: cls=effective d=0.006654 l=0.006284 f=0.07183 N=0.948 g=- lineage=- necessary=no
◆ RSCC[v3] per-gold 明细 (概率域百分点 / R=占通路lift比):
    Americas                       p(ref)=0.008836 → p(cf)=0.000153  Δp=+0.87pp  R=不可靠  
  max Δp=0.8684pp  coverage=0 D_pos=0.8684pp  label=redundant → 保留
◆ LOO:  Δp(per-gold,pp)=[-0.53]  max=-0.5299pp
  [结构: necessary=no pathway=falkland islands]

── RSCC 通路隔离倒序收缩迹（每通路独立; Δp 为百分点, R=占通路固定 lift 比）──
〔通路 Falkland Islands〕起始 p_alone(per-gold)=[+0.00]
  块#0: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 Eastern Time Zone〕起始 p_alone(per-gold)=[+0.00]
  块#1: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
〔通路 United Kingdom, with Dep〕起始 p_alone(per-gold)=[+0.01]
  块#2 结构必要=否: Δp=[+0.87]pp R=[-] maxΔp=0.8684pp cov=0 [redundant] ⇒ 概率通道不可靠(通路lift<τ) → 弃权保留(交结构通道)
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突

