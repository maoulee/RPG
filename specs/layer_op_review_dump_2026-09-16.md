# 层操作人工审核 dump（逐轨迹行为 + φ/p_gain/标注）

每块: MODEL 行=模型调用参数; ↳ 行=环境返回(树/层动作/新实体/信号); ◆ 行=φ(到最近gold的BFS跳数,越小越近) before→after、p_gain(gold覆盖增量)、标注。
断链=未命中case中最后一次推进后的第一个未推进op。sg交付(无层操作)=首次建树等基线块,进信息基准但不参与三档。
**已知近似**: gold 若是 hub 节点(profession/religion 类,如 Priest)则一切人物邻居都 1-2 跳,φ 推进会假阳性——此时以 p_gain(gold 实体是否出现)为准,φ 只作方向参考。

==============================================================================
CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5  sample s0  f1=0.00  hit=False
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27, 1993?
gold: ['Priest']
pred: NONE  pred_entities: ['NONE']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Franz Liszt
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Franz Liszt | which religious organizations did he lead | ?org)', 'subquestion'
[2] MODEL retrieve_relations: center=Franz Liszt | question=which religious organizations did he lead
[3]   ↳ rr候选: entities: Franz Liszt
question: which religious organizations did he lead
candidate_relations: people.person.r
[4] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization_membership.member | organization.organization_member.member_of
[5]   ↳ sg交付(无层操作)  块: Franz Liszt; Life of Franz Liszt; Freemasonry
[5]   ↳ 新实体 7: Franz Liszt; Freemasonry; Funérailles; Harmonies poétiques et religieuses; Life of Franz Liszt; Légende No. 1: St François d'Assise; Sarabande and Cha
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Franz Liszt | question=what leadership positions did Franz Liszt hold
[7]   ↳ rr候选: entities: Franz Liszt
question: what leadership positions did Franz Liszt hold
candidate_relations: organizati
[8] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization.founders | organization.organization_founder.organizations_founded | people.person.e
[9]   ↳ 树: 
[9]   ↳ layer_action: extend   块: Franz Liszt; Life of Franz Liszt; Franz Liszt Academy of Music
[9]   ↳ 新实体 1: Franz Liszt Academy of Music, Budapest
[9]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=1 used=0  标注=harmful-break
[10] MODEL retrieve_relations: center=Franz Liszt | question=what religious leadership positions did Franz Liszt hold
[11]   ↳ rr候选: entities: Franz Liszt
question: what religious leadership positions did Franz Liszt hold
candidate_relations: 
[12] MODEL retrieve_subgraph: center=Franz Liszt | relations=people.person.religion | organization.organization.founders | organization.organization_founder.organizations_
[13]   ↳ 树: 
[13]   ↳ layer_action: extend   块: Franz Liszt; Life of Franz Liszt; Catholicism; Cosima Wagner; Heinrich Heine
[13]   ↳ 新实体 10: Carl Czerny; Catholicism; Charles Baudelaire; Charles-Valentin Alkan; Christianity; Cosima Wagner; Fryderyk Chopin; Heinrich Heine
[13]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=10 used=0  标注=nohelp-irrelevant
[14] MODEL retrieve_relations: center=Franz Liszt | question=what religious leadership or ecclesiastical positions did Franz Liszt hold
[15]   ↳ ENV: ⚠ purity-loop reminder (3rd similar query)
[16]   ↳ rr候选: entities: Franz Liszt
question: what religious leadership or ecclesiastical positions did Franz Liszt hold
can
[17] MODEL retrieve_subgraph: center=Franz Liszt | relations=people.profession.people_with_this_profession | organization.organization_member.member_of
[18]   ↳ 树: 
[18]   ↳ layer_action: extend   块: Franz Liszt; Life of Franz Liszt; Virtuoso
[18]   ↳ 新实体 10: Arcadi Volodos; Lance Dossor; Marc-André Hamelin; Mark Gasser; Niccolò Paganini; Osman Zeki Üngör; Pablo de Sarasate; Paolo Girolamo Besozzi
[18]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=10 used=0  标注=nohelp-irrelevant
[19] MODEL answer: entities=NONE
[20]   ↳ ENV: NONE → ladder: re-select relations; [explore ✗ none] restarts once
You may fall back ONE level: re-select the weakest subgraph's r
[21] MODEL plan: entities: Franz Liszt
[22]   ↳ ENV: ⌗ RESTART on none-verdict: RESTART (the only one): your first attempt's verdict was NONE — nothing retrieved related to the answer
[23] MODEL plan: entities: Franz Liszt
[24]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Franz Liszt | which organizations was this person a member of | ?org)', 'subque
[25] MODEL retrieve_relations: center=Franz Liszt | question=which organizations was this person a member of
[26]   ↳ rr候选: entities: Franz Liszt
question: which organizations was this person a member of
candidate_relations: organizat
[27] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization_member.member_of | organization.organization_membership.member | organization.organi
[29] MODEL retrieve_relations: center=Franz Liszt | question=which organizations did this person found
[30]   ↳ rr候选: entities: Franz Liszt
question: which organizations did this person found
candidate_relations: organization.or
[31] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization_founder.organizations_founded | organization.organization.founders | organization.or
[33] MODEL answer: 
[34]   ↳ ANSWER ACCEPTED: {"entities": []}
诊断: ·→break ·→irrele ·→irrele
标注分布 {'harmful-break': 1, 'nohelp-irrelevant': 2}

==============================================================================
CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5  sample s1  f1=0.00  hit=False
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27, 1993?
gold: ['Priest']
pred: Freemasonry  pred_entities: ['Freemasonry']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Franz Liszt
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Franz Liszt | which religious organizations did he lead/manage as member or fou
[2] MODEL retrieve_relations: center=Franz Liszt | question=which religious organizations did Franz Liszt lead/manage as member or founder
[3]   ↳ rr候选: entities: Franz Liszt
question: which religious organizations did Franz Liszt lead/manage as member or founder
[4] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.founders | organization_founder.organizations_founded | organization_member.member_of
[5]   ↳ sg交付(无层操作)  块: Franz Liszt; Life of Franz Liszt; Freemasonry
[5]   ↳ 新实体 8: Franz Liszt; Franz Liszt Academy of Music, Budapest; Freemasonry; Funérailles; Harmonies poétiques et religieuses; Life of Franz Liszt; Légende No. 1:
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=?org | question=when did Franz Liszt's leadership of this organization end
[7]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: when did Franz Liszt's leadership of 
[8] MODEL retrieve_subgraph: center=Freemasonry | Franz Liszt Academy of Music, Budapest | relations=organization.membership_organization.members | business.employment_tenure.company
[9]   ↳ sg交付(无层操作)  块: Franz Liszt Academy of Music; Freemasonry; Life of Franz Liszt
[9]   ↳ 新实体 0: 
[9]   ◆ φ 1→1 (未推进)  gold=无  (基线块，不参与三档标注)
[10] MODEL retrieve_relations: center=Freemasonry | Franz Liszt Academy of Music, Budapest | question=when did Franz Liszt's leadership/membership of this organization end
[11]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: when did Franz Liszt's leadership/mem
[12] MODEL retrieve_subgraph: center=Freemasonry | Franz Liszt Academy of Music, Budapest | relations=organization.membership_organization.members | organization.organization_membership.member | organ
[13]   ↳ 树: anchor_sequence: Freemasonry ⭢ employer.employees | employment_tenure.company | membership_organization.members | organization_membership.member | org
[13]   ↳ layer_action: update layer 1 (replaced none)   块: Franz Liszt Academy of Music; Freemasonry; Life of Franz Liszt
[13]   ↳ 新实体 0: 
[13]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=0 used=0  标注=harmful-break
[14] MODEL retrieve_relations: center=Freemasonry | Franz Liszt Academy of Music, Budapest | question=what type of organization is this / is this a religious organization
[15]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: what type of organization is this / i
[16] MODEL retrieve_subgraph: center=Freemasonry | Franz Liszt Academy of Music, Budapest | relations=organization.organization_type.organizations_of_this_type | organization.organization.organization
[17]   ↳ 树: 
[17]   ↳ layer_action: update layer 1 (replaced business.employer.employees, business.emp   块: Freemasonry; Franz Liszt Academy of Music; Life of Franz Liszt; Classical music; Catholicism
[17]   ↳ 新实体 4: ABRSM; Catholicism; Christianity; Classical music
[17]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=4 used=0  标注=nohelp-irrelevant
[18] MODEL retrieve_relations: center=?org | question=is this a religious organization / what type of organization is this
[19]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: is this a religious organization / wh
[20] MODEL retrieve_subgraph: center=?org | relations=organization.organization_membership.organization | organization.organization_member.member_of | organization.
[21]   ↳ 树: anchor_sequence: Freemasonry ⭢ organization.organization_type | organization_membership.organization | organization_sector.organizations_in_this_secto
[21]   ↳ layer_action: extend   块: Franz Liszt Academy of Music; Freemasonry; Life of Franz Liszt
[21]   ↳ 新实体 0: 
[21]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=0 used=0  标注=nohelp-repeat
[22] MODEL answer: entities=NONE
[23]   ↳ ENV: NONE → ladder: re-select relations; [explore ✗ none] restarts once
You may fall back ONE level: re-select the weakest subgraph's r
[24] MODEL plan: entities: Franz Liszt
[25]   ↳ ENV: REJECTED: Wrong tool in the retrieve phase — and note the WORKFLOW ORDER: `retrieve_relations` must come BEFORE `retrieve_subgraph
[26] MODEL retrieve_relations: center=Franz Liszt | question=which religious leadership positions did he hold
[27]   ↳ rr候选: entities: Franz Liszt
question: which religious leadership positions did he hold
candidate_relations: people.p
[28] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization.founders | organization.organization_founder.organizations_founded | organization.or
[29]   ↳ 树: 
[29]   ↳ layer_action: extend   块: Franz Liszt; Life of Franz Liszt; Freemasonry
[29]   ↳ 新实体 0: 
[29]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=0 used=0  标注=nohelp-repeat
[30] MODEL answer: entities=NONE
[31]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?org=['Freemasonry', 'Franz Liszt Academy of Music, Budapest'])
[32] MODEL answer: entities=Freemasonry
[33]   ↳ ANSWER ACCEPTED: {"entities": ["Freemasonry"]}
诊断: ·→break ·→irrele ·→repeat ·→repeat
标注分布 {'harmful-break': 1, 'nohelp-irrelevant': 1, 'nohelp-repeat': 2}

==============================================================================
CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5  sample s2  f1=0.00  hit=False
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27, 1993?
gold: ['Priest']
pred: None  pred_entities: ['None']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Franz Liszt
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Franz Liszt | which organizations was he a member of / founded | ?organization)
[2] MODEL retrieve_relations: center=Franz Liszt | question=which organizations was Franz Liszt a member of / founded
[3]   ↳ rr候选: entities: Franz Liszt
question: which organizations was Franz Liszt a member of / founded
candidate_relations:
[4] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization_founder.organizations_founded | organization.founders | organization_member.member_of
[5]   ↳ sg交付(无层操作)  块: Franz Liszt; Life of Franz Liszt; Freemasonry
[5]   ↳ 新实体 8: Franz Liszt; Franz Liszt Academy of Music, Budapest; Freemasonry; Funérailles; Harmonies poétiques et religieuses; Life of Franz Liszt; Légende No. 1:
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Freemasonry | Franz Liszt Academy of Music, Budapest | question=what type of organization is this / when did Franz Liszt lead this organization
[7]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: what type of organization is this / w
[8] MODEL retrieve_subgraph: center=Freemasonry | Franz Liszt Academy of Music, Budapest | relations=organization.organization_membership.member | business.employment_tenure.company
[9]   ↳ sg交付(无层操作)  块: Franz Liszt Academy of Music; Freemasonry; Life of Franz Liszt
[9]   ↳ 新实体 0: 
[9]   ◆ φ 1→1 (未推进)  gold=无  (基线块，不参与三档标注)
[10] MODEL retrieve_relations: center=Freemasonry | Franz Liszt Academy of Music, Budapest | question=when did Franz Liszt lead this organization / what were his tenure dates
[11]   ↳ rr候选: entities: Freemasonry | Franz Liszt Academy of Music, Budapest
question: when did Franz Liszt lead this organi
[12] MODEL retrieve_subgraph: center=Freemasonry | Franz Liszt Academy of Music, Budapest | relations=people.person.employment_history | business.employment_tenure.company | organization.organization_
[13]   ↳ 树: anchor_sequence: Franz Liszt Academy of Music, Budapest ⭢ employment_tenure.company | organization_membership.member | person.employment_history (1)
[13]   ↳ layer_action: extend   块: Franz Liszt Academy of Music; Freemasonry; Life of Franz Liszt
[13]   ↳ 新实体 0: 
[13]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=0 used=0  标注=harmful-break
[14] MODEL answer: entities=None
[15]   ↳ ENV: NONE → ladder: re-select relations; [explore ✗ none] restarts once
You may fall back ONE level: re-select the weakest subgraph's r
[16] MODEL retrieve_relations: center=Franz Liszt | question=what religious organizations did Franz Liszt lead / hold positions in
[17]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?organization): [Freemasonry | Franz Liszt Academy of Music, Budapest]
  (UNRESOLVED ≠ CONTR
[18]   ↳ rr候选: entities: Franz Liszt
question: what religious organizations did Franz Liszt lead / hold positions in
candidat
[19] MODEL retrieve_subgraph: center=Franz Liszt | relations=organization.organization_member.member_of | people.person.religion
[20]   ↳ 树: 
[20]   ↳ layer_action: extend   块: Franz Liszt; Life of Franz Liszt; Catholicism; Cosima Wagner; Heinrich Heine
[20]   ↳ 新实体 10: Carl Czerny; Catholicism; Charles Baudelaire; Charles-Valentin Alkan; Christianity; Cosima Wagner; Fryderyk Chopin; Heinrich Heine
[20]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=10 used=0  标注=nohelp-irrelevant
[21] MODEL answer: entities=None
[22]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[23] MODEL answer: entities=None
[24]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[25] MODEL answer: entities=None
[26]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[27] MODEL answer: entities=None
[28]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[29] MODEL answer: entities=None
[30]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[31] MODEL answer: entities=None
[32]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
[33] MODEL answer: entities=None
[34]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?organization=['Freemasonry', 'Franz Liszt Academy of Music, Bu
诊断: ·→break ·→irrele
标注分布 {'harmful-break': 1, 'nohelp-irrelevant': 1}

==============================================================================
CASE WebQTest-1797_2fb9e2823ccf35d2103fa8846d6f2ca8  sample s0  f1=0.00  hit=False
Q: Of the people who fought in the Battle of Vicksburg, who has the earliest date of death?
gold: ['John C. Pemberton']
pred: Carter L. Stevenson | David Farragut | Henry Casey | James B. McPherson | John A  pred_entities: ['Carter L. Stevenson', 'David Farragut', 'Henry Casey', 'James B. McPherson', 'John Alexander McCle
------------------------------------------------------------------------------
[0] MODEL plan: entities: Siege of Vicksburg
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Siege of Vicksburg | who participated in this battle | ?participant)', 'subques
[2] MODEL retrieve_relations: center=Siege of Vicksburg | question=who participated in this battle
[3]   ↳ rr候选: entities: Siege of Vicksburg
question: who participated in this battle
candidate_relations: military.military_
[4] MODEL retrieve_subgraph: center=Siege of Vicksburg | relations=military_conflict.combatants | military_person.participated_in_conflicts | military_conflict.military_personne
[5]   ↳ sg交付(无层操作)  块: Siege of Vicksburg; American Civil War; Ulysses S. Grant; James B. McPherson
[5]   ↳ 新实体 57: American Civil War; Appomattox Campaign; Atlanta Campaign; Battle of Arkansas Post; Battle of Atlanta; Battle of Big Black River Bridge; Battle of Cha
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[7]   ↳ ENV: ⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable values. An event node is an abstract RECORD — it names no thing, so th
[8]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[9] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=deceased_person.cause_of_death | decease
[10]   ↳ 树: anchor_sequence: Siege of Vicksburg ⭢ military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_c
[10]   ↳ layer_action: extend   块: Siege of Vicksburg; Ulysses S. Grant; Seth Barton; Abraham Lincoln; Appomattox Campaign
[10]   ↳ 新实体 33: 1872 Republican National Convention; Abraham Lincoln; Atlanta; Bloomingburg; Breckinridge County; Caroline County; Clyde; Duisburg
[10]   ◆ φ 1→0 (推进)  p_gain=1.0  width=33 used=1  标注=helpful
[11] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[12]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?participant): [Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. Mc
[13]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[14] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=deceased_person.cause_of_death | decease
[15]   ↳ 树: 
[15]   ↳ layer_action: repeat   块: Siege of Vicksburg; Ulysses S. Grant; John Alexander McClernand; Oak Ridge Cemetery; Carter L. Stevenson
[15]   ↳ 新实体 0: 
[15]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=0 used=0  标注=nohelp-repeat
[16] MODEL answer: entities=Carter L. Stevenson | David Farragut | Henry Casey | James B. McPherson | John Alexander McClernand | John S. 
[17]   ↳ ANSWER ACCEPTED: {"entities": ["Carter L. Stevenson", "David Farragut", "Henry Casey", "James B. McPherson"
诊断: 推进→helpfu ·→repeat
标注分布 {'helpful': 1, 'nohelp-repeat': 1}

==============================================================================
CASE WebQTest-1797_2fb9e2823ccf35d2103fa8846d6f2ca8  sample s1  f1=0.00  hit=False
Q: Of the people who fought in the Battle of Vicksburg, who has the earliest date of death?
gold: ['John C. Pemberton']
pred: Ulysses S. Grant  pred_entities: ['Ulysses S. Grant']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Siege of Vicksburg
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Siege of Vicksburg | who participated in this battle | ?participant)', 'subques
[2] MODEL retrieve_relations: center=Siege of Vicksburg | question=who participated in this battle
[3]   ↳ rr候选: entities: Siege of Vicksburg
question: who participated in this battle
candidate_relations: military.military_
[4] MODEL retrieve_subgraph: center=Siege of Vicksburg | relations=military_conflict.combatants | military_person.participated_in_conflicts | military_conflict.military_personne
[5]   ↳ sg交付(无层操作)  块: Siege of Vicksburg; American Civil War; Ulysses S. Grant; James B. McPherson
[5]   ↳ 新实体 57: American Civil War; Appomattox Campaign; Atlanta Campaign; Battle of Arkansas Post; Battle of Atlanta; Battle of Big Black River Bridge; Battle of Cha
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[7]   ↳ ENV: ⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable values. An event node is an abstract RECORD — it names no thing, so th
[8]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[9] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=deceased_person.place_of_death | place_o
[10]   ↳ 树: anchor_sequence: Siege of Vicksburg ⭢ military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_c
[10]   ↳ layer_action: extend   块: Siege of Vicksburg; Ulysses S. Grant; Abraham Lincoln; John Alexander McClernand; Seth Barton
[10]   ↳ 新实体 31: 1872 Republican National Convention; Abraham Lincoln; Atlanta; Bloomingburg; Breckinridge County; Caroline County; Clyde; Duisburg
[10]   ◆ φ 1→0 (推进)  p_gain=1.0  width=31 used=0  标注=helpful
[11] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[12]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?participant): [Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. Mc
[13]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[14] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=deceased_person.cause_of_death | decease
[15]   ↳ 树: anchor_sequence: Siege of Vicksburg ⭢ military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_c
[15]   ↳ layer_action: update layer 2 (replaced none)   块: Siege of Vicksburg; Koblenz; Ulysses S. Grant; United States of America; Washington, D.C.
[15]   ↳ 新实体 3: Esophageal cancer; New York; Virginia
[15]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=3 used=0  标注=nohelp-irrelevant
[16] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[17]   ↳ ENV: ⚠ purity-loop reminder (3rd similar query)
[18]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[19]   ↳ ENV: ANSWER_READY signal
[20] MODEL answer: entities=Ulysses S. Grant
[21]   ↳ ANSWER ACCEPTED: {"entities": ["Ulysses S. Grant"]}
诊断: 推进→helpfu ·→irrele
标注分布 {'helpful': 1, 'nohelp-irrelevant': 1}

==============================================================================
CASE WebQTest-1797_2fb9e2823ccf35d2103fa8846d6f2ca8  sample s2  f1=0.00  hit=False
Q: Of the people who fought in the Battle of Vicksburg, who has the earliest date of death?
gold: ['John C. Pemberton']
pred: Ulysses S. Grant  pred_entities: ['Ulysses S. Grant']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Siege of Vicksburg
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Siege of Vicksburg | who participated in this conflict | ?person)', 'subquestio
[2] MODEL retrieve_relations: center=Siege of Vicksburg | question=who participated in this conflict
[3]   ↳ rr候选: entities: Siege of Vicksburg
question: who participated in this conflict
candidate_relations: military.militar
[4] MODEL retrieve_subgraph: center=Siege of Vicksburg | relations=military_person.participated_in_conflicts | military_conflict.combatants | military_conflict.military_personne
[5]   ↳ sg交付(无层操作)  块: Siege of Vicksburg; American Civil War; Ulysses S. Grant; James B. McPherson
[5]   ↳ 新实体 57: American Civil War; Appomattox Campaign; Atlanta Campaign; Battle of Arkansas Post; Battle of Atlanta; Battle of Big Black River Bridge; Battle of Cha
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=?person | question=when did this person die
[7]   ↳ ENV: error: variable ?person has no declared bindings. After the retrieve_subgraph that resolves it, declare its values in a checkpoint
[8] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=time.person.death_date
[9]   ↳ ENV: error: attribute 'time.person.death_date' has no matching relations in this center's reachable pool. Try a different attribute or 
[10] MODEL retrieve_relations: center=Ulysses S. Grant | James B. McPherson | David Farragut | question=when did this person die
[11]   ↳ rr候选: entities: Ulysses S. Grant | James B. McPherson | David Farragut
question: when did this person die
candidate_
[12] MODEL retrieve_subgraph: center=Ulysses S. Grant | James B. McPherson | David Farragut | Carter L. Stevenson | Henry Halleck | Jefferson Davis | relations=deceased_person.place_of_death | decease
[13]   ↳ 树: anchor_sequence: Siege of Vicksburg ⭢ military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_c
[13]   ↳ layer_action: extend   块: Siege of Vicksburg; Joseph E. Johnston; Henry Halleck; Jefferson Davis; George B. McClellan
[13]   ↳ 新实体 36: 1872 Republican National Convention; Aberjhani; Abraham Lincoln; Atlanta; Berlin; Bloomingburg; Breckinridge County; Caroline County
[13]   ◆ φ 1→0 (推进)  p_gain=1.0  width=36 used=1  标注=helpful
[14] MODEL retrieve_relations: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | question=when did this person die
[15]   ↳ rr候选: entities: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander
[16] MODEL retrieve_subgraph: center=Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernan | relations=time.person.death_date | time.event.incl
[17]   ↳ 树: anchor_sequence: Siege of Vicksburg ⭢ military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_c
[17]   ↳ layer_action: update layer 2 (replaced people.person.place_of_birth, people.dece   块: Siege of Vicksburg; Confederate States of Americ
[17]   ↳ 新实体 1: Emancipation Proclamation
[17]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=1 used=0  标注=nohelp-irrelevant
[18] MODEL emit: [sg1.f1 ✓] ?person = [Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen 
[18] MODEL emit: ANSWER_ANALYSIS
[18] MODEL emit: BASE_CANDIDATES: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Pet
[19]   ↳ ENV: ANSWER_READY signal
[20] MODEL answer: entities=Ulysses S. Grant
[21]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?person): [Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPhers
[22]   ↳ ENV: STAGE GATE: ANSWER_ANALYSIS required before answer
[23] MODEL emit: ANSWER_ANALYSIS
[23] MODEL emit: BASE_CANDIDATES:
[24]   ↳ ENV: ANSWER_READY signal
[25] MODEL answer: entities=Ulysses S. Grant
[26]   ↳ ANSWER ACCEPTED: {"entities": ["Ulysses S. Grant"]}
诊断: 推进→helpfu ·→irrele
标注分布 {'helpful': 1, 'nohelp-irrelevant': 1}

==============================================================================
CASE WebQTrn-452_f79ffe93341047ed2d8a39e5bb7d9156  sample s1  f1=0.00  hit=False
Q: What city has a located ID less than 1783503 and is home to Lala Anthony?
gold: ['Baltimore']
pred: Red Hook  pred_entities: ['Red Hook']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Lala Anthony | Carmelo Anthony
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Lala Anthony | which city is her hometown | ?city)', 'subquestion': 'which city
[2] MODEL retrieve_relations: center=Lala Anthony | question=which city is her hometown
[3]   ↳ ENV: entity_error: 'Lala Anthony' is not a confident graph entity.
candidates: {'name': 'Daphne Anthony', 'neighbor_relations': ['peopl
[4] MODEL retrieve_subgraph: center=Carmelo Anthony | relations=location.location.people_born_here | people.person.siblings
[5]   ↳ sg交付(无层操作)  块: Carmelo Anthony; Red Hook; Parents
[5]   ↳ 新实体 10: Albert Gallo; Busta Rhymes; Carmelo Anthony; Eli Wallach; James Gallo; Joe Gallo; Parents; Red Hook
[5]   ◆ φ ∞→2 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Red Hook | question=what is the located ID of this location
[7]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?city): [Red Hook]
  SUPPORT R1 (city that is home to Lala Anthony): 1 candidate(s) positive
[8]   ↳ rr候选: entities: Red Hook
question: what is the located ID of this location
candidate_relations: time.event.locations
[9] MODEL retrieve_subgraph: center=Red Hook | relations=location.location.geolocation | base.aareas.schema.administrative_area.administrative_parent
[10]   ↳ 树: anchor_sequence: Carmelo Anthony ⭢ location.people_born_here (1) ⭢ location.geolocation (0)
[10]   ↳ layer_action: extend   块: Carmelo Anthony; Red Hook; United States of America; Brooklyn; New York
[10]   ↳ 新实体 6: 2013 RoofTop Film Festival; Brooklyn; Defonte's; New York; New York City; United States of America
[10]   ◆ φ 2→1 (推进)  p_gain=0.0  width=6 used=0  标注=helpful
[11] MODEL answer: entities=Red Hook
[12]   ↳ ENV: unconsumed-entities gate: Lala Anthony
[13] MODEL retrieve_relations: center=Carmelo Anthony | question=who are his siblings
[14]   ↳ rr候选: entities: Carmelo Anthony
question: who are his siblings
candidate_relations: people.person.sibling_s | people
[15] MODEL retrieve_subgraph: center=Carmelo Anthony | relations=people.person.sibling_s | people.sibling_relationship.sibling
[16]   ↳ 树: 
[16]   ↳ layer_action: update layer 1 (replaced location.location.people_born_here)   块: Carmelo Anthony; Michelle Anthony; Robert Anthony; Wilford Anthony; Daphne Anthony
[16]   ↳ 新实体 10: Carmelo Iriarte; Country of nationality; Daphne Anthony; Date of birth; Kiyan Anthony; Mary Anthony; Michelle Anthony; Place of birth
[16]   ◆ φ 1→1 (未推进)  p_gain=0.0  width=10 used=0  标注=harmful-break
[17] MODEL answer: entities=Red Hook
[18]   ↳ ANSWER ACCEPTED: {"entities": ["Red Hook"]}
诊断: 推进→helpfu ·→break
标注分布 {'helpful': 1, 'harmful-break': 1}

==============================================================================
CASE WebQTrn-567_11fd073d11dbb5448b6e6ef3f85999f1  sample s0  f1=0.00  hit=False
Q: What Ron Howard film was released first?
gold: ['The Journey']
pred: Cocoon  pred_entities: ['Cocoon']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Ron Howard
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Ron Howard | what films did this person direct | ?film)', 'subquestion': 'what 
[2] MODEL retrieve_relations: center=Ron Howard | question=what films did this person direct
[3]   ↳ rr候选: entities: Ron Howard
question: what films did this person direct
candidate_relations: film.film_casting_direct
[4] MODEL retrieve_subgraph: center=Ron Howard | relations=film.director.film | film.film.directed_by
[5]   ↳ sg交付(无层操作)  块: Ron Howard; The 'Burbs; The Lost Symbol; American Graffiti
[5]   ↳ 新实体 54: A Beautiful Mind; American Graffiti; Anatole Litvak; Angels & Demons; Apollo 13; Arrested Development; Backdraft; Barry W. Blaustein
[5]   ◆ φ ∞→0 (推进)  gold=有  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=?film | question=when was this film released
[7]   ↳ rr候选: entities: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy 
[8] MODEL retrieve_subgraph: center=?film | relations=film.release_date_s | film.film_regional_release_date.film
[9]   ↳ 树: anchor_sequence: Ron Howard ⭢ director.film | film.directed_by (29) ⭢ film.release_date_s | film_regional_release_date.film (0)
[9]   ↳ layer_action: extend   块: Ron Howard; Clean and Sober; The 'Burbs; Closet Land; Changeling
[9]   ↳ 新实体 4: Brian Grazer; In the Heart of the Sea …(+12); Night Shift …(+10); Rush …(+4)
[9]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=4 used=0  标注=nohelp-irrelevant
[10] MODEL retrieve_subgraph: center=A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seus | relations=film.release_date_s
[11]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?film): [A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoo
[12]   ↳ 树: 
[12]   ↳ layer_action: repeat   块: Ron Howard; Clean and Sober; The 'Burbs; Closet Land; Changeling
[12]   ↳ 新实体 3: Babaloo Mandel; John Thomas Lenox; Lowell Ganz
[12]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=3 used=0  标注=nohelp-irrelevant
[13] MODEL retrieve_relations: center=Clean and Sober | The 'Burbs | Closet Land | Gung Ho | question=what is the release date of this film
[14]   ↳ rr候选: entities: Clean and Sober | The 'Burbs | Closet Land | Gung Ho
question: what is the release date of this film
[15]   ↳ ENV: ANSWER_READY signal
[16] MODEL answer: entities=Cocoon
[17]   ↳ ANSWER ACCEPTED: {"entities": ["Cocoon"]}
诊断: ·→irrele ·→irrele
标注分布 {'nohelp-irrelevant': 2}

==============================================================================
CASE WebQTrn-567_df97b91c1a9dfe15bdad689feb59f791  sample s0  f1=0.00  hit=False
Q: What is the movie about a child prodigy that Ron Howard did?
gold: ['Village of the Giants']
pred: A Beautiful Mind  pred_entities: ['A Beautiful Mind']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Ron Howard | Child prodigy
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Ron Howard | what films did this person direct or produce | ?movie)', 'subquest
[2] MODEL retrieve_relations: center=Ron Howard | question=what films did this person direct or produce
[3]   ↳ rr候选: entities: Ron Howard
question: what films did this person direct or produce
candidate_relations: film.producer
[4] MODEL retrieve_subgraph: center=Ron Howard | relations=film.director.film | film.film.directed_by | film.produced_by | film.producer.films_executive_produced
[5]   ↳ sg交付(无层操作)  块: Ron Howard; Brian Grazer; Todd Hallowell; Jay-Z: Made in America
[5]   ↳ 新实体 99: A Beautiful Mind; Akiva Goldsman; American Graffiti; Andrew Eaton; Angels & Demons; Apollo 13; Arrested Development; Backdraft
[5]   ◆ φ ∞→0 (推进)  gold=有  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seus | question=what is this film about / what are the su
[7]   ↳ rr候选: entities: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy 
[8] MODEL retrieve_subgraph: center=A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seus | relations=film.film_subject.films | film.film.subj
[9]   ↳ 树: anchor_sequence: Ron Howard ⭢ director.film | film.directed_by | film.produced_by | producer.films_executive_produced (49) ⭢ film.subjects | film_subj
[9]   ↳ layer_action: extend   块: Ron Howard; Closet Land; Brian Grazer; The Lost Symbol; EDtv
[9]   ↳ 新实体 10: Boxing; English Language; Freemasonry; Image Entertainment; Imagine Entertainment; Indie film; Pedophilia; Substance abuse
[9]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=10 used=5  标注=nohelp-irrelevant
[10] MODEL retrieve_subgraph: center=A Beautiful Mind | relations=film.film_subject.films | film.film.subjects
[11]   ↳ 树: 
[11]   ↳ layer_action: repeat   块: Ron Howard; EDtv; The Lost Symbol; Clean and Sober; Closet Land
[11]   ↳ 新实体 0: 
[11]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=0 used=0  标注=nohelp-repeat
[12] MODEL retrieve_relations: center=A Beautiful Mind | question=what is this film about / what are the subjects of this film
[13]   ↳ rr候选: entities: A Beautiful Mind
question: what is this film about / what are the subjects of this film
candidate_re
[14] MODEL retrieve_subgraph: center=A Beautiful Mind | relations=film.film_story_contributor.film_story_credits | film.film.story_by
[15]   ↳ 树: anchor_sequence: Ron Howard ⭢ director.film | film.directed_by | film.produced_by | producer.films_executive_produced (49) ⭢ film.story_by | film_stor
[15]   ↳ layer_action: update layer 2 (replaced film.film.subjects, film.film_subject.fil   块: Ron Howard; Dan Brown; Parenthood; Apollo 13; Gung Ho
[15]   ↳ 新实体 8: Babaloo Mandel; Bob Dolman; Cliff Hollingsworth; David Saperstein; Jeffrey Kluger; Jim Lovell; Lowell Ganz; The Dark Tower …(+2)
[15]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=8 used=0  标注=nohelp-irrelevant
[16] MODEL answer: entities=A Beautiful Mind
[17]   ↳ ENV: unconsumed-entities gate: Child prodigy
JOIN PATHS:
  1. Child prodigy --films/subjects--> Village of the Giants  Village of the G
[18] MODEL retrieve_subgraph: center=Child prodigy | relations=film.film_subject.films | film.film.subjects
[19]   ↳ sg交付(无层操作)  块: Child prodigy; Village of the Giants
[19]   ↳ 新实体 2: Child prodigy; Giant
[19]   ◆ φ 0→0 (覆盖gold)  gold=有  (基线块，不参与三档标注)
[20] MODEL retrieve_relations: center=Village of the Giants | question=who directed or produced this film
[21]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?movie): [A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Coco
[22]   ↳ rr候选: entities: Village of the Giants
question: who directed or produced this film
candidate_relations: film.produce
[23] MODEL retrieve_subgraph: center=Village of the Giants | relations=film.director.film | film.film.directed_by | film.produced_by | film.producer.films_executive_produced
[24]   ↳ 树: anchor_sequence: Child prodigy ⭢ film.subjects | film_subject.films (1) ⭢ director.film | film.directed_by | film.produced_by (0)
[24]   ↳ layer_action: extend   块: Child prodigy; Village of the Giants; Ron Howard; Film; Jay-Z: Made in America
[24]   ↳ 新实体 13: Adam McKay; Adventure Film; Comedy; Cult film; EDtv …(+5); Film; Grand Theft Auto …(+8); J. Edgar …(+14)
[24]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=13 used=1  标注=nohelp-irrelevant
[25] MODEL answer: entities=A Beautiful Mind
[26]   ↳ ANSWER ACCEPTED: {"entities": ["A Beautiful Mind"]}
诊断: ·→irrele ·→repeat ·→irrele ·→irrele
标注分布 {'nohelp-irrelevant': 3, 'nohelp-repeat': 1}

==============================================================================
CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec  sample s2  f1=0.00  hit=False
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?
gold: ['Poetic Justice']
pred: None  pred_entities: ['None']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Tupac Shakur | Kirk M. Petruccelli
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Tupac Shakur | which films did this person act in | ?movie)', 'subquestion': 'w
[2] MODEL retrieve_relations: center=Tupac Shakur | question=which films did this person act in
[3]   ↳ rr候选: entities: Tupac Shakur
question: which films did this person act in
candidate_relations: film.film_character.p
[4] MODEL retrieve_subgraph: center=Tupac Shakur | Kirk M. Petruccelli | relations=actor.film | film.starring | director.film | film.directed_by
[5]   ↳ sg交付(无层操作)  块: Kirk M. Petruccelli; Tupac Shakur; The Thirteenth Floor; Poetic Justice
[5]   ↳ 新实体 43: 3 Ninjas; And the Earth Did Not Swallow Him; Bullhead; California Love; Charlotte Lewin; Dr. Dre; English Language; Gang Related
[5]   ◆ φ ∞→0 (推进)  gold=有  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 | question=which person directed this film
[7]   ↳ ENV: ⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable values. An event node is an abstract RECORD — it names no thing, so th
[8]   ↳ rr候选: entities: m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9
question: 
[9] MODEL retrieve_subgraph: center=m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 | relations=film.directed_by
[10]   ↳ sg交付(无层操作)  块: Tupac Shakur; Poetic Justice; Murder Was the Case; Above the Rim
[10]   ↳ 新实体 7: Above the Rim; Birdie; Bishop; Bullet; Det. Rodriguez; Digital Underground member; Ezekiel 'Spoon' Whitmore
[10]   ◆ φ 0→0 (覆盖gold)  gold=有  (基线块，不参与三档标注)
[11] MODEL answer: entities=None
[12]   ↳ ENV: ⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable values. An event node is an abstract RECORD — it names no thing, so th
[13]   ↳ ENV: NONE → ladder: re-select relations; [explore ✗ none] restarts once
You may fall back ONE level: re-select the weakest subgraph's r
[14] MODEL retrieve_relations: center=Kirk M. Petruccelli | question=which films did this person direct
[15]   ↳ rr候选: entities: Kirk M. Petruccelli
question: which films did this person direct
candidate_relations: film.film_cast
[16] MODEL retrieve_subgraph: center=Kirk M. Petruccelli | relations=film.directed_by | director.film
[17]   ↳ 树: 
[17]   ↳ layer_action: repeat   块: Kirk M. Petruccelli; The Last Castle; Mark Steven Johnson; 3 Ninjas; Bullhead
[17]   ↳ 新实体 0: 
[17]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=0 used=0  标注=nohelp-repeat
[18] MODEL answer: entities=None
[19]   ↳ ENV: ⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable values. An event node is an abstract RECORD — it names no thing, so th
[20]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: none).
[21] MODEL answer: entities=None
[22]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[23] MODEL answer: entities=None
[24]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[25] MODEL answer: entities=None
[26]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[27] MODEL answer: entities=None
[28]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[29] MODEL answer: entities=None
[30]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[31] MODEL answer: entities=None
[32]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[33] MODEL answer: entities=None
[34]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
[35] MODEL answer: entities=None
[36]   ↳ ENV: Second refusal — answer from current support NOW (bindings so far: ?movie=['Poetic Justice', 'Bullet', 'Above the Rim', 'Murder Wa
诊断: ·→repeat
标注分布 {'nohelp-repeat': 1}

==============================================================================
CASE WebQTrn-2576_872253e47dd6ddaa213ff31eeda8783b  sample s0  f1=0.00  hit=False
Q: What continent is the country in the Eastern Time Zone that Falkland Island belong to located in?
gold: ['Americas']
pred: Western Europe  pred_entities: ['Western Europe']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Falkland Islands
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Falkland Islands | which country contains this territory | ?country)', 'subques
[2] MODEL retrieve_relations: center=Falkland Islands | question=which country contains this territory
[3]   ↳ rr候选: entities: Falkland Islands
question: which country contains this territory
candidate_relations: base.locations
[4] MODEL retrieve_subgraph: center=Falkland Islands | relations=location.location.containedby | base.aareas.schema.earth.sovereign_domain.sovereign_state | base.aareas.schema
[5]   ↳ sg交付(无层操作)  块: Falkland Islands; Americas; United Kingdom, with Depende; Atlantic Ocean
[5]   ↳ 新实体 37: Americas; Anguilla; Antigua and Barbuda; Argentina; Aruba; Atlantic Ocean; Bahamas; Barbados
[5]   ◆ φ ∞→0 (推进)  gold=有  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=United Kingdom | question=which time zones are associated with this country
[7]   ↳ rr候选: entities: United Kingdom
question: which time zones are associated with this country
candidate_relations: loca
[8] MODEL retrieve_subgraph: center=United Kingdom | relations=location.location.time_zones
[9]   ↳ sg交付(无层操作)  块: United Kingdom; Americas; South America; North America
[9]   ↳ 新实体 44: Alaska Time Zone; Amazon Time Zone; Argentina Time Zone; Atlantic Time Zone; Bolivia Time Zone; Brasília Time Zone; Central Time Zone; Chile Time Zone
[9]   ◆ φ 0→0 (覆盖gold)  gold=有  (基线块，不参与三档标注)
[10] MODEL retrieve_relations: center=United Kingdom | question=which continent contains this country
[11]   ↳ rr候选: entities: United Kingdom
question: which continent contains this country
candidate_relations: language.human_l
[12] MODEL retrieve_subgraph: center=United Kingdom | relations=location.location.containedby | location.location.primarily_containedby | location.location.partially_containe
[13]   ↳ 树: anchor_sequence: United Kingdom ⭢ sovereign_domain.sovereign_state | location.containedby | location.time_zones (0)
[13]   ↳ layer_action: extend   块: United Kingdom; United Kingdom, with Depende; Western Europe; Isle of Man; South Georgia and the South 
[13]   ↳ 新实体 21: Akrotiri and Dhekelia; Altitude; British Isles; Cayman Islands; Cyprus; English Channel; France; Gibraltar
[13]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=21 used=1  标注=nohelp-irrelevant
[14]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?time_zone): [Falkland Islands Time Zone | Atlantic Time Zone | Eastern Time Zone | ...]
  (
[15] MODEL answer: entities=Western Europe
[16]   ↳ ANSWER ACCEPTED: {"entities": ["Western Europe"]}
诊断: ·→irrele
标注分布 {'nohelp-irrelevant': 1}

==============================================================================
CASE WebQTest-1923_2d077323191d349225d8f3719925c777  sample s1  f1=0.00  hit=False
Q: The person who attended Heritage Elementary School has been in what movies?
gold: ['Miley Cyrus: Tongue Tied', 'Big Fish', 'Hannah Montana: The Movie', 'Hannah Montana and Miley Cyrus: Best of Both Worlds Concert', 'Sonic the Hedgehog', 'Sex and the City 2', 'Wi
pred: Miley Cyrus  pred_entities: ['Miley Cyrus']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Heritage Elementary School
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Heritage Elementary School | who attended this school | ?person)', 'subquestion
[2] MODEL retrieve_relations: center=Heritage Elementary School | question=who attended this school
[3]   ↳ rr候选: entities: Heritage Elementary School
question: who attended this school
candidate_relations: education.school.
[4] MODEL retrieve_subgraph: center=Heritage Elementary School | relations=education.educational_institution.students_graduates | education.education.student | people.person.education
[5]   ↳ sg交付(无层操作)  块: Heritage Elementary School; Miley Cyrus
[5]   ↳ 新实体 5: End Date; Heritage Elementary School; Major/Field Of Study; Miley Cyrus; Start Date; student: Miley Cyrus]
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Miley Cyrus | question=what movies has this person appeared in
[7]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?person): [Miley Cyrus]
  SUPPORT R1 (person who attended Heritage Elementary School): 1 can
[8]   ↳ rr候选: entities: Miley Cyrus
question: what movies has this person appeared in
candidate_relations: film.film.starrin
[9] MODEL retrieve_subgraph: center=Miley Cyrus | relations=film.film.starring | film.actor.film | film.performance.film
[10]   ↳ 树: anchor_sequence: Heritage Elementary School ⭢ education.student | educational_institution.students_graduates | person.education (6) ⭢ actor.film (0)
[10]   ↳ layer_action: extend   块: Heritage Elementary School; Miley Cyrus; Hannah Montana; Him/Herself; Bolt
[10]   ↳ 新实体 9: Bolt; Brook; Family Bond; Hannah Montana; Hannah Montana and Miley Cyrus: Best of Both Worlds Concert; Hannah Montana: The Movie; High School Musical 2; Him/Her
[10]   ◆ φ 1→0 (推进)  p_gain=0.294  width=9 used=6  标注=helpful
[11] MODEL answer: entities=Miley Cyrus
[12]   ↳ ANSWER ACCEPTED: {"entities": ["Miley Cyrus"]}
诊断: 推进→helpfu
标注分布 {'helpful': 1}

==============================================================================
CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a  sample s0  f1=1.00  hit=True
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?
gold: ['Hailemariam Desalegn']
pred: Hailemariam Desalegn  pred_entities: ['Hailemariam Desalegn']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Ethiopian birr | Prime minister
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Ethiopian birr | which country uses this currency | ?country)', 'subquestion': 
[2] MODEL retrieve_relations: center=Ethiopian birr | question=which country uses this currency
[3]   ↳ rr候选: entities: Ethiopian birr
question: which country uses this currency
candidate_relations: location.country.curr
[4] MODEL retrieve_subgraph: center=Ethiopian birr | relations=location.country.currency_used | finance.currency.countries_used
[5]   ↳ sg交付(无层操作)  块: Ethiopian birr
[5]   ↳ 新实体 2: Ethiopia; Ethiopian birr
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Ethiopia | question=who is the prime minister of this country
[7]   ↳ rr候选: entities: Ethiopia
question: who is the prime minister of this country
candidate_relations: government.governm
[8] MODEL retrieve_subgraph: center=Ethiopia | relations=government.politician.government_positions_held | government.government.government_for
[9]   ↳ 树: anchor_sequence: Ethiopian birr ⭢ currency.countries_used | country.currency_used (1) ⭢ government.government_for (0)
[9]   ↳ layer_action: extend   块: Ethiopian birr; Haile Selassie; Hailemariam Desalegn; Ethiopia; 2012-09-21-08:00
[9]   ↳ 新实体 8: 2012-09-21-08:00; East African Campaign; Eritrean War of Independence; Government of Ethiopia; Haile Selassie; Hailemariam Desalegn; Prime Minister of Ethiopia;
[9]   ◆ φ 1→0 (推进)  p_gain=1.0  width=8 used=1  标注=helpful
[10] MODEL answer: entities=Hailemariam Desalegn
[11]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?prime_minister): [Hailemariam Desalegn]
  (UNRESOLVED ≠ CONTRADICTED: a requirement whose f
[12]   ↳ ENV: unconsumed-entities gate: Prime minister
RETRIEVAL HINT:
  1. 'Prime minister' --basic_title--> jurisdiction_of_office=Ethiopia | 
[13] MODEL answer: entities=Hailemariam Desalegn
[14]   ↳ ANSWER ACCEPTED: {"entities": ["Hailemariam Desalegn"]}
诊断: 推进→helpfu
标注分布 {'helpful': 1}

==============================================================================
CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a  sample s1  f1=1.00  hit=True
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?
gold: ['Hailemariam Desalegn']
pred: Hailemariam Desalegn  pred_entities: ['Hailemariam Desalegn']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Ethiopian birr
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Ethiopian birr | which country uses this currency | ?country)', 'subquestion': 
[2] MODEL retrieve_relations: center=Ethiopian birr | question=which country uses this currency
[3]   ↳ rr候选: entities: Ethiopian birr
question: which country uses this currency
candidate_relations: location.country.curr
[4] MODEL retrieve_subgraph: center=Ethiopian birr | relations=location.country.currency_used | finance.currency.countries_used
[5]   ↳ sg交付(无层操作)  块: Ethiopian birr
[5]   ↳ 新实体 2: Ethiopia; Ethiopian birr
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Ethiopia | question=who is the prime minister of this country
[7]   ↳ rr候选: entities: Ethiopia
question: who is the prime minister of this country
candidate_relations: government.governm
[8] MODEL retrieve_subgraph: center=Ethiopia | relations=government.government_for | government.politician.government_positions_held
[9]   ↳ 树: anchor_sequence: Ethiopian birr ⭢ currency.countries_used | country.currency_used (1) ⭢ government.government_for (0)
[9]   ↳ layer_action: extend   块: Ethiopian birr; Haile Selassie; Hailemariam Desalegn; Ethiopia; 2012-09-21-08:00
[9]   ↳ 新实体 8: 2012-09-21-08:00; East African Campaign; Eritrean War of Independence; Government of Ethiopia; Haile Selassie; Hailemariam Desalegn; Prime Minister of Ethiopia;
[9]   ◆ φ 1→0 (推进)  p_gain=1.0  width=8 used=1  标注=helpful
[10] MODEL answer: entities=Hailemariam Desalegn
[11]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?prime_minister): [Hailemariam Desalegn]
  (UNRESOLVED ≠ CONTRADICTED: a requirement whose f
[12]   ↳ ENV: STAGE GATE: ANSWER_ANALYSIS required before answer
[13] MODEL emit: ANSWER_ANALYSIS
[13] MODEL emit: BASE_CANDIDATES:
[14]   ↳ ENV: ANSWER_READY signal
[15] MODEL answer: entities=Hailemariam Desalegn
[16]   ↳ ANSWER ACCEPTED: {"entities": ["Hailemariam Desalegn"]}
诊断: 推进→helpfu
标注分布 {'helpful': 1}

==============================================================================
CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a  sample s2  f1=1.00  hit=True
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?
gold: ['Hailemariam Desalegn']
pred: Hailemariam Desalegn  pred_entities: ['Hailemariam Desalegn']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Ethiopian birr | Prime minister
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Ethiopian birr | which country uses this currency | ?country)', 'subquestion': 
[2] MODEL retrieve_relations: center=Ethiopian birr | question=which country uses this currency
[3]   ↳ rr候选: entities: Ethiopian birr
question: which country uses this currency
candidate_relations: location.country.curr
[4] MODEL retrieve_subgraph: center=Ethiopian birr | relations=location.country.currency_used | finance.currency.countries_used
[5]   ↳ sg交付(无层操作)  块: Ethiopian birr
[5]   ↳ 新实体 2: Ethiopia; Ethiopian birr
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Ethiopia | question=who is the prime minister of this country
[7]   ↳ rr候选: entities: Ethiopia
question: who is the prime minister of this country
candidate_relations: government.governm
[8] MODEL retrieve_subgraph: center=Ethiopia | relations=government.government_for | government.politician.government_positions_held
[9]   ↳ 树: anchor_sequence: Ethiopian birr ⭢ currency.countries_used | country.currency_used (1) ⭢ government.government_for (0)
[9]   ↳ layer_action: extend   块: Ethiopian birr; Haile Selassie; Hailemariam Desalegn; Ethiopia; 2012-09-21-08:00
[9]   ↳ 新实体 8: 2012-09-21-08:00; East African Campaign; Eritrean War of Independence; Government of Ethiopia; Haile Selassie; Hailemariam Desalegn; Prime Minister of Ethiopia;
[9]   ◆ φ 1→0 (推进)  p_gain=1.0  width=8 used=1  标注=helpful
[10] MODEL answer: entities=Hailemariam Desalegn
[11]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?prime_minister): [Hailemariam Desalegn]
  (UNRESOLVED ≠ CONTRADICTED: a requirement whose f
[12]   ↳ ENV: unconsumed-entities gate: Prime minister
RETRIEVAL HINT:
  1. 'Prime minister' --basic_title--> jurisdiction_of_office=Ethiopia | 
[13] MODEL answer: entities=Hailemariam Desalegn
[14]   ↳ ANSWER ACCEPTED: {"entities": ["Hailemariam Desalegn"]}
诊断: 推进→helpfu
标注分布 {'helpful': 1}

==============================================================================
CASE WebQTrn-2209_c1374f388d9cc7a78365860c91218362  sample s0  f1=0.11  hit=True
Q: What year did the basketball team coached by Brad Stevens win the championship?
gold: ['2008 NBA Finals', '1969 NBA Finals', '1986 NBA Finals', '1984 NBA Finals', '1981 NBA Finals', '1976 NBA Finals', '1974 NBA Finals', '1968 NBA Finals', '1966 NBA Finals', '1965 NB
pred: 2008 NBA Finals  pred_entities: ['2008 NBA Finals']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Brad Stevens
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Brad Stevens | which basketball teams did this person coach | ?team)', 'subques
[2] MODEL retrieve_relations: center=Brad Stevens | question=which basketball teams did this person coach
[3]   ↳ rr候选: entities: Brad Stevens
question: which basketball teams did this person coach
candidate_relations: sports.spor
[4] MODEL retrieve_subgraph: center=Brad Stevens | relations=basketball.basketball_team.head_coach | sports.sports_team.coaches | sports.sports_team_coach.teams_coached
[5]   ↳ sg交付(无层操作)  块: Brad Stevens; Boston Celtics; Geno Auriemma; Butler Bulldogs men's basket
[5]   ↳ 新实体 10: Assistant Coach; Basketball; Basketball Coach; Boston Celtics; Brad Stevens; Brandon Miller; Butler Bulldogs men's basketball; Coach
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=Boston Celtics | Butler Bulldogs men's basketball | question=which championship did this team win
[7]   ↳ rr候选: entities: Boston Celtics | Butler Bulldogs men's basketball
question: which championship did this team win
can
[8] MODEL retrieve_subgraph: center=Boston Celtics | Butler Bulldogs men's basketball | relations=sports.sports_team.championships | sports.sports_championship_event.champion
[9]   ↳ 树: anchor_sequence: Brad Stevens ⭢ basketball_team.head_coach | sports_team.coaches | sports_team_coach.teams_coached (5) ⭢ sports_championship_event.cha
[9]   ↳ layer_action: extend   块: Brad Stevens; Boston Celtics
[9]   ↳ 新实体 18: 1957 NBA Finals; 1959 NBA Finals; 1960 NBA Finals; 1961 NBA Finals; 1962 NBA Finals; 1963 NBA Finals; 1964 NBA Finals; 1965 NBA Finals
[9]   ◆ φ 1→0 (推进)  p_gain=1.0  width=18 used=17  标注=helpful
[10] MODEL retrieve_relations: center=2008 NBA Finals | question=who was the head coach of the winning team
[11]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?championship): [1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 196
[12]   ↳ rr候选: entities: 2008 NBA Finals
question: who was the head coach of the winning team
candidate_relations: basketball
[13]   ↳ ENV: ANSWER_READY signal
[14] MODEL answer: entities=2008 NBA Finals
[15]   ↳ ANSWER ACCEPTED: {"entities": ["2008 NBA Finals"]}
诊断: 推进→helpfu
标注分布 {'helpful': 1}

==============================================================================
CASE WebQTest-212_01600f3a537521fc645c5891772d0e75  sample s0  f1=0.50  hit=True
Q: Which state has a population of less than 965000 and has the colorado river flowing through it?
gold: ['Arizona', 'Nevada', 'Colorado']
pred: Colorado  pred_entities: ['Colorado']
------------------------------------------------------------------------------
[0] MODEL plan: entities: Colorado River
[1]   ↳ plan分解: flow: {'id': 'f1', 'triple': '(Colorado River | which states does this river flow through | ?state)', 'subques
[2] MODEL retrieve_relations: center=Colorado River | question=which states does this river flow through
[3]   ↳ rr候选: entities: Colorado River
question: which states does this river flow through
candidate_relations: base.locatio
[4] MODEL retrieve_subgraph: center=Colorado River | relations=river.basin_countries
[5]   ↳ sg交付(无层操作)  块: Colorado River; United States of America; Mexico
[5]   ↳ 新实体 14: Amargosa River; Arkansas River; Colorado River; East Walker River; Gila River; Jarbidge River; Mexico; New River
[5]   ◆ φ ∞→1 (推进)  gold=无  (基线块，不参与三档标注)
[6] MODEL retrieve_relations: center=United States of America | question=which states does this country contain
[7]   ↳ rr候选: entities: United States of America
question: which states does this country contain
candidate_relations: base.
[8] MODEL retrieve_subgraph: center=United States of America | Mexico | relations=countries.states_provinces_within | administrative_division.country
[9]   ↳ 树: anchor_sequence: Colorado River ⭢ river.basin_countries (2) ⭢ countries.states_provinces_within | administrative_division.country (0)
[9]   ↳ layer_action: extend   块: Colorado River; Mexico; United States of America; California
[9]   ↳ 新实体 44: Alabama; Alaska; Arizona; Arkansas; Baja California; California; Colorado; Connecticut
[9]   ◆ φ 1→0 (推进)  p_gain=1.0  width=44 used=1  标注=helpful
[10]   ↳ ENV: === EVIDENCE COMMIT ===
  CANDIDATES (?state): [United States of America | Mexico]
  SUPPORT R1 (state has Colorado River flowing 
[11] MODEL retrieve: center=Arizona | California | Colorado | Nevada | New Mexico | Utah | question=what is the resident population of this state
[12]   ↳ rr候选: entities: Arizona | California | Colorado | Nevada | New Mexico | Utah
question: what is the resident populati
[13]   ↳ ENV: ANSWER_READY signal
[14] MODEL retrieve_subgraph: center=Arizona | California | Colorado | Nevada | New Mexico | Utah | relations=topic_server.population_number | statistical_region.population
[15]   ↳ 树: anchor_sequence: Colorado River ⭢ river.basin_countries (2) ⭢ countries.states_provinces_within | administrative_division.country (54) ⭢ statistical_r
[15]   ↳ layer_action: extend   块: Colorado River; Baja California; Colorado; Nevada; Arizona
[15]   ↳ 新实体 100: 100000; 101000; 103000; 105000; 107000; 113000; 120000; 124000
[15]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=100 used=0  标注=nohelp-irrelevant
[16] MODEL retrieve_relations: center=Arizona | California | Colorado | Nevada | New Mexico | Utah | Wyoming | question=what is the resident population of this state
[17]   ↳ rr候选: entities: Arizona | California | Colorado | Nevada | New Mexico | Utah | Wyoming
question: what is the residen
[18] MODEL retrieve_subgraph: center=Arizona | California | Colorado | Nevada | New Mexico | Utah | relations=topic_server.population_number | statistical_region.population
[19]   ↳ 树: 
[19]   ↳ layer_action: repeat   块: Colorado River; San Bernardino; Arizona; Baja California; Sonora
[19]   ↳ 新实体 6: 520018; 56000; 568991 …(+31); Mexicali; San Bernardino; San Luis Río Colorado
[19]   ◆ φ 0→0 (未推进)  p_gain=0.0  width=6 used=0  标注=nohelp-irrelevant
[20] MODEL retrieve_relations: center=Arizona | Colorado | Nevada | question=what is the resident population of this state
[21]   ↳ ENV: ⚠ Your checkpoint [f2 ✓] tried to change bindings (['multiple city/county-level values per state; no clear state-level totals visi
[22]   ↳ ENV: ⚠ purity-loop reminder (3rd similar query)
[23]   ↳ rr候选: entities: Arizona | Colorado | Nevada
question: what is the resident population of this state
candidate_relati
[24] MODEL answer: entities=Colorado
[25]   ↳ ANSWER ACCEPTED: {"entities": ["Colorado"]}
诊断: 推进→helpfu ·→irrele ·→irrele
标注分布 {'helpful': 1, 'nohelp-irrelevant': 2}

