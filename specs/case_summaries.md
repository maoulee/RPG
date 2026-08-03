# SAPS — Case Studies (explicit tool calls + pruned evidence)
*Each stage shows the actual `tool:` call the model emitted (real args), then the
tool result PRUNED to the gold (✓) and error (✗) branches only — irrelevant
branches omitted for clarity. Thinking is not shown. Render each card to a figure.
Legend: ✓ gold-bearing / correct · ✗ wrong (off-intent / wrong-type / rejected) ·
△ omitted noise.*

═══════════════════════════════════════════════════════════════════════
CASE 1 · SUCCESS · multi-hop + superlative discriminator
WebQTest-832 (CWQ)   Q: Lou Seal is the mascot for the team that last won the World Series when?
Gold: 2014 World Series   Agent: 2014 World Series   ✓ Correct
═══════════════════════════════════════════════════════════════════════
▸ ① tool: decompose({
     "flow":[["Lou Seal","which team does this mascot belong to","?team"],
             ["?team","when did this team last win the World Series","?date"]],
     "entities":["Lou Seal"], "answer":"?date"})
   → GTE candidates per triple (pruned):
     f1 mascot→team : ✓ sports.mascot.team   △ 2 noise rels omitted
     f2 team→title  : ✓ sports.sports_team.championships   △ omitted

▸ ② tool: select_relations({
     "selections":[{"fact_id":"f1","relations":["sports.mascot.team","sports.sports_team.team_mascot"]},
                   {"fact_id":"f2","relations":["sports.sports_league_season.championship","sports.sports_team.championships"]}]})
   relation-pruning process — GTE returns 15 candidates per fact (recall-oriented);
   the model keeps the interpretation-covering relations and prunes the rest
   (✓ keep / ✗ prune). f1 (mascot → team), all 15 accounted for:
     ✓ sports.mascot.team                       (covers mascot→team)
     ✓ sports.sports_team.team_mascot           (covers team→mascot, reverse interp.)
     ✗ sports.sports_team.championships         (championship — belongs to f2, not f1)
     ✗ baseball.baseball_team.current_coaches   ┐
     ✗ baseball.baseball_team.current_manager   │
     ✗ baseball.baseball_team.league            │
     ✗ baseball.baseball_team.division          ├ management/league/roster — off-intent
     ✗ baseball.baseball_team.historical_managers│
     ✗ baseball.baseball_manager.current_team_managed
     ✗ baseball.baseball_league.teams           │
     ✗ baseball.baseball_historical_managerial_position.team ┘
     ✗ sports.sports_team.previously_known_as   ┐
     ✗ sports.sports_team.season_record         ├ history/records — off-intent
     ✗ sports.sports_team_season_record.team    │
     ✗ sports.defunct_sports_team.later_known_as┘
     → 2 kept / 13 pruned.  f2 (team→championship): 2 kept (championships, league-season.championship) / 13 pruned.
   → evidence tree (gold path):
     Lou Seal ─[sports.mascot.team]→ San Francisco Giants ─[championships]→ {2010 WS, 2012 WS, 2014 WS}

▸ ③ tool: expand_branches({"branch_ids":["1","2"]})
   → materialized triples (gold + error):
     (Lou Seal, mascot.team, SF Giants)
     (SF Giants, championships, 2014 World Series) ✓ HAS_GT
     (SF Giants, championships, 2010 World Series) ✗ (earlier win)
     (SF Giants, championships, 2012 World Series) ✗ (earlier win)

▸ ④ tool: answer({"entities":["2014 World Series"]})
   DISCRIMINATOR: "last won" → superlative (most recent)
   AUDIT: 2010 ✗ · 2012 ✗ · 2014 ✓
KEY: superlative discriminator narrowed 3 valid wins to the latest.

═══════════════════════════════════════════════════════════════════════
CASE 2 · SUCCESS · disambiguation via one-at-a-time role + CVT passthrough
WebQTest-590 (CWQ)   Q: Which man is the leader of the country that uses "Libya, Libya, Libya" as its anthem?
Gold: Abdullah al-Thani   Agent: Abdullah al-Thani   ✓ Correct
═══════════════════════════════════════════════════════════════════════
▸ ① tool: decompose({
     "flow":[["Libya, Libya, Libya","which country uses this song as its national anthem","?country"],
             ["?country","who is the leader of this country","?man"]],
     "entities":["Libya, Libya, Libya"], "answer":"?man"})
   → GTE candidates (pruned):
     f1 anthem→country: ✓ government.national_anthem.national_anthem_of   △ omitted
     f2 country→leader : ✓ government.government_position_held.office_holder   △ omitted

▸ ② tool: select_relations({
     "selections":[{"fact_id":"f1","relations":["location.country.national_anthem","government.national_anthem_of_a_country.country","government.national_anthem.national_anthem_of"]},
                   {"fact_id":"f2","relations":["government.politician.government_positions_held","government.government_position_held.office_holder"]}]})
   → evidence tree (gold + error):
     Anthem ─[national_anthem_of]→ CVT ─[country]→ Libya ─[gov_position.jurisdiction]→ CVT ─[office_holder]→ 11 leaders

▸ ③ tool: expand_branches({"branch_ids":["1","2"]})
   → materialized triples (gold + error; CVT-transparent):
     (Anthem, national_anthem_of, CVT) → (CVT, country, Libya)
     (Libya, gov_position_held.jurisdiction, CVT) → (CVT, office_holder, Abdullah al-Thani) ✓ HAS_GT
     (CVT, office_holder, Muammar Gaddafi) ✗ (past holder)
     (CVT, office_holder, Abdessalam Jalloud) ✗ (past holder)

▸ ④ tool: answer({"entities":["Abdullah al-Thani"]})
   DISCRIMINATOR: "the leader" → current holder of a one-at-a-time role
   AUDIT: 10 past holders ✗ · Abdullah al-Thani ✓ (current)
KEY: CVT passthrough surfaced the office_holder edge; role discriminator picked current out of 11.

═══════════════════════════════════════════════════════════════════════
CASE 3 · SUCCESS · list-all (no discriminator → keep every candidate)
WebQTrn-2069 (CWQ)   Q: What language is spoken in the location that appointed Michelle Bachelet to a governmental position?
Gold: {Spanish, Mapudungun, Rapa Nui, Aymara, Puquina}   Agent: all five   ✓ Correct
═══════════════════════════════════════════════════════════════════════
▸ ① tool: decompose({
     "flow":[["Michelle Bachelet","which location appointed this person to a governmental position","?location"],
             ["?location","what language is spoken in this location","?language"]],
     "entities":["Michelle Bachelet"], "answer":"?language"})
   → GTE candidates (pruned):
     f1 appoint→loc : ✓ government.government_position_held.appointed_by   △ omitted
     f2 loc→language : ✓ location.country.languages_spoken   △ omitted

▸ ② tool: select_relations({
     "selections":[{"fact_id":"f1","relations":["government.government_position_held.appointed_by","government.government_position_held.jurisdiction_of_office"]},
                   {"fact_id":"f2","relations":["location.country.languages_spoken","language.human_language.countries_spoken_in"]}]})
   → evidence tree (gold + error):
     Bachelet ─[appointed_by]→ CVT ─[jurisdiction]→ Chile ─[languages_spoken]→ 5 languages

▸ ③ tool: expand_branches({"branch_ids":["1","2"]})
   → materialized triples (gold + error):
     (Bachelet, appointed_by, CVT) → (CVT, jurisdiction_of_office, Chile)
     (Chile, languages_spoken, Spanish Language) ✓ HAS_GT
     (Chile, languages_spoken, Mapudungun / Puquina / Rapa Nui / Aymara) ✓ HAS_GT
     (CVT, jurisdiction_of_office, Chile) ✗ (candidate by type = country, not language)

▸ ④ tool: answer({"entities":["Spanish Language","Mapudungun Language","Puquina Language","Rapa Nui Language","Aymara language"]})
   DISCRIMINATOR: none ("spoken in" = bare retrieval)
   AUDIT: Chile ✗ (wrong type) · 5 languages ✓ (no discriminator → keep all)
KEY: no discriminator invented → kept every type-matching language = gold set.

═══════════════════════════════════════════════════════════════════════
CASE 4 · FAILURE · answer absent from the local subgraph (data ceiling)
WebQTrn-1938 (CWQ)   Q: What type of government is used in the country with Northern District?
Gold: Parliamentary system   Agent: ∅ (abstain)   ✗ Incorrect
═══════════════════════════════════════════════════════════════════════
▸ ① tool: decompose({
     "flow":[["Northern District","which country contains this district","?country"],
             ["?country","what type of government does this country use","?government_type"]],
     "entities":["Northern District"], "answer":"?government_type"})
   → GTE candidates (pruned):
     f1 district→country: ✓ location.administrative_division.country   △ omitted
     f2 country→gov-type : △ government.governmental_jurisdiction.government  (reaches a body, not a type)

▸ ② tool: select_relations({
     "selections":[{"fact_id":"f1","relations":["location.administrative_division.country","base.aareas.schema.administrative_area.administrative_parent"]},
                   {"fact_id":"f2","relations":["government.governmental_jurisdiction.government","base.aareas.schema.administrative_area_type.sovereignty"]}]})
   → evidence tree (gold-target vs error):
     Northern District ─[administrative_parent]→ Israel ─[gov_jurisdiction.government]→ Cabinet of Israel
                                            └─[form_of_government]→ ✗ ABSENT (edge not in subgraph)

▸ ③ tool: expand_branches({"branch_ids":["3","6"]})   (3 expansion rounds total)
   → materialized triples (gold-target vs error):
     (Northern District, administrative_parent, Israel) ✓ correct country located
     (Israel, governmental_jurisdiction.government, Cabinet of Israel) ✗ (a body, not a type)
     (Israel, form_of_government, ???) ✗ ABSENT — gold value edge not materialized

▸ ④ tool: answer({"entities":[]})
   DISCRIMINATOR: — (target value missing; cannot apply)
   AUDIT: Israel ✗ (country, wrong type) · Cabinet of Israel ✗ (body, wrong type) · ∅ no justifiable answer
ERROR TYPE: data ceiling — gold "Parliamentary system" is an unrecorded CVT
value whose edge is absent from the 2020-dump subgraph. Not a selection/reasoning
failure: the agent located Israel and explored 3 rounds, then honestly abstained.
═══════════════════════════════════════════════════════════════════════
