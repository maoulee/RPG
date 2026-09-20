# 渲染对比：原始 vs 选中路径重建器（无 LLM 回放，逐块并排）

锚点 = 同一条 retrieve_subgraph 调用（重放逐字喂入录制的 assistant 消息）。【旧】= v06_aligned 录制渲染；【新】= 选中路径重建器渲染。其余消息类型未变，不列。


============================================================================================
## CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5 s0
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27  f1=0.0
sg 调用数: 旧 6 / 新 6

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Franz Liszt  |  relations: organization.organization_membership.member | organization.organization_member.member_of
旧: 模式 9 · 证据块 3 · 2907 字符
新: 模式 7 · 证据块 2 · 1454 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member | topic.image ⭢ composition.composer ⭢ organization_membership.member | organization_member.member_of | organization_membership.member
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Funérailles | Harmonies poétiques et religieuses | Life of Franz Liszt | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: fictional_character.based_on | topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Franz Liszt  |  relations: organization.organization.founders | organization.organization_founder.organizations_founded | people.person.employment
旧: 模式 13 · 证据块 3 · 3909 字符
新: 模式 9 · 证据块 2 · 2316 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: image.appears_in_topic_gallery ⭢ person.employment_history | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ person.employment_history | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ person.employment_history | image.appears_in_topic_gallery ⭢ composition.composer ⭢ person.employment_history | organization.founders | organization_founder.organizations_founded | person.employment_history
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt | Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft [company: Franz Liszt Academy of Music, Budapest]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft [company: Franz Liszt Academy of Music, Budapest]
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'people.person.employment_history': {'direct': ['people.person.employment_history'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
layer_action: extend
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: image.appears_in_topic_gallery ⭢ person.employment_history | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ person.employment_history | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ person.employment_history
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft [company: Franz Liszt Academy of Music, Budapest]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'people.person.employment_history': {'direct': ['people.person.employment_history'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced ganization.organization_member.member_of, anization.organization_membership.member)
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Franz Liszt  |  relations: people.person.religion | organization.organization.founders | organization.organization_founder.organizations_founded
旧: 模式 15 · 证据块 6 · 4243 字符
新: 模式 3 · 证据块 2 · 1511 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: image.appears_in_topic_gallery ⭢ person.religion | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ person.religion | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ person.religion | topic.image ⭢ composition.composer ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ influence_node.influenced_by ⭢ person.religion | person_in_fiction.representations_in_fiction ⭢ person.children ⭢ person.religion | organization.founders | organization_founder.organizations_founded | person.religion
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Funérailles | Harmonies poétiques et religieuses | Life of Franz Liszt | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --person.children--> Cosima Wagner
    --influence_node.influenced_by--> Carl Czerny | Charles Baudelaire | Heinrich Heine
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    --person.religion--> Catholicism
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    Charles-Valentin Alkan --influence_node.influenced_by--> Life of Franz Liszt
    Fryderyk Chopin --influence_node.influenced_by--> Life of Franz Liszt
── Catholicism ──
    Carl Czerny | Charles Baudelaire | Cosima Wagner | Fryderyk Chopin --person.religion--> Catholicism
── Cosima Wagner ──
    --person.religion--> Protestantism
── Heinrich Heine ──
    --person.religion--> Christianity | Judaism
── Charles-Valentin Alkan ──
    --person.religion--> Judaism
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'people.person.religion': {'direct': ['people.person.religion'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.ficti
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: image.appears_in_topic_gallery ⭢ person.religion | topic.image ⭢ person.religion | person_in_fiction.representations_in_fiction ⭢ person.religion
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --person.religion--> Catholicism
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'people.person.religion': {'direct': ['people.person.religion'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced people.person.employment_history)
```

--------------------------------------------------------------------------------------------
### 块 #3 调用: center: Franz Liszt  |  relations: people.profession.people_with_this_profession | organization.organization_member.member_of
旧: 模式 10 · 证据块 3 · 3456 字符
新: 模式 3 · 证据块 2 · 1551 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ organization_member.member_of | topic.image ⭢ profession.people_with_this_profession | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ profession.people_with_this_profession | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ profession.people_with_this_profession | topic.image ⭢ composition.composer ⭢ profession.people_with_this_profession | person_in_fiction.representations_in_fiction ⭢ person.profession ⭢ profession.people_with_this_profession | organization_member.member_of | profession.people_with_this_profession
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Funérailles | Harmonies poétiques et religieuses | Life of Franz Liszt | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --person.profession--> Virtuoso
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    Virtuoso --profession.people_with_this_profession--> Life of Franz Liszt
── Virtuoso ──
    --profession.people_with_this_profession--> Arcadi Volodos | Lance Dossor | Marc-André Hamelin | Mark Gasser | Niccolò Paganini | Osman Zeki Üngör | Pablo de Sarasate | Paolo Girolamo Besozzi | Sigismond Thalberg
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'people.profession.people_with_this_profession': {'direct': ['people.profession.people_with_this_profession'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
layer_action: extend
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ profession.people_with_this_profession | fictional_character.based_on ⭢ profession.people_with_this_profession | person_in_fiction.representations_in_fiction ⭢ profession.people_with_this_profession
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    Virtuoso --profession.people_with_this_profession--> Life of Franz Liszt
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'people.profession.people_with_this_profession': {'direct': ['people.profession.people_with_this_profession'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced ganization_founder.organizations_founded, organization.organization.founders, people.person.religion)
```

--------------------------------------------------------------------------------------------
### 块 #4 调用: center: Franz Liszt  |  relations: organization.organization_member.member_of | organization.organization_membership.member | organization.organization_fo
旧: [错误响应] {"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
新: 模式 10 · 证据块 2 · 2265 字符

【旧渲染】
```
{"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: fictional_character.based_on | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced e.profession.people_with_this_profession)
```

--------------------------------------------------------------------------------------------
### 块 #5 调用: center: Franz Liszt  |  relations: organization.organization_founder.organizations_founded | organization.organization.founders | organization.organizatio
旧: [错误响应] {"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
新: 模式 3 · 证据块 2 · 1761 字符

【旧渲染】
```
{"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ organization.founders | fictional_character.based_on ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization.founders
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced none)
```


============================================================================================
## CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5 s1
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27  f1=0.0
sg 调用数: 旧 6 / 新 6

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Franz Liszt  |  relations: organization.founders | organization_founder.organizations_founded | organization_member.member_of
旧: 模式 13 · 证据块 3 · 3461 字符
新: 模式 10 · 证据块 2 · 1903 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | topic.image ⭢ composition.composer ⭢ organization_member.member_of | organization.founders | organization_founder.organizations_founded | organization_member.member_of
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Funérailles | Harmonies poétiques et religieuses | Life of Franz Liszt | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: fictional_character.based_on | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Freemasonry | Franz Liszt Academy of Music, Budapest  |  relations: organization.membership_organization.members | business.employment_tenure.company
旧: 模式 4 · 证据块 3 · 2835 字符
新: 模式 8 · 证据块 4 · 2436 字符

【旧渲染】
```
triples:
entities: Freemasonry | Franz Liszt Academy of Music, Budapest
▸ patterns: employment_tenure.company | membership_organization.members | employer.employees ⭢ employment_tenure.company | organization_membership.organization ⭢ membership_organization.members
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft [person: Life of Franz Liszt] | m.0w1vp7h
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    m.0w1vp7h --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft [person: Life of Franz Liszt]
    --organization_member.member_of--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'Freemasonry' narrows the relation pool to just that entity's edges — ?org has 2 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?org or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). Multiple centers retrieved with one shared relation set — COMPARE them via the triples (an edge '--to--> (incumbent)' marks the current holder). triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'business.employment_tenure.company': {'direct': ['business.employment_tenure.company'], 'bridge': ['education.educational_institution_campus.educational_institution']}}
```
【新渲染】
```
triples:
entities: Franz Liszt  (sequence root; this layer applies to the frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
▸ patterns: fictional_character.based_on ⭢ employment_tenure.person ⭢ employment_tenure.company | fictional_character.based_on ⭢ organization.founders ⭢ employment_tenure.company | fictional_character.based_on ⭢ organization_member.member_of ⭢ membership_organization.members | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded ⭢ employment_tenure.company | employment_tenure.company | membership_organization.members | fictional_character.based_on ⭢ employment_tenure.person | fictional_character.based_on ⭢ organization_member.member_of
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
── Franz Liszt Academy of Music, Budapest ──
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    m.0w1vp7h --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
note: ⚠ 'Freemasonry' is 1 of ?org's 2 candidates — pass ?org or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'business.employment_tenure.company': {'direct': ['business.employment_tenure.company'], 'bridge': ['education.educational_institution_campus.educational_institution']}}
anchor_sequence: Franz Liszt ⭢ 2-step chain (frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Freemasonry | Franz Liszt Academy of Music, Budapest  |  relations: organization.membership_organization.members | organization.organization_membership.member | organization.organization_
旧: 模式 22 · 证据块 3 · 5063 字符
新: 模式 7 · 证据块 4 · 2565 字符

【旧渲染】
```
triples:
entities: Freemasonry | Franz Liszt Academy of Music, Budapest  (sequence root; this layer applies to the frontier: Life of Franz Liszt)
▸ patterns: employer.employees | employment_tenure.company | membership_organization.members | organization_membership.organization | employment_tenure.person ⭢ employer.employees | employment_tenure.person ⭢ employment_tenure.company | organization_member.member_of ⭢ membership_organization.members | organization_member.member_of ⭢ organization_membership.organization | organization_membership.member ⭢ membership_organization.members | organization_membership.member ⭢ organization_membership.organization | person.employment_history ⭢ employer.employees | person.employment_history ⭢ employment_tenure.company | organization_membership.member | organization.founders ⭢ employer.employees | organization.founders ⭢ employment_tenure.company | organization_founder.organizations_founded ⭢ employer.employees | organization_founder.organizations_founded ⭢ employment_tenure.company | organization_member.member_of ⭢ organization_membership.member | name_source.namesakes ⭢ employer.employees | name_source.namesakes ⭢ employment_tenure.company | namesake.named_after ⭢ employer.employees | namesake.named_after ⭢ employment_tenure.company
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft [person: Life of Franz Liszt] | m.0w1vp7h
    --organization.founders--> Life of Franz Liszt
    --namesake.named_after--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    m.0w1vp7h --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    Life of Franz Liszt --name_source.namesakes--> Franz Liszt Academy of Music, Budapest
    Life of Franz Liszt --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft [person: Life of Franz Liszt]
    --organization_member.member_of--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'Freemasonry' narrows the relation pool to just that entity's edges — ?org has 2 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?org or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). Multiple centers retrieved with one shared relation set — COMPARE them via the triples (an edge '--to--> (incumbent)' marks the current holder). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edg
```
【新渲染】
```
triples:
entities: Franz Liszt  (sequence root; this layer applies to the frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
▸ patterns: fictional_character.based_on ⭢ organization_membership.member | fictional_character.based_on ⭢ employment_tenure.person ⭢ employer.employees | fictional_character.based_on ⭢ organization.founders ⭢ employer.employees | fictional_character.based_on ⭢ organization_member.member_of ⭢ organization_membership.organization | employer.employees | membership_organization.members | organization.founders
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft [company: Franz Liszt Academy of Music, Budapest] | m.0w1vp7h
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
note: ⚠ 'Freemasonry' is 1 of ?org's 2 candidates — pass ?org or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['business.employment_tenure.company', 'organization.organization.founders', 'organization.organization_membership.organization']}, 'business.employment_tenure.company': {'direct': ['business.employment_tenure.company'], 'bridge': ['education.educational_institution_campus.educational_institution']}, 'business.employer.employees': {'direct': ['business.employer.employees'], 'bridge': ['education.educational_institution_campus.educational_institution']}}
anchor_sequence: Franz Liszt ⭢ 3-step chain (frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #3 调用: center: Freemasonry | Franz Liszt Academy of Music, Budapest  |  relations: organization.organization_type.organizations_of_this_type | organization.organization.organization_type | organization.
旧: 模式 16 · 证据块 5 · 4582 字符
新: 模式 3 · 证据块 2 · 1467 字符

【旧渲染】
```
triples:
entities: Freemasonry | Franz Liszt Academy of Music, Budapest  (sequence root; this layer applies to the frontier: Life of Franz Liszt)
▸ patterns: organization.founders ⭢ artist.genre ⭢ organization.organization_type | organization.founders ⭢ artist.genre ⭢ organization_sector.organizations_in_this_sector | organization.founders ⭢ artist.genre ⭢ organization_type.organizations_of_this_type | organization.founders ⭢ person.religion ⭢ religion.is_part_of | organization_founder.organizations_founded ⭢ artist.genre ⭢ organization.organization_type | organization_founder.organizations_founded ⭢ artist.genre ⭢ organization_sector.organizations_in_this_sector | organization_founder.organizations_founded ⭢ artist.genre ⭢ organization_type.organizations_of_this_type | organization_founder.organizations_founded ⭢ person.religion ⭢ religion.is_part_of | namesake.named_after ⭢ artist.genre ⭢ organization.organization_type | namesake.named_after ⭢ artist.genre ⭢ organization_sector.organizations_in_this_sector | namesake.named_after ⭢ artist.genre ⭢ organization_type.organizations_of_this_type | membership_organization.members ⭢ organization_membership.member ⭢ artist.genre ⭢ organization.organization_type | organization.organization_type | organization_sector.organizations_in_this_sector | organization_type.organizations_of_this_type | religion.is_part_of
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2
    m.0cr70y2 --organization_membership.organization--> Freemasonry
── Franz Liszt Academy of Music, Budapest ──
    --organization.founders--> Life of Franz Liszt
    --namesake.named_after--> Life of Franz Liszt
    Life of Franz Liszt --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
── Life of Franz Liszt ──
    --artist.genre--> Classical music
    --organization_member.member_of--> m.0cr70y2
    --influence_node.peers--> m.02nc2ps | m.02nc2py | m.02nc2q2 | m.03gljgl | m.04c___v | m.05yr1xx
    --person.religion--> Catholicism
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.02nc2ps | m.02nc2py | m.02nc2q2 | m.03gljgl | m.04c___v | m.05yr1xx --peer_relationship.peers--> Life of Franz Liszt
── Classical music ──
    --organization_sector.organizations_in_this_sector--> ABRSM
    --organization_type.organizations_of_this_type--> ABRSM
    ABRSM --organization.organization_type--> Classical music
── Catholicism ──
    --religion.is_part_of--> Christianity
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'Freemasonry' narrows the relation pool to just that entity's edges — ?org has 2 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?org or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). Multiple centers retrieved with one shared relation set — COMPARE them via the triples (an edge '--to--> (incumbent)' marks the current holder). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTE
```
【新渲染】
```
triples:
entities: Franz Liszt  (sequence root; this layer applies to the frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
▸ patterns: fictional_character.based_on ⭢ artist.genre ⭢ organization.organization_type | fictional_character.based_on ⭢ artist.genre ⭢ organization_sector.organizations_in_this_sector | fictional_character.based_on ⭢ artist.genre ⭢ organization_type.organizations_of_this_type
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
── Classical music ──
    --organization_sector.organizations_in_this_sector--> ABRSM
    --organization_type.organizations_of_this_type--> ABRSM
    Life of Franz Liszt --artist.genre--> Classical music
    ABRSM --organization.organization_type--> Classical music
note: ⚠ 'Freemasonry' is 1 of ?org's 2 candidates — pass ?org or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
anchor_sequence: Franz Liszt ⭢ 4-step chain (frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #4 调用: center: ?org  |  relations: organization.organization_membership.organization | organization.organization_member.member_of | organization.organizat
旧: 模式 16 · 证据块 3 · 4380 字符
新: (无 sg 响应)

【旧渲染】
```
triples:
entities: Freemasonry | Franz Liszt Academy of Music, Budapest
▸ patterns: organization.founders | organization_membership.organization | membership_organization.members ⭢ organization_member.member_of | membership_organization.members ⭢ organization_membership.organization | organization.founders ⭢ organization_member.member_of | organization_founder.organizations_founded ⭢ organization_member.member_of | organization_membership.organization ⭢ organization_member.member_of | name_source.namesakes ⭢ organization_member.member_of | namesake.named_after ⭢ organization_member.member_of | employer.employees ⭢ employment_tenure.person ⭢ organization_member.member_of | employer.employees ⭢ person.employment_history ⭢ organization_member.member_of | employment_tenure.company ⭢ employment_tenure.person ⭢ organization_member.member_of | employment_tenure.company ⭢ person.employment_history ⭢ organization_member.member_of | membership_organization.members ⭢ organization_membership.member ⭢ organization.founders | organization_membership.organization ⭢ organization_membership.member ⭢ organization.founders | organization_member.member_of
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft
    --organization.founders--> Life of Franz Liszt
    --namesake.named_after--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    Life of Franz Liszt --name_source.namesakes--> Franz Liszt Academy of Music, Budapest
    Life of Franz Liszt --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft
    --organization_member.member_of--> m.0cr70y2 [member: Life of Franz Liszt]
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: Multiple centers retrieved with one shared relation set — COMPARE them via the triples (an edge '--to--> (incumbent)' marks the current holder). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['business.employment_tenure.company', 'organization.organization.founders', 'organization.organization_membership.organization']}, 'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['business.employment_tenur
```
【新渲染】
```
(无)
```

--------------------------------------------------------------------------------------------
### 块 #5 调用: center: Franz Liszt  |  relations: organization.organization.founders | organization.organization_founder.organizations_founded | organization.organizatio
旧: 模式 17 · 证据块 3 · 4183 字符
新: 模式 0 · 证据块 0 · 1174 字符

【旧渲染】
```
triples:
entities: Franz Liszt
▸ patterns: topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member | topic.image ⭢ composition.composer ⭢ organization_membership.member | organization.founders | organization_founder.organizations_founded | organization_member.member_of | organization_membership.member
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Funérailles | Harmonies poétiques et religieuses | Life of Franz Liszt | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Funérailles | Harmonies poétiques et religieuses | Légende No. 1: St François d'Assise | Sarabande and Chaconne from Handel's Almira --composition.composer--> Life of Franz Liszt
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.organization--> Freemasonry
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organiz
```
【新渲染】
```
triples: (empty)
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
layer_action: repeat
```


============================================================================================
## CASE WebQTest-1797_2fb9e2823ccf35d2103fa8846d6f2ca8 s1
Q: Of the people who fought in the Battle of Vicksburg, who has the earliest date of death?  f1=0.0
sg 调用数: 旧 3 / 新 3

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Siege of Vicksburg  |  relations: military_conflict.combatants | military_person.participated_in_conflicts | military_conflict.military_personnel_involve
旧: 模式 11 · 证据块 10 · 7839 字符
新: 模式 24 · 证据块 10 · 12456 字符

【旧渲染】
```
triples:
entities: Siege of Vicksburg
▸ patterns: military_conflict.combatants | military_conflict.military_personnel_involved | military_person.participated_in_conflicts | military_combatant_group.conflict ⭢ military_conflict.combatants | military_conflict.military_personnel_involved ⭢ military_conflict.military_personnel_involved | military_conflict.military_personnel_involved ⭢ military_person.participated_in_conflicts | military_person.participated_in_conflicts ⭢ military_conflict.military_personnel_involved | military_person.participated_in_conflicts ⭢ military_person.participated_in_conflicts | event.included_in_event ⭢ military_conflict.combatants | event.included_in_event ⭢ military_person.participated_in_conflicts | event.entity_involved ⭢ event.locations ⭢ military_conflict.combatants
── Siege of Vicksburg ──
    --military_conflict.combatants--> m.049y2pc | m.04fvcs7
    --event.entity_involved--> United States of America
    --event.included_in_event--> American Civil War
    --military_conflict.military_personnel_involved--> Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner | William F. Draper
    m.049y2pc --military_combatant_group.conflict--> Siege of Vicksburg
    m.04fvcs7 --military_combatant_group.conflict--> Siege of Vicksburg
    Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner …(+1) --military_person.participated_in_conflicts--> Siege of Vicksburg
── American Civil War ──
    --military_conflict.combatants--> m.03z965k | m.03z98d_
    --event.locations--> United States of America
    Carter L. Stevenson | David Farragut | George B. McClellan | Henry Halleck | Henry Wilson | James B. McPherson | Jefferson Davis | John Alexander McClernand | John S. Bowen | Joseph E. Johnston | P. G. T. Beauregard | Peter Joseph Osterhaus …(+6) --military_person.participated_in_conflicts--> American Civil War
── Ulysses S. Grant ──
    --military_person.participated_in_conflicts--> Appomattox Campaign | Battle of Chapultepec | Battle of Fort Donelson | Battle of Molino del Rey | Battle of Monterrey | Battle of Palo Alto | Battle of Resaca de la Palma | Battle of Shiloh | Chattanooga Campaign | Mexican–American War | Overland Campaign | Siege of Petersburg | Siege of Veracruz
    Appomattox Campaign | Battle of Chapultepec | Battle of Fort Donelson | Battle of Molino del Rey | Battle of Monterrey | Battle of Palo Alto | Battle of Resaca de la Palma | Battle of Shiloh | Chattanooga Campaign | Overland Campaign | Siege of Petersburg | Siege of Veracruz --military_conflict.military_personnel_involved--> Ulysses S. Grant
── James B. McPherson ──
    --military_person.participated_in_conflicts--> Battle of Atlanta | Battle of Fort Donelson | Battle of Fort Henry | Battle of Kennesaw Mountain | Battle of Resaca | Battle of Shiloh
    Battle of Atlanta | Battle of Fort Donelson | Battle of Fort Henry | Battle of Kennesaw Mountain | Battle of Resaca | Battle of Shiloh --military_conflict.military_personnel_involved--> James B. McPherson
── Peter Joseph Osterhaus ──
    --military_person.participated_in_conflicts--> Atlanta Campaign | Battle of Big Black River Bridge | Battle of Lookout Mountain | Battle of Pea Ridge | Battle of Wilson's Creek | Sherman's March to the Sea
    Atlanta Campaign | Battle of Big Black River Bridge | Battle of Lookout Mountain | Battle of Pea Ridge | Battle of Wilson's Creek | Sherman's March to the Sea --military_conflict.military_personnel_involved--> Peter Joseph Osterhaus
── Carter L. Stevenson ──
    --military_person.participated_in_conflicts--> Atlanta Campaign | Battle of Lookout Mountain | Battle of Nashville | Mexican–American War | Secon
```
【新渲染】
```
triples:
entities: Siege of Vicksburg
▸ patterns: event.entity_involved | military_command.military_conflict | military_conflict.combatants | military_conflict.commanders | military_conflict.military_personnel_involved | military_person.participated_in_conflicts | event.included_in_event | military_conflict.military_personnel_involved ⭢ military_person.participated_in_conflicts | military_person.participated_in_conflicts ⭢ event.entity_involved | military_person.participated_in_conflicts ⭢ military_conflict.military_personnel_involved | event.included_in_event ⭢ military_command.military_conflict | event.included_in_event ⭢ military_conflict.combatants | event.included_in_event ⭢ military_conflict.commanders | event.includes_event ⭢ event.included_in_event | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_command.military_conflict | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_conflict.commanders | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ event.included_in_event | military_unit.conflicts_participated_in ⭢ battle.military_units_involved_in_this_conflict ⭢ event.included_in_event | event.entity_involved ⭢ military_person.participated_in_conflicts ⭢ military_conflict.combatants | military_command.military_conflict ⭢ military_command.military_commander ⭢ military_conflict.military_personnel_involved | military_command.military_conflict ⭢ military_command.military_commander ⭢ military_person.participated_in_conflicts | military_command.military_conflict ⭢ military_commander.military_commands ⭢ military_person.participated_in_conflicts | military_conflict.combatants ⭢ military_combatant_group.combatants ⭢ event.entity_involved | military_conflict.commanders ⭢ military_command.military_combatant ⭢ event.entity_involved
── Siege of Vicksburg ──
    --military_conflict.combatants--> m.049y2pc | m.04fvcs7
    --military_conflict.commanders--> m.049y2lz [military_combatant: Union; military_commander: Ulysses S. Grant] | m.049y2m5 [military_combatant: Confederate States of America; military_commander: John C. Pemberton]
    --event.entity_involved--> Confederate States of America | John C. Pemberton | Ulysses S. Grant | Union | United States of America
    --event.included_in_event--> American Civil War | Grant's Operations Against Vicksburg
    --military_conflict.military_personnel_involved--> Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner | William F. Draper
    --battle.military_units_involved_in_this_conflict--> 17th Louisiana Infantry Regiment | 31st Louisiana Infantry Regiment
    17th Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Siege of Vicksburg
    31st Louisiana Infantry Regiment --military_unit.conflicts_participated_in--> Siege of Vicksburg
    Grant's Operations Against Vicksburg --event.includes_event--> Siege of Vicksburg
    m.049y2lz --military_command.military_conflict--> Siege of Vicksburg
    m.049y2m5 --military_command.military_conflict--> Siege of Vicksburg
    Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner …(+1) (to answer with ALL of them, include "#Carter L. Stevenson::participated_in_conflicts" as one answer entity) --military_person.participated_in_conflicts--> Siege of Vicksburg
── American Civil War ──
    --military_conflict.combatants--> m.03z965k | m.03z98d_
    --military_conflict.commanders--> m.04fvgx2 [military_commander: Ulysses S. Grant] | m.04fvgx7 [military_commander: Robert E. Lee] | m.04h_gx9 [military_combatant: United States of America; military_c
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner | William F. Draper  |  relations: deceased_person.place_of_death | place_of_interment.interred_here | person.place_of_birth
旧: 模式 23 · 证据块 9 · 8330 字符
新: 模式 14 · 证据块 10 · 8239 字符

【旧渲染】
```
triples:
entities: Siege of Vicksburg  (sequence root; this layer applies to the frontier: Carter L. Stevenson | Confederate States of America | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant)
▸ patterns: military_conflict.military_personnel_involved ⭢ deceased_person.place_of_death | military_conflict.military_personnel_involved ⭢ person.place_of_birth | military_conflict.military_personnel_involved ⭢ place_of_interment.interred_here | deceased_person.place_of_death | person.place_of_birth | place_of_interment.interred_here | us_president.vice_president ⭢ deceased_person.place_of_death | us_vice_president.to_president ⭢ deceased_person.place_of_death | person.children ⭢ place_of_interment.interred_here | person.place_of_birth ⭢ person.place_of_birth | namesake.named_after ⭢ person.place_of_birth | pet_ownership.owner ⭢ pet_ownership.owner ⭢ place_of_interment.interred_here | kwconnection.subject ⭢ kwconnection.other ⭢ deceased_person.place_of_death | kwconnection.subject ⭢ kwconnection.other ⭢ place_of_interment.interred_here | kwconnection.subject ⭢ kwtopic.connections_to ⭢ deceased_person.place_of_death | kwconnection.subject ⭢ kwtopic.connections_to ⭢ place_of_interment.interred_here | kwtopic.connections_from ⭢ kwconnection.other ⭢ deceased_person.place_of_death | kwtopic.connections_from ⭢ kwconnection.other ⭢ place_of_interment.interred_here | kwtopic.connections_from ⭢ kwtopic.connections_to ⭢ deceased_person.place_of_death | kwtopic.connections_from ⭢ kwtopic.connections_to ⭢ place_of_interment.interred_here | political_convention.presidential_nominee ⭢ event.locations ⭢ person.place_of_birth | presidential_nominee.nominated_at ⭢ event.locations ⭢ person.place_of_birth | military_conflict.military_personnel_involved ⭢ location.events ⭢ person.place_of_birth
── Siege of Vicksburg ──
    --military_conflict.military_personnel_involved--> Carter L. Stevenson | David Farragut | Henry Casey | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William F. Draper | Henry Dow | William D. Turner
── Ulysses S. Grant ──
    --person.children--> Ellen Wrenshall Grant
    --kwtopic.connections_from--> ulysses simpson grant appointed general by abraham lincoln
    --presidential_nominee.nominated_at--> 1872 Republican National Convention
    --person.place_of_birth--> Point Pleasant
    --deceased_person.place_of_death--> Wilton
    --us_president.vice_president--> Henry Wilson
    General Grant National Memorial --place_of_interment.interred_here--> Ulysses S. Grant
    Jim Walsh --namesake.named_after--> Ulysses S. Grant
    m.05k6fr0 --pet_ownership.owner--> Ulysses S. Grant
    1872 Republican National Convention --political_convention.presidential_nominee--> Ulysses S. Grant
    ulysses simpson grant appointed general by abraham lincoln --kwconnection.subject--> Ulysses S. Grant
    Henry Wilson --us_vice_president.to_president--> Ulysses S. Grant
── Abraham Lincoln ──
    --kwtopic.connections_to--> ulysses simpson grant appointed general by abraham lincoln
    --deceased_person.place_of_death--> Washington, D.C.
    Oak Ridge Cemetery --place_of_interment.interred_here--> Abraham Lincoln
    ulysses simpson grant appointed general by abraham lincoln --kwconnection.other--> Abraham Lincoln
── John Alexander McClernand ──
    --person.place_of_birth--> Breckinridge County
    --deceased_person.place_of_death--> Springfield
    Oak Ridge Cemetery --place_of_interment.interred_here--> John Alexander McClernand
── Seth Barton ──
    --person.place_of_birth--> Fredericksburg
    --deceased_person.place_of_death--> Washington, D.C.
    Appomattox Campaign --military_conflict.military_personnel_involved--> Seth Barton
── Washington, D.C. ──
    Henry Wilson --deceased_person.place_of_death--> Washi
```
【新渲染】
```
triples:
entities: Siege of Vicksburg  (sequence root; this layer applies to the frontier: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner)
▸ patterns: battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_conflict.commanders ⭢ military_command.military_commander ⭢ pet_owner.pets_owned | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_conflict.commanders ⭢ military_command.military_commander ⭢ pet_ownership.owner | battle.military_units_involved_in_this_conflict ⭢ military_unit.conflicts_participated_in ⭢ military_conflict.commanders ⭢ military_command.military_commander ⭢ topic.image | military_conflict.commanders ⭢ military_command.military_commander ⭢ military_person.participated_in_conflicts ⭢ location.events ⭢ person.place_of_birth | pet_owner.pets_owned | topic.image | us_president.vice_president | location.people_born_here | deceased_person.place_of_burial | deceased_person.place_of_death | person.children | person.place_of_birth | person.places_lived | namesake.named_after
── Siege of Vicksburg ──
    --military_conflict.commanders--> m.049y2lz [military_combatant: Union]
    --battle.military_units_involved_in_this_conflict--> 31st Louisiana Infantry Regiment
── Ulysses S. Grant ──
    --person.children--> Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.
    --topic.image--> GrantBirthplace | Ulysses Grant 1870-1880
    --military_person.participated_in_conflicts--> Appomattox Campaign
    --pet_owner.pets_owned--> m.05k6cbt [owner: Jesse Root Grant] | m.05k6ddj [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6dn_ [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6drm [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6dyy [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6f3h [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6ffg [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6flg [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6fr0 [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6ft8 [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.] | m.05k6fyl [owner: Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.]
    --deceased_person.place_of_burial--> General Grant National Memorial
    --deceased_person.place_of_death--> Wilton
    --person.places_lived--> m.03pj1vh [location: Ohio] | m.04hxfk6
    --us_president.vice_president--> Henry Wilson | Schuyler Colfax
    m.049y2lz --military_command.military_commander--> Ulysses S. Grant
    m.04yytyv --military_command.military_commander--> Ulysses S. Grant
    Grant | Grant Avenue | Grant City | Grant Cottage | Grant County | Grant Parish | Grant Park | Grants Pass | Jim Walsh | U.S. Grant Hotel | Ulysses | Ulysses S. Grant Memorial …(+1) (to answer with ALL of them, include "#Grant::named_after" as one answer entity) --namesake.named_after--> Ulysses S. Grant
    m.05k6cbt | m.05k6ddj | m.05k6dn_ | m.05k6drm | m.05k6dyy | m.05k6f3h | m.05k6ffg | m.05k6flg | m.05k6fr0 | m.05k6ft8 | m.05k6fyl --pet_ownership.owner--> Ulysses S. Grant
    Point Pleasant --location.people_born_here--> Ulysses S. Grant
── David Farragut ──
    --topic.image--> Admiral David Farragut | Admiral David Farragut (1801–1870) - collodion, LC-BH82-4054 restored
    --deceased_person.pla
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner | William F. Draper  |  relations: deceased_person.cause_of_death | deceased_person.place_of_death | person.place_of_birth | place_of_interment.interred_h
旧: 模式 15 · 证据块 9 · 7343 字符
新: 模式 9 · 证据块 9 · 5390 字符

【旧渲染】
```
triples:
entities: Siege of Vicksburg  (sequence root; this layer applies to the frontier: Atlanta | Bloomingburg | Breckinridge County | Caroline County | Clyde | Duisburg | Edwards | Farragut | Fredericksburg | Fremont | General Grant National Memorial | Koblenz)
▸ patterns: military_conflict.military_personnel_involved ⭢ deceased_person.cause_of_death | military_conflict.military_personnel_involved ⭢ deceased_person.place_of_death | military_conflict.military_personnel_involved ⭢ person.place_of_birth | deceased_person.cause_of_death | deceased_person.place_of_death | person.place_of_birth | person.place_of_birth ⭢ deceased_person.place_of_death | us_national_park.state ⭢ location.containedby ⭢ deceased_person.place_of_death | administrative_division.second_level_division_of ⭢ location.containedby ⭢ deceased_person.place_of_death | location.containedby ⭢ administrative_area.administrative_children ⭢ deceased_person.place_of_death | location.containedby ⭢ administrative_area.administrative_parent ⭢ deceased_person.place_of_death | deceased_person.place_of_burial ⭢ us_president.vice_president ⭢ deceased_person.place_of_death | deceased_person.place_of_burial ⭢ us_vice_president.to_president ⭢ deceased_person.place_of_death | place_lived.location ⭢ person.places_lived ⭢ deceased_person.place_of_death | place_lived.location ⭢ place_lived.person ⭢ deceased_person.place_of_death
── Siege of Vicksburg ──
    --military_conflict.military_personnel_involved--> Ulysses S. Grant | Carter L. Stevenson | David Farragut | Henry Casey | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | William F. Draper | Henry Dow | William D. Turner
── Koblenz ──
    m.04hgzp_ --place_lived.location--> Koblenz
    Peter Joseph Osterhaus --person.place_of_birth--> Koblenz
── Ulysses S. Grant ──
    --deceased_person.cause_of_death--> Esophageal cancer
    --person.place_of_birth--> Point Pleasant
    --deceased_person.place_of_burial--> General Grant National Memorial
    --deceased_person.place_of_death--> Wilton
    --us_president.vice_president--> Henry Wilson
    Henry Wilson --us_vice_president.to_president--> Ulysses S. Grant
── United States of America ──
    Atlanta | Caroline County | Edwards | Springfield | Washington, D.C. --location.containedby--> United States of America
    Fredericksburg --administrative_division.second_level_division_of--> United States of America
── Washington, D.C. ──
    Abraham Lincoln | Henry Wilson | Joseph E. Johnston | Seth Barton | William F. Draper --deceased_person.place_of_death--> Washington, D.C.
── Peter Joseph Osterhaus ──
    --deceased_person.place_of_death--> Duisburg
    --person.places_lived--> m.04hgzp_ [person: Peter Joseph Osterhaus]
    m.04hgzp_ --place_lived.person--> Peter Joseph Osterhaus
── Caroline County ──
    --administrative_area.administrative_parent--> Virginia
    Virginia --administrative_area.administrative_children--> Caroline County
    Carter L. Stevenson --deceased_person.place_of_death--> Caroline County
── Fredericksburg ──
    --location.containedby--> Virginia
    Carter L. Stevenson --person.place_of_birth--> Fredericksburg
    Seth Barton --person.place_of_birth--> Fredericksburg
── David Farragut ──
    --person.place_of_birth--> Farragut
    --deceased_person.place_of_death--> Portsmouth
    General Grant National Memorial --us_national_park.state--> New York
    Henry Casey --deceased_person.place_of_death--> Bloomingburg
    Henry Dow --person.place_of_birth--> Scotland
    James B. McPherson --person.place_of_birth--> Clyde
    James B. McPherson --deceased_person.place_of_death--> Atlanta
    John Alexander McClernand --person.place_of_birth--> Breckinridge County
    John Alexander McClernand --deceased_person.place_of_death--> Springfield
    John S. Bowen --person.place_of_birth--> Savannah
    John S. Bowen --deceased_person.place_of_death--> Edwards
    Ralph Pomeroy Buckland --person
```
【新渲染】
```
triples:
entities: Siege of Vicksburg  (sequence root; this layer applies to the frontier: Carter L. Stevenson | David Farragut | Henry Casey | Henry Dow | James B. McPherson | John Alexander McClernand | John S. Bowen | Peter Joseph Osterhaus | Ralph Pomeroy Buckland | Seth Barton | Ulysses S. Grant | William D. Turner)
▸ patterns: us_president.vice_president | location.people_born_here | deceased_person.cause_of_death | deceased_person.place_of_burial | deceased_person.place_of_death | person.children | person.place_of_birth | person.places_lived | namesake.named_after
── Ulysses S. Grant ──
    --deceased_person.cause_of_death--> Esophageal cancer
    --person.children--> Ellen Wrenshall Grant | Frederick Dent Grant | Jesse Root Grant | Ulysses S. Grant Jr.
    --deceased_person.place_of_burial--> General Grant National Memorial
    --deceased_person.place_of_death--> Wilton
    --person.places_lived--> m.03pj1vh [location: Ohio] | m.04hxfk6
    --us_president.vice_president--> Henry Wilson | Schuyler Colfax
    Grant | Grant Avenue | Grant City | Grant Cottage | Grant County | Grant Parish | Grant Park | Grants Pass | Jim Walsh | U.S. Grant Hotel | Ulysses | Ulysses S. Grant Memorial …(+1) (to answer with ALL of them, include "#Grant::named_after" as one answer entity) --namesake.named_after--> Ulysses S. Grant
    Point Pleasant --location.people_born_here--> Ulysses S. Grant
── David Farragut ──
    --deceased_person.place_of_burial--> Woodlawn Cemetery
    --deceased_person.place_of_death--> Portsmouth
    --person.places_lived--> m.03prc7s
    David Porter --person.children--> David Farragut
    Farragut Career Academy | Farragut High School | Farragut Square --namesake.named_after--> David Farragut
    Farragut --location.people_born_here--> David Farragut
── James B. McPherson ──
    --deceased_person.place_of_burial--> Fort McPherson National Cemetery
    --deceased_person.place_of_death--> Atlanta
    --person.places_lived--> m.03pj0kp [location: Ohio]
    Fort McPherson --namesake.named_after--> James B. McPherson
    McPherson Square --namesake.named_after--> James B. McPherson
    Clyde --location.people_born_here--> James B. McPherson
── John Alexander McClernand ──
    --person.children--> Edward John McClernand
    --deceased_person.place_of_burial--> Oak Ridge Cemetery
    --deceased_person.place_of_death--> Springfield
    --person.places_lived--> m.04hsssl [location: Springfield]
    Breckinridge County --location.people_born_here--> John Alexander McClernand
── Peter Joseph Osterhaus ──
    --person.place_of_birth--> Koblenz
    --deceased_person.place_of_burial--> Berlin
    --deceased_person.place_of_death--> Duisburg
    --person.places_lived--> m.03pk3n7 | m.04hgzp_ [location: Koblenz]
── Carter L. Stevenson ──
    --deceased_person.place_of_death--> Caroline County
    --person.places_lived--> m.03pl0f0 [location: Virginia]
    Fredericksburg --location.people_born_here--> Carter L. Stevenson
── Seth Barton ──
    --deceased_person.place_of_death--> Washington, D.C.
    --person.places_lived--> m.03pl1r_ [location: Virginia]
    Fredericksburg --location.people_born_here--> Seth Barton
── Ralph Pomeroy Buckland ──
    --deceased_person.place_of_burial--> Oakwood Cemetery
    --deceased_person.place_of_death--> Fremont
    Leyden --location.people_born_here--> Ralph Pomeroy Buckland
── John S. Bowen ──
    --person.place_of_birth--> Savannah
    --deceased_person.place_of_death--> Edwards
    Henry Casey --deceased_person.place_of_death--> Bloomingburg
    Henry Dow --person.place_of_birth--> Scotland
    Quincy --location.people_born_here--> William D. Turner
note: ⚠ 'Carter L. Stevenson' is 1 of ?participant's 13 candidates — pass ?participant or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not a
```


============================================================================================
## CASE WebQTest-626_01ad90831a03b6c5ef17898ccd80a639 s0
Q: What setting of the fictional universe Tempus Unbound is bisected by the Missouri River?  f1=1.0
sg 调用数: 旧 3 / 新 3

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Tempus Unbound  |  relations: fictional_setting.universe
旧: 模式 10 · 证据块 6 · 4045 字符
新: 模式 18 · 证据块 8 · 4898 字符

【旧渲染】
```
triples:
entities: Tempus Unbound
▸ patterns: fictional_setting.universe | location_in_fiction.works_set_here ⭢ fictional_setting.universe | book_subject.works ⭢ fictional_setting.universe | fictional_setting.universe ⭢ fictional_setting.universe | fictional_setting.works_set_here ⭢ fictional_setting.universe | fictional_universe.fictional_objects ⭢ fictional_setting.universe | fictional_universe.locations ⭢ fictional_setting.universe | fictional_universe.works_set_here ⭢ fictional_setting.universe | work_of_fiction.part_of_these_fictional_universes ⭢ fictional_setting.universe | work_of_fiction.setting ⭢ fictional_setting.universe
── Tempus Unbound ──
    --fictional_universe.fictional_objects--> Lemurian citadel | Lemurian windows into any place or time
    --fictional_universe.locations--> Kansas | Lemuria | Long Island | New York City
    --work_of_fiction.part_of_these_fictional_universes--> Sacred Band of Stepsons | The Sacred Band of Stepsons universe
    --work_of_fiction.setting--> Beyond Sanctuary | Citadel of Lemuria | Kansas | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Long Island | Mari, Syria | Meridian | Pinnacle House | Sandia
    Kansas | Lemuria | Long Island | New York City --fictional_setting.universe--> Tempus Unbound
    Lemuria --book_subject.works--> Tempus Unbound
    Sacred Band of Stepsons --book_subject.works--> Tempus Unbound
    Lemuria | Lemurian citadel | Lemurian windows into any place or time | Meridian | Sacred Band of Stepsons | The Sacred Band of Stepsons universe --location_in_fiction.works_set_here--> Tempus Unbound
── The Sacred Band of Stepsons universe ──
    Abarsis Valley | Battleplain of Chaeronea | Beyond Sanctuary | Chaeronea | Citadel of Lemuria | City at the Edge of Time | Free Nisibis | Kansas | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Long Island …(+11) --fictional_setting.universe--> The Sacred Band of Stepsons universe
── Sacred Band of Stepsons ──
    Battleplain of Chaeronea | Chaeronea | Free Nisibis | Lemuria | Meridian | Meridian battleplain | Nisibis | Peace Falls | Pinnacle House | Theban Cadmea | Tyse | Wizardwall …(+1) --fictional_setting.universe--> Sacred Band of Stepsons
── Lemuria ──
    --fictional_setting.universe--> Thieves' World fictional shared universe
── Lemurian windows into any place or time ──
    --fictional_setting.universe--> Thieves' World fictional shared universe
── Beyond Sanctuary ──
    --fictional_setting.universe--> Thieves' World fictional shared universe
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'fictional_setting.universe': {'direct': ['fictional_universe.fictional_setting.universe'], 'bridge': ['base.militaryinfiction.location_in_fiction.works_set_here', 'book.written_work.next_in_series', 'fictional_universe.fictional_setting.works_set_here', 'fictional_universe.fictional_universe.works_set_here', 'f
```
【新渲染】
```
triples:
entities: Tempus Unbound
▸ patterns: location_in_fiction.works_set_here | written_work.next_in_series | fictional_setting.universe | fictional_setting.works_set_here | fictional_universe.works_set_here | work_of_fiction.setting | location_in_fiction.works_set_here ⭢ written_work.next_in_series | location_in_fiction.works_set_here ⭢ fictional_setting.universe | literary_series.fictional_universe ⭢ written_work.next_in_series | literary_series.fictional_universe ⭢ work_of_fiction.setting | fictional_character.appears_in_these_fictional_universes ⭢ work_of_fiction.setting | fictional_object.featured_in_fictional_universe ⭢ location_in_fiction.works_set_here | fictional_object.featured_in_fictional_universe ⭢ fictional_setting.universe | fictional_object.featured_in_fictional_universe ⭢ work_of_fiction.setting | fictional_setting.universe ⭢ location_in_fiction.works_set_here | fictional_setting.works_set_here ⭢ location_in_fiction.works_set_here | fictional_setting.works_set_here ⭢ written_work.next_in_series | fictional_setting.works_set_here ⭢ fictional_setting.universe
── Tempus Unbound ──
    --work_of_fiction.setting--> Beyond Sanctuary | Citadel of Lemuria | Kansas | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Long Island | Manhattan | Mari, Syria | Meridian | New York | Pinnacle House | Sandia
    Faun --fictional_character.appears_in_these_fictional_universes--> Tempus Unbound
    Lemurian citadel --fictional_object.featured_in_fictional_universe--> Tempus Unbound
    Lemurian windows into any place or time --fictional_object.featured_in_fictional_universe--> Tempus Unbound
    The Sacred Band --literary_series.fictional_universe--> Tempus Unbound
    City at the Edge of Time --written_work.next_in_series--> Tempus Unbound
    Kansas | Lemuria | Long Island | New York City --fictional_setting.universe--> Tempus Unbound
    Beyond Sanctuary | Citadel | Citadel of Lemuria | Egypt | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Manhattan | Mari, Syria | Meridian | New York | Pinnacle House …(+5) (to answer with ALL of them, include "#Beyond Sanctuary::works_set_here" as one answer entity) --location_in_fiction.works_set_here--> Tempus Unbound
── The Sacred Band ──
    --written_work.next_in_series--> Wars don’t bring lasting peace, only lasting death.
    --work_of_fiction.setting--> Abarsis Valley | Abarsis's Overlook | Bandara | Bandaran island chain | Battleplain of Chaeronea | Beyond Overlook | Beyond Sanctuary | Chaeronea | Citadel of Lemuria | Downwind | Free Nisibis | Lemuria | Lemurian citadel | Lemurian windows into any place or time | Meridian battleplain | Mygdonia | Nisibis | Peace Falls | Pinnacle House | Rankan Mageguild | Ratfall | Sanctuary | Stepsons' barracks | The Misty Isles | Theban Cadmea | Tyse | liminal | warrior-monk academy
    Storm Seed --written_work.next_in_series--> The Sacred Band
    Beyond Sanctuary | Lemuria | Lemurian citadel --location_in_fiction.works_set_here--> The Sacred Band
── Beyond Sanctuary ──
    --written_work.next_in_series--> Beyond the Veil
    --fictional_setting.universe--> The Sacred Band of Stepsons universe | Thieves' World fictional shared universe
    --location_in_fiction.works_set_here--> Beyond Wizardwall | Beyond the Veil
    An End to Dreaming --written_work.next_in_series--> Beyond Sanctuary
    Black Nisibis | Citadel | Free Nisibis | Nisibis | Rankan Mageguild | Wizardwall --location_in_fiction.works_set_here--> Beyond Sanctuary
── Lemuria ──
    --fictional_setting.universe--> Sacred Band of Stepsons | The Sacred Band of Stepsons universe | Thieves' World fictional shared universe
    --location_in_fiction.works_set_here--> Storm Seed
── Lemurian citadel ──
    --fictional_setting.universe--> The Sacred Band of Stepsons universe
    --location_in_fiction.works_set_here--> Storm Seed
    Storm Seed --work_of_fiction.setting--> Lemurian citadel
── Lemurian windows into any place or time ──
    --fictio
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: ?setting  |  relations: location.location.partially_contained_by | location.location.containedby | location.location.primarily_containedby
旧: 模式 73 · 证据块 9 · 14567 字符
新: 模式 16 · 证据块 10 · 9740 字符

【旧渲染】
```
triples:
entities: Tempus Unbound | Beyond Sanctuary | Citadel of Lemuria | Meridian | Pinnacle House | Sandia | The Sacred Band of Stepsons universe | Battleplain of Chaeronea | Free Nisibis | Peace Falls | Tyse | Wizardwall | Abarsis Valley | City at the Edge of Time | Nisibis | Theban Cadmea | Meridian battleplain | liminal  (sequence root; this layer applies to the frontier: Kansas | Lemuria | Long Island | New York City)
▸ patterns: location.containedby | location_in_fiction.contained_by ⭢ location.containedby | location_in_fiction.contained_by ⭢ location.primarily_containedby | location_in_fiction.contains ⭢ location.containedby | location_in_fiction.contains ⭢ location.primarily_containedby | location_in_fiction.universe ⭢ location.containedby | location_in_fiction.universe ⭢ location.primarily_containedby | location_represented_in_fiction.representations ⭢ location.containedby | fictional_setting.contained_by ⭢ location.containedby | fictional_setting.contains ⭢ location.containedby | fictional_setting.universe ⭢ location.containedby | fictional_universe.locations ⭢ location.containedby | location.containedby ⭢ location.containedby | location.contains ⭢ location.containedby | event_in_fiction.location ⭢ work_of_fiction.setting ⭢ location.containedby | location_in_fiction.contained_by ⭢ administrative_area.administrative_parent ⭢ location.containedby | location_in_fiction.contained_by ⭢ bibs_location.country ⭢ location.containedby | location_in_fiction.contained_by ⭢ countries.states_provinces_within ⭢ location.containedby | location_in_fiction.contained_by ⭢ states_and_provences.country ⭢ location.containedby | location_in_fiction.contained_by ⭢ location_in_fiction.contained_by ⭢ location.containedby | location_in_fiction.contained_by ⭢ location_in_fiction.contains ⭢ location.containedby | location_in_fiction.contained_by ⭢ location_represented_in_fiction.representations ⭢ location.containedby | location_in_fiction.contained_by ⭢ river.basin_countries ⭢ location.partially_contained_by | location_in_fiction.contained_by ⭢ administrative_division.second_level_division_of ⭢ location.containedby | location_in_fiction.contained_by ⭢ country.administrative_divisions ⭢ location.containedby | location_in_fiction.contained_by ⭢ location.containedby ⭢ location.containedby | location_in_fiction.contained_by ⭢ location.containedby ⭢ location.partially_contained_by | location_in_fiction.contained_by ⭢ location.partially_containedby ⭢ location.containedby | location_in_fiction.contains ⭢ river.basin_countries ⭢ location.partially_contained_by | location_in_fiction.languages ⭢ human_language.main_country ⭢ location.containedby | event_in_fiction.location ⭢ fictional_setting.events ⭢ location.containedby | fictional_language.where_spoken ⭢ human_language.main_country ⭢ location.primarily_containedby | fictional_language.where_spoken ⭢ human_language.region ⭢ location.primarily_containedby | fictional_object.location ⭢ fictional_setting.setting_type ⭢ location.containedby | fictional_organization.appears_in_universes ⭢ fictional_setting.universe ⭢ location.containedby | fictional_organization.appears_in_universes ⭢ fictional_universe.locations ⭢ location.containedby | fictional_setting.contains ⭢ location_in_fiction.setting_type ⭢ location.primarily_containedby | fictional_setting.contains ⭢ location_represented_in_fiction.representations ⭢ location.containedby | fictional_setting.events ⭢ event_in_fiction.location ⭢ location.containedby | fictional_setting.fictional_characters_born_here ⭢ event_in_fiction.location ⭢ location.containedby | fictional_setting.languages ⭢ location_in_fiction.languages ⭢ location.primarily_containedby | fictional_setting.languages ⭢ human_language.main_country ⭢ location.primarily_containedby | fictional_setting.languages ⭢ human_language.region ⭢ location.primarily_containedby | fictional_setting.setting_type ⭢ location_represented_in_fiction.representations ⭢ location.containedby | fictional_setting.work
```
【新渲染】
```
triples:
entities: Tempus Unbound  (sequence root; this layer applies to the frontier: Abarsis Valley | Battleplain of Chaeronea | Beyond Sanctuary | Chaeronea | Citadel of Lemuria | City at the Edge of Time | Free Nisibis | Kansas | Lemuria | Long Island | Meridian | Meridian battleplain)
▸ patterns: literary_series.fictional_universe ⭢ work_of_fiction.setting ⭢ location_in_fiction.contains | literary_series.fictional_universe ⭢ work_of_fiction.setting ⭢ location_in_fiction.universe | fictional_character.appears_in_these_fictional_universes ⭢ work_of_fiction.setting ⭢ location_in_fiction.contains | fictional_character.appears_in_these_fictional_universes ⭢ work_of_fiction.setting ⭢ location_in_fiction.universe | literary_series.fictional_universe ⭢ work_of_fiction.setting ⭢ location_in_fiction.contained_by ⭢ administrative_area.administrative_parent | literary_series.fictional_universe ⭢ work_of_fiction.setting ⭢ location_in_fiction.contained_by ⭢ location_in_fiction.contains | literary_series.fictional_universe ⭢ work_of_fiction.setting ⭢ fictional_object.location ⭢ location_in_fiction.universe | fictional_character.appears_in_these_fictional_universes ⭢ work_of_fiction.setting ⭢ location_in_fiction.contained_by ⭢ administrative_area.administrative_parent | administrative_area.administrative_parent | location_in_fiction.contains | location_in_fiction.universe | government_position_held.district_represented | location.containedby | location.contains | location.partially_containedby | location.partiallycontains
── Tempus Unbound ──
    Faun --fictional_character.appears_in_these_fictional_universes--> Tempus Unbound
    The Sacred Band --literary_series.fictional_universe--> Tempus Unbound
── Kansas ──
    --administrative_area.administrative_parent--> United States of America
    --location.containedby--> Contiguous United States | Midwestern United States | West North Central States
    --location.contains--> g.120_f_8w | g.120_rrtl | g.120jr2z0 | g.120kh6kk
    --location.partiallycontains--> m.0wg90t8 [partially_contains: Missouri River] | m.0wg90tf [partially_contains: Arkansas River] | m.0wg90tm [partially_contains: Republican River] | m.0wg90ts [partially_contains: Smoky Hill River] | m.0wg90ty [partially_contains: Cimarron River] | m.0wg90v2 [partially_contains: Ozarks] | m.0wg90vm [partially_contains: Marais des Cygnes River] | m.0wg90w4 [partially_contains: Marmaton River] | m.0wg90wp [partially_contains: Verdigris River] | m.0wg90ww [partially_contains: Spring River] | m.0wg90x0 [partially_contains: Salt Fork Arkansas River] | m.0wg90x5 [partially_contains: Big Blue River] | m.0wg90xb [partially_contains: Blue River] | m.0wg90xh [partially_contains: Little Osage River] | m.0wg90xn [partially_contains: Arikaree River] | m.0wjpmb0 [partially_contains: Neosho River]
    Chautauqua County | Cheyenne County | Clark County | Clay County | Cloud County | Coffey County | Comanche County | Crawford County | Decatur County | Dickinson County | Doniphan County | Douglas County …(+60) (to answer with ALL of them, include "#Chautauqua County::administrative_parent" as one answer entity) --administrative_area.administrative_parent--> Kansas
    Atchison County | Elwood | Kansas City | Kansas River | Leavenworth | Topeka --location.containedby--> Kansas
    m.010d12r0 | m.05kdhfp | m.05kgzyh | m.0gm5dzf --government_position_held.district_represented--> Kansas
    Arikaree River | Arkansas River | Big Blue River | Blue River | Cimarron River | Little Osage River | Marais des Cygnes River | Marmaton River | Missouri River | Neosho River | Ozarks | Republican River …(+5) (to answer with ALL of them, include "#Arikaree River::partially_containedby" as one answer entity) --location.partially_containedby--> Kansas
── Long Island ──
    --location.containedby--> New York | United States of America
    --location.contains--> Matty T's Roadhouse | Shinnecock Light
    Amityville | Babylon | Baldwin | Bay Shore | Bellmore | Bethpage | Dix 
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Missouri River  |  relations: location.location.partially_contains | location.location.partially_contained_by
旧: 模式 10 · 证据块 10 · 6149 字符
新: 模式 19 · 证据块 10 · 6577 字符

【旧渲染】
```
triples:
entities: Missouri River
▸ patterns: location.partially_contained_by | location.partially_contains | river.basin_countries ⭢ location.partially_contains | river.mouth ⭢ location.partially_contained_by | river.mouth ⭢ location.partially_contains | location.partially_containedby ⭢ location.partially_contains | location.partially_contains ⭢ location.partially_contains | partial_containment_relationship.partially_contains ⭢ location.partially_contained_by | river.basin_countries ⭢ location.containedby ⭢ location.partially_contained_by | river.mouth ⭢ river.origin ⭢ location.partially_contained_by
── Missouri River ──
    --river.basin_countries--> United States of America
    --river.mouth--> Mississippi River
    --location.partially_contained_by--> m.0wg900g | m.0wg906w | m.0wg90jv | m.0wg90lw | m.0wg90p7 | m.0wg90rv | m.0wg90t8
    --location.partially_containedby--> Kansas | South Dakota
    Big Sioux River | Blue River | Grand River | James River | Kansas River | Little Missouri River | Platte River | White River | Yellowstone River --river.mouth--> Missouri River
    Iowa | Kansas | Missouri | Montana | Nebraska | North Dakota | South Dakota | m.0wg900g | m.0wg906w | m.0wg90jv | m.0wg90lw | m.0wg90p7 …(+2) --location.partially_contains--> Missouri River
── Mississippi River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg9009 | m.0wg906q
    Arkansas | Illinois | Iowa | Kentucky | Louisiana | Minnesota | Mississippi | Missouri | Tennessee | Wisconsin --location.partially_contains--> Mississippi River
── Blue River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90xb
    Kansas --location.partially_contains--> Blue River
    Missouri --location.partially_contains--> Blue River
── Arikaree River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90xn
    Kansas --location.partially_contains--> Arikaree River
    Nebraska --location.partially_contains--> Arikaree River
── Big Blue River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90x5
    Kansas --location.partially_contains--> Big Blue River
    Nebraska --location.partially_contains--> Big Blue River
── Little Osage River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90xh
    Kansas --location.partially_contains--> Little Osage River
    Missouri --location.partially_contains--> Little Osage River
── Marais des Cygnes River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90vm
    Kansas --location.partially_contains--> Marais des Cygnes River
    Missouri --location.partially_contains--> Marais des Cygnes River
── Arkansas River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90tf
    Kansas --location.partially_contains--> Arkansas River
── Cimarron River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90ty
    Kansas --location.partially_contains--> Cimarron River
── Marmaton River ──
    --location.containedby--> United States of America
    --location.partially_contained_by--> m.0wg90w4
    Missouri --location.partially_contains--> Marmaton River
    Iowa --location.partially_contains--> Big Sioux River | Grand River | Platte River
    Kansas --location.partially_contains--> Kansas River | Neosho River | Ozarks
    Missouri --location.partially_contains--> Chariton River | Des Moines River | Grand River | Nishnabotna River | Ozarks | Platte River
    Montana --location.partially_contains--> Little Missouri River | Yellowstone River
    Nebraska --location.partially_contains--> White River
    Neosho River --location.containedby--> United States of America
    North America --location.partially_contains--> United States o
```
【新渲染】
```
triples:
entities: Missouri River
▸ patterns: river.mouth | location.containedby | location.partially_contained_by | location.partially_containedby | location.partially_contains | river.basin_countries ⭢ location.partially_containedby | river.basin_countries ⭢ location.partially_contains | river.cities ⭢ location.containedby | river.mouth ⭢ location.containedby | river.mouth ⭢ location.partially_contained_by | river.mouth ⭢ location.partially_containedby | river.mouth ⭢ location.partially_contains | river.origin ⭢ location.containedby | topic.notable_types ⭢ geographical_feature.category ⭢ river.mouth | topic.notable_types ⭢ geographical_feature.category ⭢ location.partially_contained_by | location.partially_contained_by ⭢ location.partiallycontains ⭢ location.partially_contains | location.partially_contained_by ⭢ partial_containment_relationship.partially_contained_by ⭢ location.partially_contains | partial_containment_relationship.partially_contains ⭢ location.partiallycontains ⭢ location.partially_containedby | partial_containment_relationship.partially_contains ⭢ partial_containment_relationship.partially_contained_by ⭢ location.partially_containedby
── Missouri River ──
    --river.basin_countries--> United States of America
    --river.cities--> Great Falls
    --location.containedby--> North America | United States of America
    --river.mouth--> Mississippi River
    --topic.notable_types--> River
    --river.origin--> Brower's Spring
    --location.partially_contained_by--> m.0wg900g | m.0wg906w | m.0wg90jv | m.0wg90lw | m.0wg90p7 | m.0wg90rv | m.0wg90t8
    --location.partially_containedby--> Iowa | Kansas | Missouri | Montana | Nebraska | North Dakota | South Dakota
    Big Sioux River | Blue River | Grand River | James River | Kansas River | Little Missouri River | Platte River | White River | Yellowstone River --river.mouth--> Missouri River
    Iowa | Kansas | Missouri | Montana | Nebraska | North Dakota | South Dakota | m.0wg900g | m.0wg906w | m.0wg90jv | m.0wg90lw | m.0wg90rv …(+1) (to answer with ALL of them, include "#Iowa::partially_contains" as one answer entity) --location.partially_contains--> Missouri River
── Mississippi River ──
    --geographical_feature.category--> River
    --location.partially_contained_by--> m.0wg9009 | m.0wg906q
    --location.partially_containedby--> Arkansas | Illinois | Iowa | Kentucky | Louisiana | Minnesota | Mississippi | Tennessee | Wisconsin
    Lower Mississippi River --location.containedby--> Mississippi River
    Arkansas River --river.mouth--> Mississippi River
    Des Moines River --river.mouth--> Mississippi River
    Arkansas | Illinois | Iowa | Kentucky | Louisiana | Minnesota | Mississippi | Tennessee | Wisconsin --location.partially_contains--> Mississippi River
── Blue River ──
    --location.partially_contained_by--> m.0wg90xb
    --location.partially_containedby--> Kansas | Missouri
    Kansas --location.partially_contains--> Blue River
    Missouri --location.partially_contains--> Blue River
── Kansas ──
    --location.partially_contains--> Arikaree River | Arkansas River | Big Blue River | Cimarron River | Kansas River | Little Osage River | Marais des Cygnes River | Marmaton River | Neosho River | Ozarks | Republican River | Salt Fork Arkansas River | Smoky Hill River | Solomon River | Spring River | Verdigris River
    --location.partiallycontains--> m.0wg90t8
    Kansas River --location.containedby--> Kansas
    Arikaree River | Arkansas River | Big Blue River | Cimarron River | Kansas River | Little Osage River | Marais des Cygnes River | Marmaton River | Neosho River | Ozarks | Republican River | Salt Fork Arkansas River …(+4) (to answer with ALL of them, include "#Arikaree River::partially_containedby" as one answer entity) --location.partially_containedby--> Kansas
── Iowa ──
    --location.partially_contains--> Big Sioux River | Chariton River | Des Moines River | Grand River | Nishnabotna River | Platte River
    m.0wg906w --partial_containment_rel
```


============================================================================================
## CASE WebQTrn-1731_4eea981607dbe17b040580ce4cd93ec4 s0
Q: What did Randy Jackson play in the Eclipse Tour?  f1=1.0
sg 调用数: 旧 4 / 新 4

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Randy Jackson  |  relations: artist.concert_tours
旧: 模式 0 · 证据块 0 · 1107 字符
新: 模式 8 · 证据块 5 · 2575 字符

【旧渲染】
```
triples: (empty)
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'artist.concert_tours': {'direct': ['music.artist.concert_tours'], 'bridge': ['music.group_member.membership', 'music.group_membership.member']}}
```
【新渲染】
```
triples:
entities: Randy Jackson
▸ patterns: group_member.membership | group_membership.member | composer.compositions ⭢ composition.composer ⭢ group_member.membership | composer.compositions ⭢ composition.composer ⭢ group_membership.member | group_member.membership ⭢ musical_group.member ⭢ artist.concert_tours | group_membership.member ⭢ group_membership.group ⭢ artist.concert_tours | group_membership.member ⭢ group_membership.role ⭢ group_member.instruments_played ⭢ group_member.membership | track_contribution.contributor ⭢ track_contribution.role ⭢ group_member.instruments_played ⭢ group_membership.member
── Randy Jackson ──
    --composer.compositions--> Too Much Ain't Enough Love
    --group_member.membership--> g.11b6btynmz | m.01vxjq8 [end: 1987-08:00; group: Journey; role: Bass guitar | Vocals; start: 1985-08:00] | m.01vxjqg [group: Verdine White & Randy Jackson] | m.040rysf [group: Breakfast Club; has_value: Period (end) | Period (start); role: Bass guitar] | m.043dm0_ [group: Methods of Mayhem] | m.0ggf17l [group: The Sign]
    m.010n9k6l --track_contribution.contributor--> Randy Jackson
    m.01vxjq8 | m.01vxjqg | m.040rysf | m.043dm0_ | m.0ggf17l --group_membership.member--> Randy Jackson
── Jonathan Cain ──
    --group_member.instruments_played--> Bass guitar
    --group_member.membership--> g.11b6bwf1m9 | m.01tz9k6 [group: Journey; has_no_value: Period (end); role: Guitar | Keyboard]
    Too Much Ain't Enough Love --composition.composer--> Jonathan Cain
    m.01tz9k6 --group_membership.member--> Jonathan Cain
── Neal Schon ──
    --group_member.membership--> g.11b6bfd9cl | m.01tf0q1 [group: Journey; has_no_value: Period (end); role: Vocals]
    Too Much Ain't Enough Love --composition.composer--> Neal Schon
    m.01tf0q1 --group_membership.member--> Neal Schon
── Journey ──
    --artist.concert_tours--> Eclipse Tour | Escape Tour | Frontiers Tour | Raised on Radio Tour | Revelation Tour
    --musical_group.member--> g.11b6btynmz
    m.01vxjq8 --group_membership.group--> Journey
── Bass guitar ──
    m.010n9k6l --track_contribution.role--> Bass guitar
    m.01vxjq8 --group_membership.role--> Bass guitar
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'artist.concert_tours': {'direct': ['music.artist.concert_tours'], 'bridge': ['music.group_member.membership', 'music.group_membership.member']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Eclipse Tour  |  relations: artist.concert_tours | group_membership.group
旧: 模式 12 · 证据块 9 · 4410 字符
新: 模式 5 · 证据块 4 · 2409 字符

【旧渲染】
```
triples:
entities: Eclipse Tour
▸ patterns: artist.concert_tours | artist.concert_tours ⭢ artist.concert_tours | artist.concert_tours ⭢ group_membership.group | concert_tour.artist ⭢ artist.concert_tours | concert_tour.artist ⭢ group_membership.group | album.supporting_tours ⭢ album.artist ⭢ artist.concert_tours | album.supporting_tours ⭢ album.artist ⭢ group_membership.group | album.supporting_tours ⭢ artist.album ⭢ artist.concert_tours | album.supporting_tours ⭢ artist.album ⭢ group_membership.group | concert_tour.album_or_release_supporting ⭢ album.artist ⭢ group_membership.group | concert_tour.album_or_release_supporting ⭢ artist.album ⭢ group_membership.group | group_membership.group
── Eclipse Tour ──
    --concert_tour.album_or_release_supporting--> Eclipse
    --concert_tour.artist--> Journey
    Journey --artist.concert_tours--> Eclipse Tour
    Eclipse --album.supporting_tours--> Eclipse Tour
── Journey ──
    --artist.album--> Eclipse
    --artist.concert_tours--> Escape Tour | Frontiers Tour | Raised on Radio Tour | Revelation Tour
    --musical_group.member--> m.010j_yzn | m.010jvpfy | m.01tbtvb | m.01tf0q1 [has_no_value: Period (end); member: Neal Schon; role: Vocals] | m.01tz9k6 [has_no_value: Period (end); member: Jonathan Cain; role: Guitar | Keyboard] | m.01v_qs5 [role: Keyboard | Vocals] | m.01vxjq8 [end: 1987-08:00; member: Randy Jackson; role: Bass guitar | Vocals; start: 1985-08:00] | m.01wgt4x [has_no_value: Period (end); role: Vocals] | m.01whmnm | m.01wmlt1 [role: Guitar] | m.04hcpx3 | m.05nn6x0 [role: Bass guitar | Vocals] | m.05nn6xb [has_no_value: Period (end)] | m.0k_8v9l | m.0k_8v9s [role: Guitar] | m.0k_8vdf [has_no_value: Period (end); role: Bass guitar | Vocals] | m.0k_8vt5 | m.0k_8vtt [role: Keyboard | Vocals] | m.0k_8vv6 | m.0nktrkp | m.0w8hmsf | m.0w8jwhs | m.0wh5y9z
    Eclipse --album.artist--> Journey
    m.010j_yzn | m.010jvpfy | m.01tbtvb | m.01tf0q1 | m.01tz9k6 | m.01v_qs5 | m.01vxjq8 | m.01wgt4x | m.01whmnm | m.01wmlt1 | m.04hcpx3 | m.05nn6x0 …(+11) --group_membership.group--> Journey
── Vocals ──
    m.01tf0q1 | m.01v_qs5 | m.01vxjq8 | m.01wgt4x | m.05nn6x0 | m.0k_8vdf | m.0k_8vtt --group_membership.role--> Vocals
── Bass guitar ──
    m.01vxjq8 | m.05nn6x0 | m.0k_8vdf --group_membership.role--> Bass guitar
── Guitar ──
    m.01tz9k6 | m.01wmlt1 | m.0k_8v9s --group_membership.role--> Guitar
── Keyboard ──
    m.01tz9k6 | m.01v_qs5 | m.0k_8vtt --group_membership.role--> Keyboard
── Jonathan Cain ──
    --group_member.membership--> m.01tz9k6 [has_no_value: Period (end); member: Jonathan Cain; role: Guitar | Keyboard]
    m.01tz9k6 --group_membership.member--> Jonathan Cain
── Neal Schon ──
    --group_member.membership--> m.01tf0q1 [has_no_value: Period (end); member: Neal Schon; role: Vocals]
    m.01tf0q1 --group_membership.member--> Neal Schon
── Randy Jackson ──
    --group_member.membership--> m.01vxjq8 [end: 1987-08:00; member: Randy Jackson; role: Bass guitar | Vocals; start: 1985-08:00]
    m.01vxjq8 --group_membership.member--> Randy Jackson
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph show
```
【新渲染】
```
triples:
entities: Randy Jackson  (sequence root; this layer applies to the frontier: Eclipse Tour)
▸ patterns: group_membership.member ⭢ group_membership.group | group_membership.member ⭢ group_membership.group ⭢ concert_tour.artist | group_membership.member ⭢ musical_group.member ⭢ concert_tour.artist | artist.concert_tours | group_member.membership ⭢ musical_group.member ⭢ musical_group.member
── Randy Jackson ──
    --group_member.membership--> g.11b6btynmz
    m.01vxjq8 | m.040rysf | m.043dm0_ --group_membership.member--> Randy Jackson
── Journey ──
    --artist.concert_tours--> Eclipse Tour
    --musical_group.member--> m.01vxjq8 [end: 1987-08:00; role: Bass guitar | Vocals; start: 1985-08:00] | g.11b6btynmz | m.010j_yzn | m.010jvpfy | m.01tbtvb | m.01tf0q1 [has_no_value: Period (end); role: Vocals] | m.01tz9k6 [has_no_value: Period (end); role: Guitar | Keyboard] | m.01v_qs5 [role: Keyboard | Vocals] | m.01wgt4x [has_no_value: Period (end); role: Vocals] | m.01whmnm | m.01wmlt1 [role: Guitar] | m.04hcpx3 | m.05nn6x0 [role: Bass guitar | Vocals] | m.05nn6xb [has_no_value: Period (end)] | m.0k_8v9l | m.0k_8v9s [role: Guitar] | m.0k_8vdf [has_no_value: Period (end); role: Bass guitar | Vocals] | m.0k_8vt5 | m.0k_8vtt [role: Keyboard | Vocals] | m.0k_8vv6 | m.0nktrkp | m.0w8hmsf | m.0w8jwhs | m.0wh5y9z
    Eclipse Tour --concert_tour.artist--> Journey
    Raised on Radio Tour --concert_tour.artist--> Journey
    m.01vxjq8 --group_membership.group--> Journey
── Breakfast Club ──
    m.040rysf --group_membership.group--> Breakfast Club
── Methods of Mayhem ──
    m.043dm0_ --group_membership.group--> Methods of Mayhem
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'artist.concert_tours': {'direct': ['music.artist.concert_tours'], 'bridge': ['music.concert_tour.artist']}, 'group_membership.group': {'direct': ['music.group_membership.group'], 'bridge': ['music.concert_tour.artist']}}
anchor_sequence: Randy Jackson ⭢ 2-step chain (frontier: Eclipse Tour)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Randy Jackson  |  relations: group_member.instruments_played | instrument.instrumentalists
旧: 模式 6 · 证据块 6 · 3703 字符
新: 模式 15 · 证据块 5 · 3542 字符

【旧渲染】
```
triples:
entities: Randy Jackson
▸ patterns: group_member.instruments_played | group_member.instruments_played ⭢ group_member.instruments_played | group_member.instruments_played ⭢ instrument.instrumentalists | group_membership.member ⭢ group_membership.role ⭢ group_member.instruments_played | group_membership.member ⭢ group_membership.role ⭢ instrument.instrumentalists | instrument.instrumentalists
── Randy Jackson ──
    --group_member.instruments_played--> Bass guitar | Keyboard
    --group_member.membership--> m.01vxjq8 [end: 1987-08:00; group: Journey; start: 1985-08:00] | m.040rysf [group: Breakfast Club; has_value: Period (end) | Period (start)]
    m.01vxjq8 --group_membership.member--> Randy Jackson
    m.040rysf --group_membership.member--> Randy Jackson
── Vocals ──
    --instrument.instrumentalists--> Benjamin Booker | James Swaim | Mitali Mukherjee | Stephen Melton | g.11ksgk_85 | g.12hhgp2nt
    Stephen Melton --group_member.instruments_played--> Vocals
    m.01vxjq8 --group_membership.role--> Vocals
── Bass guitar ──
    --instrument.instrumentalists--> Gunnar H. Thomsen | Yu~ki | g.121qgg1g
    Paul Lee --group_member.instruments_played--> Bass guitar
    m.01vxjq8 --group_membership.role--> Bass guitar
    m.040rysf --group_membership.role--> Bass guitar
── Breakfast Club ──
    --musical_group.member--> m.040rysf [group: Breakfast Club; has_value: Period (end) | Period (start)]
    m.040rysf --group_membership.group--> Breakfast Club
── Journey ──
    --musical_group.member--> m.01vxjq8 [end: 1987-08:00; group: Journey; start: 1985-08:00]
    m.01vxjq8 --group_membership.group--> Journey
── Keyboard ──
    Jonathan Cain --group_member.instruments_played--> Keyboard
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'group_member.instruments_played': {'direct': ['music.group_member.instruments_played'], 'bridge': ['common.topic.image', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor']}, 'instrument.instrumentalists': {'direct': ['music.instrument.instrumentalists'], 'bridge': ['music.group_member.instruments_played', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor']}}
anchor_sequence: Randy Jackson ⭢ artist.concert_tours | group_member.instruments_played (0)
layer_action: extend
```
【新渲染】
```
triples:
entities: Randy Jackson
▸ patterns: topic.image | group_member.instruments_played | track_contribution.contributor | artist.origin ⭢ topic.image | group_member.instruments_played ⭢ topic.image | group_member.instruments_played ⭢ instrument.instrumentalists | producer.releases_produced ⭢ topic.image | group_member.membership ⭢ group_membership.role ⭢ group_member.instruments_played | group_membership.member ⭢ group_membership.role ⭢ group_member.instruments_played | group_membership.member ⭢ group_membership.role ⭢ instrument.instrumentalists | track_contribution.contributor ⭢ track_contribution.role ⭢ group_member.instruments_played | track_contribution.contributor ⭢ track_contribution.role ⭢ instrument.instrumentalists | album.artist ⭢ album.contributor | artist.album ⭢ album.contributor | producer.releases_produced ⭢ album.contributor
── Randy Jackson ──
    --artist.album--> Randy Jackson's Music Club, Vol. 1
    --topic.image--> Randyjacksonpic | jackson.jpg
    --group_member.instruments_played--> Bass guitar | Keyboard
    --group_member.membership--> m.01vxjq8 [end: 1987-08:00; group: Journey; start: 1985-08:00]
    --artist.origin--> Scarborough
    --producer.releases_produced--> Randy Jackson's Music Club, Vol. 1
    Randy Jackson's Music Club, Vol. 1 --album.artist--> Randy Jackson
    m.010mrzsl | m.010n9k6l | m.011wxrc3 --track_contribution.contributor--> Randy Jackson
    m.01vxjq8 --group_membership.member--> Randy Jackson
── Bass guitar ──
    --topic.image--> A Mexican Fender Jazz Bass (front and back views) | A sunburst-colored Fender Precision Bass | Martin EB18 Bass Guitar in flight case
    --instrument.instrumentalists--> Gunnar H. Thomsen | Yu~ki | g.121qgg1g
    Jonathan Cain --group_member.instruments_played--> Bass guitar
    Paul Lee --group_member.instruments_played--> Bass guitar
    m.010n9k6l --track_contribution.role--> Bass guitar
    m.01vxjq8 --group_membership.role--> Bass guitar
── Vocals ──
    --instrument.instrumentalists--> Benjamin Booker | James Swaim | Mitali Mukherjee | Stephen Melton | g.11ksgk_85 | g.12hhgp2nt
    Stephen Melton --group_member.instruments_played--> Vocals
    m.01vxjq8 --group_membership.role--> Vocals
── Randy Jackson's Music Club, Vol. 1 ──
    --album.contributor--> m.0vs6gwh | m.0vx57bm | m.0xncxj9
    --topic.image--> Randy Jackson's Music Club, Vol. 1 cover
── Scarborough ──
    --topic.image--> Location of Scarborough (red) compared to the rest of Toronto (yellow). | Scarborough locator
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'group_member.instruments_played': {'direct': ['music.group_member.instruments_played'], 'bridge': ['common.topic.image', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor']}, 'instrument.instrumentalists': {'direct': ['music.instrument.instrumentalists'], 'bridge': ['music.group_member.instruments_played', 'music.group_member.membership', 'music.group_membership.member', 'music.track_contribution.contributor']}}
anchor_sequence: Randy Jackson ⭢ 1-step chain
layer_action: update layer 1 (replaced music.artist.concert_tours)
```

--------------------------------------------------------------------------------------------
### 块 #3 调用: center: Eclipse Tour  |  relations: artist.track | performance_role.guest_performances | featured_artist.recordings | album.supporting_tours
旧: 模式 7 · 证据块 4 · 2979 字符
新: 模式 6 · 证据块 3 · 1305 字符

【旧渲染】
```
triples:
entities: Eclipse Tour  (sequence root; this layer applies to the frontier: Journey)
▸ patterns: album.supporting_tours | album.artist ⭢ album.supporting_tours | artist.album ⭢ album.supporting_tours | artist.genre ⭢ album.genre ⭢ album.supporting_tours | featured_artist.recordings | artist.concert_tours ⭢ album.supporting_tours | concert_tour.artist ⭢ album.supporting_tours
── Eclipse Tour ──
    --concert_tour.artist--> Journey
    Journey --artist.concert_tours--> Eclipse Tour
    Eclipse --album.supporting_tours--> Eclipse Tour
── Journey ──
    --artist.album--> Eclipse | Raised on Radio
    --artist.concert_tours--> Raised on Radio Tour
    --artist.genre--> Hard rock | Rock music
    --featured_artist.recordings--> Going Down Alone
    Eclipse | Raised on Radio | Raised on Radio Tour --album.artist--> Journey
── Eclipse ──
    --album.genre--> Hard rock | Rock music
── Raised on Radio ──
    --album.genre--> Hard rock | Rock music
    --album.supporting_tours--> Raised on Radio Tour
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'artist.track': {'direct': ['artist.track'], 'bridge': []}, 'performance_role.guest_performances': {'direct': ['performance_role.guest_performances'], 'bridge': []}, 'featured_artist.recordings': {'direct': ['music.featured_artist.recordings'], 'bridge': ['music.concert_tour.artist']}, 'album.supporting_tours': {'direct': ['music.album.supporting_tours'], 'bridge': []}}
anchor_sequence: Eclipse Tour ⭢ album.supporting_tours | featured_artist.recordings (1)
layer_action: update layer 1 (replaced music.artist.concert_tours, music.group_membership.group)
```
【新渲染】
```
triples:
entities: Eclipse Tour
▸ patterns: album.supporting_tours | concert_tour.artist | artist.concert_tours ⭢ featured_artist.recordings | concert_tour.artist ⭢ featured_artist.recordings | artist.concert_tours ⭢ artist.album ⭢ album.supporting_tours | concert_tour.artist ⭢ artist.album ⭢ album.supporting_tours
── Eclipse Tour ──
    --concert_tour.artist--> Journey
    Journey --artist.concert_tours--> Eclipse Tour
    Eclipse --album.supporting_tours--> Eclipse Tour
── Journey ──
    --artist.album--> Raised on Radio
    --featured_artist.recordings--> Going Down Alone
── Raised on Radio ──
    --album.supporting_tours--> Raised on Radio Tour
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'artist.track': {'direct': ['artist.track'], 'bridge': []}, 'performance_role.guest_performances': {'direct': ['performance_role.guest_performances'], 'bridge': []}, 'featured_artist.recordings': {'direct': ['music.featured_artist.recordings'], 'bridge': ['music.concert_tour.artist']}, 'album.supporting_tours': {'direct': ['music.album.supporting_tours'], 'bridge': []}}
```


============================================================================================
## CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a s0
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?  f1=1.0
sg 调用数: 旧 2 / 新 2

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Ethiopian birr  |  relations: location.country.currency_used | finance.currency.countries_used
旧: 模式 2 · 证据块 1 · 1332 字符
新: 模式 2 · 证据块 1 · 466 字符

【旧渲染】
```
triples:
entities: Ethiopian birr
▸ patterns: currency.countries_used | country.currency_used
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
    Ethiopia --country.currency_used--> Ethiopian birr
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
```
【新渲染】
```
triples:
entities: Ethiopian birr
▸ patterns: currency.countries_used | country.currency_used
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
    Ethiopia --country.currency_used--> Ethiopian birr
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Ethiopia  |  relations: government.politician.government_positions_held | government.government.government_for
旧: 模式 11 · 证据块 6 · 4518 字符
新: 模式 6 · 证据块 2 · 2634 字符

【旧渲染】
```
triples:
entities: Ethiopian birr  (sequence root; this layer applies to the frontier: Ethiopia)
▸ patterns: currency.countries_used ⭢ government.government_for | country.currency_used ⭢ government.government_for | government.government_for | politician.government_positions_held | government_position_held.jurisdiction_of_office ⭢ politician.government_positions_held | governmental_jurisdiction.governing_officials ⭢ politician.government_positions_held | person.nationality ⭢ politician.government_positions_held | kingdom.rulers ⭢ politician.government_positions_held | monarch.kingdom ⭢ politician.government_positions_held | location.events ⭢ event.entity_involved ⭢ politician.government_positions_held | event.locations ⭢ event.entity_involved ⭢ politician.government_positions_held
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
    Ethiopia --country.currency_used--> Ethiopian birr
── Haile Selassie ──
    --politician.government_positions_held--> m.010pzwzw [jurisdiction_of_office: Ethiopia]
    --monarch.kingdom--> Ethiopia
    --person.nationality--> Ethiopia
    East African Campaign | Eritrean War of Independence | Second Italo-Ethiopian War --event.entity_involved--> Haile Selassie
    m.010pzwzw --government_position_held.office_holder--> Haile Selassie
    Ethiopia --kingdom.rulers--> Haile Selassie
── Hailemariam Desalegn ──
    --politician.government_positions_held--> m.0l0j4x3 [jurisdiction_of_office: Ethiopia] | m.0n1nqyj [basic_title: Prime minister; from: 2012-09-21-08:00; has_no_value: To; jurisdiction_of_office: Ethiopia; office_position_or_title: Prime Minister of Ethiopia]
    --person.nationality--> Ethiopia
    m.0n1nqyj --government_position_held.office_holder--> Hailemariam Desalegn
── Ethiopia ──
    --location.events--> East African Campaign | Eritrean War of Independence | Second Italo-Ethiopian War
    --governmental_jurisdiction.governing_officials--> m.010pzwzw [jurisdiction_of_office: Ethiopia] | m.0l0j4x3 [jurisdiction_of_office: Ethiopia] | m.0n1nqyj [basic_title: Prime minister; from: 2012-09-21-08:00; has_no_value: To; jurisdiction_of_office: Ethiopia; office_position_or_title: Prime Minister of Ethiopia]
    Government of Ethiopia --government.government_for--> Ethiopia
    m.010pzwzw | m.0l0j4x3 | m.0n1nqyj --government_position_held.jurisdiction_of_office--> Ethiopia
    East African Campaign | Eritrean War of Independence | Second Italo-Ethiopian War --event.locations--> Ethiopia
── 2012-09-21-08:00 ──
    m.0n1nqyj --government_position_held.from--> 2012-09-21-08:00
── Prime Minister of Ethiopia ──
    m.0n1nqyj --government_position_held.office_position_or_title--> Prime Minister of Ethiopia
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across
```
【新渲染】
```
triples:
entities: Ethiopian birr  (sequence root; this layer applies to the frontier: Ethiopia)
▸ patterns: currency.countries_used ⭢ government.government_for | currency.countries_used ⭢ government_position_held.jurisdiction_of_office | currency.countries_used ⭢ governmental_jurisdiction.governing_officials | government.government_for | government_position_held.jurisdiction_of_office | person.nationality
── Ethiopian birr ──
    --currency.countries_used--> Ethiopia
── Ethiopia ──
    --governmental_jurisdiction.governing_officials--> m.010g4d59 | m.010g4dpz | m.010g4fwg | m.010g4gn8 [basic_title: Prime minister] | m.010g4h86 | m.010g4hmc [basic_title: Prime minister] | m.010g4j4k [basic_title: Prime minister] | m.010g5f9p [basic_title: Prime minister] | m.010g5q86 [basic_title: Prime minister] | m.010pzwzw [office_holder: Haile Selassie] | m.0clv82n [basic_title: Prime minister] | m.0j5r5mg | m.0kmspfs [governmental_body: House of Peoples' Representatives] | m.0l0j1hv | m.0l0j4x3 | m.0n1nqyj [basic_title: Prime minister; from: 2012-09-21-08:00; has_no_value: To; office_holder: Hailemariam Desalegn; office_position_or_title: Prime Minister of Ethiopia] | m.0r47zs7 | m.0wzwgtk [governmental_body: House of Peoples' Representatives] | m.0y4w972
    Government of Ethiopia --government.government_for--> Ethiopia
    m.010g4d59 | m.010g4dpz | m.010g4fwg | m.010g4gn8 | m.010g4h86 | m.010g4hmc | m.010g4j4k | m.010g5f9p | m.010g5q86 | m.010pzwzw | m.0clv82n | m.0j5r5mg …(+7) (to answer with ALL of them, include "#m.010g4d59::jurisdiction_of_office" as one answer entity) --government_position_held.jurisdiction_of_office--> Ethiopia
    Baeda Maryam I | Demetros | Gebre Krestos | Gigar | Haile Selassie | Hailemariam Desalegn | Tekle Giyorgis I | Tekle Haymanot II --person.nationality--> Ethiopia
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'government.politician.government_positions_held': {'direct': ['government.politician.government_positions_held'], 'bridge': ['government.government_position_held.jurisdiction_of_office', 'government.governmental_jurisdiction.governing_officials', 'people.person.nationality']}}
anchor_sequence: Ethiopian birr ⭢ 2-step chain (frontier: Ethiopia)
layer_action: extend
```


============================================================================================
## CASE WebQTrn-2209_c1374f388d9cc7a78365860c91218362 s0
Q: What year did the basketball team coached by Brad Stevens win the championship?  f1=0.111
sg 调用数: 旧 2 / 新 2

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Brad Stevens  |  relations: basketball.basketball_team.head_coach | sports.sports_team.coaches | sports.sports_team_coach.teams_coached
旧: 模式 13 · 证据块 7 · 4604 字符
新: 模式 16 · 证据块 4 · 3413 字符

【旧渲染】
```
triples:
entities: Brad Stevens
▸ patterns: basketball_team.head_coach | sports_team_coach.teams_coached | basketball_coach.team ⭢ sports_team.coaches | basketball_team.head_coach ⭢ sports_team.coaches | sports_team_coach.teams_coached ⭢ sports_team.coaches | sports_team_coach_tenure.coach ⭢ sports_team.coaches | sports_team_coach_tenure.coach ⭢ sports_team_coach.teams_coached | basketball_coach.previous_teams ⭢ basketball_historical_coach_position.team ⭢ basketball_team.head_coach | basketball_coach.previous_teams ⭢ basketball_historical_coach_position.team ⭢ sports_team.coaches | topic.notable_types ⭢ person.profession ⭢ sports_team_coach.teams_coached | sport.team_coaches ⭢ sports_team_coach.sports_coached ⭢ sports_team_coach.teams_coached | sports_team_coach.sports_coached ⭢ sport.team_coaches ⭢ sports_team_coach.teams_coached | sports_team.coaches
── Brad Stevens ──
    --topic.notable_types--> Basketball Coach
    --basketball_coach.previous_teams--> m.0wfd2k7
    --sports_team_coach.sports_coached--> Basketball
    --basketball_coach.team--> Boston Celtics
    --sports_team_coach.teams_coached--> m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics] | m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball] | m.0w4828t [position: Head coach; team: Butler Bulldogs men's basketball]
    m.0w3_qv3 | m.0w48285 | m.0w4828t | m.0wfd2k7 --sports_team_coach_tenure.coach--> Brad Stevens
    Boston Celtics --basketball_team.head_coach--> Brad Stevens
    Basketball --sport.team_coaches--> Brad Stevens
── Boston Celtics ──
    --sports_team.coaches--> m.0w1g5hx [position: Coach] | m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics]
    m.0w1g5hx --sports_team_coach_tenure.team--> Boston Celtics
    m.0w3_qv3 --sports_team_coach_tenure.team--> Boston Celtics
── Geno Auriemma ──
    --person.profession--> Basketball Coach
    --sports_team_coach.sports_coached--> Basketball
    --sports_team_coach.teams_coached--> m.0y98dfs [has_no_value: To; position: Basketball Coach]
    Basketball --sport.team_coaches--> Geno Auriemma
── Butler Bulldogs men's basketball ──
    --sports_team.coaches--> m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball] | m.0w4828t [position: Head coach; team: Butler Bulldogs men's basketball]
    --basketball_team.head_coach--> Brandon Miller
    --basketball_team.previous_coaches--> m.0wfd2k7
    m.0w48285 | m.0w4828t | m.0wfd2k7 --basketball_historical_coach_position.team--> Butler Bulldogs men's basketball
── Assistant Coach ──
    --coaching_position.coaches--> m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball]
    m.0w48285 --sports_team_coach_tenure.position--> Assistant Coach
── Head coach ──
    m.0w3_qv3 --sports_team_coach_tenure.position--> Head coach
    m.0w4828t --sports_team_coach_tenure.position--> Head coach
── Coach ──
    m.0w1g5hx --sports_team_coach_tenure.position--> Coach
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately
```
【新渲染】
```
triples:
entities: Brad Stevens
▸ patterns: basketball_coach.previous_teams | basketball_coach.team | basketball_team.head_coach | sports_team_coach.teams_coached | basketball_coach.team ⭢ sports_team.coaches | basketball_team.head_coach ⭢ sports_team.coaches | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ basketball_coach.team | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ basketball_team.head_coach | basketball_historical_coach_position.coach ⭢ basketball_historical_coach_position.team ⭢ sports_team.coaches | topic.notable_types ⭢ person.profession ⭢ sports_team_coach.teams_coached | sport.team_coaches ⭢ sports_team_coach.sports_coached ⭢ sports_team_coach.teams_coached | sports_team_coach.teams_coached ⭢ sports_team_coach_tenure.team ⭢ basketball_coach.team | sports_team_coach.teams_coached ⭢ sports_team_coach_tenure.team ⭢ basketball_team.head_coach | sports_team_coach_tenure.coach ⭢ sports_team_coach_tenure.team ⭢ basketball_coach.team | sports_team_coach_tenure.coach ⭢ sports_team_coach_tenure.team ⭢ basketball_team.head_coach | basketball_historical_coach_position.coach
── Brad Stevens ──
    --topic.notable_types--> Basketball Coach
    --basketball_coach.previous_teams--> m.0wfd2k7 [team: Butler Bulldogs men's basketball]
    --basketball_coach.team--> Boston Celtics
    --sports_team_coach.teams_coached--> m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics] | m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball] | m.0w4828t [position: Head coach; team: Butler Bulldogs men's basketball]
    m.0w48285 --sports_team_coach_tenure.coach--> Brad Stevens
    m.0wfd2k7 --basketball_historical_coach_position.coach--> Brad Stevens
    Boston Celtics --basketball_team.head_coach--> Brad Stevens
    Basketball --sport.team_coaches--> Brad Stevens
── Boston Celtics ──
    --sports_team.coaches--> m.0w1g5hx [position: Coach] | m.0w3_qv3 [has_no_value: To; position: Head coach; team: Boston Celtics]
── Geno Auriemma ──
    --person.profession--> Basketball Coach
    --sports_team_coach.sports_coached--> Basketball
    --sports_team_coach.teams_coached--> m.0y98dfs [has_no_value: To; position: Basketball Coach]
── Butler Bulldogs men's basketball ──
    --sports_team.coaches--> m.0w48285 [position: Assistant Coach; team: Butler Bulldogs men's basketball] | m.0w4828t [position: Head coach; team: Butler Bulldogs men's basketball]
    --basketball_team.head_coach--> Brandon Miller
    Brandon Miller | m.0w48285 | m.0wfd2k7 --basketball_coach.team--> Butler Bulldogs men's basketball
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'basketball.basketball_team.head_coach': {'direct': ['basketball.basketball_team.head_coach'], 'bridge': ['basketball.basketball_coach.previous_teams', 'sports.sports_team_coach.teams_coached', 'sports.sports_team_coach_tenure.coach']}, 'sports.sports_team.coaches': {'direct': ['sports.sports_team.coaches'], 'bridge': ['basketball.basketball_coach.previous_teams', 'basketball.basketball_coach.team', 'sports.sports_team_coach.teams_coached', 'sports.sports_team_coach_tenure.coach']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Boston Celtics | Butler Bulldogs men's basketball  |  relations: sports.sports_team.championships | sports.sports_championship_event.champion
旧: 模式 4 · 证据块 2 · 3082 字符
新: 模式 1 · 证据块 1 · 1282 字符

【旧渲染】
```
triples:
entities: Brad Stevens  (sequence root; this layer applies to the frontier: Assistant Coach | Boston Celtics | Butler Bulldogs men's basketball | Head coach | To)
▸ patterns: basketball_team.head_coach ⭢ sports_championship_event.champion | basketball_team.head_coach ⭢ sports_team.championships | sports_championship_event.champion | sports_team.championships
── Brad Stevens ──
    --basketball_coach.previous_teams--> m.0wfd2k7
    Boston Celtics --basketball_team.head_coach--> Brad Stevens
── Boston Celtics ──
    --sports_team.championships--> 1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals | 1976 NBA Finals | 1981 NBA Finals | 1984 NBA Finals | 1986 NBA Finals | 2008 NBA Finals
    1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals …(+5) --sports_championship_event.champion--> Boston Celtics
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'Boston Celtics' narrows the relation pool to just that entity's edges — ?team has 2 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?team or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
anchor_sequence: Brad Stevens ⭢ basketball_team.head_coach | sports_team.coaches | sports_team_coach.teams_coached (5) ⭢ sports_championship_event.champion | sports_team.championships (0)
layer_action: extend
```
【新渲染】
```
triples:
entities: Brad Stevens  (sequence root; this layer applies to the frontier: Boston Celtics | Butler Bulldogs men's basketball)
▸ patterns: sports_championship_event.champion
── Boston Celtics ──
    1957 NBA Finals | 1959 NBA Finals | 1960 NBA Finals | 1961 NBA Finals | 1962 NBA Finals | 1963 NBA Finals | 1964 NBA Finals | 1965 NBA Finals | 1966 NBA Finals | 1968 NBA Finals | 1969 NBA Finals | 1974 NBA Finals …(+5) (to answer with ALL of them, include "#1957 NBA Finals::champion" as one answer entity) --sports_championship_event.champion--> Boston Celtics
note: ⚠ 'Boston Celtics' is 1 of ?team's 2 candidates — pass ?team or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
anchor_sequence: Brad Stevens ⭢ 2-step chain (frontier: Boston Celtics | Butler Bulldogs men's basketball)
layer_action: extend
```


============================================================================================
## CASE WebQTrn-2576_872253e47dd6ddaa213ff31eeda8783b s0
Q: What continent is the country in the Eastern Time Zone that Falkland Island belong to located in?  f1=0.0
sg 调用数: 旧 3 / 新 3

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Falkland Islands  |  relations: location.location.containedby | base.aareas.schema.earth.sovereign_domain.sovereign_state | base.aareas.schema.administ
旧: 模式 18 · 证据块 6 · 5521 字符
新: 模式 24 · 证据块 5 · 5737 字符

【旧渲染】
```
fact_id: sg1
triples:
entities: Falkland Islands
▸ patterns: location.containedby | administrative_area.administrative_area_type ⭢ administrative_area_type.sovereignty | administrative_area.administrative_children ⭢ administrative_area_type.sovereignty | administrative_area.administrative_children ⭢ sovereign_domain.sovereign_state | administrative_area.administrative_parent ⭢ location.containedby | island.island_group ⭢ location.containedby | island_group.islands_in_group ⭢ location.containedby | administrative_division.first_level_division_of ⭢ administrative_area_type.sovereignty | administrative_division.first_level_division_of ⭢ sovereign_domain.sovereign_state | administrative_division.first_level_division_of ⭢ location.containedby | country.first_level_divisions ⭢ administrative_area_type.sovereignty | country.first_level_divisions ⭢ sovereign_domain.sovereign_state | location.containedby ⭢ administrative_area_type.sovereignty | location.containedby ⭢ sovereign_domain.sovereign_state | location.containedby ⭢ location.containedby | location.contains ⭢ location.containedby | administrative_area_type.sovereignty | sovereign_domain.sovereign_state
── Falkland Islands ──
    --administrative_area.administrative_area_type--> UK overseas territory
    --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    --location.containedby--> Americas | Atlantic Ocean | Falkland Islands | South America | United Kingdom, with Dependencies and Territories
    --administrative_division.first_level_division_of--> United Kingdom, with Dependencies and Territories
    --island_group.islands_in_group--> East Falkland | New Island | South Georgia and the South Sandwich Islands | West Falkland
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> Falkland Islands
    East Falkland | New Island | Port Stanley Airport | Stanley | West Falkland --location.containedby--> Falkland Islands
    Americas --location.contains--> Falkland Islands
    Atlantic Ocean --location.contains--> Falkland Islands
    United Kingdom, with Dependencies and Territories --country.first_level_divisions--> Falkland Islands
    East Falkland | New Island | South Georgia and the South Sandwich Islands | West Falkland --island.island_group--> Falkland Islands
── Americas ──
    Anguilla | Antigua and Barbuda | Aruba | Bahamas | Barbados | Belize | Bermuda | Bonaire | British Virgin Islands | Canada | Caribbean | Cayman Islands …(+6) --location.containedby--> Americas
── United Kingdom, with Dependencies and Territories ──
    --sovereign_domain.sovereign_state--> United Kingdom
    British Antarctic Territory | British Indian Ocean Territory | Jersey | Pitcairn Islands | Saint Helena | Saint Helena, Ascension and Tristan da Cunha | South Georgia and the South Sandwich Islands | United Kingdom | Wales --location.containedby--> United Kingdom, with Dependencies and Territories
    UK crown dependency --administrative_area_type.sovereignty--> United Kingdom, with Dependencies and Territories
    UK overseas territory --administrative_area_type.sovereignty--> United Kingdom, with Dependencies and Territories
── Atlantic Ocean ──
    Bermuda | East Falkland | New Island | South Georgia and the South Sandwich Islands | West Falkland --location.containedby--> Atlantic Ocean
── East Falkland ──
    Stanley --location.containedby--> East Falkland
── South America ──
    Argentina | Bolivia | Brazil | Colombia --location.containedby--> South America
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUT
```
【新渲染】
```
fact_id: sg1
triples:
entities: Falkland Islands
▸ patterns: administrative_area.administrative_area_type | island_group.islands_in_group | government_position_held.jurisdiction_of_office | administrative_division.first_level_division_of | administrative_division_capital_relationship.administrative_division | location.containedby | location.contains | administrative_area.administrative_children ⭢ administrative_area_type.sovereignty | administrative_area.administrative_children ⭢ sovereign_domain.sovereign_state | island.island_group ⭢ administrative_area.administrative_area_type | island.island_group ⭢ administrative_division.first_level_division_of | island.island_group ⭢ location.containedby | island.island_group ⭢ location.contains | island_group.islands_in_group ⭢ administrative_area.administrative_area_type | island_group.islands_in_group ⭢ administrative_division.first_level_division_of | island_group.islands_in_group ⭢ location.containedby | island_group.islands_in_group ⭢ location.contains | country.first_level_divisions ⭢ administrative_area_type.sovereignty | country.first_level_divisions ⭢ sovereign_domain.sovereign_state | country.first_level_divisions ⭢ administrative_division.first_level_division_of | location.containedby ⭢ administrative_area.administrative_area_type | location.containedby ⭢ administrative_area_type.sovereignty | location.containedby ⭢ sovereign_domain.sovereign_state | government_position_held.jurisdiction_of_office ⭢ political_district.representatives ⭢ location.containedby
── Falkland Islands ──
    --administrative_area.administrative_area_type--> UK overseas territory
    --location.containedby--> Americas | Atlantic Ocean | South America | United Kingdom, with Dependencies and Territories
    --administrative_division.first_level_division_of--> United Kingdom, with Dependencies and Territories
    --island_group.islands_in_group--> East Falkland | Lively Island | New Island | Pebble Island | Saunders Island, Falkland Islands | South Georgia and the South Sandwich Islands | West Falkland
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> Falkland Islands
    m.0j_97ls --administrative_division_capital_relationship.administrative_division--> Falkland Islands
    Port Stanley Airport --location.containedby--> Falkland Islands
    Stanley --location.containedby--> Falkland Islands
    Americas --location.contains--> Falkland Islands
    Atlantic Ocean --location.contains--> Falkland Islands
    United Kingdom, with Dependencies and Territories --country.first_level_divisions--> Falkland Islands
    East Falkland --island.island_group--> Falkland Islands
    South Georgia and the South Sandwich Islands --island.island_group--> Falkland Islands
    m.010wxphf | m.010wxs9y | m.09jy10q | m.0zbfy6d --government_position_held.jurisdiction_of_office--> Falkland Islands
── United Kingdom, with Dependencies and Territories ──
    --administrative_area.administrative_area_type--> Sovereign domain
    --sovereign_domain.sovereign_state--> United Kingdom
    South Georgia and the South Sandwich Islands --location.containedby--> United Kingdom, with Dependencies and Territories
    Akrotiri and Dhekelia | Anguilla | Bermuda | British Antarctic Territory | British Indian Ocean Territory | British Virgin Islands | Cayman Islands | Gibraltar | Guernsey | Isle of Man | Jersey | Montserrat …(+4) (to answer with ALL of them, include "#Akrotiri and Dhekelia::first_level_division_of" as one answer entity) --administrative_division.first_level_division_of--> United Kingdom, with Dependencies and Territories
    UK crown dependency --administrative_area_type.sovereignty--> United Kingdom, with Dependencies and Territories
    UK overseas territory --administrative_area_type.sovereignty--> United Kingdom, with Dependencies and Territories
── South Georgia and the South Sandwich Islands ──
    --administrative_area.administrative_area_type--> UK overseas territory
 
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: United Kingdom  |  relations: location.location.time_zones
旧: 模式 11 · 证据块 10 · 6177 字符
新: 模式 4 · 证据块 6 · 2079 字符

【旧渲染】
```
fact_id: sg2
triples:
entities: United Kingdom
▸ patterns: administrative_division.country ⭢ location.time_zones | administrative_area.administrative_children ⭢ administrative_division.country ⭢ location.time_zones | administrative_division.country ⭢ island.island_group ⭢ location.time_zones | administrative_division.country ⭢ island_group.islands_in_group ⭢ location.time_zones | administrative_area.administrative_children ⭢ administrative_division.country ⭢ location.containedby ⭢ location.time_zones | administrative_area.administrative_children ⭢ administrative_division.country ⭢ location.contains ⭢ location.time_zones | administrative_area.administrative_children ⭢ administrative_division.country ⭢ time_zone.locations_in_this_time_zone ⭢ location.time_zones | administrative_division.country ⭢ island_group.islands_in_group ⭢ location.containedby ⭢ location.time_zones | administrative_division.country ⭢ island_group.islands_in_group ⭢ location.contains ⭢ location.time_zones | administrative_division.country ⭢ island_group.islands_in_group ⭢ location.time_zones ⭢ location.time_zones | location.time_zones
── United Kingdom ──
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> United Kingdom
    South Georgia and the South Sandwich Islands --administrative_division.country--> United Kingdom
── Americas ──
    --location.contains--> Anguilla | Montserrat | Turks and Caicos Islands | Falkland Islands
    --location.time_zones--> Alaska Time Zone | Amazon Time Zone | Argentina Time Zone | Atlantic Time Zone | Bolivia Time Zone | Brasília Time Zone | Central Time Zone | Chile Time Zone | Clipperton Island Time Zone | Colombia Time Zone | Cuba Time Zone | East Greenland Time Zone | Eastern Caribbean Time Zone | Eastern Time Zone | Ecuador Time Zone | Falkland Islands Time Zone | Fernando de Noronha Time Zone | French Guiana Time Zone | Galápagos Time Zone | Guyana Time Zone | Mountain Time Zone | Newfoundland Time Zone | Pacific Time Zone | Paraguay Time Zone | Peru Time Zone | Saint Pierre and Miquelon Time Zone | South Georgia and the South Sandwich Islands Time Zone | Suriname Time Zone | Uruguay Time Zone | Venezuela Time Zone | West Greenland Time Zone | Western European Time Zone
    Anguilla | Falkland Islands | Montserrat | Turks and Caicos Islands --location.containedby--> Americas
── South America ──
    --location.time_zones--> Amazon Time Zone | Argentina Time Zone | Bolivia Time Zone | Brasília Time Zone | Chile Time Zone | Colombia Time Zone | Ecuador Time Zone | Falkland Islands Time Zone | Fernando de Noronha Time Zone | French Guiana Time Zone | Guyana Time Zone | Paraguay Time Zone | Peru Time Zone | Suriname Time Zone | Uruguay Time Zone | Venezuela Time Zone
    Falkland Islands --location.containedby--> South America
── North America ──
    --location.time_zones--> Alaska Time Zone | Atlantic Time Zone | Central Time Zone | East Greenland Time Zone | Eastern Time Zone | Hawaii-Aleutian Time Zone | Mountain Time Zone | Newfoundland Time Zone | Pacific Time Zone | Saint Pierre and Miquelon Time Zone | West Greenland Time Zone
    Anguilla | Montserrat | Turks and Caicos Islands --location.containedby--> North America
── Eastern Caribbean Time Zone ──
    --time_zone.locations_in_this_time_zone--> Anguilla | Montserrat
    Anguilla | Antigua and Barbuda | Barbados | Dominica | Grenada | Martinique | Montserrat | Saint Kitts and Nevis | Saint Lucia | Saint Vincent and the Grenadines --location.time_zones--> Eastern Caribbean Time Zone
── Falkland Islands ──
    --location.containedby--> Falkland Islands
    --island_group.islands_in_group--> South Georgia and the South Sandwich Islands
    --location.time_zones--> Falkland Islands Time Zone
    Stanley --location.containedby--> Falkland Islands
    South Georgia and the South Sandwich Islands --island.island_group--> Falkland Islands
── Anguilla ──
    --location.containedby--> Leeward Islands
    --administrative_di
```
【新渲染】
```
fact_id: sg2
triples:
entities: Falkland Islands  (sequence root; this layer applies to the frontier: United Kingdom)
▸ patterns: location.containedby ⭢ administrative_area.administrative_children ⭢ location.time_zones | location.containedby ⭢ administrative_area.administrative_parent ⭢ location.time_zones | location.containedby ⭢ administrative_division.country ⭢ location.time_zones | administrative_division.country
── Falkland Islands ──
    --location.containedby--> United Kingdom, with Dependencies and Territories
── United Kingdom, with Dependencies and Territories ──
    --administrative_area.administrative_children--> Anguilla | Bermuda | South Georgia and the South Sandwich Islands
    Anguilla | Bermuda | South Georgia and the South Sandwich Islands --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    Anguilla --administrative_division.country--> United Kingdom, with Dependencies and Territories
── United Kingdom ──
    Gibraltar | Isle of Man | Jersey | South Georgia and the South Sandwich Islands | Wales --administrative_division.country--> United Kingdom
── Anguilla ──
    --location.time_zones--> Eastern Caribbean Time Zone
── South Georgia and the South Sandwich Islands ──
    --location.time_zones--> South Georgia and the South Sandwich Islands Time Zone
── Bermuda ──
    --location.time_zones--> Atlantic Time Zone
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'location.location.time_zones': {'direct': ['location.location.time_zones'], 'bridge': ['location.administrative_division.country']}}
anchor_sequence: Falkland Islands ⭢ 2-step chain (frontier: United Kingdom)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: United Kingdom  |  relations: location.location.containedby | location.location.primarily_containedby | location.location.partially_containedby | bas
旧: 模式 16 · 证据块 7 · 5208 字符
新: 模式 6 · 证据块 6 · 3466 字符

【旧渲染】
```
fact_id: sg3
triples:
entities: United Kingdom
▸ patterns: sovereign_domain.sovereign_state | location.containedby | administrative_area.administrative_children ⭢ location.containedby | administrative_area.administrative_children ⭢ location.partially_containedby | administrative_area.administrative_parent ⭢ location.containedby | administrative_area.administrative_parent ⭢ location.partially_containedby | administrative_area.subdivides_place ⭢ location.containedby | administrative_area.subdivides_place ⭢ location.partially_containedby | administrative_area.subdividing_place ⭢ location.containedby | administrative_area.subdividing_place ⭢ location.partially_containedby | administrative_division.country ⭢ location.containedby | location.containedby ⭢ location.containedby | location.containedby ⭢ location.partially_containedby | location.containedby ⭢ location.primarily_containedby | location.partially_containedby | location.primarily_containedby
── United Kingdom ──
    --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    --location.containedby--> United Kingdom, with Dependencies and Territories | Western Europe
    --administrative_area.subdivides_place--> United Kingdom, with Dependencies and Territories
    United Kingdom, with Dependencies and Territories --administrative_area.administrative_children--> United Kingdom
    Guernsey --location.containedby--> United Kingdom
    Wales --location.containedby--> United Kingdom
    Gibraltar | Isle of Man | South Georgia and the South Sandwich Islands --administrative_division.country--> United Kingdom
    United Kingdom, with Dependencies and Territories --sovereign_domain.sovereign_state--> United Kingdom
    United Kingdom, with Dependencies and Territories --administrative_area.subdividing_place--> United Kingdom
── United Kingdom, with Dependencies and Territories ──
    --location.partially_containedby--> Altitude | Atlantic Ocean | Cyprus | English Channel | Greater Antilles | Iberian Peninsula | Indian Ocean | Irish Sea | Leeward Islands | Lucayan Archipelago | Pacific Ocean | Virgin Islands | Western Europe
    Akrotiri and Dhekelia | Anguilla | Bermuda | British Antarctic Territory | British Indian Ocean Territory | British Virgin Islands | Cayman Islands | Falkland Islands | Gibraltar | Isle of Man | Jersey | Montserrat …(+5) --location.containedby--> United Kingdom, with Dependencies and Territories
    Normandy --location.partially_containedby--> United Kingdom, with Dependencies and Territories
── Western Europe ──
    France --location.partially_containedby--> Western Europe
    Netherlands --location.partially_containedby--> Western Europe
    France | Netherlands | Portugal --location.primarily_containedby--> Western Europe
── Isle of Man ──
    --location.containedby--> British Isles | Irish Sea
── South Georgia and the South Sandwich Islands ──
    --location.containedby--> Americas | Atlantic Ocean
── Gibraltar ──
    --location.containedby--> Iberian Peninsula
── English Channel ──
    Guernsey --location.containedby--> English Channel
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was pl
```
【新渲染】
```
fact_id: sg3
triples:
entities: Falkland Islands  (sequence root; this layer applies to the frontier: United Kingdom)
▸ patterns: location.containedby | location.containedby ⭢ administrative_area.administrative_children | location.containedby ⭢ location.partially_containedby | location.containedby ⭢ administrative_area.administrative_parent ⭢ administrative_area.administrative_children | location.containedby ⭢ sovereign_domain.sovereign_state ⭢ administrative_area.administrative_children | administrative_area.administrative_children
── Falkland Islands ──
    --location.containedby--> Atlantic Ocean | South America | United Kingdom, with Dependencies and Territories
── United Kingdom, with Dependencies and Territories ──
    --administrative_area.administrative_children--> Akrotiri and Dhekelia | British Antarctic Territory | British Indian Ocean Territory | British Virgin Islands | Cayman Islands | Gibraltar | Guernsey | Isle of Man | Jersey | Montserrat | Pitcairn Islands | Saint Helena, Ascension and Tristan da Cunha | Turks and Caicos Islands | United Kingdom
    --location.partially_containedby--> Altitude | Cyprus | English Channel | Greater Antilles | Iberian Peninsula | Indian Ocean | Irish Sea | Leeward Islands | Lucayan Archipelago | Pacific Ocean | Virgin Islands | Western Europe
    --sovereign_domain.sovereign_state--> United Kingdom
    Saint Helena, Ascension and Tristan da Cunha --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    United Kingdom --administrative_area.administrative_parent--> United Kingdom, with Dependencies and Territories
    Normandy --location.partially_containedby--> United Kingdom, with Dependencies and Territories
── South America ──
    --location.partially_containedby--> Northern Hemisphere | Southern Hemisphere
    Ecuador | France | Overseas France --location.partially_containedby--> South America
── United Kingdom ──
    --administrative_area.administrative_children--> Wales
    --location.containedby--> Western Europe
    Guernsey --location.containedby--> United Kingdom
── Atlantic Ocean ──
    Portugal --location.partially_containedby--> Atlantic Ocean
    Spain --location.partially_containedby--> Atlantic Ocean
── Saint Helena, Ascension and Tristan da Cunha ──
    --administrative_area.administrative_children--> Saint Helena
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'location.location.containedby': {'direct': ['location.location.containedby'], 'bridge': ['base.aareas.schema.administrative_area.administrative_children', 'location.administrative_division.country']}, 'location.location.primarily_containedby': {'direct': ['location.location.primarily_containedby'], 'bridge': ['location.location.containedby']}, 'location.location.partially_containedby': {'direct': ['location.location.partially_containedby'], 'bridge': ['base.aareas.schema.administrative_area.administrative_children', 'location.location.containedby']}}
anchor_sequence: Falkland Islands ⭢ 3-step chain (frontier: United Kingdom)
layer_action: extend
```


============================================================================================
## CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec s0
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?  f1=1.0
sg 调用数: 旧 2 / 新 2

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Tupac Shakur | Kirk M. Petruccelli  |  relations: film.actor.film | film.directed_by
旧: 模式 19 · 证据块 9 · 7920 字符
新: 模式 24 · 证据块 10 · 7594 字符

【旧渲染】
```
triples:
entities: Tupac Shakur | Kirk M. Petruccelli
▸ patterns: actor.film | film.film_art_direction_by ⭢ film.directed_by | film.film_production_design_by ⭢ film.directed_by | film_production_designer.films_production_designed ⭢ film.directed_by | film_subject.films ⭢ film.directed_by | performance.actor ⭢ actor.film | producer.releases_produced ⭢ film.directed_by | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ film.directed_by | actor.film ⭢ film.starring ⭢ film.directed_by | film.film_art_direction_by ⭢ film.music ⭢ actor.film | film.film_art_direction_by ⭢ music_contributor.film ⭢ actor.film | film.film_art_direction_by ⭢ producer.releases_produced ⭢ actor.film | featured_artist.recordings ⭢ recording.artist ⭢ film.directed_by | featured_artist.recordings ⭢ recording.featured_artists ⭢ film.directed_by | producer.releases_produced ⭢ film.music ⭢ actor.film | producer.releases_produced ⭢ music_contributor.film ⭢ actor.film | recording.featured_artists ⭢ recording.artist ⭢ film.directed_by | film.directed_by
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down
    m.09twb36 --award_nomination.award_nominee--> Kirk M. Petruccelli
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome …(+2) --film.film_production_design_by--> Kirk M. Petruccelli
── Tupac Shakur ──
    --award_nominee.award_nominations--> m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)] | m.0mv8gv3 [award: MTV Video Music Award for Best Rap Video; ceremony: 1996 MTV Video Music Awards; nominated_for: California Love]
    --actor.film--> m.02vb3h0 [character: Lucky] | m.02vcpnk [character: Tank] | m.02vcykh [character: Digital Underground member] | m.0j_81z [character: Bishop] | m.0js_kj [character: Birdie] | m.0jyn86 [character: Det. Rodriguez] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore] | m.0pcn9p9 [character: Sniper]
    --film_subject.films--> Tupac: Hip Hop Genius
    --featured_artist.recordings--> California Love | Ghetto Fabulous
    --producer.releases_produced--> Poetic Justice
    m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 --performance.actor--> Tupac Shakur
    m.0j_l784 --award_nomination.award_nominee--> Tupac Shakur
    m.0mv8gv3 --award_nomination.award_nominee--> Tupac Shakur
    California Love --recording.featured_artists--> Tupac Shakur
    Ghetto Fabulous --recording.featured_artists--> Tupac Shakur
── Janet Jackson ──
    --music_contributor.film--> m.02vckpm | Poetic Justice
    m.02vckpm --performance.actor--> Janet Jackson
    Poetic Justice --film.music--> Janet Jackson
── Poetic Justice ──
    --film.directed_by--> John Singleton
    --film.starring--> m.02vb3h0 [character: Lucky] | m.02vckpm
    m.02vb3h0 --performance.film--> Poetic Justice
    m.02vckpm --performance.film--> Poetic Justice
── Dr. Dre ──
    --award_nominee.award_nominations--> m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)] | m.0mv8gv3 [award: MTV Video Music Award for Best Rap Video; ceremony: 1996 MTV Video Music Awards; nominated_for: California
```
【新渲染】
```
triples:
entities: Tupac Shakur | Kirk M. Petruccelli
▸ patterns: award_nomination.award_nominee | award_nominee.award_nominations | actor.film | film.film_production_design_by | film_subject.films | producer.releases_produced | award_nominee.award_nominations ⭢ award_nomination.award_nominee | film.film_art_direction_by ⭢ film.directed_by | film.film_art_direction_by ⭢ film.film_production_design_by | film.film_art_direction_by ⭢ producer.releases_produced | film.film_production_design_by ⭢ film.directed_by | film_art_director.films_art_directed ⭢ producer.releases_produced | film_production_designer.films_production_designed ⭢ film.directed_by | producer.releases_produced ⭢ film.directed_by | producer.releases_produced ⭢ film.film_production_design_by | award_nomination.award_nominee ⭢ award_nominated_work.award_nominations ⭢ film.directed_by | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nominated_work.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nominated_work.award_nominations ⭢ film.film_production_design_by | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ film.directed_by | actor.film ⭢ performance.film ⭢ producer.releases_produced | film.film_art_direction_by ⭢ film.music ⭢ actor.film | film.film_art_direction_by ⭢ music_contributor.film ⭢ award_nomination.award_nominee | film.film_art_direction_by ⭢ music_contributor.film ⭢ actor.film
── Tupac Shakur ──
    --award_nominee.award_nominations--> m.0_tln3r [award: NAACP Image Award for Outstanding Actor in a Motion Picture; ceremony: 26th NAACP Image Awards; nominated_for: Poetic Justice] | m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)] | m.0j_l78n [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: How Do U Want It] | m.0mv8gv3 [award: MTV Video Music Award for Best Rap Video; ceremony: 1996 MTV Video Music Awards; nominated_for: California Love] | m.0mw779x [award: MTV Video Music Award for Best Rap Video; ceremony: 2003 MTV Video Music Awards; nominated_for: Thugz Mansion] | m.0z86_19 [award: Soul Train Music Award for Best R&B/Soul or Rap Music Video; ceremony: 1997 Soul Train Music Awards; nominated_for: How Do You Want It]
    --actor.film--> m.02vb3h0 [character: Lucky] | m.02vcpnk [character: Tank] | m.02vcykh [character: Digital Underground member] | m.0j_81z [character: Bishop] | m.0js_kj [character: Birdie] | m.0jyn86 [character: Det. Rodriguez] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore] | m.0pcn9p9 [character: Sniper]
    --film_subject.films--> Biggie & Tupac | Tupac: Hip Hop Genius
    --producer.releases_produced--> 15 Years on Death Row | Death Row: The Singles Collection | Gang Related | Greatest Hits | Poetic Justice | Still I Rise | Strictly 4 My N.I.G.G.A.Z... | Supercop | The Don Killuminati: The 7 Day Theory | West Side | オール・アイズ・オン・ミー
    m.0_tln3r | m.0j_l784 | m.0j_l78n | m.0j_l7hc | m.0j_pbc9 | m.0lyw79d | m.0m0q4k7 | m.0m3g28_ | m.0mv8gv3 | m.0mw779x | m.0ndlnz1 | m.0nf_zwj …(+7) (to answer with ALL of them, include "#m.0_tln3r::award_nominee" as one answer entity) --award_nomination.award_nominee--> Tupac Shakur
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    --film_art_director.films_art_directed--> Poetic Justice
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor
    m.09twb36 --award_nomination.award_nominee--> Kirk M. Petruccelli
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_d
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Kirk M. Petruccelli  |  relations: film.director.film | film.film_crewmember.films_crewed | film.film_job.films_with_this_crew_job
旧: 模式 11 · 证据块 10 · 5468 字符
新: 模式 24 · 证据块 10 · 7693 字符

【旧渲染】
```
triples:
entities: Kirk M. Petruccelli
▸ patterns: film_crewmember.films_crewed | film.film_art_direction_by ⭢ director.film | film.film_production_design_by ⭢ director.film | film_art_director.films_art_directed ⭢ director.film | film_crew_gig.crewmember ⭢ film_crewmember.films_crewed | film_crew_gig.crewmember ⭢ film_job.films_with_this_crew_job | film_crewmember.films_crewed ⭢ film_job.films_with_this_crew_job | film_production_designer.films_production_designed ⭢ director.film | person.profession ⭢ film_job.films_with_this_crew_job | director.film | film_job.films_with_this_crew_job
── Kirk M. Petruccelli ──
    --film_art_director.films_art_directed--> Philadelphia Experiment II | Poetic Justice
    --film_crewmember.films_crewed--> m.0pcv8vs [film: The Ambulance; film_crew_role: Set decorator second]
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down
    --person.profession--> Film Art Director
    m.0pcv8vs --film_crew_gig.crewmember--> Kirk M. Petruccelli
    Philadelphia Experiment II --film.film_art_direction_by--> Kirk M. Petruccelli
    Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome …(+2) --film.film_production_design_by--> Kirk M. Petruccelli
    m.0n8j4gn --marriage.spouse--> Kirk M. Petruccelli
── Film Art Director ──
    --film_job.films_with_this_crew_job--> m.0cl7qzg | m.0m2hcxq | m.0nb1sxg | m.0p7hzn2 | m.0p7qw85 | m.0p7r129 | m.0pcb_8l | m.0pcb_c_ | m.0pcp8w9 | m.0pyv2ff | m.0q27855 | m.0r8t5zm | m.0r8vw5k | m.0s862jl | m.0s8z_qq | m.0sxbybk | m.0t4s93c | m.0t4y1sk | m.0t5b735 | m.0t5bhpz | m.0v9q5k4 | m.0v_bsfm | m.0w05jcj | m.0w05jkx | m.0w5r80v | m.0wb_gxk | m.0wbrn1v | m.0wbrn60 | m.0y61vwg | m.0yqhkmc | m.0yrnfj7
    m.0cl7qzg | m.0m2hcxq | m.0nb1sxg | m.0p7hzn2 | m.0p7qw85 | m.0p7r129 | m.0pcb_8l | m.0pcb_c_ | m.0pcp8w9 | m.0pyv2ff | m.0q27855 | m.0r8t5zm …(+19) --film_crew_gig.film_crew_role--> Film Art Director
── 3 Ninjas ──
    Jon Turteltaub --director.film--> 3 Ninjas
── Bullhead ──
    Ken Twohy --director.film--> Bullhead
── Ghost Rider ──
    Mark Steven Johnson --director.film--> Ghost Rider
── Killing Season ──
    Mark Steven Johnson --director.film--> Killing Season
── Lara Croft: Tomb Raider ──
    Simon West --director.film--> Lara Croft: Tomb Raider
── Mark Steven Johnson ──
    --director.film--> When in Rome
── Murder in the First ──
    Marc Rocco --director.film--> Murder in the First
── Mystery Men ──
    Kinka Usher --director.film--> Mystery Men
    John Singleton --director.film--> Poetic Justice
    Josef Rusnak --director.film--> The Thirteenth Floor
    Marc Rocco --director.film--> Where the Day Takes You
    Peter Winther --director.film--> The Librarian: Quest for the Spear
    Rod Lurie --director.film--> The Last Castle
    Roland Emmerich --director.film--> The Patriot | White House Down
    Stephen Cornwell --director.film--> Philadelphia Experiment II
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates ent
```
【新渲染】
```
triples:
entities: Kirk M. Petruccelli
▸ patterns: award_nominee.award_nominations | film_art_director.films_art_directed | film_crewmember.films_crewed | film_production_designer.films_production_designed | marriage.spouse | person.profession | film.film_art_direction_by ⭢ director.film | film.film_art_direction_by ⭢ film_production_designer.films_production_designed | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film_art_director.films_art_directed | film_art_director.films_art_directed ⭢ film_production_designer.films_production_designed | film_crew_gig.crewmember ⭢ film_job.films_with_this_crew_job | film_crewmember.films_crewed ⭢ film_job.films_with_this_crew_job | film_production_designer.films_production_designed ⭢ director.film | film_production_designer.films_production_designed ⭢ film_art_director.films_art_directed | person.profession ⭢ film_job.films_with_this_crew_job | person.spouse_s ⭢ marriage.spouse | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ person.profession | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ person.profession | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ person.profession | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ person.profession | marriage.spouse ⭢ marriage.spouse ⭢ film_crewmember.films_crewed | person.spouse_s ⭢ marriage.spouse ⭢ film_crewmember.films_crewed | award_nomination.award_nominee ⭢ award_nomination.nominated_for ⭢ film.executive_produced_by ⭢ person.profession
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    --film_art_director.films_art_directed--> And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice
    --film_crewmember.films_crewed--> m.0pcv8vs [film: The Ambulance; film_crew_role: Set decorator second]
    --film_production_designer.films_production_designed--> 3 Ninjas | Anaconda | Blade | Bullhead | Fantastic Four: Rise of the Silver Surfer | Ghost Rider | Killing Season | Lara Croft Tomb Raider: The Cradle of Life | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Incredible Hulk | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down | Zookeeper
    --person.profession--> Film Art Director | Production Designer
    --person.spouse_s--> m.0n8j4gn [has_no_value: To; has_value: Location of ceremony; type_of_union: Marriage]
    m.09twb36 --award_nomination.award_nominee--> Kirk M. Petruccelli
    m.0pcv8vs --film_crew_gig.crewmember--> Kirk M. Petruccelli
    Philadelphia Experiment II --film.film_art_direction_by--> Kirk M. Petruccelli
    Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Anaconda | Bullhead | Fantastic Four: Rise of the Silver Surfer | Ghost Rider | Lara Croft Tomb Raider: The Cradle of Life | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot …(+2) (to answer with ALL of them, include "#3 Ninjas::film_production_design_by" as one answer entity) --film.film_production_design_by--> Kirk M. Petruccelli
    m.0n8j4gn --marriage.spouse--> Kirk M. Petruccelli
── Film Art Director ──
    --film_job.films_with_this_crew_job--> m.0cl7qzg | m.0m2hcxq | m.0nb1sxg | m.0p7hzn2 | m.0p7qw85 | m.0p7r129 | m.0pcb_8l | m.0pcb_c_ | m.0pcp8w9 | m.0pyv2ff | m.0q27855 | m.0r8t5zm | m.0r8vw5k | m.0s862jl | m.0s8z_qq | m.0sxbybk | m.0t4s93c | m.0t4y1sk | m.0t5b735 | m.0t5bhpz | m.0v9q5k4 | m.0v_bsfm | m.0w05jcj | m.0w05jkx | m.0w5r80v | m.0wb_gxk | m.0wbrn1v | m.0wbrn60 | m.0y61vwg | m.0yqhkmc | m.0yrnfj7
    Barry Chusid --person.profession--> Film Art Director
── Barry Chusid ──
    --award_nominee.award_nominations--> m.09twb36 [awar
```


============================================================================================
## CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec s2
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?  f1=0.0
sg 调用数: 旧 3 / 新 3

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Tupac Shakur | Kirk M. Petruccelli  |  relations: actor.film | film.starring | director.film | film.directed_by
旧: 模式 36 · 证据块 10 · 10865 字符
新: 模式 24 · 证据块 10 · 10683 字符

【旧渲染】
```
triples:
entities: Tupac Shakur | Kirk M. Petruccelli
▸ patterns: actor.film | actor.film ⭢ film.starring | film.film_art_direction_by ⭢ director.film | film.film_art_direction_by ⭢ film.directed_by | film.film_art_direction_by ⭢ film.starring | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film.directed_by | film.film_production_design_by ⭢ film.starring | film.subjects ⭢ director.film | film_production_designer.films_production_designed ⭢ director.film | film_subject.films ⭢ director.film | film_subject.films ⭢ film.directed_by | performance.actor ⭢ actor.film | performance.actor ⭢ film.starring | producer.releases_produced ⭢ director.film | producer.releases_produced ⭢ film.directed_by | producer.releases_produced ⭢ film.starring | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ director.film | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ director.film | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ film.directed_by | actor.film ⭢ film.starring ⭢ director.film | actor.film ⭢ film.starring ⭢ film.directed_by | featured_artist.recordings ⭢ recording.artist ⭢ director.film | featured_artist.recordings ⭢ recording.artist ⭢ film.directed_by | featured_artist.recordings ⭢ recording.featured_artists ⭢ director.film | featured_artist.recordings ⭢ recording.featured_artists ⭢ film.directed_by | producer.releases_produced ⭢ film.music ⭢ actor.film | producer.releases_produced ⭢ music_contributor.film ⭢ actor.film | recording.featured_artists ⭢ recording.artist ⭢ director.film | recording.featured_artists ⭢ recording.artist ⭢ film.directed_by | director.film | film.directed_by | film.starring | person.languages ⭢ film.language ⭢ siteid.film | person.nationality ⭢ film.country ⭢ siteid.film
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down
    m.09twb36 --award_nomination.award_nominee--> Kirk M. Petruccelli
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome …(+2) --film.film_production_design_by--> Kirk M. Petruccelli
── Tupac Shakur ──
    --award_nominee.award_nominations--> m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)] | m.0mv8gv3 [award: MTV Video Music Award for Best Rap Video; ceremony: 1996 MTV Video Music Awards; nominated_for: California Love]
    --actor.film--> m.02vb3h0 [character: Lucky] | m.02vcpnk [character: Tank] | m.02vcykh [character: Digital Underground member] | m.0j_81z [character: Bishop] | m.0js_kj [character: Birdie] | m.0jyn86 [character: Det. Rodriguez] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore] | m.0pcn9p9 [character: Sniper]
    --film_subject.films--> Tupac: Hip Hop Genius
    --person.languages--> English Language
    --person.nationality--> United States of America
    --featured_artist.recordings--> California Love | Ghetto Fabulous
    --producer.releases_produced--> Poetic Justice | Gang Related
    m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 --performance.actor--> Tupac Shakur
    m.0j_l784 --award_nomination.award_nominee--> Tupac Shakur
    m.0mv8gv3 --award_nomination.award_nominee--> Tupac Shakur
    Cal
```
【新渲染】
```
triples:
entities: Tupac Shakur | Kirk M. Petruccelli
▸ patterns: award_nomination.award_nominee | award_nominee.award_nominations | actor.film | film.film_production_design_by | film_art_director.films_art_directed | film_subject.films | performance.actor | producer.releases_produced | award_nominee.award_nominations ⭢ award_nomination.award_nominee | film.film_art_direction_by ⭢ director.film | film.film_art_direction_by ⭢ film.directed_by | film.film_art_direction_by ⭢ film.film_production_design_by | film.film_art_direction_by ⭢ film.starring | film.film_art_direction_by ⭢ producer.releases_produced | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film.directed_by | film.film_production_design_by ⭢ film.starring | film.film_production_design_by ⭢ film_art_director.films_art_directed | film.subjects ⭢ director.film | film_art_director.films_art_directed ⭢ producer.releases_produced | film_production_designer.films_production_designed ⭢ director.film | film_production_designer.films_production_designed ⭢ film.directed_by | film_production_designer.films_production_designed ⭢ film.starring | film_production_designer.films_production_designed ⭢ film_art_director.films_art_directed
── Tupac Shakur ──
    --award_nominee.award_nominations--> m.0_tln3r [award: NAACP Image Award for Outstanding Actor in a Motion Picture; ceremony: 26th NAACP Image Awards; nominated_for: Poetic Justice] | m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)] | m.0j_l78n [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: How Do U Want It] | m.0mv8gv3 [award: MTV Video Music Award for Best Rap Video; ceremony: 1996 MTV Video Music Awards; nominated_for: California Love] | m.0mw779x [award: MTV Video Music Award for Best Rap Video; ceremony: 2003 MTV Video Music Awards; nominated_for: Thugz Mansion] | m.0z86_19 [award: Soul Train Music Award for Best R&B/Soul or Rap Music Video; ceremony: 1997 Soul Train Music Awards; nominated_for: How Do You Want It]
    --actor.film--> m.02vb3h0 [character: Lucky] | m.02vcpnk [character: Tank] | m.02vcykh [character: Digital Underground member] | m.0j_81z [character: Bishop] | m.0js_kj [character: Birdie] | m.0jyn86 [character: Det. Rodriguez] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore] | m.0pcn9p9 [character: Sniper]
    --film_subject.films--> Biggie & Tupac | Tupac: Hip Hop Genius
    --producer.releases_produced--> 15 Years on Death Row | Death Row: The Singles Collection | Gang Related | Greatest Hits | Poetic Justice | Still I Rise | Strictly 4 My N.I.G.G.A.Z... | Supercop | The Don Killuminati: The 7 Day Theory | West Side | オール・アイズ・オン・ミー
    m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 --performance.actor--> Tupac Shakur
    m.0_tln3r | m.0j_l784 | m.0j_l78n | m.0j_l7hc | m.0j_pbc9 | m.0lyw79d | m.0m0q4k7 | m.0m3g28_ | m.0mv8gv3 | m.0mw779x | m.0ndlnz1 | m.0nf_zwj …(+7) (to answer with ALL of them, include "#m.0_tln3r::award_nominee" as one answer entity) --award_nomination.award_nominee--> Tupac Shakur
    Tupac: Hip Hop Genius --film.subjects--> Tupac Shakur
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    --film_art_director.films_art_directed--> And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | Where the Day Takes You | Anaconda | Fantastic Four: Rise of the Silver Surfer | Lara Croft Tomb Raider: The Cradle of Life | White House Down
    m.09twb36 --award_nomination.award_n
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9  |  relations: film.directed_by
旧: 模式 6 · 证据块 10 · 3996 字符
新: 模式 5 · 证据块 3 · 2312 字符

【旧渲染】
```
triples:
entities: m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9
▸ patterns: film.starring ⭢ film.directed_by | performance.film ⭢ film.directed_by | actor.film ⭢ producer.releases_produced ⭢ film.directed_by | performance.actor ⭢ film_subject.films ⭢ film.directed_by | performance.actor ⭢ producer.releases_produced ⭢ film.directed_by | film.directed_by
── Tupac Shakur ──
    --actor.film--> m.02vcpnk [character: Tank] | m.02vcykh [character: Digital Underground member] | m.0j_81z [character: Bishop] | m.0js_kj [character: Birdie] | m.0jyn86 [character: Det. Rodriguez] | m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore] | m.02vb3h0 [actor: Tupac Shakur; character: Lucky] | m.0pcn9p9 [actor: Tupac Shakur; character: Sniper]
    --film_subject.films--> Tupac: Hip Hop Genius
    --producer.releases_produced--> Poetic Justice
    m.02vb3h0 | m.02vcpnk | m.02vcykh | m.0j_81z | m.0js_kj | m.0jyn86 | m.0jz0c4 | m.0pcn9p9 --performance.actor--> Tupac Shakur
── Poetic Justice ──
    --film.directed_by--> John Singleton
    --film.starring--> m.02vb3h0 [actor: Tupac Shakur; character: Lucky] | m.02tb74m | m.02vckpm | m.02vcy64 | m.02vd72n | m.03jpsrt | m.03l7r6x | m.05k9530 | m.0cgc3xp | m.0h3043j | m.0h5k4_n | m.0ncdr8_ | m.0ncdr99
    m.02vb3h0 --performance.film--> Poetic Justice
── Murder Was the Case ──
    --film.directed_by--> Dr. Dre
    --film.starring--> m.0pcn9p9 [actor: Tupac Shakur; character: Sniper]
    m.0pcn9p9 --performance.film--> Murder Was the Case
── Above the Rim ──
    --film.starring--> m.0js_kj [character: Birdie]
    m.0js_kj --performance.film--> Above the Rim
── Birdie ──
    --film_character.portrayed_in_films--> m.0js_kj [character: Birdie]
    m.0js_kj --performance.character--> Birdie
── Bishop ──
    --film_character.portrayed_in_films--> m.0j_81z [character: Bishop]
    m.0j_81z --performance.character--> Bishop
── Bullet ──
    --film.starring--> m.02vcpnk [character: Tank]
    m.02vcpnk --performance.film--> Bullet
── Det. Rodriguez ──
    --film_character.portrayed_in_films--> m.0jyn86 [character: Det. Rodriguez]
    m.0jyn86 --performance.character--> Det. Rodriguez
── Digital Underground member ──
    --film_character.portrayed_in_films--> m.02vcykh [character: Digital Underground member]
    m.02vcykh --performance.character--> Digital Underground member
── Ezekiel 'Spoon' Whitmore ──
    --film_character.portrayed_in_films--> m.0jz0c4 [character: Ezekiel 'Spoon' Whitmore]
    m.0jz0c4 --performance.character--> Ezekiel 'Spoon' Whitmore
    Tupac: Hip Hop Genius --film.directed_by--> Charlotte Lewin
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: Multiple centers retrieved with one shared relation set — COMPARE them via the triples (an edge '--to--> (incumbent)' marks the current holder). triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'film.directed_by': {'direct': ['film.film.directed_by'], 'bridge': ['film.film.starring']}}
```
【新渲染】
```
triples:
entities: Tupac Shakur
▸ patterns: award_nomination.award_nominee ⭢ award_nominated_work.award_nominations ⭢ film.directed_by | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nominated_work.award_nominations ⭢ film.directed_by | award_nominee.award_nominations ⭢ award_nominated_work.award_nominations ⭢ film.starring | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ film.directed_by
── Tupac Shakur ──
    --award_nominee.award_nominations--> m.0_tln3r [award: NAACP Image Award for Outstanding Actor in a Motion Picture; ceremony: 26th NAACP Image Awards; nominated_for: Poetic Justice] | m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)]
    m.0_tln3r --award_nomination.award_nominee--> Tupac Shakur
    m.0j_l784 --award_nomination.award_nominee--> Tupac Shakur
── Poetic Justice ──
    --award_nominated_work.award_nominations--> m.0_tln3r [award: NAACP Image Award for Outstanding Actor in a Motion Picture; ceremony: 26th NAACP Image Awards; nominated_for: Poetic Justice]
    --film.directed_by--> John Singleton
    --film.starring--> m.02tb74m | m.02vb3h0 [actor: Tupac Shakur; character: Lucky] | m.02vckpm [actor: Janet Jackson] | m.02vcy64 | m.02vd72n | m.03jpsrt | m.03l7r6x | m.05k9530 | m.0cgc3xp | m.0h3043j | m.0h5k4_n | m.0ncdr8_ | m.0ncdr99
── Dr. Dre ──
    --award_nominee.award_nominations--> m.0j_l784 [award: Grammy Award for Best Rap Performance by a Duo or Group; ceremony: 39th Annual Grammy Awards; nominated_for: California Love (album version)]
    Murder Was the Case --film.directed_by--> Dr. Dre
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.directed_by': {'direct': ['film.film.directed_by'], 'bridge': ['film.film.starring']}}
layer_action: repeat
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: Kirk M. Petruccelli  |  relations: film.directed_by | director.film
旧: 模式 11 · 证据块 7 · 5228 字符
新: 模式 17 · 证据块 10 · 8506 字符

【旧渲染】
```
triples:
entities: Kirk M. Petruccelli
▸ patterns: film.film_art_direction_by ⭢ director.film | film.film_art_direction_by ⭢ film.directed_by | film.film_production_design_by ⭢ director.film | film.film_production_design_by ⭢ film.directed_by | film_production_designer.films_production_designed ⭢ director.film | film_production_designer.films_production_designed ⭢ film.directed_by | director.film | film.directed_by | film.film_production_design_by ⭢ siteid.film | film_production_designer.films_production_designed ⭢ siteid.film | person.nationality ⭢ film.country ⭢ siteid.film
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36
    --film_production_designer.films_production_designed--> 3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down
    --person.nationality--> United States of America
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Bullhead | Ghost Rider | Killing Season | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome …(+2) --film.film_production_design_by--> Kirk M. Petruccelli
── The Last Castle ──
    --film.country--> United States of America
    --film.directed_by--> Rod Lurie
    --film.w_id--> m.0599sjg
    Rod Lurie --director.film--> The Last Castle
    m.0599sjg --siteid.film--> The Last Castle
── Mark Steven Johnson ──
    --director.film--> Ghost Rider | Killing Season | When in Rome
    Ghost Rider | Killing Season | When in Rome --film.directed_by--> Mark Steven Johnson
── 3 Ninjas ──
    --film.directed_by--> Jon Turteltaub
    Jon Turteltaub --director.film--> 3 Ninjas
── Bullhead ──
    --film.directed_by--> Ken Twohy
    Ken Twohy --director.film--> Bullhead
── Lara Croft: Tomb Raider ──
    --film.directed_by--> Simon West
    Simon West --director.film--> Lara Croft: Tomb Raider
── Marc Rocco ──
    --director.film--> Murder in the First | Where the Day Takes You
    Murder in the First --film.directed_by--> Marc Rocco
    Where the Day Takes You --film.directed_by--> Marc Rocco
    And the Earth Did Not Swallow Him --film.directed_by--> Severo Pérez
    John Singleton --director.film--> Poetic Justice
    Josef Rusnak --director.film--> The Thirteenth Floor
    Kinka Usher --director.film--> Mystery Men
    Mystery Men --film.directed_by--> Kinka Usher
    Peter Winther --director.film--> The Librarian: Quest for the Spear
    Philadelphia Experiment II --film.directed_by--> Stephen Cornwell
    Poetic Justice --film.directed_by--> John Singleton
    Roland Emmerich --director.film--> The Patriot | White House Down
    Stephen Cornwell --director.film--> Philadelphia Experiment II
    The Librarian: Quest for the Spear --film.directed_by--> Peter Winther
    The Patriot --film.directed_by--> Roland Emmerich
    The Thirteenth Floor --film.directed_by--> Josef Rusnak
    White House Down --film.directed_by--> Roland Emmerich
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's con
```
【新渲染】
```
triples:
entities: Kirk M. Petruccelli
▸ patterns: award_nominee.award_nominations | film.film_art_direction_by | film_production_designer.films_production_designed | film.film_art_direction_by ⭢ director.film | film.film_art_direction_by ⭢ film.directed_by | film.film_art_direction_by ⭢ film.film_production_design_by | film.film_art_direction_by ⭢ film_production_designer.films_production_designed | film.film_production_design_by ⭢ film.film_art_direction_by | film_art_director.films_art_directed ⭢ film_production_designer.films_production_designed | film_production_designer.films_production_designed ⭢ director.film | film_production_designer.films_production_designed ⭢ film.directed_by | film_production_designer.films_production_designed ⭢ film_art_director.films_art_directed | film.film_art_direction_by ⭢ award_nominated_work.award_nominations | film.film_production_design_by ⭢ award_nominated_work.award_nominations | film.film_production_design_by ⭢ siteid.film | film_production_designer.films_production_designed ⭢ award_nominated_work.award_nominations | film_production_designer.films_production_designed ⭢ siteid.film
── Kirk M. Petruccelli ──
    --award_nominee.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot]
    --film_art_director.films_art_directed--> Poetic Justice
    --film_production_designer.films_production_designed--> 3 Ninjas | Anaconda | Blade | Bullhead | Fantastic Four: Rise of the Silver Surfer | Ghost Rider | Killing Season | Lara Croft Tomb Raider: The Cradle of Life | Lara Croft: Tomb Raider | Murder in the First | Mystery Men | The Incredible Hulk | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | When in Rome | Where the Day Takes You | White House Down | Zookeeper
    And the Earth Did Not Swallow Him | Philadelphia Experiment II | Poetic Justice --film.film_art_direction_by--> Kirk M. Petruccelli
    3 Ninjas | Anaconda | Fantastic Four: Rise of the Silver Surfer | Lara Croft Tomb Raider: The Cradle of Life | Mystery Men | The Last Castle | The Librarian: Quest for the Spear | The Patriot | The Thirteenth Floor | White House Down --film.film_production_design_by--> Kirk M. Petruccelli
── White House Down ──
    --award_nominated_work.award_nominations--> m.0_vwczr [award_nominee: Channing Tatum] | m.0wjg1wz [award_nominee: Channing Tatum] | m.0wjg9vg [award_nominee: Channing Tatum] | m.0wjgcwx [has_value: Award Nominee] | m.0wjghl3 [award_nominee: Channing Tatum] | m.0ytbpht [has_value: Award Nominee]
    --film.film_art_direction_by--> Charlotte Rouleau | David Gaucher | Isabelle Guay | Jean-Pierre Paquet | Martina Javorova | Robert Parle
    David Gaucher | Isabelle Guay | Jean-Pierre Paquet | Robert Parle --film_art_director.films_art_directed--> White House Down
── The Patriot ──
    --award_nominated_work.award_nominations--> m.09twb36 [award_nominee: Kirk M. Petruccelli | Richard F. Mays | Tom Reta; ceremony: Art Directors Guild Awards 2000; nominated_for: The Patriot] | m.09tzl16 [award_nominee: Caleb Deschanel] | m.09vqhmy | m.09wpcxt [nominated_for: The Patriot] | m.0b3v06m | m.0b7sc93 [award_nominee: Caleb Deschanel] | m.0pct97z [award_nominee: John Williams] | m.0pd14mf | m.0z5gjnq [has_value: Award Nominee]
    --film.directed_by--> Roland Emmerich
    Roland Emmerich --director.film--> The Patriot
── Poetic Justice ──
    --award_nominated_work.award_nominations--> m.08hhgkp [award_nominee: Janet Jackson] | m.0_tk0n5 [award_nominee: Janet Jackson; ceremony: 26th NAACP Image Awards] | m.0_tln3r [award: NAACP Image Award for Outstanding Actor in a Motion Picture; award_nominee: Tupac Shakur; ceremony: 26th NAACP Image Awards] | m.0hp0rkj [award_nominee: Janet Jackson] | m.0k079lq [award_nominee: Janet Jackson] | m.0n1pty4 [award_nominee: Janet Jackson]
    --film.film_production_design_by--> Keith Brian Burns
    Keith Brian Bur
```


============================================================================================
## CASE WebQTrn-567_11fd073d11dbb5448b6e6ef3f85999f1 s0
Q: What Ron Howard film was released first?  f1=0.0
sg 调用数: 旧 3 / 新 3

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Ron Howard  |  relations: film.director.film | film.film.directed_by
旧: 模式 15 · 证据块 10 · 4925 字符
新: 模式 24 · 证据块 10 · 17716 字符

【旧渲染】
```
triples:
entities: Ron Howard
▸ patterns: director.film | film.directed_by | director.film ⭢ director.film | director.film ⭢ film.directed_by | film.executive_produced_by ⭢ director.film | film.executive_produced_by ⭢ film.directed_by | film.produced_by ⭢ director.film | film.produced_by ⭢ film.directed_by | producer.film ⭢ director.film | producer.film ⭢ film.directed_by | producer.films_executive_produced ⭢ director.film | producer.films_executive_produced ⭢ film.directed_by | actor.film ⭢ performance.film ⭢ director.film | actor.film ⭢ performance.film ⭢ film.directed_by | performance.actor ⭢ film.starring ⭢ film.directed_by
── Ron Howard ──
    --actor.film--> A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | Rush | Splash | The Da Vinci Code | The Dark Tower | The Dilemma | The Lost Symbol | The Missing | The Paper | Willow | Clean and Sober | Closet Land | The 'Burbs | Changeling | m.0jtdhv [character: Steve] | m.0gz5fdc [character: Billy Rhinelander]
    --producer.films_executive_produced--> Leo and Loree | The 'Burbs
    m.0gz5fdc --performance.actor--> Ron Howard
    m.0jtdhv --performance.actor--> Ron Howard
    A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto …(+17) --film.directed_by--> Ron Howard
    Arrested Development | Leo and Loree | The 'Burbs --film.executive_produced_by--> Ron Howard
    Beyond the Mat | Changeling | Clean and Sober | Closet Land | J. Edgar | The 'Burbs | The Alamo | The Lost Symbol --film.produced_by--> Ron Howard
── The 'Burbs ──
    --film.directed_by--> Joe Dante
    Joe Dante --director.film--> The 'Burbs
── The Lost Symbol ──
    --film.directed_by--> Mark Romanek
    Mark Romanek --director.film--> The Lost Symbol
── American Graffiti ──
    --film.directed_by--> George Lucas
    --film.starring--> m.0jtdhv [character: Steve]
    George Lucas --director.film--> American Graffiti
    m.0jtdhv --performance.film--> American Graffiti
── Clean and Sober ──
    --film.directed_by--> Glenn Gordon Caron
    Glenn Gordon Caron --director.film--> Clean and Sober
── Closet Land ──
    --film.directed_by--> Radha Bharadwaj
    Radha Bharadwaj --director.film--> Closet Land
── Leo and Loree ──
    --film.directed_by--> Jerry Paris
    Jerry Paris --director.film--> Leo and Loree
── Presidential Reunion ──
    --film.directed_by--> Jake Szymanski
    Jake Szymanski --director.film--> Presidential Reunion
── Arrested Development ──
    --film.directed_by--> Mitchell Hurwitz
    Mitchell Hurwitz --director.film--> Arrested Development
── Beyond the Mat ──
    --film.directed_by--> Barry W. Blaustein
    Barry W. Blaustein --director.film--> Beyond the Mat
    Changeling --film.directed_by--> Clint Eastwood
    J. Edgar --film.directed_by--> Clint Eastwood
    The Alamo --film.directed_by--> John Lee Hancock
    The Journey --film.directed_by--> Anatole Litvak
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer a
```
【新渲染】
```
triples:
entities: Ron Howard
▸ patterns: award_honor.award_winner | award_nominee.award_nominations | award_winner.awards_won | director.film | film.directed_by | producer.film | producer.films_executive_produced | award_honor.award_winner ⭢ award_winner.awards_won | award_winner.awards_won ⭢ award_honor.award_winner | director.film ⭢ producer.films_executive_produced | film.directed_by ⭢ producer.films_executive_produced | film.executive_produced_by ⭢ director.film | film.executive_produced_by ⭢ film.directed_by | film.produced_by ⭢ film.directed_by | film.written_by ⭢ producer.films_executive_produced | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ award_honor.award_winner | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ award_winner.awards_won | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ award_honor.award_winner | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ award_winner.awards_won | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ award_honor.award_winner | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ award_winner.awards_won | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ award_honor.award_winner | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ award_winner.awards_won | director.film ⭢ siteid.film
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b [award_nominee: Carol Greenwald | David Kirschner | Dorothea Gillim | Ellen Cockrill | Jon Shapiro | Matthew Baughman; ceremony: 41st Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.05bkr1w [award: Academy Award for Best Director; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05bkyhb [award: Academy Award for Best Director; ceremony: 74th Academy Awards; nominated_for: A Beautiful Mind] | m.05bm2lq [award: Academy Award for Best Picture; award_nominee: Brian Grazer | Eric Fellner; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05brffw [award: Academy Award for Best Picture; award_nominee: Ron Howard; ceremony: 74th Academy Awards; nominated_for: A Beautiful Mind] | m.07zqyp3 [award: BAFTA Award for Best Direction; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.07zqyxh [award: BAFTA Award for Best Direction; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lbx1t [award: BAFTA Award for Best Film; award_nominee: Brian Grazer; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lby3g [award: BAFTA Award for Best Film; award_nominee: Brian Grazer | Eric Fellner | Tim Bevan; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.090dj60 [ceremony: 34th Golden Globe Awards; nominated_for: The Shootist] | m.090y4n1 [ceremony: 35th Golden Globe Awards; nominated_for: Happy Days] | m.095h15z [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 53rd Golden Globe Awards; nominated_for: Apollo 13] | m.095h1h2 [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 59th Golden Globe Awards; nominated_for: A Beautiful Mind] | m.095h1tj [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 66th Golden Globe Awards; nominated_for: Frost/Nixon] | m.09k3n_p [award: Critics' Choice Movie Award for Best Director; ceremony: 11th Critics' Choice Awards; nominated_for: Cinderella Man] | m.09k3nwh [award: Critics' Choice Movie Award for Best Director; ceremony: 14th Critics' Choice Awards; nominated_for: Frost/Nixon] | m.09k3p5_ [award: Critics' Choice Movie Award for Best Director; ceremony: 7th Critics' Choice Awards; nominated_for: A Beautiful Mind] | m.09sc2mb [ceremony: 61st Directors Guild of America Awards; nominated_for: Frost/Nixon] | m.09sc2vl [ceremony: 54th Directors Guild of America Awards; nominated_for: A Beautiful Mind] | m.09tjrrf [award: Satellite Award for Best Director; ceremony
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: ?film  |  relations: film.release_date_s | film.film_regional_release_date.film
旧: 模式 10 · 证据块 10 · 7872 字符
新: 模式 2 · 证据块 5 · 1629 字符

【旧渲染】
```
triples:
entities: Ron Howard | Clean and Sober | Closet Land | The 'Burbs | Changeling  (sequence root; this layer applies to the frontier: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto)
▸ patterns: film.release_date_s | film_regional_release_date.film | director.film ⭢ film.release_date_s | director.film ⭢ film_regional_release_date.film | film.directed_by ⭢ film.release_date_s | film.release_date_s ⭢ film_regional_release_date.film | film_regional_release_date.film ⭢ film.release_date_s | film.executive_produced_by ⭢ film.produced_by ⭢ film_regional_release_date.film | film.produced_by ⭢ film.executive_produced_by ⭢ film.release_date_s | film.produced_by ⭢ film.executive_produced_by ⭢ film_regional_release_date.film
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b | m.05bkr1w | m.05bkyhb | m.05bm2lq | m.05brffw | m.07zqyp3 | m.07zqyxh | m.08lbx1t | m.08lby3g | m.090dj60 | m.090y4n1 | m.095h15z | m.095h1h2 | m.095h1tj | m.09k3n_p | m.09k3nwh | m.09k3p5_ | m.09sc2mb | m.09sc2vl | m.09tjrrf | m.09z78wm | m.0b6b2xw | m.0b6b38g | m.0gkjjsg | m.0glkp4v | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 | m.0m_1x_7 | m.0mwh9_v | m.0my74fy | m.0n4htv8 | m.0n4kzq9 | m.0n4psbw | m.0n4t7bh | m.0n5lv65 …(+12)
    --award_winner.awards_won--> m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm
    --actor.film--> Cocoon | Cotton Candy | EDtv | Gung Ho | Jay-Z: Made in America | Night Shift | m.0gz5dg6 | m.0gz5ds2 | m.0gz5fdc | m.0jtdhv
    m.0gz5ds2 | m.0gz5fdc | m.0jtdhv --performance.actor--> Ron Howard
    m.010g1d9b | m.05bkr1w | m.05bkyhb | m.05bm2lq | m.05brffw | m.07zqyp3 | m.07zqyxh | m.08lbx1t | m.08lby3g | m.090dj60 | m.090y4n1 | m.095h15z …(+40) --award_nomination.award_nominee--> Ron Howard
    m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm --award_honor.award_winner--> Ron Howard
    A Beautiful Mind | Angels & Demons | Apollo 13 | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Gung Ho | In the Heart of the Sea …(+12) --film.directed_by--> Ron Howard
    Leo and Loree --film.executive_produced_by--> Ron Howard
    A Beautiful Mind | Angels & Demons | Changeling | Cinderella Man | Clean and Sober | Closet Land | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Jay-Z: Made in America | Rush …(+4) --film.produced_by--> Ron Howard
── Clean and Sober ──
    --film.release_date_s--> m.0gl9mxs | m.0j57t1s | m.0j5945z
    m.0gl9mxs | m.0j57t1s | m.0j5945z --film_regional_release_date.film--> Clean and Sober
── The 'Burbs ──
    --film.release_date_s--> m.0j587l8 | m.0jsp5pk [film_release_region: United States of America]
    m.0cs4jzc | m.0j587l8 | m.0jsp5pk --film_regional_release_date.film--> The 'Burbs
── Closet Land ──
    --film.executive_produced_by--> Brian Grazer
    --film.release_date_s--> m.0j568g3
    m.0j568g3 --film_regional_release_date.film--> Closet Land
── Changeling ──
    --film.produced_by--> Brian Grazer
── Brian Grazer ──
    --award_nominee.award_nominations--> m.010g1d9b | m.05bm2lq | m.05brffw | m.08lbx1t | m.08lby3g | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 | m.0m_1x_7 | m.0mwh9_v | m.0my74fy | m.0n4htv8 | m.0n4kzq9 | m.0n4psbw | m.0n4t7bh | m.0n5lv65 | m.0nbbh6b | m.0svn6jn | m.0swwxv8 | m.0zxzdbd
    --award_winner.awards_won--> m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm
    m.010g1d9b | m.05bm2lq | m.05brffw | m.08lbx1t | m.08lby3g | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 …(+12) --award_nomination.award_nominee--> Brian Grazer
    m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm 
```
【新渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Changeling | Cinderella Man | Clean and Sober | Closet Land | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv)
▸ patterns: topic.image | film.release_date_s
── Clean and Sober ──
    --film.release_date_s--> m.0gl9mxs | m.0j57t1s | m.0j5945z
── Cocoon ──
    --topic.image--> m.0bg6160
    --film.release_date_s--> m.0j568bc
── EDtv ──
    --topic.image--> EdTV
    --film.release_date_s--> m.0j589v8
── Closet Land ──
    --film.release_date_s--> m.0j568g3
── Cotton Candy ──
    --film.release_date_s--> m.0ryb30f [film_release_region: United States of America]
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.release_date_s': {'direct': ['film.film.release_date_s'], 'bridge': ['common.topic.image', 'film.film.soundtrack', 'music.soundtrack.film']}, 'film.film_regional_release_date.film': {'direct': ['film.film_regional_release_date.film'], 'bridge': ['common.topic.image', 'film.film.soundtrack', 'music.soundtrack.film']}}
anchor_sequence: Ron Howard ⭢ 2-step chain (frontier: A Beautiful Mind | Angels & Demons | Apollo 13)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | Rush | Splash | The Da Vinci Code | The Dark Tower | The Dilemma | The Lost Symbol | The Missing | The Paper | Willow | Clean and Sober | Closet Land | The 'Burbs | Changeling  |  relations: film.release_date_s
旧: 模式 10 · 证据块 10 · 7942 字符
新: 模式 10 · 证据块 10 · 2920 字符

【旧渲染】
```
triples:
entities: Ron Howard | Clean and Sober | Closet Land | The 'Burbs | Changeling
▸ patterns: film.release_date_s | film.executive_produced_by ⭢ film.release_date_s | film.produced_by ⭢ film.release_date_s | film.written_by ⭢ film.release_date_s | film_regional_release_date.film ⭢ film.release_date_s | film.executive_produced_by ⭢ director.film ⭢ film.release_date_s | film.executive_produced_by ⭢ film.directed_by ⭢ film.release_date_s | film.produced_by ⭢ director.film ⭢ film.release_date_s | film.produced_by ⭢ film.directed_by ⭢ film.release_date_s | director.film ⭢ film.written_by ⭢ film.written_by ⭢ film.release_date_s
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b | m.05bkr1w | m.05bkyhb | m.05bm2lq | m.05brffw | m.07zqyp3 | m.07zqyxh | m.08lbx1t | m.08lby3g | m.090dj60 | m.090y4n1 | m.095h15z | m.095h1h2 | m.095h1tj | m.09k3n_p | m.09k3nwh | m.09k3p5_ | m.09sc2mb | m.09sc2vl | m.09tjrrf | m.09z78wm | m.0b6b2xw | m.0b6b38g | m.0gkjjsg | m.0glkp4v | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 | m.0m_1x_7 | m.0mwh9_v | m.0my74fy | m.0n4htv8 | m.0n4kzq9 | m.0n4psbw | m.0n4t7bh | m.0n5lv65 …(+12)
    --award_winner.awards_won--> m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm
    --producer.film--> Cocoon | Gung Ho | Night Shift | Parenthood | Splash | m.0gz5dg6 | m.0gz5ds2 | m.0gz5fdc | m.0jtdhv | Closet Land
    m.0gz5ds2 | m.0gz5fdc | m.0jtdhv --performance.actor--> Ron Howard
    m.010g1d9b | m.05bkr1w | m.05bkyhb | m.05bm2lq | m.05brffw | m.07zqyp3 | m.07zqyxh | m.08lbx1t | m.08lby3g | m.090dj60 | m.090y4n1 | m.095h15z …(+40) --award_nomination.award_nominee--> Ron Howard
    m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm --award_honor.award_winner--> Ron Howard
    Cocoon --film.directed_by--> Ron Howard
    Arrested Development | Leo and Loree | The 'Burbs --film.executive_produced_by--> Ron Howard
    Changeling | Clean and Sober | Closet Land | EDtv | The 'Burbs --film.produced_by--> Ron Howard
    Cotton Candy --film.written_by--> Ron Howard
── Clean and Sober ──
    --film.release_date_s--> m.0gl9mxs | m.0j57t1s | m.0j5945z
    m.0gl9mxs | m.0j57t1s | m.0j5945z --film_regional_release_date.film--> Clean and Sober
── The 'Burbs ──
    --film.release_date_s--> m.0j587l8 | m.0jsp5pk [film_release_region: United States of America]
    m.0j587l8 --film_regional_release_date.film--> The 'Burbs
    m.0jsp5pk --film_regional_release_date.film--> The 'Burbs
── Closet Land ──
    --film.executive_produced_by--> Brian Grazer
    --film.release_date_s--> m.0j568g3
    m.0j568g3 --film_regional_release_date.film--> Closet Land
── Changeling ──
    --film.produced_by--> Brian Grazer
── Brian Grazer ──
    --award_nominee.award_nominations--> m.010g1d9b | m.05bm2lq | m.05brffw | m.08lbx1t | m.08lby3g | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 | m.0m_1x_7 | m.0mwh9_v | m.0my74fy | m.0n4htv8 | m.0n4kzq9 | m.0n4psbw | m.0n4t7bh | m.0n5lv65 | m.0nbbh6b | m.0svn6jn | m.0swwxv8 | m.0zxzdbd
    --award_winner.awards_won--> m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm
    --producer.film--> EDtv | Splash
    m.010g1d9b | m.05bm2lq | m.05brffw | m.08lbx1t | m.08lby3g | m.0k1j58y | m.0lmtm8f | m.0ltshlx | m.0lv464x | m.0lv467q | m.0lv4ffs | m.0m0bwv0 …(+12) --award_nomination.award_nominee--> Brian Grazer
    m.03mlppw | m.04kcph9 | m.0lts_jr | m.0mvjqsr | m.0mwh6d0 | m.0n4xc5_ | m.0swwvgm --award_honor.award_winner--> Brian Grazer
    Arrested Development --film.produced_by--> Brian Grazer
    Splash --film.produced_by--> Brian Grazer
── Gung Ho ──
    --film.release_date_s--> m.0j585bd | m.0jsp0xb [film_release_region: United States of America] | m.0v3n_55 | m.0v3n___ | m.0v3n_dl | m.0v3n_lr | m.0v3n_s3 | m.0v3nycj [film_release_region: Australia] | m.0v3nylt | m.0v3nysd | m.0v3nyzf [film_release_region: Netherlands] | m.0v3nzrz 
```
【新渲染】
```
triples:
entities: Ron Howard
▸ patterns: topic.image | film.directed_by ⭢ topic.image | film.executive_produced_by ⭢ topic.image | film.executive_produced_by ⭢ film.release_date_s | film.produced_by ⭢ topic.image | film.produced_by ⭢ film.release_date_s | film.written_by ⭢ film.release_date_s | director.film ⭢ siteid.film | film.directed_by ⭢ siteid.film | film.produced_by ⭢ siteid.film
── Ron Howard ──
    --director.film--> EDtv
    --topic.image--> Ronhoward
    EDtv --film.directed_by--> Ron Howard
    Gung Ho --film.directed_by--> Ron Howard
    Gung Ho | Leo and Loree | The 'Burbs --film.executive_produced_by--> Ron Howard
    Beyond the Mat | Clean and Sober | Closet Land | EDtv | Far and Away | Jay-Z: Made in America | The 'Burbs --film.produced_by--> Ron Howard
    Cotton Candy --film.written_by--> Ron Howard
── Gung Ho ──
    --topic.image--> Poster from the Motion Picture
    --film.release_date_s--> m.0j585bd | m.0jsp0xb [film_release_region: United States of America] | m.0v3n_55 | m.0v3n___ | m.0v3n_dl | m.0v3n_lr | m.0v3n_s3 | m.0v3nycj [film_release_region: Australia] | m.0v3nylt | m.0v3nysd | m.0v3nyzf [film_release_region: Netherlands] | m.0v3nzrz | m.0v3nzz7
── EDtv ──
    --topic.image--> EdTV
    --film.release_date_s--> m.0j589v8
    m.0599zj7 --siteid.film--> EDtv
── Beyond the Mat ──
    --film.release_date_s--> m.0gl8q74 | m.0j56jmn
    m.0599sc3 --siteid.film--> Beyond the Mat
── Clean and Sober ──
    --film.release_date_s--> m.0gl9mxs | m.0j57t1s | m.0j5945z
── Far and Away ──
    --film.release_date_s--> m.0gl8xq2 | m.0j58rfq | m.0j58xjd
── Jay-Z: Made in America ──
    --film.release_date_s--> m.0zw34_y [film_release_region: Canada] | m.0zw34xn [film_regional_debut_venue: 2013 Toronto International Film Festival] | m.0zw355k [film_release_region: United States of America]
── The 'Burbs ──
    --film.release_date_s--> m.0j587l8 | m.0jsp5pk [film_release_region: United States of America]
── Leo and Loree ──
    --topic.image--> m.0hnhsz2
    --film.release_date_s--> m.0s91cct [film_release_region: United States of America]
── Closet Land ──
    --film.release_date_s--> m.0j568g3
note: ⚠ 'A Beautiful Mind' is 1 of ?film's 33 candidates — pass ?film or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.release_date_s': {'direct': ['film.film.release_date_s'], 'bridge': ['common.topic.image', 'film.film.soundtrack', 'music.soundtrack.film']}}
layer_action: repeat
```


============================================================================================
## CASE WebQTrn-567_df97b91c1a9dfe15bdad689feb59f791 s0
Q: What is the movie about a child prodigy that Ron Howard did?  f1=0.0
sg 调用数: 旧 6 / 新 6

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Ron Howard  |  relations: film.director.film | film.film.directed_by | film.produced_by | film.producer.films_executive_produced
旧: 模式 39 · 证据块 10 · 10636 字符
新: 模式 24 · 证据块 10 · 17278 字符

【旧渲染】
```
triples:
entities: Ron Howard
▸ patterns: director.film | film.directed_by | film.produced_by | producer.films_executive_produced | director.film ⭢ director.film | director.film ⭢ film.directed_by | director.film ⭢ film.produced_by | director.film ⭢ producer.films_executive_produced | film.directed_by ⭢ film.produced_by | film.directed_by ⭢ producer.films_executive_produced | film.executive_produced_by ⭢ director.film | film.executive_produced_by ⭢ film.directed_by | film.executive_produced_by ⭢ film.produced_by | film.produced_by ⭢ film.produced_by | film.produced_by ⭢ producer.films_executive_produced | film.written_by ⭢ film.produced_by | producer.film ⭢ director.film | producer.film ⭢ film.directed_by | producer.film ⭢ film.produced_by | producer.film ⭢ producer.films_executive_produced | producer.films_executive_produced ⭢ director.film | producer.films_executive_produced ⭢ film.directed_by | producer.films_executive_produced ⭢ film.produced_by | producer.films_executive_produced ⭢ producer.films_executive_produced | writer.film ⭢ film.produced_by | writer.film ⭢ producer.films_executive_produced | person.children ⭢ film.produced_by | person.parents ⭢ film.produced_by | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ producer.films_executive_produced | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ producer.films_executive_produced | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ producer.films_executive_produced | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ producer.films_executive_produced | award_winner.awards_won ⭢ award_winner.awards_won ⭢ film.produced_by | award_winner.awards_won ⭢ award_winner.awards_won ⭢ producer.films_executive_produced | actor.film ⭢ performance.film ⭢ director.film | actor.film ⭢ performance.film ⭢ film.directed_by | performance.actor ⭢ performance.film ⭢ director.film | performance.actor ⭢ performance.film ⭢ film.directed_by | performance.actor ⭢ performance.film ⭢ film.produced_by
── Ron Howard ──
    --award_nominee.award_nominations--> m.0zxmxhf [award: BAFTA Award for Best British Film; ceremony: 67th British Academy Film Awards; nominated_for: Rush] | m.0m_1x_7 [award_nominee: Brian Grazer | Bruce Akiyama | Carol Greenwald | David Kirschner | Dean Criswell | Ellen Cockrill; ceremony: 34th Daytime Creative Arts Emmy Awards; nominated_for: Curious George]
    --award_winner.awards_won--> m.03mlppw [award: Academy Award for Best Picture; award_winner: Brian Grazer; ceremony: 74th Academy Awards; honored_for: A Beautiful Mind]
    --person.children--> Bryce Dallas Howard
    --actor.film--> A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | Rush | Splash | The Da Vinci Code | The Dark Tower | The Dilemma | The Lost Symbol | The Missing | The Paper | Willow | Clean and Sober | Closet Land | The 'Burbs | Changeling | J. Edgar | m.0jtdhv [character: Steve] | m.0k7rl9 [character: Genius]
    --producer.films_executive_produced--> Arrested Development | Gung Ho | Leo and Loree | The 'Burbs
    --person.parents--> Rance Howard
    m.04hvctr | m.0gz5ds2 | m.0jtdhv | m.0k7rl9 --performance.actor--> Ron Howard
    m.08lby3g | m.0yfbbn9 | m.0zxmxhf | m.0zxzdbd --award_nomination.award_nominee--> Ron Howard
    Rance Howard --person.children--> Ron Howard
    A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto …(+17) --film.directed_by--> Ron Howard
    Arrested Development | Leo and Loree | The 'Burbs --film.executive_produced_by--> Ron Howard
    Bryce Dallas Howard --person.parents--> Ron Howard
   
```
【新渲染】
```
triples:
entities: Ron Howard
▸ patterns: award_honor.award_winner | award_nominee.award_nominations | award_winner.awards_won | director.film | film.directed_by | film.produced_by | producer.films_executive_produced | award_honor.award_winner ⭢ award_winner.awards_won | award_winner.awards_won ⭢ award_honor.award_winner | film.executive_produced_by ⭢ director.film | award_honor.award_winner ⭢ award_honor.honored_for ⭢ producer.films_executive_produced | award_honor.award_winner ⭢ award_winner.awards_won ⭢ producer.films_executive_produced | award_nomination.award_nominee ⭢ award_nominated_work.award_nominations ⭢ producer.films_executive_produced | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ award_honor.award_winner | award_nomination.award_nominee ⭢ award_nomination.award_nominee ⭢ award_winner.awards_won | award_nomination.award_nominee ⭢ award_nomination.nominated_for ⭢ producer.films_executive_produced | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ award_honor.award_winner | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ award_winner.awards_won | award_nomination.award_nominee ⭢ award_nominee.award_nominations ⭢ producer.films_executive_produced | award_nominee.award_nominations ⭢ award_nominated_work.award_nominations ⭢ producer.films_executive_produced | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ award_honor.award_winner | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ award_winner.awards_won | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ film.produced_by | award_nominee.award_nominations ⭢ award_nomination.nominated_for ⭢ producer.films_executive_produced
── Ron Howard ──
    --award_nominee.award_nominations--> m.010g1d9b [award_nominee: Carol Greenwald | David Kirschner | Dorothea Gillim | Ellen Cockrill | Jon Shapiro | Matthew Baughman; ceremony: 41st Daytime Creative Arts Emmy Awards; nominated_for: Curious George] | m.05bkr1w [award: Academy Award for Best Director; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05bkyhb [award: Academy Award for Best Director; ceremony: 74th Academy Awards; nominated_for: A Beautiful Mind] | m.05bm2lq [award: Academy Award for Best Picture; award_nominee: Brian Grazer | Eric Fellner; ceremony: 81st Academy Awards; nominated_for: Frost/Nixon] | m.05brffw [award: Academy Award for Best Picture; award_nominee: Ron Howard; ceremony: 74th Academy Awards; nominated_for: A Beautiful Mind] | m.07zqyp3 [award: BAFTA Award for Best Direction; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.07zqyxh [award: BAFTA Award for Best Direction; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lbx1t [award: BAFTA Award for Best Film; award_nominee: Brian Grazer; ceremony: 55th British Academy Film Awards; nominated_for: A Beautiful Mind] | m.08lby3g [award: BAFTA Award for Best Film; award_nominee: Brian Grazer | Eric Fellner | Tim Bevan; ceremony: 62nd British Academy Film Awards; nominated_for: Frost/Nixon] | m.090dj60 [ceremony: 34th Golden Globe Awards; nominated_for: The Shootist] | m.090y4n1 [ceremony: 35th Golden Globe Awards; nominated_for: Happy Days] | m.095h15z [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 53rd Golden Globe Awards; nominated_for: Apollo 13] | m.095h1h2 [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 59th Golden Globe Awards; nominated_for: A Beautiful Mind] | m.095h1tj [award: Golden Globe Award for Best Director - Motion Picture; ceremony: 66th Golden Globe Awards; nominated_for: Frost/Nixon] | m.09k3n_p [award: Critics' Choice Movie Award for Best Director; ceremony: 11th Critics' Choice Awards; nominated_for: Cinderella Man] | m.09k3nwh [award: Critics' Choice Movie Award for Best Director; ceremony: 14th Critics' Choice Awards; nominated_for: Frost/Nixon] | m.09k3p5_ [award: Critics' Choice Movie Award for Best D
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | Ransom | Rush | Splash | The Da Vinci Code | The Dark Tower | The Dilemma | The Lost Symbol | The Missing | The Paper | Willow | Clean and Sober | Closet Land | The 'Burbs | Changeling | J. Edgar | Arrested Development | Leo and Loree  |  relations: film.film_subject.films | film.film.subjects
旧: 模式 17 · 证据块 7 · 4956 字符
新: 模式 4 · 证据块 9 · 3882 字符

【旧渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: A Beautiful Mind | Angels & Demons | Apollo 13 | Arrested Development | Backdraft | Beyond the Mat | Changeling | Cinderella Man | Clean and Sober | Closet Land | Cocoon | Cotton Candy)
▸ patterns: film.subjects | film_subject.films | film.genre ⭢ film_subject.films | film.executive_produced_by ⭢ film.produced_by ⭢ film.subjects | film.executive_produced_by ⭢ film.produced_by ⭢ film_subject.films | film.executive_produced_by ⭢ producer.film ⭢ film.subjects | film.executive_produced_by ⭢ producer.film ⭢ film_subject.films | film.language ⭢ written_work.original_language ⭢ film.subjects | film.language ⭢ written_work.original_language ⭢ film_subject.films | film.production_companies ⭢ film.production_companies ⭢ film.subjects | film.production_companies ⭢ film.production_companies ⭢ film_subject.films | film.production_companies ⭢ production_company.films ⭢ film.subjects | film.production_companies ⭢ production_company.films ⭢ film_subject.films | producer.film ⭢ film.directed_by ⭢ film.subjects | producer.film ⭢ film.directed_by ⭢ film_subject.films | producer.film ⭢ producer.film ⭢ film.subjects | producer.film ⭢ producer.film ⭢ film_subject.films
── Ron Howard ──
    --producer.film--> Closet Land | The Lost Symbol
    Cinderella Man --film.directed_by--> Ron Howard
    EDtv --film.directed_by--> Ron Howard
── Closet Land ──
    --film.executive_produced_by--> Brian Grazer
    --film.genre--> Indie film
    --film.language--> English Language
    --film.production_companies--> Image Entertainment | Imagine Entertainment
    --film.subjects--> Pedophilia
    Pedophilia --film_subject.films--> Closet Land
── Brian Grazer ──
    --producer.film--> Cinderella Man | EDtv | The Lost Symbol
    Cinderella Man | EDtv | The Lost Symbol --film.produced_by--> Brian Grazer
── The Lost Symbol ──
    --written_work.original_language--> English Language
    --film.production_companies--> Imagine Entertainment
    --film.subjects--> Freemasonry
    Freemasonry --film_subject.films--> The Lost Symbol
── EDtv ──
    --film.production_companies--> Image Entertainment
    --film.subjects--> Television
    Television --film_subject.films--> EDtv
── Cinderella Man ──
    --film.subjects--> Boxing
    Image Entertainment --production_company.films--> Cinderella Man
── Clean and Sober ──
    --film.subjects--> Substance abuse
    Imagine Entertainment --production_company.films--> Clean and Sober
    Substance abuse --film_subject.films--> Clean and Sober
    Indie film --film_subject.films--> The Independent
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'A Beautiful Mind' narrows the relation pool to just that entity's edges — ?movie has 37 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?movie or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES 
```
【新渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: A Beautiful Mind | Angels & Demons | Apollo 13 | Arrested Development | Backdraft | Changeling | Cinderella Man | Clean and Sober | Closet Land | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas)
▸ patterns: film.genre | film.sequel | film.subjects | netflix_title.netflix_genres
── Cinderella Man ──
    --film.genre--> Biographical film | Drama | Historical period drama | Romance Film | Sports films
    --netflix_title.netflix_genres--> 20th Century Period Pieces | Biographical Dramas | Dramas Based on Real Life | Romantic Dramas | Romantic Movies | Sports Stories
    --film.subjects--> Boxing
── Dr. Seuss' How the Grinch Stole Christmas ──
    --film.genre--> Comedy | Family | Fantasy
    --netflix_title.netflix_genres--> Ages 11-12 | Book Characters | Family Adventures | Family Comedies | Family Features | Family Sci-Fi & Fantasy | Movies based on children's books | Movies for ages 11 to 12 | Movies/TV for ages 11 to 12
── A Beautiful Mind ──
    --film.genre--> Biographical film | Documentary film | Drama | Historical period drama | Psychological thriller | Romance Film
    --netflix_title.netflix_genres--> 20th Century Period Pieces | Biographical Dramas | Dramas Based on Real Life | Romantic Dramas | Romantic Movies
── Angels & Demons ──
    --film.genre--> Crime Fiction | Mystery | Thriller
    --netflix_title.netflix_genres--> Crime Thrillers | Dramas Based on Bestsellers | Dramas Based on the Book | Mysteries | Suspense
    --film.sequel--> The Lost Symbol
    The Da Vinci Code --film.sequel--> Angels & Demons
── Backdraft ──
    --film.genre--> Action Film | Crime Fiction | Drama | Mystery | Thriller
    --netflix_title.netflix_genres--> Action/Adventure | Crime Dramas | Crime Thrillers | Mysteries
── Drama ──
    Apollo 13 | Changeling | Clean and Sober | Closet Land | Cocoon --film.genre--> Drama
── Closet Land ──
    --film.genre--> Dystopia | Indie film | Political drama | Psychological thriller
    --film.subjects--> Pedophilia
── Cocoon ──
    --film.genre--> Film adaptation | Science Fiction
    --netflix_title.netflix_genres--> Dramas Based on Contemporary Literature | Dramas Based on the Book | Sci-Fi & Fantasy
── Apollo 13 ──
    --film.genre--> Adventure Film
    --netflix_title.netflix_genres--> 20th Century Period Pieces | Dramas Based on Real Life
    Arrested Development --film.genre--> Comedy
    Arrested Development --netflix_title.netflix_genres--> Television
    Changeling --film.genre--> Mystery | Thriller
    Clean and Sober --netflix_title.netflix_genres--> Medical drama
    Clean and Sober --film.subjects--> Substance abuse
    Cotton Candy --film.genre--> Comedy | Music
note: ⚠ 'A Beautiful Mind' is 1 of ?movie's 37 candidates — pass ?movie or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.film_subject.films': {'direct': ['film.film_subject.films'], 'bridge': ['film.film.genre', 'film.film.sequel', 'media_common.adapted_work.adaptations', 'media_common.netflix_title.netflix_genres']}, 'film.film.subjects': {'direct': ['film.film.subjects'], 'bridge': ['film.film.genre', 'film.film.sequel', 'media_common.adapted_work.adaptations', 'media_common.netflix_title.netflix_genres']}}
anchor_sequence: Ron Howard ⭢ 2-step chain (frontier: A Beautiful Mind | Angels & Demons | Apollo 13)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #2 调用: center: A Beautiful Mind  |  relations: film.film_subject.films | film.film.subjects
旧: 模式 3 · 证据块 5 · 2550 字符
新: 模式 3 · 证据块 6 · 1508 字符

【旧渲染】
```
triples:
entities: Ron Howard
▸ patterns: film.directed_by ⭢ film_subject.films | film.produced_by ⭢ film_subject.films | film_subject.films
── Ron Howard ──
    --award_winner.awards_won--> m.03mlppw
    --actor.film--> m.0jtdhv | m.0k7rl9
    m.04hvctr | m.0gz5ds2 | m.0jtdhv | m.0k7rl9 --performance.actor--> Ron Howard
    EDtv --film.directed_by--> Ron Howard
    The Lost Symbol --film.directed_by--> Ron Howard
    Clean and Sober | Closet Land | EDtv | The Lost Symbol --film.produced_by--> Ron Howard
── EDtv ──
    Television --film_subject.films--> EDtv
── The Lost Symbol ──
    Freemasonry --film_subject.films--> The Lost Symbol
── Clean and Sober ──
    Substance abuse --film_subject.films--> Clean and Sober
── Closet Land ──
    Pedophilia --film_subject.films--> Closet Land
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'A Beautiful Mind' narrows the relation pool to just that entity's edges — ?movie has 37 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?movie or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
layer_action: repeat
```
【新渲染】
```
triples:
entities: Ron Howard
▸ patterns: film.directed_by ⭢ film_subject.films | film.produced_by ⭢ film_subject.films | personal_film_appearance.person ⭢ personal_film_appearance.film ⭢ film_subject.films
── Ron Howard ──
    EDtv --film.directed_by--> Ron Howard
    The Lost Symbol --film.directed_by--> Ron Howard
    m.0gz61x3 --personal_film_appearance.person--> Ron Howard
    Clean and Sober | Closet Land | EDtv | The Lost Symbol --film.produced_by--> Ron Howard
── EDtv ──
    Television --film_subject.films--> EDtv
── The Lost Symbol ──
    Freemasonry --film_subject.films--> The Lost Symbol
── Clean and Sober ──
    Substance abuse --film_subject.films--> Clean and Sober
── Closet Land ──
    Pedophilia --film_subject.films--> Closet Land
── The Independent ──
    m.0gz61x3 --personal_film_appearance.film--> The Independent
    Indie film --film_subject.films--> The Independent
note: ⚠ 'A Beautiful Mind' is 1 of ?movie's 37 candidates — pass ?movie or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
layer_action: repeat
```

--------------------------------------------------------------------------------------------
### 块 #3 调用: center: A Beautiful Mind  |  relations: film.film_story_contributor.film_story_credits | film.film.story_by
旧: 模式 5 · 证据块 8 · 5384 字符
新: 模式 3 · 证据块 1 · 2731 字符

【旧渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: Boxing | Freemasonry | Pedophilia | Substance abuse | Television)
▸ patterns: film.story_by | director.film ⭢ film.story_by | director.film ⭢ film_story_contributor.film_story_credits | film.directed_by ⭢ film.story_by | film_story_contributor.film_story_credits
── Ron Howard ──
    --actor.film--> Angels & Demons | Apollo 13 | Cinderella Man | Cocoon | Far and Away | Frost/Nixon | Gung Ho | Inferno | Parenthood | Splash | The Da Vinci Code | The Dark Tower | The Lost Symbol | Willow | m.0jtdhv | m.0k7rl9
    m.0jtdhv --performance.actor--> Ron Howard
    m.0k7rl9 --performance.actor--> Ron Howard
    Angels & Demons | Apollo 13 | Cinderella Man | Cocoon | Far and Away | Frost/Nixon | Gung Ho | Inferno | Parenthood | Splash | The Da Vinci Code | The Dark Tower …(+2) --film.directed_by--> Ron Howard
    Far and Away --film.story_by--> Ron Howard
    Parenthood --film.story_by--> Ron Howard
── Dan Brown ──
    --film_story_contributor.film_story_credits--> Angels & Demons | Inferno | The Da Vinci Code | The Lost Symbol
    Angels & Demons | Inferno | The Da Vinci Code | The Lost Symbol --film.story_by--> Dan Brown
── Parenthood ──
    --film.story_by--> Babaloo Mandel | Lowell Ganz
    Babaloo Mandel --film_story_contributor.film_story_credits--> Parenthood
    Lowell Ganz --film_story_contributor.film_story_credits--> Parenthood
── Apollo 13 ──
    --film.story_by--> Jeffrey Kluger | Jim Lovell
    Jeffrey Kluger --film_story_contributor.film_story_credits--> Apollo 13
    Jim Lovell --film_story_contributor.film_story_credits--> Apollo 13
── Gung Ho ──
    --film.story_by--> Babaloo Mandel | Lowell Ganz
    Babaloo Mandel --film_story_contributor.film_story_credits--> Gung Ho
    Lowell Ganz --film_story_contributor.film_story_credits--> Gung Ho
── Far and Away ──
    --film.story_by--> Bob Dolman
    Bob Dolman --film_story_contributor.film_story_credits--> Far and Away
── Cinderella Man ──
    --film.story_by--> Cliff Hollingsworth
    Cliff Hollingsworth --film_story_contributor.film_story_credits--> Cinderella Man
── Cocoon ──
    --film.story_by--> David Saperstein
    David Saperstein --film_story_contributor.film_story_credits--> Cocoon
    Brian Grazer --film_story_contributor.film_story_credits--> Splash
    Frost/Nixon --film.story_by--> Peter Morgan
    George Lucas --film_story_contributor.film_story_credits--> Willow
    Peter Morgan --film_story_contributor.film_story_credits--> Frost/Nixon
    Splash --film.story_by--> Brian Grazer
    Stephen King --film_story_contributor.film_story_credits--> The Dark Tower
    The Dark Tower --film.story_by--> Stephen King
    Willow --film.story_by--> George Lucas
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: ⚠ Passing only 'A Beautiful Mind' narrows the relation pool to just that entity's edges — ?movie has 37 candidates whose relations may differ. For full-frontier relation discovery, pass the variable ?movie or ALL relevant entities together. A single literal is fine when the tree continuation handles it (the system walks from the root regardless). SEQUENCE EXTENSION applied to several frontier members — the new layer's edges are per-candidate: COMPARE them across the candidates (values, dates, ids) and commit the discriminated one(s), never the whole frontier roster. Mid-chain entities are HOPS, not answers. triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jo
```
【新渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: A Beautiful Mind)
▸ patterns: award_honor.honored_for | award_nominated_work.award_nominations | film.produced_by
── A Beautiful Mind ──
    --award_nominated_work.award_nominations--> m.05bkyhb [award: Academy Award for Best Director; award_nominee: Ron Howard; ceremony: 74th Academy Awards] | m.05brffw [award: Academy Award for Best Picture; award_nominee: Brian Grazer | Ron Howard; ceremony: 74th Academy Awards] | m.07zqyxh [award: BAFTA Award for Best Direction; award_nominee: Ron Howard; ceremony: 55th British Academy Film Awards] | m.08lbx1t [award: BAFTA Award for Best Film; award_nominee: Brian Grazer | Ron Howard; ceremony: 55th British Academy Film Awards] | m.095h1h2 [award: Golden Globe Award for Best Director - Motion Picture; award_nominee: Ron Howard; ceremony: 59th Golden Globe Awards] | m.09k3p5_ [award: Critics' Choice Movie Award for Best Director; award_nominee: Ron Howard; ceremony: 7th Critics' Choice Awards] | m.09sc2vl [award_nominee: Ron Howard; ceremony: 54th Directors Guild of America Awards] | m.0nbbh6b [award: Australian Film Institute Award for Best Foreign Film; award_nominee: Brian Grazer | Ron Howard; ceremony: 44th Australian Film Institute Awards]
    --film.produced_by--> Brian Grazer
    m.03mlppw | m.03mlsw7 | m.09dyy55 | m.09k3ns1 --award_honor.honored_for--> A Beautiful Mind
note: ⚠ 'A Beautiful Mind' is 1 of ?movie's 37 candidates — pass ?movie or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.film_story_contributor.film_story_credits': {'direct': ['film.film_story_contributor.film_story_credits'], 'bridge': ['award.award_honor.honored_for', 'award.award_nominated_work.award_nominations', 'award.award_nomination.nominated_for', 'award.award_winning_work.awards_won', 'film.film.produced_by', 'film.producer.film']}, 'film.film.story_by': {'direct': ['film.film.story_by'], 'bridge': ['award.award_honor.honored_for', 'award.award_nominated_work.award_nominations', 'award.award_nomination.nominated_for', 'award.award_winning_work.awards_won', 'film.film.produced_by', 'film.producer.film']}}
anchor_sequence: Ron Howard ⭢ 3-step chain (frontier: A Beautiful Mind)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #4 调用: center: Child prodigy  |  relations: film.film_subject.films | film.film.subjects
旧: 模式 3 · 证据块 2 · 1541 字符
新: 模式 3 · 证据块 2 · 675 字符

【旧渲染】
```
triples:
entities: Child prodigy
▸ patterns: film.subjects | film_subject.films | film_subject.films ⭢ film.subjects
── Child prodigy ──
    --film_subject.films--> Village of the Giants
    Village of the Giants --film.subjects--> Child prodigy
── Village of the Giants ──
    --film.subjects--> Giant
note: evidence blocks group triples by entity. 'h --rel--> t1 | t2' merges tails; m.xxx [key: value] shows a CVT's attributes inline. Compare blocks by bracketed values to discriminate candidates.
note: triples are the evidence: 'h --rel--> t1 | t2 | ...' (one head, many tails) or 'h1 | h2 | ... --rel--> tail' (many heads, one tail), '|' separates entities. Entities shown as m.xxx / g.xxx are EVENT nodes — abstract compound entities whose ATTRIBUTES are the event's content. EXAMPLE: 'm.0abc --performance.character--> Denver | --performance.actor--> Jon Favreau' means 'a performance event where the character Denver was played by Jon Favreau'. Event nodes are NEVER answer candidates and NEVER variable bindings — answer and bind with the event's named ATTRIBUTES (actor, character, office holder, jurisdiction). Discriminator attributes (dates, incumbent) appear as their own edges — read them to pick latest/largest/incumbent. Each subgraph shows the FULL evidence its pattern paths justify — an edge may legitimately reappear across subgraphs with its complete tail set. Pick the next center FROM these triples.
relation_expansion: {'film.film.subjects': {'direct': ['film.film.subjects'], 'bridge': ['film.film_subject.films']}}
```
【新渲染】
```
triples:
entities: Child prodigy
▸ patterns: film.subjects | film_subject.films | film_subject.films ⭢ film.subjects
── Child prodigy ──
    --film_subject.films--> Village of the Giants
    Village of the Giants --film.subjects--> Child prodigy
── Village of the Giants ──
    --film.subjects--> Giant
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'film.film.subjects': {'direct': ['film.film.subjects'], 'bridge': ['film.film_subject.films']}}
```

--------------------------------------------------------------------------------------------
### 块 #5 调用: center: Village of the Giants  |  relations: film.director.film | film.film.directed_by | film.produced_by | film.producer.films_executive_produced
旧: 模式 24 · 证据块 10 · 7718 字符
新: 模式 12 · 证据块 10 · 4886 字符

【旧渲染】
```
triples:
entities: Child prodigy  (sequence root; this layer applies to the frontier: Village of the Giants)
▸ patterns: film.subjects ⭢ director.film | film.subjects ⭢ film.directed_by | film.subjects ⭢ film.produced_by | director.film | film.directed_by | film.produced_by | producer.films_executive_produced | director.film ⭢ director.film | film.story_by ⭢ film.directed_by | film_story_contributor.film_story_credits ⭢ director.film | film_story_contributor.film_story_credits ⭢ film.directed_by | producer.film ⭢ film.directed_by | topic.notable_types ⭢ topic.notable_types ⭢ director.film | topic.notable_types ⭢ topic.notable_types ⭢ film.directed_by | film.genre ⭢ film.genre ⭢ director.film | film.genre ⭢ film.genre ⭢ film.directed_by | film.genre ⭢ netflix_title.netflix_genres ⭢ producer.films_executive_produced | film.starring ⭢ performance.actor ⭢ film.produced_by | performance.film ⭢ performance.actor ⭢ director.film | performance.film ⭢ performance.actor ⭢ film.directed_by | performance.film ⭢ performance.actor ⭢ film.produced_by | performance.film ⭢ performance.actor ⭢ producer.films_executive_produced | object_profile.prominent_type ⭢ topic.notable_types ⭢ producer.films_executive_produced | object.type ⭢ topic.notable_types ⭢ producer.films_executive_produced
── Child prodigy ──
    Village of the Giants --film.subjects--> Child prodigy
── Village of the Giants ──
    --film.directed_by--> Bert I. Gordon
    --film.genre--> Adventure Film | Cult film | Comedy
    --topic.notable_types--> Film
    --film.produced_by--> Bert I. Gordon
    --object_profile.prominent_type--> Film
    --film.starring--> m.02vbp6p | m.0k7rl9 [character: Genius]
    --film.story_by--> Bert I. Gordon
    --object.type--> Film
    Bert I. Gordon | m.02vbp6p | m.0k7rl9 --director.film--> Village of the Giants
    Bert I. Gordon --film_story_contributor.film_story_credits--> Village of the Giants
── Ron Howard ──
    --actor.film--> A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto | Gung Ho | In the Heart of the Sea | Inferno | Jay-Z: Made in America | Night Shift | Parenthood | Presidential Reunion | The Missing | m.0k7rl9 [character: Genius]
    --producer.films_executive_produced--> Arrested Development | Gung Ho | Leo and Loree | The 'Burbs
    m.0k7rl9 --performance.actor--> Ron Howard
    A Beautiful Mind | Angels & Demons | Apollo 13 | Backdraft | Cinderella Man | Cocoon | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Far and Away | Frost/Nixon | Grand Theft Auto …(+8) --film.directed_by--> Ron Howard
    A Beautiful Mind | Angels & Demons | Beyond the Mat | Changeling | Cinderella Man | Clean and Sober | Closet Land | Cowboys & Aliens | Curious George | Curious George 2: Follow That Monkey! | Dr. Seuss' How the Grinch Stole Christmas | EDtv …(+5) --film.produced_by--> Ron Howard
── Film ──
    American Graffiti | Angels & Demons | Backdraft | Beyond the Mat | Clean and Sober | Closet Land | Cotton Candy | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Frost/Nixon | Gung Ho | J. Edgar …(+14) --topic.notable_types--> Film
── Jay-Z: Made in America ──
    Diane Weyermann | Erica Huggins | Jay-Z | Jeffrey Skoll | Jon Kamen | Paul Chibe | Sidney Beaumont | Steve Stoute --producer.films_executive_produced--> Jay-Z: Made in America
── Todd Hallowell ──
    --producer.films_executive_produced--> Angels & Demons | Dr. Seuss' How the Grinch Stole Christmas | EDtv | Frost/Nixon | Ransom | The Alamo | The Da Vinci Code | The Dilemma
── Bert I. Gordon ──
    --director.film--> The Food of the Gods
    The Food of the Gods --film.directed_by--> Bert I. Gordon
── Frost/Nixon ──
    Karen Kehela --producer.films_executive_produced--> Frost/Nixon
    Peter Morgan --producer.films_executive_produced--> Frost/Nixon
── Angels & Demons ──
    Dan Brown --producer.films_executive_produced
```
【新渲染】
```
triples:
entities: Ron Howard  (sequence root; this layer applies to the frontier: Village of the Giants)
▸ patterns: award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ actor.film ⭢ film.starring | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ actor.film ⭢ performance.film | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ actor.film ⭢ film.starring | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ actor.film ⭢ performance.film | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ actor.film ⭢ film.starring ⭢ film.prequel | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ actor.film ⭢ film.starring ⭢ performance.film | award_nominee.award_nominations ⭢ award_nominee.award_nominations ⭢ actor.film ⭢ film.starring ⭢ film.prequel | director.film | film.prequel | film.starring | film_story_contributor.film_story_credits | award_nominee.award_nominations ⭢ award_nomination.award_nominee ⭢ actor.film
── Ron Howard ──
    --award_nominee.award_nominations--> m.0v4_x4x [award: Primetime Emmy Award for Outstanding Children's Program; ceremony: 34th Primetime Emmy Awards; nominated_for: Through the Magic Pyramid] | m.0zgtpgn [ceremony: 20th Screen Actors Guild Awards; nominated_for: Arrested Development] | m.0n5lv65 [award_nominee: Brian Grazer | Bruce Richmond | Erik Bork | Graham Yost | Janace Tashjian | John P. Melfi; ceremony: Producers Guild of America Awards 1998; nominated_for: From the Earth to the Moon]
── Village of the Giants ──
    --film.starring--> m.02vbp6p | m.02vbct8 | m.02vbpfx | m.02vbpy5 | m.02vbxc4 | m.02vc637 | m.02vd155 | m.02vdcc7 | m.03l9s4y | m.045p3fq [special_performance_type: Uncredited] | m.0gkckfy | m.0gkclg6 | m.0k7rl4 | m.0k7rl9 [actor: Ron Howard; character: Genius] | m.0k7rlg | m.0k7rlm
    Bert I. Gordon --director.film--> Village of the Giants
    m.02vbp6p --performance.film--> Village of the Giants
    H. G. Wells --film_story_contributor.film_story_credits--> Village of the Giants
    The Food of the Gods --film.prequel--> Village of the Giants
── The 'Burbs ──
    --film.starring--> m.0cs4jzc | m.02t9_dv | m.02vbw8c | m.03jpjwn | m.03jqk69 | m.03jsg8s | m.03jspdl | m.0crs4gs | m.0cry7vd | m.0cs1m1_ | m.0csdqj9 | m.0csr65x | m.0gcgytm | m.0k4m8r | m.0k4m8x | m.0k4m96
    m.0cs4jzc --performance.film--> The 'Burbs
── Grand Theft Auto ──
    --film.starring--> m.0cf_kmk | m.012zgzm4 | m.02vbsyn | m.02vc0b2 | m.04hvctr [actor: Ron Howard; character: Sam Freeman] | m.0cg0t64 | m.0cg7p9g | m.0cs3hss [actor: Clint Howard]
    m.0cf_kmk --performance.film--> Grand Theft Auto
── Inferno ──
    --film.starring--> g.11b70v3xbj | g.11b7xfzlry | g.11b7xksjgn | g.11btwg_m1x | g.11btwjcccm | g.11btwjcws8
── Rance Howard ──
    --actor.film--> m.02vbp6p | m.0cf_kmk | m.0cs4jzc | m.0vs4ppm
    m.0v4_x4x --award_nomination.award_nominee--> Rance Howard
── Arrested Development ──
    --film.starring--> m.059v00g
    m.059v00g --performance.film--> Arrested Development
    m.0hn2r8q --performance.film--> Arrested Development
── Tom Hanks ──
    --award_nominee.award_nominations--> m.0n5lv65 [award_nominee: Brian Grazer | Bruce Richmond | Erik Bork | Graham Yost | Janace Tashjian | John P. Melfi; ceremony: Producers Guild of America Awards 1998; nominated_for: From the Earth to the Moon]
    --actor.film--> g.11b70v3xbj | m.0czymt8
── David Cross ──
    --actor.film--> m.059v00g
    m.0zgtpgn --award_nomination.award_nominee--> David Cross
── Jason Bateman ──
    --actor.film--> m.059v017
    m.0zgtpgn --award_nomination.award_nominee--> Jason Bateman
    The Lost Symbol --film.prequel--> Angels & Demons
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIB
```

