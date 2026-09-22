# RSCC 人审重放 dump（轨迹块标记 + 倒序移除逐步概率）— 2026-09-22

对齐旧实现:证据按时间序拼接构成 prompt(score_layer_op_probs 的
Vseq/Vloo 同款,块=annotate_layer_ops 拆分);RSCC 移除=同一拼接序
里跳过被删块(保留块相对位置不变)。每块给旧标记(IG 级联 d/l/f/N/g/
lineage/cls + pathway 裁决/必要)与 RSCC 概率(p_ref→p_cf,ratio,
判据 ratio=p_cf/p_ref,<0.90=Informative 保留,≥0.90=移除)。



========== CASE WebQTrn-2784_b64250ae3c9d6c724133d09dad5593ec|s2 ==========
Q: What movie featuring Tupac was directed by Kirk M. Petruccelli?
gold=['Poetic Justice']  实际answer='Poetic Justice' f1=1.0
p0=0.01329  pF=0.4657  pG*(收缩后)=-
子图独立概率 [Tupac Shakur] = 0.3404
子图独立概率 [Kirk M. Petruccelli] = 0.2621

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
◆ 旧标记: cls=effective d=0.6006 l=0.3038 f=0.6006 N=1.0 g=★ lineage=- necessary=yes
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
◆ 旧标记: cls=effective d=0.0803 l=0.0803 f=0.3745 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 倒序收缩逐步概率迹（概率变化 + 结构必要性）──
  初始状态: p=0.4657 (块 [0, 1])
  块#0 [Tupac Shakur]: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  块#1 [Kirk M. Petruccell]: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  终态 p=-
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTest-626_01ad90831a03b6c5ef17898ccd80a639|s0 ==========
Q: What setting of the fictional universe Tempus Unbound is bisected by the Missouri River?
gold=['Kansas']  实际answer='Kansas' f1=1.0
p0=0.00386  pF=0.1826  pG*(收缩后)=-
子图独立概率 [Tempus Unbound] = 0.3361
子图独立概率 [Missouri River] = 0.2472

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
◆ 旧标记: cls=effective d=0.3354 l=0.142 f=0.3352 N=1.0 g=★ lineage=- necessary=yes
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
◆ 旧标记: cls=effective d=0.07733 l=0.04822 f=0.2291 N=1.0 g=- lineage=- necessary=yes
◆ RSCC: 结构必要 → 结构优先保留(不进概率删除)

── RSCC 倒序收缩逐步概率迹（概率变化 + 结构必要性）──
  初始状态: p=0.1826 (块 [0, 1])
  块#0 [Tempus Unbound]: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  块#1 [Missouri River]: 结构必要(删除断链) → 结构优先保留 (结构必要=是(删除断链))
  终态 p=-
  双通道小结: 结构必要块=['0', '1'] | 概率移除块=无 | 两通道无冲突



========== CASE WebQTrn-21_6671d5347b1b3cfe482cf5894cc6a05a|s0 ==========
Q: Who is the prime minister of where the currency used in the country, is Ethiopian birr?
gold=['Hailemariam Desalegn']  实际answer='Haile Selassie | Hailemariam Desalegn' f1=0.667
p0=0.4208  pF=0.7195  pG*(收缩后)=0.7388
子图独立概率 [Ethiopian birr] = 0.3479
子图独立概率 [Ethiopia] = 0.7388

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
◆ 旧标记: cls=effective d=0.2189 l=0.009404 f=0.2189 N=1.0 g=- lineage=✓ necessary=n/a
◆ RSCC: p 0.7195 → 移除后 0.7388  Δp=0.01929 (+2.7%)  ratio=1.027 → 移除  [结构: necessary=n/a pathway=ethiopian birr]

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
◆ 旧标记: cls=effective d=0.1368 l=0.1368 f=0.3393 N=0.944 g=★ lineage=- necessary=n/a
◆ RSCC: p 0.7388 → 移除后 0.3502  Δp=-0.3886 (-52.6%)  ratio=0.474 → 保留  [结构: necessary=n/a pathway=ethiopian birr]

── RSCC 倒序收缩逐步概率迹（概率变化 + 结构必要性）──
  初始状态: p=0.7195 (块 [0, 1])
  块#0 [Ethiopian birr] 结构=n/a(通路未达): p 0.7195 → 0.7388  Δp=0.01929 (+2.7%)  ratio=1.027 ⇒ Redundant-valid → 移除
  块#1 [Ethiopia] 结构=n/a(通路未达): p 0.7388 → 0.3502  Δp=-0.3886 (-52.6%)  ratio=0.474 ⇒ Informative → 保留
  终态 p=0.7388 (整体变化 +2.7%)
  双通道小结: 结构必要块=无 | 概率移除块=['0'] | 两通道无冲突

