#!/usr/bin/env python3
"""PATH-LEVEL ADMISSION in _display_license_filter (user ruling 2026-09-12).

The edge-level license rule predates the pattern-walk architecture: it tests
every hop's relation against the submitted names, so an engine-derived
pattern whose mid hop is a bridge relation (UK --administrative_children->
territory --time_zones-> zone) loses BOTH hops — the mid-hop edge is
"unlicensed", its endpoint therefore never becomes licensed, and the
terminal edge (a SUBMITTED relation) fails the node test. Walk succeeded,
evidence zeroed, misreported as RELATION_MISMATCH (realign5 UK/ETZ
specimens).

Under treq.multistep (pattern calls) the unit of admission is now the PATH:
a path is legal iff its LAST hop is a submitted relation; mid hops license
their nodes by path membership. Plain calls keep the legacy edge rule
byte-identically (standing config regression guard).

Pure synthetic fixtures — no data pkl dependency.
Run: python3 tests/test_license_path_admission.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kgqa.agent.seq_tools import _display_license_filter


class _PE:
    """Minimal PatternEvidence stand-in (the filter only touches these)."""

    def __init__(self, paths, triples, candidates):
        self.tree_data = {"paths": paths}
        self.triples = triples
        self.candidates = candidates


TZ = "location.location.time_zones"
ADMIN = "base.aareas.schema.administrative_area.administrative_children"

PATH_OK = {"nodes": ["United Kingdom", "Anguilla", "Atlantic Time Zone"],
           "relations": [ADMIN, TZ]}
PATH_BAD_LAST = {"nodes": ["United Kingdom", "Anguilla"],
                 "relations": [ADMIN]}          # last hop NOT submitted

TRIPLES = [
    ("United Kingdom", ADMIN, "Anguilla"),            # mid hop
    ("Anguilla", TZ, "Atlantic Time Zone"),           # submitted terminal
    ("Anguilla", "unrelated.relation", "Drift Node"), # drift off a licensed node
]
PE = _PE([PATH_OK, PATH_BAD_LAST], list(TRIPLES),
         ["Anguilla", "Atlantic Time Zone", "Drift Node"])


def _run(multistep):
    treq = {"rel_names": [TZ], "multistep": multistep}
    bres = {"pe_list": [{ "P1": PE }]}
    kept, cands, bres2 = _display_license_filter(
        treq, bres, [("United Kingdom", 0)], list(TRIPLES),
        ["Anguilla", "Atlantic Time Zone", "Drift Node"])
    return kept, cands, bres2


def test_pattern_mode_admits_by_last_hop():
    kept, cands, bres2 = _run({0: {(1, 2): (frozenset(), frozenset())}})
    kinds = {(h, r) for h, r, _t in kept}
    assert ("United Kingdom", ADMIN) in kinds, "mid hop must ride the path"
    assert ("Anguilla", TZ) in kinds, "submitted terminal must survive"
    # drift edge off a licensed node may ride kept_triples (endpoint rule,
    # same tolerance as legacy) — but its NODE never licenses and the
    # bad-last-hop path is removed from the render copy
    paths = bres2["pe_list"][0]["P1"].tree_data["paths"]
    assert paths == [PATH_OK], "only the submitted-terminated path renders"
    assert "Drift Node" not in cands, "drift-only nodes stay unlicensed"
    assert "Atlantic Time Zone" in cands


def test_plain_mode_keeps_legacy_edge_rule():
    kept, cands, _bres2 = _run({})
    kinds = {(h, r) for h, r, _t in kept}
    assert ("United Kingdom", ADMIN) not in kinds, \
        "legacy rule: unsubmitted mid-hop relation is drift"
    assert ("Anguilla", TZ) not in kinds, \
        "legacy rule: terminal loses too (node never licensed) — the seam"


def test_render_form_node_head_stripped():
    treq = {"rel_names": [TZ], "multistep": {0: 1}}
    pe = _PE([{"nodes": ["m.abc: [from=..]", "X"], "relations": [TZ]}],
             [("m.abc: [from=..]", TZ, "X")], ["X"])
    kept, cands, bres2 = _display_license_filter(
        treq, {"pe_list": [{"P1": pe}]}, [("United Kingdom", 0)],
        [("m.abc: [from=..]", TZ, "X")], ["X"])
    assert kept == [("m.abc: [from=..]", TZ, "X")]
    assert bres2["pe_list"][0]["P1"].tree_data["paths"], \
        "render-form node must not empty the path list (537 specimen)"


if __name__ == "__main__":
    test_pattern_mode_admits_by_last_hop()
    test_plain_mode_keeps_legacy_edge_rule()
    test_render_form_node_head_stripped()
    print("license path-admission: 3/3 OK")
