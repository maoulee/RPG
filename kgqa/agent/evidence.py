"""EVIDENCE SET — the structured single source of truth for evidence
(redesign charter 2026-09-24, ZEROETH RULE):

    Apart from TWO legal exceptions — (a) logprob scoring must construct a
    text prompt, (b) the MODEL's own declarations (checkpoint bindings /
    answer entities) must be parsed from input text — EVERY consumer of
    evidence (render, dedup, idempotency, answer-pool harvest, join
    checks, evaluation attribution) reads THIS structured object. The
    rendered text is a PROJECTION of the EvidenceSet for the model's eyes;
    the environment NEVER reads its own rendered text back.

Lifecycle per retrieve_subgraph call:
    walker chains -> EvidenceSet.build(chains, kinds, ctx) -> presenter
    projection; the call's EvidenceSet is appended to ctx.evidence_log and
    unioned into ctx.delivered (fact-key set, via entity_kinds-adjacent
    fact keys from seq_tools._edge_fact_key).

Consumers (migrated in stages behind SEQ_EVIDENCE_V2):
    - answer legal pool   : endpoints + CVT-record attrs from evidence_log
    - idempotency (_sg_served): (root, pattern-set) keys — no text
    - join/merge checks   : pool endpoints from evidence_log
    - RSCC attribution    : per-call edge ownership from evidence_log
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from kgqa.agent.entity_kinds import entity_kind, is_cvt, is_transit

Edge = Tuple[str, str, str]            # (head_name, rel_full_name, tail_name)
Record = Tuple[str, List[Tuple[str, str]]]   # (cvt_name, [(attr_key, value)])


@dataclass
class EvidenceSet:
    """One call's structured evidence. rows = merged display rows (visual
    only); edges/records are the truth; delivered_keys are fact keys."""
    root: str = ""
    patterns: List[str] = field(default_factory=list)     # selected pattern labels
    edges: List[Edge] = field(default_factory=list)        # ALL walked edges incl. passthrough
    records: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)  # cvt -> attr -> values
    endpoints: Set[str] = field(default_factory=set)       # NAMED endpoints (answer-legal surface)
    delivered_keys: Set[Tuple] = field(default_factory=set)  # fact keys contributed THIS call

    # ---------- construction ----------
    @classmethod
    def build(cls, chains, ctx, fact_key_fn) -> "EvidenceSet":
        """chains: walker WalkChain dicts with full edge lists (names).
        fact_key_fn: seq_tools._edge_fact_key (h, r, t, inv_map) -> key."""
        ev = cls()
        seen_edges: Set[Edge] = set()
        for ch in chains or []:
            for (h, r, t, role) in ch.get("named_edges", ()):
                e = (h, r, t)
                if e in seen_edges:
                    continue
                seen_edges.add(e)
                ev.edges.append(e)
                for name in (h, t):
                    if entity_kind(name) == "NAMED":
                        ev.endpoints.add(name)
                    elif is_cvt(name):
                        ev.records.setdefault(name, {})
            for (cvt, key, value) in ch.get("record_attrs", ()):
                ev.records.setdefault(cvt, {}).setdefault(key, []).append(value)
        ev.delivered_keys = {fact_key_fn(h, r, t) for (h, r, t) in ev.edges}
        return ev

    # ---------- queries (the ONLY interfaces consumers may use) ----------
    def answer_pool(self) -> List[str]:
        """Named endpoints + CVT attribute values (the answer-legal surface)."""
        pool = list(self.endpoints)
        for attrs in self.records.values():
            for values in attrs.values():
                pool.extend(values)
        return pool

    def owns_edge(self, key) -> bool:
        return key in self.delivered_keys

    def to_projection_meta(self) -> dict:
        """Structured metadata for the presenter (labels/records); the
        presenter renders TEXT from this + edges, never re-parses text."""
        return {"patterns": list(self.patterns),
                "records": {k: dict(v) for k, v in self.records.items()}}


class EvidenceLog:
    """Case-scope ledger: append-only log of EvidenceSets + the unioned
    delivered-key set. THIS replaces ctx.accumulated_triples /
    fact_evidence / fact_candidate_pool overlaps as the single 'already
    delivered' authority (stage-gated migration)."""

    def __init__(self):
        self.calls: List[EvidenceSet] = []
        self.delivered: Set[Tuple] = set()

    def append(self, ev: EvidenceSet):
        self.calls.append(ev)
        self.delivered |= ev.delivered_keys

    def answer_pool(self, fid: Optional[str] = None) -> List[str]:
        if fid is None:
            pool: List[str] = []
            for ev in self.calls:
                pool.extend(ev.answer_pool())
            return pool
        # fid-scoped pools remain keyed by the caller during migration
        pool: List[str] = []
        for ev in self.calls:
            pool.extend(ev.answer_pool())
        return pool

    def is_delivered(self, key) -> bool:
        return key in self.delivered
