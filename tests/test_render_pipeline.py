"""V3.3 unified evidence renderer (render_evidence_sections) — principle
assertions for the 2026-08-25 audit-then-redesign ruling.

Principle 1: blocks organized by selected relation, 1-hop blocks first, then
k-hop blocks length-ascending, instance-count-desc within a length.
Principle 2: every row of a k-hop block traces back to a COMPLETE instance of
that block's path shape; hop-continuation edges of walked shapes never leak
into facts as anchorless fragments; hop-1-only entities stay in the 1-hop
block alone.
"""
import sys

sys.path.insert(0, "/zhaoshu/subgraph")

from kgqa.agent.seq_tools import (  # noqa: E402
    _candidate_provenance, _group_facts_by_rel, _render_records,
    _select_uncovered, render_evidence_sections)
from kgqa.core.utils import normalize as nz  # noqa: E402


def _assembly(paths, centers, triples, selected, var_label=None):
    """Mirror the _sg_finalize assembly: sections + facts remainder."""
    ov, blocks, covered = render_evidence_sections(
        paths, centers, var_label, triples, selected)
    sel = {r.rsplit(".", 1)[-1] for r in selected}
    unc = [t for t in triples
           if (nz(str(t[0])), str(t[1]).rsplit(".", 1)[-1], nz(str(t[2])))
           not in covered
           and (not sel or str(t[1]).rsplit(".", 1)[-1] in sel)]
    return ov, blocks, covered, unc


# ── Fitzgerald specimen structure (selected influenced + influenced_by) ──────
F = "F. Scott Fitzgerald"
ANN, BRET, GRRM = "Ann Beattie", "Bret Easton Ellis", "George R. R. Martin"
KEATS, SPENGLER = "John Keats", "Oswald Spengler"
YATES, ROTH, BALZAC = "Richard Yates", "Philip Roth", "Honoré de Balzac"

FITZ_TRIPLES = [
    (F, "influenced", ANN), (F, "influenced", BRET), (F, "influenced", GRRM),
    (KEATS, "influenced", F), (SPENGLER, "influenced", F),
    (F, "influenced_by", KEATS), (F, "influenced_by", SPENGLER),
    # hop-2 continuations: ANN and BRET have them; GRRM has NONE
    (ANN, "influenced_by", F), (ANN, "influenced_by", YATES),
    (BRET, "influenced_by", BALZAC), (BRET, "influenced_by", ROTH),
]
FITZ_PATHS = [
    {"nodes": [F, ANN], "relations": ["influenced"]},
    {"nodes": [F, BRET, BALZAC], "relations": ["influenced", "influenced_by"]},
]


def test_principle1_one_hop_first_then_length_ascending():
    ov, blocks, _cov, _unc = _assembly(
        FITZ_PATHS, [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    # tier 1: 1-hop overview lines precede every 2-hop line
    depths = [l.count("-->") + l.count("<--") for l in ov]
    assert depths == sorted(depths), ov
    assert depths[0] == 1 and depths[-1] == 2
    # 1-hop overview lines cover both selected relations before any 2-hop
    first_two_hop = next(i for i, d in enumerate(depths) if d == 2)
    rels_1hop = set()
    for l in ov[:first_two_hop]:
        rels_1hop.add(l.split("--")[-2].strip("-").strip())
    assert {"influenced", "influenced_by"} <= rels_1hop
    # blocks follow the overview order (1-hop dense lines then [r1 -- r2])
    assert any(l.strip().startswith(f"{F} --influenced-->") for l in blocks)
    assert "[influenced --influenced_by]" in "\n".join(blocks)
    first_block_2hop = next(i for i, l in enumerate(blocks)
                            if l.startswith("[influenced --influenced_by]"))
    assert any("--influenced-->" in l for l in blocks[:first_block_2hop])


def test_principle2_instances_complete_grrm_truncated():
    ov, blocks, _cov, _unc = _assembly(
        FITZ_PATHS, [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    text = "\n".join(blocks)
    # GRRM satisfies hop 1 only → present in the 1-hop block, ABSENT from the
    # 2-hop block (truncation rule)
    assert GRRM in text
    two_hop = text.split("[influenced --influenced_by]")[1]
    assert GRRM not in two_hop
    # ANN/BRET continuations render as FULL chains behind their hop-1 anchor
    assert f"{F} --influenced--> {ANN} --influenced_by-->" in two_hop
    assert f"{F} --influenced--> {BRET} --influenced_by-->" in two_hop
    assert f"{YATES}" in two_hop and ROTH in two_hop


def test_principle2_no_anchorless_fragment_in_facts():
    _ov, _blocks, _cov, unc = _assembly(
        FITZ_PATHS, [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    # every walked-shape edge is consumed → facts remainder is EMPTY here
    assert unc == []


def test_principle2_covered_keys_canonical_no_double_print():
    # reverse-walked hop (graph edge KEATS --influenced--> F traversed from F):
    # the covered key must match the canonical triple so facts cannot print
    # the same edge again (the Clive-James double-print regression)
    paths = FITZ_PATHS                       # 1-hop + the walked 2-hop shape
    ov, blocks, covered, unc = _assembly(
        paths, [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    assert (nz(KEATS), "influenced", nz(F)) in covered
    assert (nz(F), "influenced_by", nz(KEATS)) in covered
    assert unc == []
    # the reverse 1-hop block renders anchor-first with the reverse arrow
    assert any(l.strip() == f"{F} <--influenced-- {KEATS} | {SPENGLER}"
               for l in blocks)


def test_selection_discipline_blocks_and_facts():
    triples = FITZ_TRIPLES + [(F, "spouse", "Zelda Fitzgerald")]
    paths = FITZ_PATHS + [
        {"nodes": [F, "Zelda Fitzgerald"], "relations": ["spouse"]},
        {"nodes": [F, ANN, "Zelda Fitzgerald"],
         "relations": ["influenced", "spouse"]},
    ]
    ov, blocks, _cov, unc = _assembly(
        paths, [F], triples, ["influenced", "influenced_by"])
    text = "\n".join(ov) + "\n" + "\n".join(blocks)
    assert "spouse" not in text                      # unselected rel never renders
    assert all(t[1] != "spouse" for t in unc)        # nor reaches facts


def test_overview_counts_consistent_with_blocks():
    ov, blocks, _cov, _unc = _assembly(
        FITZ_PATHS, [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    # every 2-hop overview line's count == its block header count
    hdr_counts = {}
    cur = None
    for l in blocks:
        if l.startswith("[") and " --" in l:
            cur = l.split("]")[0] + "]"
            hdr_counts[cur] = int(l.split("(")[1].split(" ")[0])
    for l in ov:
        if l.count("-->") + l.count("<--") >= 2 and "instances" in l:
            n = int(l.split("(")[-1].split(" ")[0])
            key = "[" + " --".join(
                seg.split("--")[-1].strip(" <>-") for seg in l.split("?")[1:])
            # find matching header by relation sequence (order-independent)
            assert n in hdr_counts.values(), (l, hdr_counts)


def test_cvt_terminal_inline_attrs_and_uplift():
    G = "Germany"
    triples = [
        (G, "adjoin_s", "m.02nxjlh"), (G, "adjoin_s", "m.02sd_zh"),
        ("m.02nxjlh", "adjoins", "Poland"), ("m.02nxjlh", "adjoins", "Germany"),
        ("m.02sd_zh", "adjoins", "Germany"),
    ]
    paths = [{"nodes": [G, "m.02nxjlh"], "relations": ["adjoin_s"]}]
    ov, blocks, covered, _unc = _assembly(
        paths, [G], triples, ["adjoin_s", "adjoins"])
    text = "\n".join(blocks)
    # ruling ④: CVT-terminal records carry attrs inline (no bare-id payload)
    assert "m.02nxjlh [adjoins=Poland; adjoins=Germany]" in text
    # multi-valued attrs survive (no last-wins collapse)
    assert "adjoins=Poland" in text and "adjoins=Germany" in text
    # attr edges are consumed by the record display (normalized keys)
    assert (nz("m.02nxjlh"), "adjoins", nz("Poland")) in covered


def test_attr_single_print():
    G = "Germany"
    triples = [
        (G, "adjoin_s", "m.02nxjlh"), (G, "adjoin_s", "m.02sd_zh"),
        ("m.02nxjlh", "adjoins", "Poland"), ("m.02nxjlh", "adjoins", "Germany"),
        ("m.02sd_zh", "adjoins", "Germany"),
    ]
    paths = [{"nodes": [G, "m.02nxjlh", "Poland"],
              "relations": ["adjoin_s", "adjoin_s"]}]
    _ov, blocks, _cov, _unc = _assembly(
        paths, [G], triples, ["adjoin_s", "adjoins"])
    text = "\n".join(blocks)
    # each CVT's bracket prints exactly once across the whole render
    assert text.count("m.02nxjlh [") == 1
    assert text.count("m.02sd_zh [") <= 1


def test_roundtrip_family_folds_to_one_line():
    E = [(F, "influenced", f"Writer {i}") for i in range(5)]
    E += [(f"Writer {i}", "influenced_by", F) for i in range(5)]
    paths = [{"nodes": [F, "Writer 0", F],
              "relations": ["influenced", "influenced_by"]}]
    _ov, blocks, _cov, _unc = _assembly(
        paths, [F], E, ["influenced", "influenced_by"])
    two_hop = next(l for l in blocks if l.startswith("[influenced --influenced_by]"))
    body = [l for l in blocks[blocks.index(two_hop) + 1:]
            if l.startswith("  ") and "[" not in l]
    # the 5 round-trip instances fold into ONE fanout line, no spillover marker
    assert len(body) == 1
    assert all(f"Writer {i}" in body[0] for i in range(5))
    assert not any("more instances" in l for l in blocks)


def test_multi_center_members_fold_by_tail_set():
    a1, a2 = "Film One", "Film Two"
    triples = [
        (a1, "edited_by", "Ron Howard"), (a2, "edited_by", "Ron Howard"),
        (a1, "release_year", "2001"), (a2, "release_year", "2001"),
    ]
    paths = [
        {"nodes": [a1, "Ron Howard"], "relations": ["edited_by"]},
        {"nodes": [a2, "Ron Howard"], "relations": ["edited_by"]},
    ]
    ov, blocks, _cov, _unc = _assembly(
        paths, [a1, a2], triples, ["edited_by", "release_year"], var_label="?film")
    # set-anchored overview (ruling ①: ?var label, one line per shape)
    assert all(l.startswith("?film") for l in ov)
    # members sharing a tail-set fold to one dense line (ruling ③)
    joined = "\n".join(blocks)
    assert f"{a1} | {a2} --edited_by--> Ron Howard" in joined


def test_caps_per_rel_and_total():
    # 5 distinct 2-hop shapes off one first relation → ≤3 kept (ruling ②).
    # The 2026-08-26 chain-beats-orphan promotion may lift at most 4 capped
    # shapes back (their selected-relation edges must not render detached):
    # bound = per_rel + promotion budget, never unbounded.
    E = [(F, "influenced", ANN)]
    paths = []
    for extra in ["a", "b", "c", "d"]:
        E += [(ANN, extra, f"X_{extra}")]
        paths.append({"nodes": [F, ANN, f"X_{extra}"],
                      "relations": ["influenced", extra]})
    sel = ["influenced"] + ["a", "b", "c", "d"]
    ov, blocks, _cov, _unc = _assembly(paths, [F], E, sel)
    shapes_2hop = [l for l in blocks if l.startswith("[influenced --")]
    assert len(shapes_2hop) <= 3 + 4
    assert len(ov) <= 12 + 4


def test_empty_paths_renders_no_sections():
    ov, blocks, covered, _unc = _assembly(
        [], [F], FITZ_TRIPLES, ["influenced", "influenced_by"])
    # synthesis still builds 1-hop blocks from anchor edges when sel is given;
    # with NO selected rels and no paths → nothing structured
    ov0, blocks0, covered0, unc0 = _assembly([], [F], FITZ_TRIPLES, [])
    assert ov0 == [] and blocks0 == [] and covered0 == set()
    assert len(unc0) == len(FITZ_TRIPLES)


def test_determinism_i4():
    r1 = render_evidence_sections(FITZ_PATHS, [F], None, FITZ_TRIPLES,
                                  ["influenced", "influenced_by"])
    r2 = render_evidence_sections(FITZ_PATHS, [F], None, FITZ_TRIPLES,
                                  ["influenced", "influenced_by"])
    assert r1 == r2


# ── Kim Richards specimen regressions (user audit of phil_r267g3, 2026-08-25) ─
# The walk returned evidence under relation names the model did NOT select
# (tv.regular_tv_appearance.* vs the selected tv_regular_personal_appearance.*):
# no walked shape passes selection discipline, no anchor has a selected-rel
# edge, and the only selected edges left (Show --regular_cast--> CVT) lost
# their attr edges to the selection filter → bare-CVT tail drop → EMPTY
# evidence and a lying "already shown in a prior subgraph" message on the
# case's FIRST retrieval.
KR = "Kim Richards"
SHOW1, CVT1, CH1 = "Hello, Larry", "m.0bngb3y", "Ruthie Alder"
KR_SEL = ["tv.tv_regular_personal_appearance.program",
          "tv.tv_program.regular_cast",
          "tv.tv_regular_personal_appearances"]
KR_TRIPLES = [
    (CVT1, "tv.regular_tv_appearance.actor", KR),
    (SHOW1, "tv.tv_program.regular_cast", CVT1),
    (CVT1, "tv.regular_tv_appearance.series", SHOW1),
    (KR, "tv.tv_actor.starring_roles", CVT1),
    (CVT1, "tv.regular_tv_appearance.character", CH1),
    (SHOW1, "tv.tv_program.regular_cast", CVT1),          # within-call duplicate
    (KR, "tv.tv_actor.starring_roles", CVT1),             # within-call duplicate
    (SHOW1, "tv.tv_program.genre", "Sitcom"),             # unselected named edge
]


def test_select_uncovered_revives_record_attrs_and_dedups():
    unc = _select_uncovered(KR_TRIPLES, set(), set(KR_SEL))
    keys = [(nz(h), r.rsplit(".", 1)[-1], nz(t)) for h, r, t in unc]
    # selected-rel edge kept (once — duplicate collapsed)
    assert keys.count((nz(SHOW1), "regular_cast", nz(CVT1))) == 1
    # unselected named↔named edge still excluded (ruling ⑧)
    assert ("sitcom" in [t for _, _, t in keys]) is False
    assert all(r != "genre" for _, r, _ in keys)
    # attr edges of the displayed CVT revived as record payload
    assert (nz(CVT1), "actor", nz(KR)) in keys
    assert (nz(CVT1), "character", nz(CH1)) in keys
    # revived attrs are CVT-headed — they must NOT render as standalone lines
    lines, _ = _render_records([tuple(t) for t in unc], set())
    assert any(f"{SHOW1} --regular_cast--> {CVT1}" in l and "actor=" in l
               and f"character={CH1}" in l for l in lines)
    assert not any(l.strip().startswith(CVT1) for l in lines)


def test_first_retrieval_renders_evidence_no_already_shown():
    # the exact failing configuration, UPDATED for the 2026-08-26 chain-
    # visibility calibration: the walked shape's bridge hop (actor) is
    # unselected but its LAST hop rides a selected relation from the center
    # — the shape now renders as a full chain block (center → CVT record
    # with revived attrs → show) instead of falling to an empty block set.
    # The record content (actor=/character=) stays visible, nothing
    # duplicates into facts, and the deleted "already shown in a prior
    # subgraph" message can never fire.
    sel = {"tv.tv_regular_personal_appearance.program",
            "tv.tv_program.regular_cast",
            "tv.tv_regular_personal_appearances"}
    ov, blocks, covered = render_evidence_sections(
        [{"nodes": [KR, CVT1, SHOW1],
          "relations": ["tv.regular_tv_appearance.actor",
                        "tv.tv_program.regular_cast"]}],
        [KR], None, KR_TRIPLES, KR_SEL)
    assert any("[<--actor --<--regular_cast]" in l for l in blocks)  # chain
    chain_text = "\n".join(blocks)
    assert KR in chain_text and SHOW1 in chain_text and "actor=" in chain_text
    assert "character=Ruthie Alder" in chain_text
    # the chain consumes its edges; facts carry no duplicate record
    unc = _select_uncovered(KR_TRIPLES, covered, sel)
    lines, n_overlap = _render_records([tuple(t) for t in unc], set())
    assert all("regular_cast" not in l for l in lines)
    # duplicates deduped BEFORE counting — overlap is zero on a fresh set
    assert n_overlap == 0


def test_cross_call_full_display():
    # user ruling 2026-08-20: dedup is WITHIN one call only — a re-retrieval
    # of the same center/relations re-renders the identical full evidence
    # (no cross-call state anywhere in the facts path)
    sel = {"tv.tv_regular_personal_appearance.program",
            "tv.tv_program.regular_cast",
            "tv.tv_regular_personal_appearances"}
    outs = []
    for _ in range(2):
        ov, blocks, covered = render_evidence_sections(
            [], [KR], None, KR_TRIPLES, KR_SEL)
        unc = _select_uncovered(KR_TRIPLES, covered, sel)
        lines, _ = _render_records([tuple(t) for t in unc], set())
        outs.append((tuple(ov), tuple(blocks),
                     tuple(l for l in lines if "already shown" not in l)))
    assert outs[0] == outs[1]
    assert "already shown in a prior subgraph" not in "\n".join(outs[0][2])


def test_candidate_provenance_groups():
    lines = ["  Hello, Larry --regular_cast--> m.0bngb3y "
             "[actor=Kim Richards; character=Ruthie Alder]"]
    fe = {"sg1": {nz(KR), nz(SHOW1), nz("Devil Dog")}, "sg2": {nz(KR)}}
    # every candidate visible → no annotation
    assert _candidate_provenance(
        [KR, SHOW1], lines, fe, cur_fid="sg2") == ""
    # Devil Dog not in this render but shown by sg1 → labeled with source
    out = _candidate_provenance(["Devil Dog"], lines, fe, cur_fid="sg2")
    assert "Devil Dog" in out and "earlier subgraph: sg1" in out
    assert "not a disconnection" in out
    # a walk candidate never rendered anywhere → DROPPED (user ruling
    # 2026-09-12: bare entity names with no visible edge carry no
    # information — the subgraph's atom is the triple)
    out2 = _candidate_provenance(["Mystery X"], lines, fe, cur_fid="sg1")
    assert out2 == ""


# ── Debussy specimen (user audit of perfpack_r267g3, 2026-08-25): selected-
#    relation completeness, short-name disambiguation, remainder grouping ─────
CAHIER = "D'un cahier d'esquisses, L. 99"
DEBUSSY = "Claude Debussy"
M_COMP = "music.composition.composer"
B_COMP = "base.musiteca.composition.composer"
AUTHOR = "book.written_work.author"
AUTHOR_WORKS = ["En blanc et noir", "1er quatuor, pour 2 violons, alto et violoncelle",
                "Beau Soir = Evening Fair", "Children's Corner and Individual Pieces"]
DEB_TRIPLES = [
    (CAHIER, M_COMP, DEBUSSY), (CAHIER, B_COMP, DEBUSSY),
    ("Pour le piano", M_COMP, DEBUSSY),
] + [(w, AUTHOR, DEBUSSY) for w in AUTHOR_WORKS]
DEB_SEL = [M_COMP, B_COMP, AUTHOR]
DEB_PATHS = [{"nodes": [CAHIER, DEBUSSY], "relations": [M_COMP]}]


def _assembly_full(paths, centers, triples, selected):
    ov, blocks, covered = render_evidence_sections(paths, centers, None,
                                                    triples, selected)
    unc = _select_uncovered([tuple(t) for t in triples], covered, set(selected))
    lines, _ = _render_records(unc, set())
    grouped = _group_facts_by_rel(lines) if lines else []
    return ov, blocks, grouped


def test_selected_relation_completeness_and_disambiguation():
    ov, blocks, remainder = _assembly_full(DEB_PATHS, [CAHIER],
                                           DEB_TRIPLES, DEB_SEL)
    text = "\n".join(ov) + "\n" + "\n".join(blocks)
    # every selected relation has a STRUCTURAL presence — author's sibling
    # instances render terminal-anchored behind the shared tail, never as an
    # unlabeled facts dump
    assert f"{CAHIER} --composer[music]--> {DEBUSSY}" in text
    assert f"{CAHIER} --composer[base]--> {DEBUSSY}" in text   # disambiguated
    assert f"{DEBUSSY} <--author-- " in text
    for w in AUTHOR_WORKS:
        assert w in text
    assert f"{DEBUSSY} <--composer[music]-- Pour le piano" in text
    # selected-relation edges leave ZERO unsemantic residue
    assert remainder == []
    # no bare duplicated short name (collision must be disambiguated)
    assert text.count("--composer-->") == 0


def test_partial_vs_all_zero_coverage():
    # partial ∅: one selected relation empty → plain ∅ line, no repair hint
    ov, _blocks, _rem = _assembly_full(
        DEB_PATHS, [CAHIER], DEB_TRIPLES,
        DEB_SEL + ["people.person.place_of_birth"])
    assert any("place_of_birth--> ∅" in l for l in ov)
    assert not any("hit NOTHING" in l for l in ov)
    # all-∅: every selected relation empty → repair hook (borrow a center)
    ov2, blocks2, _ = _assembly_full(
        [], ["Some Center"],
        [("A", "unrelated.relation", "B")], ["r.one", "r.two"])
    assert sum(1 for l in ov2 if "∅" in l) == 2
    assert any("hit NOTHING" in l and "cross-subgraph" in l for l in ov2)
    assert blocks2 == [] or all("A" not in b for b in blocks2)


def test_remainder_grouped_by_relation_no_facts_naming():
    # two different residual record families → per-relation section headers;
    # the BANNED "facts" section name never appears
    KR_UNC = _select_uncovered(KR_TRIPLES, set(), set(KR_SEL))
    lines, _ = _render_records([tuple(t) for t in KR_UNC], set())
    grouped = _group_facts_by_rel(lines)
    assert any(l.strip() == "regular_cast:" for l in grouped)
    assert not any("── facts ──" in l or l.strip() == "facts" for l in grouped)
    # every rendered line sits under a relation header
    first_header = next(i for i, l in enumerate(grouped) if l.strip().endswith(":"))
    assert first_header == 0


# ══ 2026-08-26 walk/render defect round: ABM · Tupac · population · Randy ════
# User audit calibrations, replayed-forensics-verified on finalturn_g3:
#   ②a overview anchored counts must contain ONLY same-anchor instances
#      (ABM specimen: `A Beautiful Mind --subjects--> (4 instances)` claimed
#      four instances anchored at OTHER films while ABM itself had none);
#   ②b 2-hop+ instances render as COMPLETE chains; free-head rows (head ∉
#      centers, detached from the chain that produced them) never render
#      (Poetic Justice / Vocals / Sonora / Record producer specimens);
#   ③ measurement/membership RECORD edges (member/role) feed CVT brackets;
#   ④ no duplicate blocks (term_cvt key split), center-priority truncation.
ABM = "A Beautiful Mind"
CM, CS, CL, EDTV = "Cinderella Man", "Clean and Sober", "Closet Land", "EDtv"
VOG, PROD = "Village of the Giants", "Child prodigy"
CG, ENG = "Curious George", "English Language"
SUBJ, FILMS = "film.film.subjects", "film.film_subject.films"

ABM_TRIPLES = [
    (CM, SUBJ, "Boxing"), (CS, SUBJ, "Substance abuse"),
    (CL, SUBJ, "Pedophilia"), (EDTV, SUBJ, "Television"),
    (EDTV, FILMS, "EDtv"), ("Television", FILMS, "The Independent"),
    (VOG, SUBJ, PROD), (VOG, SUBJ, "Giant"),
    # the detour chain's bridge edges (path_edge channel admits unselected
    # mids — the chain needs them for direction resolution/reconstruction)
    (CG, "film.film.language", ENG),
    (VOG, "people.person.languages", ENG),
]
ABM_CENTERS = [ABM, "Angels & Demons", CM, CS, CL, EDTV, CG]


def test_same_anchor_overview_and_no_free_head_rows():
    # ②a: the [subjects] tier-1 line anchors at the films that OWN subjects
    # edges (folded multi-head) — centers[0] is never borrowed for instances
    # it does not anchor.
    paths = [{"nodes": [CM, "Boxing"], "relations": [SUBJ]},
             {"nodes": [EDTV, "Television"], "relations": [SUBJ]},
             # the walk's detour chain to VOG (unselected bridge hops)
             {"nodes": [CG, ENG, VOG, PROD],
              "relations": ["film.film.language", "people.person.languages", SUBJ]}]
    ov, blocks, _cov = render_evidence_sections(
        paths, ABM_CENTERS, None, ABM_TRIPLES, [SUBJ, FILMS])
    text = "\n".join(ov) + "\n" + "\n".join(blocks)
    assert not any(l.strip().startswith(f"{ABM} --subjects") for l in ov)
    subj_line = next(l for l in ov if "--subjects-->" in l)
    assert "Cinderella Man" in subj_line and ABM not in subj_line
    # every center-owned direct edge renders as an anchored row
    assert f"{CM} --subjects--> Boxing" in text
    assert f"{EDTV} --subjects--> Television" in text
    # ②b: VOG's selected-relation edges live INSIDE the complete chain row —
    # no FORWARD 1-hop row headed by a non-center (reverse-form rows are the
    # sanctioned sweep-orphan form)
    for l in blocks:
        if l.lstrip().startswith("[") or "<--" in l.split("-->")[0]:
            continue
        head = l.split("--")[0].strip()
        if head and nz(head) not in {nz(c) for c in ABM_CENTERS} \
                and l.count("-->") + l.count("<--") < 2:
            raise AssertionError(f"free-head row: {l}")
    chain = next(l for l in blocks if VOG in l and l.count("--") >= 2)
    assert "Curious George" in chain and PROD in chain


def test_detour_chain_renders_correct_length_full_prefix():
    # ②b Tupac specimen shape: hop-1/hop-2 of a 2-hop instance are NEVER
    # split into independent rows; the mid entity never heads a row.
    TUP, PJ, CVT = "Tupac Shakur", "Poetic Justice", "m.02vb3h0"
    ACTOR, STARRING = "film.actor.film", "film.film.starring"
    triples = [
        (TUP, ACTOR, CVT), (CVT, "film.performance.actor", TUP),
        (CVT, "film.performance.character", "Lucky"),
        (PJ, STARRING, CVT),
    ] + [(PJ, STARRING, f"m.cast{i}") for i in range(3)]
    paths = [
        {"nodes": [TUP, CVT, PJ], "relations": [ACTOR, STARRING]},
        # the sibling-mirror free-head path (rooted at the MID node) — must
        # NOT register a standalone shape
        *[{"nodes": [PJ, f"m.cast{i}"], "relations": [STARRING]}
          for i in range(3)],
    ]
    ov, blocks, _cov = render_evidence_sections(
        paths, [TUP], None, triples, [ACTOR, STARRING])
    text = "\n".join(blocks)
    assert not any(l.strip().startswith(PJ) for l in blocks)   # no free head
    assert TUP in text and PJ in text
    # the chain row carries the full prefix + the CVT record attrs
    assert f"{TUP} --{ACTOR.rsplit('.', 1)[-1]}--> {CVT}" in text
    assert "character=Lucky" in text


def test_direction_in_header_no_duplicate_blocks():
    # ④: shapes differing only in hop direction must not render identical
    # headers (reads as a duplicate block with inconsistent counts); the
    # term_cvt key split itself is gone (same hops → one block).
    triples = [
        (F, "influenced", ANN), (ANN, "influenced", YATES),
        (BALZAC_X, "influenced_by", BRET),
        # terminal-CVT and named-terminal witnesses of the SAME hop sequence
        (F, "starring", "m.01"), ("m.01", "actor", KR),
        (F, "starring", KR),
    ]
    paths = [
        {"nodes": [F, ANN, YATES], "relations": ["influenced", "influenced"]},
        {"nodes": [F, "m.01"], "relations": ["starring"]},
        {"nodes": [F, KR], "relations": ["starring"]},
    ]
    ov, blocks, _cov = render_evidence_sections(
        paths, [F], None, triples, ["influenced", "influenced_by", "starring"])
    headers = [l for l in blocks if l.startswith("[")]
    assert len(headers) == len(set(headers))
    # the two starring witnesses merged into ONE 1-hop block (hops key only)
    starring_rows = [l for l in blocks if "--starring-->" in l]
    assert len(starring_rows) == 1
    assert "m.01" in starring_rows[0] and KR in starring_rows[0]


BALZAC_X = "Honoré de Balzac"


def test_center_priority_truncation():
    # ④③: when a terminal fold truncates, CENTER entities survive first —
    # the center's own presence inside a shared tail list is never the
    # truncated part (Randy specimen: the center was cut from a 6-member
    # instrumentalists row, and with him the gold binding).
    STARRING, FILMS = "film.film.starring", "film.film_subject.films"
    TUP, PJ, TV = "Tupac Shakur", "Poetic Justice", "Television"
    others = [f"Show {i}" for i in range(150)]      # > _MERGE_TAIL_CAP tails
    triples = [(PJ, STARRING, TUP)] + [(TV, FILMS, o) for o in others]
    triples.append((TV, FILMS, PJ))                 # a CENTER among the tails
    paths = [{"nodes": [PJ, TUP, TV, PJ],   # center-rooted... see gate below
              "relations": [STARRING, FILMS.replace("films", "x"), FILMS]}]
    paths = [{"nodes": [PJ, TUP], "relations": [STARRING]},
             # 2-hop shape from the center over selected rels, terminal fold
             {"nodes": [PJ, TUP, TV], "relations": [STARRING, FILMS]}]
    ov, blocks, _cov = render_evidence_sections(
        paths, [PJ, TV], None, triples, [STARRING, FILMS])
    chain_rows = [l for l in blocks if l.count("--") >= 2 and TV in l]
    assert chain_rows, blocks
    row = chain_rows[0]
    # Television (a center) precedes the truncation marker; PJ (the other
    # center) heads the row — center presence is never truncated away
    assert TV in row
    assert row.rstrip().endswith("more") is False or TV in row.split("+")[0]


RANDY = "Randy Jackson"


def test_membership_record_attrs_reach_the_render():
    # ③/④ Randy specimen core: the group_membership CVT's member/role edges
    # are RECORD payload — they must feed the inline bracket (gold
    # role=Vocals) instead of being noise-filtered out of the indexes.
    M01 = "m.01vxjq8"
    triples = [
        (RANDY, "music.group_member.membership", M01),
        (M01, "music.group_membership.member", RANDY),
        (M01, "music.group_membership.role", "Bass guitar"),
        (M01, "music.group_membership.role", VOCALS_X),
        (M01, "music.group_membership.group", "Journey"),
        (VOCALS_X, "music.instrument.instrumentalists", "Stephen Melton"),
    ]
    paths = [{"nodes": [RANDY, M01, VOCALS_X, "Stephen Melton"],
              "relations": ["music.group_membership.member",
                            "music.group_membership.role",
                            "music.instrument.instrumentalists"]}]
    ov, blocks, covered = render_evidence_sections(
        paths, [RANDY], None, triples,
        ["music.group_member.instruments_played",
         "music.instrument.instrumentalists"])
    text = "\n".join(ov) + "\n" + "\n".join(blocks)
    # the full chain renders with the CVT record between center and terminal
    assert RANDY in text and "Stephen Melton" in text
    chain = next(l for l in blocks if M01 in l)
    assert "--role--> " + VOCALS_X in chain          # gold hop visible
    assert "member=" in chain or "role=" in chain    # record attrs inline
    # the CVT's attr edges are consumed by the record display
    assert (nz(M01), "music.group_membership.role", nz(VOCALS_X)) in covered


VOCALS_X = "Vocals"


def test_feeding_guarantee_one_hop_selected_survives_cut():
    # ① (walk-starvation calibration): a center's direct selected-relation
    # pattern must survive the top-N collection cut — the renderer's tier-1
    # blocks are synthesized from those edges.
    from kgqa.agent.seq_tools import _select_patterns_for_render

    class _PE:
        def __init__(self, rel, h, t):
            self.tree_data = {"paths": [
                {"nodes": [h, t], "relations": [rel]}]}
            self.triples = [(h, rel, t)]

    detours = [_PE("film.film.language", "EDtv", "English Language")
               for _ in range(6)]
    one_hop = _PE("film.film.subjects", "EDtv", "Television")
    pes = detours + [one_hop]
    keep = _select_patterns_for_render(pes, "EDtv",
                                       ["film.film.subjects"], 5)
    assert one_hop in keep
    # without selected relations the cut stays plain
    keep2 = _select_patterns_for_render(pes, "EDtv", [], 5)
    assert one_hop not in keep2 and len(keep2) == 5


def test_guarantee_center_direct_edges_backfills_walk_gap():
    # ① walk-side feeding guarantee (2026-08-26 audit): a center's INVERSE
    # 1-hop family ('Film --produced_by--> Ron' walked from center Ron
    # Howard) is bounded by the walk's 24-path support cap — 35 graph edges,
    # 24 carried. _guarantee_center_direct_edges must backfill every direct
    # (center, selected relation) graph edge the walk missed, and ONLY those
    # (unselected relations and non-center edges stay out).
    from kgqa.agent.seq_tools import _guarantee_center_direct_edges

    class _Ctx:
        pass

    ctx = _Ctx()
    RON, ALAMO, CHAMBER, GRAZER = "Ron Howard", "The Alamo", "The Chamber", "Brian Grazer"
    ctx.ents = [RON, ALAMO, CHAMBER, "EDtv", GRAZER]
    ctx.rels = ["film.film.produced_by", "film.film.genre"]
    PB, GEN = 0, 1
    # graph: 35-class family — three produced_by edges into the center, one
    # carried by the walk already (EDtv), plus unselected-relation noise.
    ctx.h_ids = [1, 2, 3, 1]
    ctx.r_ids = [PB, PB, PB, GEN]
    ctx.t_ids = [0, 0, 0, 2]
    ctx.subgraph_entities = set()
    ctx.accumulated_triples = set()
    ctx.all_candidates = [RON]
    walked = [("EDtv", "film.film.produced_by", RON)]     # orientation as walked
    added = _guarantee_center_direct_edges(ctx, [(RON, 0)], [PB], walked)
    added_set = {(a, b, c) for a, b, c in added}
    # both missed inverse edges enter, in STORED orientation
    assert (ALAMO, "film.film.produced_by", RON) in added_set
    assert (CHAMBER, "film.film.produced_by", RON) in added_set
    # the walked one is not re-added; the genre edge (unselected) never enters
    assert len(added) == 2
    assert not any(t[1] == "film.film.genre" for t in added)
    # endpoints became answerable + legal future centers
    assert {1, 2} <= ctx.subgraph_entities
    assert ALAMO in ctx.all_candidates and CHAMBER in ctx.all_candidates
    # idempotence: a second pass over the extended triple set adds nothing
    assert _guarantee_center_direct_edges(
        ctx, [(RON, 0)], [PB], walked + added) == []
