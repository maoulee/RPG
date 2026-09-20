# 渲染对比：原始 vs 选中路径重建器（无 LLM 回放，逐块并排）

锚点 = 同一条 retrieve_subgraph 调用（重放逐字喂入录制的 assistant 消息）。【旧】= v06_aligned 录制渲染；【新】= 选中路径重建器渲染。其余消息类型未变，不列。


============================================================================================
## CASE WebQTest-1379_255da87c2560e4248091e82a1c0686c5 s0
Q: What was Franz Liszt' career that had him ending up leading a religious organization before March 27  f1=0.0
sg 调用数: 旧 6 / 新 6

--------------------------------------------------------------------------------------------
### 块 #0 调用: center: Franz Liszt  |  relations: organization.organization_membership.member | organization.organization_member.member_of
旧: 模式 9 · 证据块 3 · 2907 字符
新: 模式 8 · 证据块 3 · 1749 字符

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
▸ patterns: fictional_character.based_on | topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member | image.appears_in_topic_gallery ⭢ influence_node.influenced ⭢ fictional_character.based_on
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --influence_node.influenced--> Fryderyk Chopin
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Fryderyk Chopin ──
    Frédéric Chopin --fictional_character.based_on--> Fryderyk Chopin
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Franz Liszt  |  relations: organization.organization.founders | organization.organization_founder.organizations_founded | people.person.employment
旧: 模式 13 · 证据块 3 · 3909 字符
新: 模式 9 · 证据块 2 · 2245 字符

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
▸ patterns: image.appears_in_topic_gallery ⭢ organization.founders | image.appears_in_topic_gallery ⭢ organization_founder.organizations_founded | image.appears_in_topic_gallery ⭢ person.employment_history | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ person.employment_history | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ person.employment_history
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
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
新: 模式 3 · 证据块 2 · 1555 字符

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
▸ patterns: image.appears_in_topic_gallery ⭢ profession.people_with_this_profession | topic.image ⭢ profession.people_with_this_profession | person_in_fiction.representations_in_fiction ⭢ profession.people_with_this_profession
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
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
新: 模式 11 · 证据块 3 · 2566 字符

【旧渲染】
```
{"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: fictional_character.based_on | image.appears_in_topic_gallery ⭢ organization_founder.organizations_founded | image.appears_in_topic_gallery ⭢ organization_member.member_of | image.appears_in_topic_gallery ⭢ organization_membership.member | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | topic.image ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization_membership.member | image.appears_in_topic_gallery ⭢ influence_node.influenced ⭢ fictional_character.based_on
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --influence_node.influenced--> Fryderyk Chopin
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
── Fryderyk Chopin ──
    Frédéric Chopin --fictional_character.based_on--> Fryderyk Chopin
note: SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization.organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
anchor_sequence: Franz Liszt ⭢ 1-step chain
layer_action: update layer 1 (replaced e.profession.people_with_this_profession)
```

--------------------------------------------------------------------------------------------
### 块 #5 调用: center: Franz Liszt  |  relations: organization.organization_founder.organizations_founded | organization.organization.founders | organization.organizatio
旧: [错误响应] {"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
新: 模式 6 · 证据块 2 · 2028 字符

【旧渲染】
```
{"error": "dispatch_retrieve_subgraph: 'dict' object has no attribute 'append'"}
```
【新渲染】
```
triples:
entities: Franz Liszt
▸ patterns: image.appears_in_topic_gallery ⭢ organization.founders | image.appears_in_topic_gallery ⭢ organization_membership.member | topic.image ⭢ organization.founders | topic.image ⭢ organization_membership.member | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_membership.member
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
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
新: 模式 11 · 证据块 3 · 2198 字符

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
▸ patterns: fictional_character.based_on | topic.image ⭢ organization.founders | topic.image ⭢ organization_founder.organizations_founded | topic.image ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization.founders | fictional_character.based_on ⭢ organization_founder.organizations_founded | fictional_character.based_on ⭢ organization_member.member_of | person_in_fiction.representations_in_fiction ⭢ organization.founders | person_in_fiction.representations_in_fiction ⭢ organization_founder.organizations_founded | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of | image.appears_in_topic_gallery ⭢ influence_node.influenced ⭢ fictional_character.based_on
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --influence_node.influenced--> Fryderyk Chopin
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
── Fryderyk Chopin ──
    Frédéric Chopin --fictional_character.based_on--> Fryderyk Chopin
note: Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.founders': {'direct': ['organization.organization.founders'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_founder.organizations_founded': {'direct': ['organization.organization_founder.organizations_founded'], 'bridge': ['fictional_universe.fictional_character.based_on']}, 'organization_member.member_of': {'direct': ['organization.organization_member.member_of'], 'bridge': ['fictional_universe.fictional_character.based_on']}}
```

--------------------------------------------------------------------------------------------
### 块 #1 调用: center: Freemasonry | Franz Liszt Academy of Music, Budapest  |  relations: organization.membership_organization.members | business.employment_tenure.company
旧: 模式 4 · 证据块 3 · 2835 字符
新: 模式 12 · 证据块 4 · 2842 字符

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
▸ patterns: topic.image ⭢ organization.founders ⭢ employment_tenure.company | topic.image ⭢ organization_founder.organizations_founded ⭢ employment_tenure.company | topic.image ⭢ organization_member.member_of ⭢ membership_organization.members | fictional_character.based_on ⭢ organization_membership.member ⭢ membership_organization.members | fictional_character.based_on ⭢ person.employment_history ⭢ employment_tenure.company | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of ⭢ membership_organization.members | employment_tenure.company | membership_organization.members | topic.image ⭢ organization_member.member_of | fictional_character.based_on ⭢ organization_membership.member | fictional_character.based_on ⭢ person.employment_history | person_in_fiction.representations_in_fiction ⭢ organization_member.member_of
── Franz Liszt ──
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
    Life of Franz Liszt --person_in_fiction.representations_in_fiction--> Franz Liszt
── Life of Franz Liszt ──
    --person.employment_history--> m.04kp4ft [person: Life of Franz Liszt]
    --organization_member.member_of--> m.0cr70y2 [organization: Freemasonry]
    --organization_founder.organizations_founded--> Franz Liszt Academy of Music, Budapest
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
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
新: 模式 8 · 证据块 4 · 2679 字符

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
▸ patterns: image.appears_in_topic_gallery ⭢ organization_membership.member | topic.image ⭢ organization_membership.member | fictional_character.based_on ⭢ organization_membership.member | fictional_character.based_on ⭢ employment_tenure.person ⭢ employment_tenure.company ⭢ employment_tenure.company | employer.employees | membership_organization.members | organization.founders | fictional_character.based_on ⭢ employment_tenure.person
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
── Life of Franz Liszt ──
    Franz Liszt Academy of Music, Budapest --organization.founders--> Life of Franz Liszt
    m.0cr70y2 --organization_membership.member--> Life of Franz Liszt
    m.04kp4ft --employment_tenure.person--> Life of Franz Liszt
── Franz Liszt Academy of Music, Budapest ──
    --employer.employees--> m.04kp4ft | m.0w1vp7h
    m.04kp4ft --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
    m.0w1vp7h --employment_tenure.company--> Franz Liszt Academy of Music, Budapest
── Freemasonry ──
    --membership_organization.members--> m.0cr70y2 [organization: Freemasonry]
note: ⚠ 'Freemasonry' is 1 of ?org's 2 candidates — pass ?org or all of them to compare their relations. (Tree continuation walks from the root regardless.) SEQUENCE EXTENSION: the new layer's edges are per-frontier-member — COMPARE across candidates and commit the discriminated one(s); mid-chain entities are HOPS, not answers. Evidence blocks group by entity; 'h --rel--> t1 | t2' merges tails. m.xxx/g.xxx are EVENT nodes — answer/bind their bracketed ATTRIBUTES, never the node; discriminator attributes (dates) are their own edges. Pick the next center FROM these triples.
relation_expansion: {'organization.organization_membership.member': {'direct': ['organization.organization_membership.member'], 'bridge': ['business.employment_tenure.company', 'organization.organization.founders', 'organization.organization_membership.organization']}, 'business.employment_tenure.company': {'direct': ['business.employment_tenure.company'], 'bridge': ['education.educational_institution_campus.educational_institution']}, 'business.employer.employees': {'direct': ['business.employer.employees'], 'bridge': ['education.educational_institution_campus.educational_institution']}}
anchor_sequence: Franz Liszt ⭢ 3-step chain (frontier: Franz Liszt Academy of Music, Budapest | Freemasonry)
layer_action: extend
```

--------------------------------------------------------------------------------------------
### 块 #3 调用: center: Freemasonry | Franz Liszt Academy of Music, Budapest  |  relations: organization.organization_type.organizations_of_this_type | organization.organization.organization_type | organization.
旧: 模式 16 · 证据块 5 · 4582 字符
新: 模式 12 · 证据块 4 · 2657 字符

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
▸ patterns: book.editions ⭢ book_subject.works ⭢ organization.organization_type | book.editions ⭢ book_subject.works ⭢ organization_sector.organizations_in_this_sector | book.editions ⭢ book_subject.works ⭢ organization_type.organizations_of_this_type | book.editions ⭢ written_work.subjects ⭢ organization.organization_type | book.editions ⭢ written_work.subjects ⭢ organization_sector.organizations_in_this_sector | book.editions ⭢ written_work.subjects ⭢ organization_type.organizations_of_this_type | image.appears_in_topic_gallery ⭢ person.religion ⭢ religion.is_part_of | topic.image ⭢ person.religion ⭢ religion.is_part_of | fictional_character.based_on ⭢ artist.genre ⭢ organization.organization_type | fictional_character.based_on ⭢ artist.genre ⭢ organization_sector.organizations_in_this_sector | fictional_character.based_on ⭢ artist.genre ⭢ organization_type.organizations_of_this_type | fictional_character.based_on ⭢ person.religion ⭢ religion.is_part_of
── Franz Liszt ──
    --image.appears_in_topic_gallery--> Life of Franz Liszt
    --fictional_character.based_on--> Life of Franz Liszt
    Franz Liszt, Vol. 1: The Virtuoso Years, 1811-1847 --book.editions--> Franz Liszt
    Life of Franz Liszt --topic.image--> Franz Liszt
── Classical music ──
    --organization_sector.organizations_in_this_sector--> ABRSM
    --organization_type.organizations_of_this_type--> ABRSM
    --book_subject.works--> Franz Liszt, Vol. 1: The Virtuoso Years, 1811-1847
    Life of Franz Liszt --artist.genre--> Classical music
    ABRSM --organization.organization_type--> Classical music
    Franz Liszt, Vol. 1: The Virtuoso Years, 1811-1847 --written_work.subjects--> Classical music
── Life of Franz Liszt ──
    --person.religion--> Catholicism
── Catholicism ──
    --religion.is_part_of--> Christianity
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

