"""Fixtures for the evidence presentation layer (overview + relation blocks).

Fixture families (specs/rendering_mechanism_design.md "呈现层" section):
  1. the historical/synthetic specimens — one per mechanism, at the
     PHASE-2.5 grammar (2026-08-23 user reviews of render dumps):
       C1 terminal records, C2 sibling-row folding, C3 multi-hop chains,
       C4 pattern-level overview (slots, one line per pattern),
       C5 branch-ref compressed submission,
       C6 SET anchors for multi-center (?var) walks — never per-member lines,
       C7 relation-name columns (formal head/tail column names are GONE),
       C8 entity capacity back to the old stack's 120 — ≤120 entities are
       ALWAYS fully displayed; only >120 truncates, and then with a ref.
     SEPARATOR HIERARCHY: L1 ``|`` never inside a cell, L2 ``(a; b)`` for
     in-cell entity lists, L3 ``[k=v; k=v]`` for record attrs.
  2. REAL evidence objects mined from finished trajectories
     (tests/evidence_display_real_fixtures.json) — CVT-dense / multi-relation
     / long-tail / multi-center subgraphs, re-audited through
     check_invariants (anchors + anchor_label honored when present).

candidates/note are assembled by the caller (retrieve_subgraph) and are out of
scope here — this suite covers the triples block only.
"""
import json
import os
import re
import unittest
from types import SimpleNamespace

from kgqa.stages.evidence_display import (
    BLOCK_CAP, CELL_CAP, CELL_LIST_CAP, ROW_CAP, _collect_patterns, build_view,
    check_invariants, render_evidence, render_records_compat,
)

RE = render_evidence


# ── specimen corpus ─────────────────────────────────────────────────────────
# 1. Ethiopia — 4-link gold chain: stitching turns pass-through hops into
#    CHAIN blocks (C3); every link entity survives in a chain row.
ETHIOPIA_CHAIN = [
    ("Ethiopia", "location.country.currency_formerly_used", "Ethiopian birr"),
    ("Ethiopian birr", "finance.currency.countries_used", "Ethiopia"),
    ("Ethiopia", "location.country.continent", "Africa"),
    ("Africa", "location.continent.countries", "Ethiopia"),
    ("Ethiopia", "location.country.capital", "Addis Ababa"),
    ("Addis Ababa", "location.administrative_division.country", "Ethiopia"),
]
# 2. Nordic — back-edge suppression + C2 fold: three countries sharing ONE
#    tail-set merge into a single row with an L2 heads cell.
NORDIC_BACKEDGE = [
    ("Norway", "location.country.nordic_countries", "Nordic countries"),
    ("Nordic countries", "common.topic.notable_for", "x"),   # noisy → dropped
    ("Sweden", "location.country.nordic_countries", "Nordic countries"),
    ("Finland", "location.country.nordic_countries", "Nordic countries"),
    ("Norway", "location.country.nordic_countries", "Nordic countries"),  # dup
]
# 3. Finland — date=value literals survive; the Euro CVT is a TERMINAL record.
FINLAND_DATE_VALUE = [
    ("Finland", "location.country.date_founded", "1917-12-06"),
    ("Euro", "finance.currency.introduced", "m.eur1"),
    ("m.eur1", "measurement_unit.dated_money_value.effective_date",
     "2002-01-01T00:00:00"),
    ("m.eur1", "measurement_unit.dated_money_value.value", "5.94573"),
]
# 4. Düsseldorf — kind_of edges are NOT dropped (non-empty payload survives).
DUSSELDORF_KIND_OF = [
    ("Düsseldorf", "location.location.containedby", "North Rhine-Westphalia"),
    ("Düsseldorf", "location.location.geonames_parent_places_kind", "m.g1"),
    ("m.g1", "location.geonames_parent_places.kind_of", "Kreisfreie Stadt"),
]
# 5. Gingrich — the center's chain is never severed: the position record
#    details print once; the second (US-House) spoke is a bare ref row.
GINGRICH_CHAIN = [
    ("Newt Gingrich", "government.politician.government_positions_held", "m.p1"),
    ("m.p1", "government.government_position_held.basic_title",
     "Speaker of the United States House of Representatives"),
    ("m.p1", "government.government_position_held.from", "2011-01-05"),
    ("United States House of Representatives",
     "government.governmental_jurisdiction.governing_officials", "m.p1"),
]
# 6. Faroese — full tail set under C8: one head, five tails → ONE folded row,
#    ALL tails inside the L2 cell (≤120 ⇒ fully visible).
FAROESE_TAILSET = [
    ("Denmark", "location.country.languages_spoken", t)
    for t in ["Danish", "Faroese", "Greenlandic", "German", "English"]
]
# 7. Angelina — hub CVT: the SAME award record reached via two spokes; its
#    attribute line prints exactly ONCE, the second spoke is a bare ref.
ANGELINA_BRACKET_ONCE = [
    ("Angelina Jolie", "award.award_nominee.award_nominations", "m.aw1"),
    ("Academy Awards", "award.award_category.winners", "m.aw1"),
    ("m.aw1", "award.award_honor.award", "Academy Award for Best Supporting Actress"),
    ("m.aw1", "award.award_honor.year", "1999"),
    ("m.aw1", "award.award_honor.ceremony", "Academy Awards"),
]
# 8. Sandler — spoke suppression + uniform hoist: every performance record
#    carries actor=Adam Sandler (uniform → (all:) once) but differs in film.
SANDLER_UNIFORM = [
    ("Adam Sandler", "film.performance.actor", f"m.s{i}") for i in range(1, 4)
] + [
    ("m.s1", "film.performance.actor", "Adam Sandler"),
    ("m.s1", "film.performance.film", "Billy Madison"),
    ("m.s1", "film.performance.character", "Billy Madison (character)"),
    ("m.s2", "film.performance.actor", "Adam Sandler"),
    ("m.s2", "film.performance.film", "Happy Gilmore"),
    ("m.s2", "film.performance.character", "Happy Gilmore (character)"),
    ("m.s3", "film.performance.actor", "Adam Sandler"),
    ("m.s3", "film.performance.film", "The Waterboy"),
    ("m.s3", "film.performance.character", "Bobby Boucher"),
]
# 9. Kim — bare CVT tails (zero non-noisy attrs) are dropped, named tails stay.
KIM_BARE_TAIL = [
    ("Kim Kardashian", "people.person.spouse_s", "m.sp1"),
    ("m.sp1", "people.marriage.type_of_union", "marriage"),
    ("Kim Kardashian", "people.person.nationality", "United States"),
    ("Kim Kardashian", "people.person.places_lived", "m.pl1"),
    # m.pl1 has ONLY type.* attrs → bare → dropped
    ("m.pl1", "type.type.instance", "x"),
]
# 10. Vicksburg — records group under their (head, relation): two sieges are
#     rows of ONE terminal table, date column sorted.
VICKSBURG_RECORDS = [
    ("Vicksburg", "battle.military_conflict.combatants", "m.w1"),
    ("Vicksburg", "battle.military_conflict.combatants", "m.w2"),
    ("m.w1", "battle.military_conflict.date", "1863-05-18"),
    ("m.w1", "battle.military_conflict.combatant", "Union Army"),
    ("m.w2", "battle.military_conflict.date", "1862-05-18"),
    ("m.w2", "battle.military_conflict.combatant", "Confederate Army"),
]
# 11. Brad Stevens — the phase-1 mockup case (mixed named edges + CVT records).
BRAD_STEVENS = [
    ("Brad Stevens", "basketball.basketball_coach.team", "Boston Celtics"),
    ("Boston Celtics", "basketball.basketball_team.head_coach", "Brad Stevens"),
    ("Brad Stevens", "sports.sports_team_coach.teams_coached", "m.0w3_qv3"),
    ("Brad Stevens", "sports.sports_team_coach.teams_coached", "m.0w48285"),
    ("Brad Stevens", "sports.sports_team_coach.teams_coached", "m.0w4828t"),
    ("m.0w3_qv3", "sports.sports_team_coach.coach_position.coach", "Brad Stevens"),
    ("m.0w3_qv3", "sports.sports_team_coach.coach_position.position", "Head coach"),
    ("m.0w3_qv3", "sports.sports_team_coach.coach_position.team", "Boston Celtics"),
    ("m.0w48285", "sports.sports_team_coach.coach_position.coach", "Brad Stevens"),
    ("m.0w48285", "sports.sports_team_coach.coach_position.position", "Assistant Coach"),
    ("m.0w48285", "sports.sports_team_coach.coach_position.team",
     "Butler Bulldogs men's basketball"),
    ("m.0w4828t", "sports.sports_team_coach.coach_position.coach", "Brad Stevens"),
    ("m.0w4828t", "sports.sports_team_coach.coach_position.position", "Head coach"),
    ("m.0w4828t", "sports.sports_team_coach.coach_position.team",
     "Butler Bulldogs men's basketball"),
]
# 12. Libya — has_no_value → to=(incumbent) cell picks the current holder.
LIBYA_INCUMBENT = [
    ("Libya", "x.office_holders", "m.pm1"),
    ("Libya", "x.office_holders", "m.pm2"),
    ("m.pm1", "x.office_holder", "Abdullah al-Thani"),
    ("m.pm1", "x.basic_title", "Prime minister"),
    ("m.pm1", "x.from", "2014-06-09T00:00:00"),
    ("m.pm1", "x.has_no_value", "To"),
    ("m.pm2", "x.office_holder", "Ali Zeidan"),
    ("m.pm2", "x.basic_title", "Prime minister"),
    ("m.pm2", "x.from", "2012-11-14T00:00:00"),
    ("m.pm2", "x.to", "2014-03-11T00:00:00"),
]
# 13. Ethiopia inflation — measurement (date, value) pairing stays per-record.
ETHIOPIA_MEASUREMENT = [
    ("Ethiopia", "x.inflation_rate", f"m.inf{i}") for i in range(5)
] + [
    ("m.inf0", "x.date", "1998-12-31T00:00:00"), ("m.inf0", "x.percentage", "4.12345678"),
    ("m.inf1", "x.date", "2001-12-31T00:00:00"), ("m.inf1", "x.percentage", "5.12345678"),
    ("m.inf2", "x.date", "2004-12-31T00:00:00"), ("m.inf2", "x.percentage", "6.12345678"),
    ("m.inf3", "x.date", "2007-12-31T00:00:00"), ("m.inf3", "x.percentage", "7.12345678"),
    ("m.inf4", "x.date", "2010-12-31T00:00:00"), ("m.inf4", "x.percentage", "8.12345678"),
]
# 14. noisy/self-loop/twin-CVT hygiene in one pile.
HYGIENE = [
    ("A", "common.topic.alias", "B"),                 # noisy edge → dropped
    ("A", "x.member", "B"),                           # hub-quartet → dropped
    ("A", "x.same", "a"),                             # self-loop → dropped
    ("A", "x.rel", "B"),
    ("A", "x.rel", "B"),                              # within-call dup → once
    ("A", "y.rel", "m.t1"),                           # twin CVTs, identical attrs
    ("A", "y.rel", "m.t2"),
    ("m.t1", "y.k", "V"), ("m.t2", "y.k", "V"),
]
# 15. multi-head record block → anchor column appears (multi-center calls).
MULTI_HEAD_RECORDS = [
    ("Boston Celtics", "sports.sports_team_coach.teams_coached", "m.c1"),
    ("Butler Bulldogs", "sports.sports_team_coach.teams_coached", "m.c2"),
    ("m.c1", "x.position", "Head coach"), ("m.c1", "x.coach", "Brad Stevens"),
    ("m.c2", "x.position", "Head coach"), ("m.c2", "x.coach", "Barry Collier"),
]
# 16. block-budget truncation: 6 relations → block cap + in-cell entity cap.
MANY_RELATIONS = [
    ("Hub", f"rel.r{i}", f"t{i}") for i in range(5)
] + [
    ("Hub", "rel.longtails", f"tail{i}") for i in range(7)
]
# 17. cell-budget truncation: >CELL_CAP value marked with ellipsis.
LONG_VALUE = [
    ("Q", "x.answer",
     "The Extremely Long Official Name Of Some Entity That Exceeds The Cell "
     "Cap By A Wide Margin So It Must Be Marked As Truncated"),
]
# 18. Mandela (real, WebQTest-1470) — the correction-1 specimen: a single
#     government_positions_held record renders as a TERMINAL line, attrs are
#     terminal values (no walkable-edge columns).
MANDELA_RECORD = [
    ("Nelson Mandela", "government.politician.government_positions_held",
     "m.040vj88"),
    ("m.040vj88", "government.government_position_held.office_holder",
     "Nelson Mandela"),
    ("m.040vj88", "government.government_position_held.jurisdiction_of_office",
     "South Africa"),
]
# 19. Mandela (real, capture 2 core) — corrections 2+3 specimen: sibling folds
#     + the book→subjects chain, trimmed to the discriminating core.
MANDELA_FOLD_CHAIN = [
    ("Nelson Mandela", "people.person.nationality", "South Africa"),
    ("Mandela House", "symbols.namesake.named_after", "Nelson Mandela"),
    ("Nelson Mandela Metropolitan University", "symbols.namesake.named_after",
     "Nelson Mandela"),
    ("Nandela Square", "symbols.namesake.named_after", "Nelson Mandela"),
    ("Mandela House", "location.location.containedby", "South Africa"),
    ("Nelson Mandela Metropolitan University", "location.location.containedby",
     "South Africa"),
    ("Nelson Mandela Square", "location.location.containedby", "South Africa"),
    ("Nelson Mandela", "symbols.name_source.namesakes", "Mandela House"),
    ("Nelson Mandela", "symbols.name_source.namesakes",
     "Nelson Mandela Metropolitan University"),
    ("Nelson Mandela", "symbols.name_source.namesakes", "Nelson Mandela Square"),
    ("Nelson Mandela", "book.author.book_editions_published",
     "Long Walk to Freedom"),
    ("Long Walk to Freedom", "book.written_work.subjects", "South Africa"),
]
# fix the intentional typo above (keep the entity real)
MANDELA_FOLD_CHAIN[3] = ("Nelson Mandela Square", "symbols.namesake.named_after",
                         "Nelson Mandela")
# 20. mid-hop FANOUT (C3 + L2): two parallel chains share start/end; the
#     middle hop merges into ONE parenthesized cell.
MID_HOP_FANOUT = [
    ("A", "x.r1", "m1"), ("A", "x.r1", "m2"),
    ("m1", "x.r2", "B"), ("m2", "x.r2", "B"),
]
# 21. separator-hierarchy fallback: an entity containing ';' is never joined
#     into an L2 cell — the rows stay unfolded (hierarchy beats compactness).
SEMICOLON_FALLBACK = [
    ("X; Y", "r.z", "T"), ("A2", "r.z", "T"),
]
# 22. multi-value attr with an unsafe value → first value + exact …+K marker.
UNSAFE_ATTR_VALUES = [
    ("H", "x.rec", "m.u1"),
    ("m.u1", "x.k", "a; b"), ("m.u1", "x.k", "c"),
]
# 23. Missouri River (real, WebQTest-626_74344) — the C4 specimen.
MISSOURI_RIVER = [
    ("Missouri River", "location.location.partially_containedby", "Iowa"),
    ("Missouri River", "location.location.partially_containedby", "Kansas"),
    ("Missouri River", "location.location.partially_containedby", "Missouri"),
    ("Missouri River", "location.location.partially_containedby", "Nebraska"),
    ("Iowa", "location.location.partially_contains", "Missouri River"),
    ("Kansas", "location.location.partially_contains", "Missouri River"),
    ("Missouri", "location.location.partially_contains", "Missouri River"),
    ("Nebraska", "location.location.partially_contains", "Missouri River"),
    ("Missouri River", "geography.body_of_water.bridges", "ASB Bridge"),
    ("Missouri River", "geography.body_of_water.bridges", "Bob Kerrey Pedestrian Bridge"),
    ("ASB Bridge", "transportation.bridge.body_of_water_spanned", "Missouri River"),
    ("Bob Kerrey Pedestrian Bridge", "transportation.bridge.body_of_water_spanned", "Missouri River"),
    ("ASB Bridge", "transportation.bridge.locale", "Kansas City"),
    ("Bob Kerrey Pedestrian Bridge", "transportation.bridge.locale", "Omaha"),
    ("Kansas City", "base.biblioness.bibs_location.state", "Missouri"),
    ("Omaha", "base.biblioness.bibs_location.state", "Nebraska"),
    ("Council Bluffs", "base.biblioness.bibs_location.state", "Iowa"),
    ("Des Moines", "base.biblioness.bibs_location.state", "Iowa"),
    ("Iowa", "government.governmental_jurisdiction.official_symbols", "m.04st84s"),
    ("Iowa", "government.governmental_jurisdiction.official_symbols", "m.04stk8v"),
    ("m.04st84s", "location.location_symbol_relationship.Kind_of_symbol", "State bird"),
    ("m.04st84s", "location.location_symbol_relationship.date_adopted", "1933-08:00"),
    ("m.04st84s", "location.location_symbol_relationship.symbol", "American goldfinch"),
    ("m.04stk8v", "location.location_symbol_relationship.Kind_of_symbol", "State Fish"),
    ("m.04stk8v", "location.location_symbol_relationship.date_adopted", "2001-08:00"),
    ("m.04stk8v", "location.location_symbol_relationship.symbol", "Channel catfish"),
]
MISSOURI_ANCHORS = ["Missouri River"]
# 24. Boston Celtics championships (C5/C8): 22 tails — under C8 this is
#     BELOW 120 ⇒ FULL display, no truncation, no ref.
BOSTON_CHAMPIONSHIPS = [
    ("Boston Celtics", "sports.sports_team.championships", t) for t in [
        "1946 NBA Finals", "1949 NBA Finals", "1951 NBA Finals",
        "1953 NBA Finals", "1955 NBA Finals", "1957 NBA Finals"]
] + [
    ("Boston Celtics", "sports.sports_team.championships", t) for t in [
        "1959 NBA Finals", "1960 NBA Finals", "1961 NBA Finals",
        "1962 NBA Finals", "1963 NBA Finals", "1964 NBA Finals",
        "1965 NBA Finals", "1966 NBA Finals", "1968 NBA Finals",
        "1969 NBA Finals", "1974 NBA Finals", "1976 NBA Finals",
        "1981 NBA Finals", "1984 NBA Finals", "1986 NBA Finals",
        "2008 NBA Finals"]
]
# 25. >120-tail set — the ONLY truncation regime left (C8): 120 shown,
#     …+N more in cell, exact counts + branch ref.
HUGE_TAILSET = [
    ("Hub", "rel.long_list", f"item {i:03d}") for i in range(137)
]
# 26. heads-side >120 (many heads, one tail) — ref anchors at the TAIL
#     (expansion is direction-agnostic: center matches either edge side).
HEADS_CAP_BIG = [
    (f"Head {i}", "rel.join_side", "Shared Tail") for i in range(130)
]
# 27. 12-entity block (the C8 specimen): fully visible, no marker, no ref.
TWELVE_ENTITIES = [
    ("Imagine Entertainment", "production.company.films", t) for t in [
        "Dr. Seuss' How the Grinch Stole Christmas", "Frost/Nixon",
        "The Missing", "Curious George", "Beyond the Mat", "Clean and Sober",
        "Closet Land", "EDtv", "Far and Away", "The 'Burbs",
        "Jay-Z: Made in America", "Katy Perry: Part of Me"]
]
# 28. Ron Howard (real, WebQTrn-567_11fd) — the C6 multi-center specimen,
#     trimmed: ?var-expanded films + release-date records + edited_by pairs.
RONHOWARD_MEMBERS = ["Cocoon", "EDtv", "Far and Away", "Backdraft", "Ransom",
                     "Gung Ho", "Night Shift", "Splash", "Willow", "Apollo 13"]
RONHOWARD_MC = [
    # release-date records hang off the films (terminal records, set anchor)
    ("Cocoon", "film.film.release_date_s", "m.d1"),
    ("EDtv", "film.film.release_date_s", "m.d2"),
    ("Far and Away", "film.film.release_date_s", "m.d3"),
    ("m.d1", "film.film_regional_release_date.release_date", "1985-06-21"),
    ("m.d1", "film.film_regional_release_date.film_release_region", "United States of America"),
    ("m.d2", "film.film_regional_release_date.release_date", "1999-03-12"),
    ("m.d3", "film.film_regional_release_date.release_date", "1992-05-22"),
    # edited_by: films → editors (fwd from the member side) + editor --film-->
    ("Cocoon", "film.film.edited_by", "Daniel P. Hanley"),
    ("Cocoon", "film.film.edited_by", "Mike Hill"),
    ("EDtv", "film.film.edited_by", "Daniel P. Hanley"),
    ("EDtv", "film.film.edited_by", "Mike Hill"),
    ("Far and Away", "film.film.edited_by", "Daniel P. Hanley"),
    ("Far and Away", "film.film.edited_by", "Mike Hill"),
    ("Backdraft", "film.film.edited_by", "Daniel P. Hanley"),
    ("Ransom", "film.film.edited_by", "Daniel P. Hanley"),
    ("Ransom", "film.film.edited_by", "Mike Hill"),
    ("Daniel P. Hanley", "film.editor.film", "Cocoon"),
    ("Daniel P. Hanley", "film.editor.film", "EDtv"),
    ("Daniel P. Hanley", "film.editor.film", "Far and Away"),
    ("Mike Hill", "film.editor.film", "Cocoon"),
    ("Mike Hill", "film.editor.film", "EDtv"),
    ("Mike Hill", "film.editor.film", "Far and Away"),
    ("Mike Hill", "film.editor.film", "Ransom"),
]



# 30. Germany (real, WebQTrn-849) — the C9 specimen: adjoin_s records with
#     BACK-EDGES from the neighbors (Poland/Czech --adjoin_s--> same records)
#     must NOT become their own pattern lines; overview anchored at the walk
#     start only. GERMANY_PATHS = the walk's real tree_data structures (C-raw).
GERMANY = [
    ("Germany", "location.location.partially_contains", "Alps"),
    ("Germany", "location.location.partially_contains", "North European Plain"),
    ("Germany", "location.location.adjoin_s", "m.g1"),
    ("Germany", "location.location.adjoin_s", "m.g2"),
    ("m.g1", "location.adjoining_relationship.adjoins", "Germany"),
    ("m.g1", "location.adjoining_relationship.adjoins", "Poland"),
    ("m.g2", "location.adjoining_relationship.adjoins", "Germany"),
    ("m.g2", "location.adjoining_relationship.adjoins", "Czech Republic"),
    ("Poland", "location.location.adjoin_s", "m.g1"),          # record back-edge
    ("Czech Republic", "location.location.adjoin_s", "m.g2"),  # record back-edge
    ("Alps", "location.location.partially_containedby", "Germany"),  # reverse hop
]
GERMANY_PATHS = [
    {"nodes": ["Germany", "m.g1: [adjoins=Germany, adjoins=Poland]"],
     "relations": ["location.location.adjoin_s"]},
    {"nodes": ["Germany", "m.g2: [adjoins=Germany, adjoins=Czech Republic]"],
     "relations": ["location.location.adjoin_s"]},
    {"nodes": ["Germany", "Alps"],
     "relations": ["location.location.partially_contains"]},
    {"nodes": ["Germany", "m.g1: [adjoins=Germany, adjoins=Poland]", "Poland"],
     "relations": ["location.location.adjoin_s",
                   "location.location.adjoin_s"]},
]

def _no_pipe_in_cells(lines):
    """Hard rule: L1 '|' never inside a rendered cell — every table line
    splits into exactly its column count."""
    bad = []
    headers = None
    for ln in lines:
        if ln.startswith("── "):
            headers = None
            continue
        if not ln.strip() or ln.startswith("  ") or \
                ln.lstrip().startswith("..."):
            continue
        n = len(ln.split("|"))
        if headers is None:
            headers = n
        elif n != headers:
            bad.append(ln)
    return bad


class TestSpecimens(unittest.TestCase):
    """Each specimen: shape assertions + full I1-I5/C4-C8 audit."""

    def test_01_ethiopia_chain_stitched(self):
        lines = RE(ETHIOPIA_CHAIN)
        joined = "\n".join(lines)
        # three 2-hop chains as full-shape TITLES + slot columns
        self.assertIn("── Ethiopia --currency_formerly_used--> ?x "
                      "--countries_used--> ?y ─", joined)
        self.assertIn("Ethiopia | currency_formerly_used | countries_used",
                      joined)
        self.assertIn("Ethiopia | Ethiopian birr         | Ethiopia", joined)
        for link in ("Ethiopian birr", "Africa", "Addis Ababa"):
            self.assertIn(link, joined)
        self.assertEqual(check_invariants(ETHIOPIA_CHAIN), [])

    def test_02_nordic_backedge_folded(self):
        lines = RE(NORDIC_BACKEDGE)
        joined = "\n".join(lines)
        self.assertIn("(Norway; Sweden; Finland) | Nordic countries", joined)
        self.assertNotIn("notable_for", joined)
        self.assertEqual(check_invariants(NORDIC_BACKEDGE), [])

    def test_03_finland_date_value(self):
        lines = RE(FINLAND_DATE_VALUE)
        joined = "\n".join(lines)
        self.assertIn("1917-12-06", joined)
        self.assertIn("effective_date=2002-01-01", joined)
        self.assertIn("value=5.95", joined)
        self.assertIn("(terminal records)", joined)
        self.assertEqual(check_invariants(FINLAND_DATE_VALUE), [])

    def test_04_dusseldorf_kind_of(self):
        lines = RE(DUSSELDORF_KIND_OF)
        joined = "\n".join(lines)
        self.assertIn("kind_of=Kreisfreie Stadt", joined)
        self.assertIn("North Rhine-Westphalia", joined)
        self.assertEqual(check_invariants(DUSSELDORF_KIND_OF), [])

    def test_05_gingrich_chain(self):
        lines = RE(GINGRICH_CHAIN)
        joined = "\n".join(lines)
        for link in ("Newt Gingrich", "Speaker of the United States House of "
                     "Representatives", "2011-01-05"):
            self.assertIn(link, joined)
        self.assertIn("(terminal records)", joined)
        self.assertEqual(joined.count("m.p1"), 2)
        self.assertEqual(check_invariants(GINGRICH_CHAIN), [])

    def test_06_faroese_tailset_folded(self):
        lines = RE(FAROESE_TAILSET)
        joined = "\n".join(lines)
        self.assertIn("  Denmark --languages_spoken--> ?x (5 instances)", lines)
        self.assertIn(
            "Denmark | (Danish; Faroese; Greenlandic; German; English)", joined)
        self.assertNotIn("…+", joined)        # C8: ≤120 ⇒ nothing hidden
        self.assertEqual(check_invariants(FAROESE_TAILSET), [])

    def test_07_angelina_bracket_once(self):
        lines = RE(ANGELINA_BRACKET_ONCE)
        joined = "\n".join(lines)
        self.assertEqual(joined.count("Academy Award for Best Supporting "
                                      "Actress"), 1)
        self.assertEqual(joined.count("m.aw1"), 2)
        self.assertEqual(check_invariants(ANGELINA_BRACKET_ONCE), [])

    def test_08_sandler_uniform(self):
        lines = RE(SANDLER_UNIFORM)
        joined = "\n".join(lines)
        for f in ("Billy Madison", "Happy Gilmore", "The Waterboy"):
            self.assertIn(f, joined)
        # C7: record table columns = [record relation, attrs...]
        self.assertIn("actor | film          | character", joined)
        self.assertIn("(all: actor=Adam Sandler)", joined)
        self.assertEqual(joined.count("(all:"), 1)
        self.assertEqual(check_invariants(SANDLER_UNIFORM), [])

    def test_09_kim_bare_tail(self):
        lines = RE(KIM_BARE_TAIL)
        joined = "\n".join(lines)
        self.assertNotIn("m.pl1", joined)
        self.assertIn("United States", joined)
        self.assertIn("type_of_union=marriage", joined)
        self.assertEqual(check_invariants(KIM_BARE_TAIL), [])

    def test_10_vicksburg_records(self):
        view = build_view(VICKSBURG_RECORDS)
        lines = RE(VICKSBURG_RECORDS)
        self.assertEqual(len(view.record_groups), 1)
        joined = "\n".join(lines)
        self.assertIn("Union Army", joined)
        self.assertIn("Confederate Army", joined)
        first_data = next(l for l in lines if l.startswith("m.w"))
        self.assertIn("1862-05-18", first_data)
        self.assertEqual(check_invariants(VICKSBURG_RECORDS), [])

    def test_11_brad_stevens_mockup(self):
        lines = RE(BRAD_STEVENS, anchors=["Brad Stevens"])
        joined = "\n".join(lines)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        self.assertEqual(len(ov), 2)
        self.assertIn("  Brad Stevens --teams_coached--> [3 records]", ov)
        self.assertIn("  Brad Stevens --team--> ?x --head_coach--> ?y", ov)
        # C7 titles + relation columns everywhere
        self.assertIn("── Brad Stevens --teams_coached--> [records] "
                      "(terminal records) ─", joined)
        self.assertIn("teams_coached | position        | team", joined)
        self.assertIn("── Brad Stevens --team--> ?x --head_coach--> ?y ─",
                      joined)
        self.assertIn("Brad Stevens | team           | head_coach", joined)
        self.assertIn("(all: coach=Brad Stevens)", joined)
        self.assertEqual(check_invariants(BRAD_STEVENS,
                                          anchors=["Brad Stevens"]), [])

    def test_12_libya_incumbent(self):
        lines = RE(LIBYA_INCUMBENT)
        joined = "\n".join(lines)
        self.assertIn("(incumbent)", joined)
        self.assertIn("from       | to", joined)
        self.assertIn("(all: basic_title=Prime minister)", joined)
        self.assertEqual(check_invariants(LIBYA_INCUMBENT), [])

    def test_13_ethiopia_measurement(self):
        lines = RE(ETHIOPIA_MEASUREMENT)
        joined = "\n".join(lines)
        self.assertIn("inflation_rate | date       | percentage", joined)
        first_data = next(l for l in lines if l.startswith("m.inf"))
        self.assertIn("1998-12-31", first_data)
        self.assertIn("4.12", first_data)
        self.assertEqual(check_invariants(ETHIOPIA_MEASUREMENT), [])

    def test_14_hygiene(self):
        view = build_view(HYGIENE)
        lines = RE(HYGIENE)
        joined = "\n".join(lines)
        self.assertEqual(view.dropped["noisy_edges"], 2)
        self.assertEqual(view.dropped["self_loops"], 1)
        self.assertEqual(view.dropped["dup_edges"], 1)
        self.assertEqual(view.dropped["dup_records"], 1)
        self.assertEqual(joined.count("| B"), 1)
        self.assertEqual(check_invariants(HYGIENE), [])

    def test_15_multi_head_records(self):
        lines = RE(MULTI_HEAD_RECORDS)
        joined = "\n".join(lines)
        # C7: anchor column first, then the record relation column
        self.assertIn("?node           | teams_coached | position   | coach",
                      joined)
        self.assertIn("Brad Stevens", joined)
        self.assertIn("Barry Collier", joined)
        self.assertEqual(check_invariants(MULTI_HEAD_RECORDS), [])

    def test_16_block_budget(self):
        lines = RE(MANY_RELATIONS, block_cap=3, cell_list_cap=3)
        joined = "\n".join(lines)
        self.assertIn("+3 more relations truncated", joined)
        self.assertEqual(check_invariants(MANY_RELATIONS, block_cap=3,
                                          cell_list_cap=3), [])
        # in-cell entity cap (EXPLICIT tight cap): ONE marker + C5 ref
        lines = RE(MANY_RELATIONS, block_cap=6, cell_list_cap=3)
        joined = "\n".join(lines)
        self.assertIn("…+4 more", joined)
        self.assertIn('+4 more (total 7). To answer with ALL of them, '
                      'include "#Hub::longtails" as one answer entity — the '
                      'system expands the ref to the full list.', joined)
        self.assertEqual(check_invariants(MANY_RELATIONS, block_cap=6,
                                          cell_list_cap=3), [])
        # DEFAULT caps (C8): the 7-tail set is fully shown, nothing hidden
        lines = RE(MANY_RELATIONS, block_cap=6)
        joined = "\n".join(lines)
        self.assertNotIn("…+", joined)
        self.assertNotIn("as one answer entity", joined)
        # record rows keep the ROW cap (measurement fixture, 5 records)
        lines = RE(ETHIOPIA_MEASUREMENT, row_cap=3)
        self.assertIn("... +2 more records (total 5)", "\n".join(lines))
        self.assertEqual(check_invariants(ETHIOPIA_MEASUREMENT, row_cap=3), [])

    def test_17_long_value(self):
        lines = RE(LONG_VALUE)
        self.assertIn("…", "\n".join(lines))
        self.assertEqual(check_invariants(LONG_VALUE), [])

    def test_18_mandela_terminal_record(self):
        lines = RE(MANDELA_RECORD)
        joined = "\n".join(lines)
        self.assertIn(
            "── Nelson Mandela --government_positions_held--> [records] "
            "(terminal records) ─", joined)
        self.assertIn(
            "m.040vj88 [office_holder=Nelson Mandela; "
            "jurisdiction_of_office=South Africa]", joined)
        self.assertEqual(check_invariants(MANDELA_RECORD), [])

    def test_19_mandela_fold_and_chain(self):
        lines = RE(MANDELA_FOLD_CHAIN, anchors=["Nelson Mandela"])
        joined = "\n".join(lines)
        # C2 folds under relation-named columns, anchor side first
        self.assertIn("(Mandela House; Nelson Mandela Metropolitan University; "
                      "Nelson Mandela Square) | South Africa", joined)
        self.assertIn("Nelson Mandela | (Mandela House; Nelson Mandela "
                      "Metropolitan University; Nelson Mandela Square)", joined)
        # C3 chain as a shape title + slot columns
        self.assertIn("── Nelson Mandela --book_editions_published--> ?x "
                      "--subjects--> ?y ─", joined)
        self.assertIn("Nelson Mandela | Long Walk to Freedom    | South Africa",
                      joined)
        self.assertEqual(check_invariants(MANDELA_FOLD_CHAIN,
                                          anchors=["Nelson Mandela"]), [])

    def test_20_mid_hop_fanout_l2(self):
        lines = RE(MID_HOP_FANOUT)
        joined = "\n".join(lines)
        self.assertIn("── A --r1--> ?x --r2--> ?y ─", joined)
        self.assertIn("(m1; m2)", joined)
        row = next(l for l in lines if "(m1; m2)" in l)
        self.assertEqual([c.strip() for c in row.split("|")],
                         ["A", "(m1; m2)", "B"])
        self.assertNotIn("more chains", joined)
        self.assertEqual(check_invariants(MID_HOP_FANOUT), [])

    def test_21_semicolon_fallback_unfolded(self):
        lines = RE(SEMICOLON_FALLBACK)
        joined = "\n".join(lines)
        self.assertIn("X; Y", joined)
        self.assertIn("A2", joined)
        self.assertNotIn("(X; Y", joined)
        self.assertEqual(check_invariants(SEMICOLON_FALLBACK), [])

    def test_22_unsafe_attr_values(self):
        lines = RE(UNSAFE_ATTR_VALUES)
        joined = "\n".join(lines)
        self.assertIn("a; b …+1 more", joined)
        self.assertEqual(check_invariants(UNSAFE_ATTR_VALUES), [])

    def test_23_missouri_river_pattern_overview(self):
        lines = RE(MISSOURI_RIVER, anchors=MISSOURI_ANCHORS)
        joined = "\n".join(lines)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        self.assertIn("  Missouri River --partially_containedby--> ?x "
                      "(3 instances)", ov)
        self.assertIn("  Missouri River <--partially_contains-- ?x "
                      "(3 instances)", ov)
        self.assertIn("  Missouri River --partially_containedby--> ?x "
                      "--partially_contains--> ?y", ov)
        for state in ("Iowa", "Kansas", "Missouri)", "Nebraska"):
            self.assertFalse(any(l.startswith(f"  {state} --partially_contains-->")
                                 for l in ov),
                             f"per-edge line survived: {state}")
        self.assertTrue(any("--bridges--> ?x" in l for l in ov), ov)
        # C9: non-start record groups (Iowa's symbols) produce NO pattern
        # line — they render in the terminal-records block below only
        self.assertFalse(any("official_symbols" in l for l in ov))
        view = build_view(MISSOURI_RIVER, anchors=MISSOURI_ANCHORS)
        self.assertEqual(len(ov), len(_collect_patterns(view)))
        self.assertLess(len(ov), view.n_groups)
        self.assertEqual(check_invariants(MISSOURI_RIVER,
                                          anchors=MISSOURI_ANCHORS), [])

    def test_24_boston_22_tails_fully_shown(self):
        """C8: 22 ≤ 120 ⇒ FULL display — no marker, no ref (the ref only
        fires above 120)."""
        lines = RE(BOSTON_CHAMPIONSHIPS)
        joined = "\n".join(lines)
        self.assertIn("Boston Celtics | championships", joined)
        for t in ("1946 NBA Finals", "1986 NBA Finals", "2008 NBA Finals"):
            self.assertIn(t, joined)
        self.assertNotIn("…+", joined)
        self.assertNotIn("as one answer entity", joined)
        self.assertEqual(check_invariants(BOSTON_CHAMPIONSHIPS), [])

    def test_25_huge_tailset_truncates_with_ref(self):
        """>120 (137) — the only truncation regime: 120 shown, exact counts,
        branch ref; token passes the LIVE answer-layer regex and expands."""
        lines = RE(HUGE_TAILSET)
        joined = "\n".join(lines)
        self.assertIn("…+17 more", joined)
        self.assertIn("+17 more (total 137). To answer with ALL of them, "
                      'include "#Hub::long_list" as one answer entity — the '
                      "system expands the ref to the full list.", joined)
        from kgqa.agent.tools import _BRANCH_RE, _expand_branch_refs
        m = re.search(r'include "(#[^"]+)"', joined)
        self.assertIsNotNone(_BRANCH_RE.match(m.group(1)))
        ctx = SimpleNamespace(
            h_ids=[0] * 137, r_ids=[0] * 137, t_ids=list(range(1, 138)),
            ents=["Hub"] + [f"item {i:03d}" for i in range(137)],
            rels=["rel.long_list"])
        got = _expand_branch_refs(ctx, [m.group(1)])
        self.assertEqual(len(got), 137)
        self.assertEqual(got[0], "item 000")
        self.assertEqual(check_invariants(HUGE_TAILSET), [])

    def test_26_heads_cap_ref_anchors_at_tail(self):
        """>120 hidden HEADS: the ref anchors at the (shown) TAIL — expansion
        is direction-agnostic, so #Shared Tail::join_side yields all heads."""
        lines = RE(HEADS_CAP_BIG)
        joined = "\n".join(lines)
        self.assertIn("…+10 more", joined)
        self.assertIn('"#Shared Tail::join_side" as one answer entity', joined)
        from kgqa.agent.tools import _BRANCH_RE, _expand_branch_refs
        m = re.search(r'include "(#[^"]+)"', joined)
        self.assertIsNotNone(_BRANCH_RE.match(m.group(1)))
        ctx = SimpleNamespace(
            h_ids=list(range(1, 131)), r_ids=[0] * 130, t_ids=[0] * 130,
            ents=["Shared Tail"] + [f"Head {i}" for i in range(130)],
            rels=["rel.join_side"])
        got = _expand_branch_refs(ctx, [m.group(1)])
        self.assertEqual(len(got), 130)
        self.assertEqual(check_invariants(HEADS_CAP_BIG), [])

    def test_27_rowcap_refs_for_dropped_groups(self):
        triples = [(f"H{i}", "rel.z", f"T{i}") for i in range(7)]
        lines = RE(triples, row_cap=3, block_cap=2)
        joined = "\n".join(lines)
        self.assertIn("+4 more edges (total 7)", joined)
        self.assertIn('"#H3::z" as one answer entity', joined)
        self.assertIn("(also: #H4::z | #H5::z)", joined)
        self.assertEqual(check_invariants(triples, row_cap=3, block_cap=2), [])

    def test_28_ronhoward_set_anchor_shapes(self):
        """C6: the ?var-expanded multi-center walk renders ONE line per
        (relation, direction) anchored at ?film — never per member; C7 shape
        titles + relation columns; release-date records as terminal rows."""
        lines = RE(RONHOWARD_MC, anchors=RONHOWARD_MEMBERS, anchor_label="?film")
        joined = "\n".join(lines)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        # set-anchored shapes, single digits
        self.assertIn("  ?film --edited_by--> ?x (9 instances)", ov)
        self.assertIn("  ?film <--film-- ?x (7 instances)", ov)
        self.assertIn("  ?film --release_date_s--> [3 records]", ov)
        self.assertLessEqual(len(ov), 6)
        # NO per-member pattern lines
        for m in RONHOWARD_MEMBERS:
            self.assertFalse(any(l.startswith(f"  {m} --") for l in ov),
                             f"per-member line survived: {m}")
        # C7: shape titles + ?film(10 centers) anchor column
        self.assertIn("── ?film --edited_by--> ?x ─", joined)
        self.assertIn("?film(10 centers)", joined)
        # editor side rows anchor-first (rev): (films) left, editors right
        self.assertIn("(Cocoon; EDtv; Far and Away; Ransom) | "
                      "(Daniel P. Hanley; Mike Hill)", joined)
        # 12-entity block (C8 specimen family): fully visible
        self.assertEqual(check_invariants(RONHOWARD_MC,
                                          anchors=RONHOWARD_MEMBERS,
                                          anchor_label="?film"), [])

    def test_29_twelve_entities_fully_shown(self):
        """C8 specimen: a 12-entity block is FULLY visible — no …+N more,
        no hidden, no ref (the dump's missing-4-answers bug)."""
        lines = RE(TWELVE_ENTITIES)
        joined = "\n".join(lines)
        self.assertIn("(Dr. Seuss' How the Grinch Stole Christmas; "
                      "Frost/Nixon; The Missing; Curious George; Beyond the "
                      "Mat; Clean and Sober; Closet Land; EDtv; Far and Away; "
                      "The 'Burbs; Jay-Z: Made in America; "
                      "Katy Perry: Part of Me)", joined)
        self.assertNotIn("…+", joined)
        self.assertNotIn("more", joined)
        self.assertEqual(check_invariants(TWELVE_ENTITIES), [])



    def test_30_germany_start_anchored_raw_paths(self):
        """C9 + C-raw: the overview is anchored at the WALK START only;
        record back-edge heads (Poland/Czech) never anchor lines; the raw
        tree_data structures render real multi-hop shapes."""
        lines = RE(GERMANY, anchors=["Germany"], patterns=GERMANY_PATHS)
        joined = "\n".join(lines)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        for l in ov:
            self.assertTrue(l.startswith("  Germany "),
                            f"non-start anchor survived: {l!r}")
        self.assertIn("  Germany --adjoin_s--> [2 records]", ov)
        self.assertIn("  Germany --partially_contains--> ?x (2 instances)", ov)
        self.assertIn("  Germany --adjoin_s--> ?x --adjoin_s--> ?y", ov)
        # C11: the walk did NOT walk the contains→containedby round trip —
        # the reverse edge renders in the SUPPLEMENT block (display-only)
        self.assertIn("── partially_containedby ─", joined)
        self.assertIn("Germany | Alps", joined)
        self.assertFalse(any("Poland --" in l or "Czech Republic --" in l
                             for l in ov))
        # rule 2: back-edge entities surface as record attr values
        self.assertIn("adjoins", joined)
        self.assertIn("(Germany; Poland)", joined)
        # C11: the pattern records block IS the record presentation — the
        # flattened supplement no longer re-renders covered records
        self.assertEqual(joined.count("(Germany; Poland)"), 1)
        # C-consist: pattern counts == block rows
        from kgqa.stages.evidence_display import build_view as _bv, \
            render_view as _rv
        _v = _bv(GERMANY, anchors=["Germany"], patterns=GERMANY_PATHS)
        _l, _rep = _rv(_v)
        for b in _rep["blocks"]:
            if "pattern_count" in b:
                self.assertEqual(b["n_rows_total"], b["pattern_count"],
                                 b["title"])
        self.assertEqual(check_invariants(GERMANY, anchors=["Germany"],
                                          patterns=GERMANY_PATHS), [])



    def test_31_eleanor_single_source_of_truth(self):
        """C11: overview counts == block instance rows (real capture with the
        walk's tree paths); candidates traceable to blocks."""
        data = json.load(open(os.path.join(os.path.dirname(__file__),
                                           "evidence_display_real_fixtures.json")))
        fx = next(f for f in data if f["tag"] == "eleanor_shapes")
        triples = [tuple(t) for t in fx["triples"]]
        lines = RE(triples, anchors=fx["anchors"],
                   anchor_label=fx.get("anchor_label"),
                   patterns=fx.get("patterns"))
        joined = "\n".join(lines)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        for l in ov:
            self.assertTrue(l.startswith("  Eleanor Roosevelt "), l)
        # chain blocks carry the SHAPE's terminal semantics: student chains
        # end at student values, institution chains at institutions
        self.assertIn("Eleanor Roosevelt | education              | student",
                      joined)
        self.assertIn("Eleanor Roosevelt | m.03j_v30 | Allenswood Academy",
                      joined)
        # records blocks show attrs once (I2) with (all:) hoist
        self.assertIn("(all: student=Eleanor Roosevelt)", joined)
        # candidates of THIS call (FDR/Anna etc. belong to the NEXT call's
        # students_graduates subgraph, audited there)
        cands = ["Eleanor Roosevelt", "Allenswood Academy", "The New School",
                 "Eleanor Roosevelt High School"]
        self.assertEqual(check_invariants(triples, anchors=fx["anchors"],
                                          anchor_label=fx.get("anchor_label"),
                                          patterns=fx.get("patterns"),
                                          candidates=cands), [])


class TestSeparatorHierarchy(unittest.TestCase):
    """Hard constraint: L1 '|' never appears inside a rendered cell."""

    def test_no_pipe_in_any_cell(self):
        corpus = [ETHIOPIA_CHAIN, NORDIC_BACKEDGE, FINLAND_DATE_VALUE,
                  DUSSELDORF_KIND_OF, GINGRICH_CHAIN, FAROESE_TAILSET,
                  ANGELINA_BRACKET_ONCE, SANDLER_UNIFORM, KIM_BARE_TAIL,
                  VICKSBURG_RECORDS, BRAD_STEVENS, LIBYA_INCUMBENT,
                  ETHIOPIA_MEASUREMENT, HYGIENE, MULTI_HEAD_RECORDS,
                  MANY_RELATIONS, LONG_VALUE, MANDELA_RECORD,
                  MANDELA_FOLD_CHAIN, MID_HOP_FANOUT, SEMICOLON_FALLBACK,
                  UNSAFE_ATTR_VALUES, MISSOURI_RIVER, BOSTON_CHAMPIONSHIPS,
                  HUGE_TAILSET, HEADS_CAP_BIG, RONHOWARD_MC,
                  TWELVE_ENTITIES]
        kw = {id(RONHOWARD_MC): {"anchors": RONHOWARD_MEMBERS,
                                 "anchor_label": "?film"},
              id(MISSOURI_RIVER): {"anchors": MISSOURI_ANCHORS},
              id(MANDELA_FOLD_CHAIN): {"anchors": ["Nelson Mandela"]},
              id(BRAD_STEVENS): {"anchors": ["Brad Stevens"]}}
        for corpus_triples in corpus:
            self.assertEqual(
                _no_pipe_in_cells(RE(corpus_triples,
                                     **kw.get(id(corpus_triples), {}))), [],
                f"cell-internal '|' in {corpus_triples[:2]}")

    def test_no_pipe_in_real_fixtures(self):
        path = os.path.join(os.path.dirname(__file__),
                            "evidence_display_real_fixtures.json")
        if not os.path.exists(path):
            self.skipTest("real fixtures not dumped yet")
        for fx in json.load(open(path)):
            lines = RE([tuple(t) for t in fx["triples"]],
                       anchors=fx.get("anchors") or (),
                       anchor_label=fx.get("anchor_label"))
            self.assertEqual(_no_pipe_in_cells(lines), [],
                             f"cell-internal '|' in {fx['case_id']}")


class TestDropInCompat(unittest.TestCase):
    """render_records_compat must stay a drop-in for _render_records."""

    def test_signature_and_return(self):
        shown = set()
        lines, n_overlap = render_records_compat(BRAD_STEVENS, shown)
        self.assertIsInstance(lines, list)
        self.assertEqual(n_overlap, 0)
        self.assertTrue(lines[0].startswith("pattern paths:"))

    def test_overlap_counted(self):
        shown = set()
        render_records_compat(BRAD_STEVENS, shown)
        _, n_overlap = render_records_compat(BRAD_STEVENS, shown)
        self.assertEqual(n_overlap, 4)   # 3 records + 1 chain key

    def test_no_shown_set(self):
        lines, n_overlap = render_records_compat(BRAD_STEVENS)
        self.assertGreater(len(lines), 0)
        self.assertEqual(n_overlap, 0)

    def test_empty_input(self):
        self.assertEqual(render_records_compat([]), ([], 0))

    def test_mandela_compat_with_anchors(self):
        lines, n_overlap = render_records_compat(
            MANDELA_FOLD_CHAIN, anchors=["Nelson Mandela"])
        self.assertEqual(n_overlap, 0)
        self.assertTrue(any("--subjects--> ?y" in ln for ln in lines))

    def test_ronhoward_compat_set_anchor(self):
        lines, n_overlap = render_records_compat(
            RONHOWARD_MC, anchors=RONHOWARD_MEMBERS, anchor_label="?film")
        self.assertEqual(n_overlap, 0)
        self.assertTrue(any(ln.startswith("  ?film --") for ln in lines))


class TestBudgetDefaults(unittest.TestCase):
    def test_budget_constants(self):
        # C8: entity capacity back to the OLD stack's economy-law level
        self.assertEqual((ROW_CAP, BLOCK_CAP, CELL_CAP, CELL_LIST_CAP),
                         (40, 12, 120, 120))

    def test_i4_purity_deterministic(self):
        a = RE(BRAD_STEVENS, anchors=["Brad Stevens"])
        b = RE(list(BRAD_STEVENS), anchors=["Brad Stevens"])
        self.assertEqual(a, b)


class TestRealTrajectoryFixtures(unittest.TestCase):
    """Evidence mined from real finished trajectories. Each fixture = the
    canonicalized all_triples a retrieve_subgraph call actually rendered
    (multi-center fixtures carry their member set + ?var label)."""

    PATH = os.path.join(os.path.dirname(__file__),
                        "evidence_display_real_fixtures.json")

    def test_real_fixtures(self):
        if not os.path.exists(self.PATH):
            self.skipTest("real fixtures not dumped yet")
        data = json.load(open(self.PATH))
        self.assertGreaterEqual(len(data), 6)
        for fx in data:
            triples = [tuple(t) for t in fx["triples"]]
            v = check_invariants(triples, anchors=fx.get("anchors") or (),
                                 anchor_label=fx.get("anchor_label"))
            self.assertEqual(v, [], f"{fx['case_id']}/{fx['tag']}: {v}")
            lines = RE(triples, anchors=fx.get("anchors") or (),
                       anchor_label=fx.get("anchor_label"))
            self.assertTrue(lines[0].startswith("pattern paths:"))
            view = build_view(triples, anchors=fx.get("anchors") or (),
                              anchor_label=fx.get("anchor_label"))
            n_ov = sum(1 for l in lines
                       if l.startswith("  ") and ("-->" in l or "<--" in l))
            if not any("more paths" in l for l in lines):
                n_pat = len(_collect_patterns(view))
                self.assertEqual(n_ov, n_pat, fx["case_id"])

    def test_ronhoward_real_multicenter_shapes(self):
        """The full 1377-triple multi-center capture: overview collapses to
        ONE line per (relation, direction) — single digits to teens, not 73+;
        anchors are set symbols; 12-entity cells fully shown."""
        data = json.load(open(self.PATH))
        fx = next(f for f in data if f["tag"] == "multi_center_var")
        triples = [tuple(t) for t in fx["triples"]]
        anchors, label = fx["anchors"], fx["anchor_label"]
        lines = RE(triples, anchors=anchors, anchor_label=label)
        ov = [l for l in lines
              if l.startswith("  ") and ("-->" in l or "<--" in l)]
        self.assertLessEqual(len(ov), 22)      # ≈ one per relation×direction
        set_lines = [l for l in ov if l.startswith(f"  {label} ")]
        self.assertGreaterEqual(len(set_lines), 8)
        # members never head an overview line
        for m in anchors:
            self.assertFalse(any(l.startswith(f"  {m} --") or
                                 l.startswith(f"  {m} <--") for l in ov))
        # C8: the biggest folded cell in this capture is ≤120 → no in-cell
        # truncation markers except any legitimately >120 hub
        self.assertEqual(check_invariants(triples, anchors=anchors,
                                          anchor_label=label), [])


if __name__ == "__main__":
    unittest.main()
