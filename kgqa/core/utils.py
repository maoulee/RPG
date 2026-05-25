"""Pure utility functions for the KGQA pipeline.

String normalization, relation formatting, XML extraction, entity context
building, candidate matching, and answer-set F1 computation.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9%.' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def rel_to_text(rel: str) -> str:
    """Return original dot-notation format for LLM display: 'people.person.religion'"""
    return rel


def rel_to_text_short(rel: str) -> str:
    """Short format (last 2 segments) for GTE retrieval: 'person religion'"""
    parts = rel.split(".")
    return " ".join(p.replace("_", " ") for p in parts[-2:]) if len(parts) >= 2 else rel.replace("_", " ")


def extract_xml_tag(text, tag):
    """Extract content between <tag>...</tag>, returns None if not found."""
    if not text:
        return None
    match = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# Entity / relation context
# ---------------------------------------------------------------------------

def get_entity_contexts(entity_names, h_ids, r_ids, t_ids, ents, rels):
    """For each candidate entity, extract surrounding relation context from subgraph.
    Similar to check_entities' [Context: ...] annotation."""
    # Import here to avoid circular dependency — is_cvt_like lives in traversal/cvt.py
    from kgqa.traversal.cvt import is_cvt_like

    # Build name->idx lookup
    name_to_indices = {}
    for i, e in enumerate(ents):
        name_to_indices.setdefault(e, []).append(i)

    contexts = {}
    for cand in entity_names:
        indices = name_to_indices.get(cand, [])
        if not indices:
            continue
        idx_set = set(indices)
        outgoing = []
        incoming = []
        for i in range(len(h_ids)):
            if h_ids[i] in idx_set:
                rel_text = rel_to_text(rels[r_ids[i]]) if 0 <= r_ids[i] < len(rels) else "?"
                t_name = ents[t_ids[i]] if 0 <= t_ids[i] < len(ents) else "?"
                if not is_cvt_like(t_name) and t_name != cand:
                    outgoing.append(f"{rel_text}->{t_name}")
            if t_ids[i] in idx_set:
                rel_text = rel_to_text(rels[r_ids[i]]) if 0 <= r_ids[i] < len(rels) else "?"
                h_name = ents[h_ids[i]] if 0 <= h_ids[i] < len(ents) else "?"
                if not is_cvt_like(h_name) and h_name != cand:
                    incoming.append(f"{h_name}->{rel_text}")
        parts = outgoing[:2] + incoming[:1]
        if parts:
            contexts[cand] = "; ".join(parts)
    return contexts


# ---------------------------------------------------------------------------
# Candidate matching
# ---------------------------------------------------------------------------

def candidate_hit(cands: List[str], targets: List[str]) -> bool:
    norm_cands = [normalize(c) for c in cands if c.strip()]
    if not norm_cands:
        return False
    for t in targets:
        nt = normalize(t)
        for c in norm_cands:
            if c == nt or nt in c or c in nt:
                return True
    # Fuzzy fallback: catch near-matches like "Connor" vs "Conner"
    # Only for entities >= 8 chars to avoid false positives on short names
    for t in targets:
        nt = normalize(t)
        if len(nt) < 8:
            continue
        for c in norm_cands:
            if len(c) < 8:
                continue
            if SequenceMatcher(None, c, nt).ratio() >= 0.92:
                return True
    return False


def strict_candidate_hit(cands: List[str], targets: List[str]) -> bool:
    """Strict matching: exact or substring with min length 4."""
    norm_cands = [normalize(c) for c in cands]
    for t in targets:
        nt = normalize(t)
        if len(nt) < 2:
            continue
        for c in norm_cands:
            if len(c) < 2:
                continue
            if c == nt:
                return True
            shorter = min(len(c), len(nt))
            if shorter >= 4 and (nt in c or c in nt):
                return True
    return False


def sample_triple(rel_idx: int, h_ids, r_ids, t_ids, entity_list, relation_list) -> str:
    """Sample one (head, relation, tail) triple for a given relation index."""
    for i in range(len(r_ids)):
        if r_ids[i] == rel_idx:
            h_name = entity_list[h_ids[i]] if 0 <= h_ids[i] < len(entity_list) else "?"
            t_name = entity_list[t_ids[i]] if 0 <= t_ids[i] < len(entity_list) else "?"
            r_name = relation_list[r_ids[i]] if 0 <= r_ids[i] < len(relation_list) else "?"
            return f"({h_name}) -[{r_name}]-> ({t_name})"
    return ""


def sample_triple_batch(rel_indices, h_ids, r_ids, t_ids, entity_list, relation_list):
    """Sample one triple per relation index. Returns dict: rel_idx -> triple_str."""
    result = {}
    seen_rels = set(rel_indices)
    for i in range(len(r_ids)):
        r = r_ids[i]
        if r in seen_rels and r not in result:
            h_name = entity_list[h_ids[i]] if 0 <= h_ids[i] < len(entity_list) else "?"
            t_name = entity_list[t_ids[i]] if 0 <= t_ids[i] < len(entity_list) else "?"
            r_name = relation_list[r] if 0 <= r < len(relation_list) else "?"
            result[r] = f"({h_name}) -[{r_name}]-> ({t_name})"
            if len(result) == len(seen_rels):
                break
    return result


def compute_match_stats(predicted: List[str], gold: List[str]) -> Dict[str, float]:
    """Compute P/R/F1 between predicted and gold answer sets.

    Returns: {'precision': float, 'recall': float, 'f1': float,
              'matched_gold': int, 'matched_pred': int, 'n_gold': int, 'n_pred': int}
    Uses the same matching logic as candidate_hit (normalize + substring + fuzzy).
    """
    if not predicted or not gold:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
                'matched_gold': 0, 'matched_pred': 0, 'n_gold': len(gold), 'n_pred': len(predicted)}

    norm_pred = [normalize(c) for c in predicted if c.strip()]
    norm_gold = [normalize(t) for t in gold if t.strip()]
    if not norm_pred or not norm_gold:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
                'matched_gold': 0, 'matched_pred': 0, 'n_gold': len(gold), 'n_pred': len(predicted)}

    def _matches(c: str, t: str) -> bool:
        if c == t or t in c or c in t:
            return True
        if len(c) >= 8 and len(t) >= 8 and SequenceMatcher(None, c, t).ratio() >= 0.92:
            return True
        return False

    # Recall: how many gold items matched by at least one prediction
    matched_gold = 0
    for t in norm_gold:
        if any(_matches(c, t) for c in norm_pred):
            matched_gold += 1

    # Precision: how many predictions matched at least one gold item
    matched_pred = 0
    for c in norm_pred:
        if any(_matches(c, t) for t in norm_gold):
            matched_pred += 1

    precision = matched_pred / len(norm_pred) if norm_pred else 0.0
    recall = matched_gold / len(norm_gold) if norm_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {'precision': precision, 'recall': recall, 'f1': f1,
            'matched_gold': matched_gold, 'matched_pred': matched_pred,
            'n_gold': len(norm_gold), 'n_pred': len(norm_pred)}


# ---------------------------------------------------------------------------
# Constraint entity extraction
# ---------------------------------------------------------------------------

def _extract_constraint_entities(cs):
    """Extract constraint entities for evidence tree sorting priority."""
    constraints = []
    # pathentity roles from decomposition
    for er in getattr(cs, 'entity_roles', []):
        if er.get('role') == 'pathentity':
            constraints.append(er['entity'])
    # breakpoint (endpoint) entities
    for idx in getattr(cs, 'breakpoints', {}).values():
        if idx is not None and hasattr(cs, 'ents') and 0 <= idx < len(cs.ents):
            constraints.append(cs.ents[idx])
    return constraints


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------

def _extract_graph_evidence(reason_prompt) -> str:
    """Extract GRAPH EVIDENCE section from a stored reason prompt."""
    if not isinstance(reason_prompt, str):
        return ""
    m = re.search(r'GRAPH EVIDENCE:\s*\n(.*?)(?=━━━|CANDIDATE ENTITIES|STEP |\Z)', reason_prompt, re.DOTALL)
    if m:
        return m.group(1).rstrip()
    return ""


# ---------------------------------------------------------------------------
# Attempt scoring
# ---------------------------------------------------------------------------

def _attempt_score(state, candidate_threshold=50):
    """Score a planning attempt for comparison. Penalizes candidate explosion."""
    if state.get("error"):
        return (-1, -1, -1, -1)
    n_cand = len(state.get("answer_candidates", []))
    under_threshold = 1 if n_cand <= candidate_threshold else 0
    return (
        state.get("max_cov", 0),
        under_threshold,
        len(state.get("paths", [])),
        -n_cand,
    )
