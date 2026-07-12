#!/usr/bin/env python3
"""GT-suspect filter for RL training data.

Builds a clean training set by filtering out cases with noisy or unreachable
gold answers. Filtering dimensions:
  1. gt_hit=False (gold not in subgraph candidates — unreachable)
  2. Hard-irreducible multi-slot ambiguity (gold picked minority slot with no
     disambiguation signal in question)
  3. Date-filter + multi-candidate artifact (NOT-EXISTS clause with CVT
     date masking and multiple candidates — likely completeness artifact)

Output:
  - Clean trajectories (with S_plan, S_select, S_reason, total_score)
  - Filtered cases with reasons
  - Statistics report (Chinese)

Usage:
    python scripts/filter_gt_suspect.py \\
        --trajectories data/offline_grpo/traj_cwq.jsonl \\
        --cwq-pkl data/cwq_processed/test_literal_and_language_fixed_path_completed.pkl \\
        --sparql data/cwq_sparql/test.json \\
        --output data/offline_grpo/traj_cwq_clean.jsonl \\
        --report data/offline_grpo/filter_report.txt

Options:
    --no-gt-hit         Skip gt_hit filter (keep unreachable cases)
    --no-ambiguity      Skip ambiguity filter (keep ambiguous cases)
    --no-date-filter    Skip date-filter filter (keep NOT-EXISTS artifacts)
    --keep-suspect      Keep GT-suspect cases in separate output for inspection
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kgqa.core.utils import normalize, candidate_hit


# ===========================================================================
# Multi-slot concept ambiguity (reused from screen_annotation_ambiguity.py)
# ===========================================================================

CONCEPTS = {
    'LANGUAGE': {
        'slots': {
            'official_language':  (['official_language'], ['official']),
            'languages_spoken':   (['languages_spoken'],
                                   ['all language', 'languages are', 'languages spoken',
                                    'languages do', 'language do', 'language are']),
        },
        'ambiguity_note': 'official vs all; generic singular "language spoken" is ~80% all',
    },
    'CURRENCY': {
        'slots': {
            'currency_used':          (['country.currency_used'],
                                       ['current', 'today', 'present', 'now use',
                                        'currency of', "currency is", 'what currency',
                                        'what money', 'uses the']),
            'currency_formerly_used': (['currency_formerly_used'],
                                       ['before', 'former', 'formerly', 'previous',
                                        'prior', 'used to', 'was the', 'old', 'past',
                                        'earlier', 'used before', 'pre-euro', 'adapted']),
        },
        'ambiguity_note': 'current vs former; former keyworded, current is 95% default',
    },
    'RELIGION': {
        'slots': {
            'religion_percentage': (['religion_percentage.religion'],
                                    ['predominant', 'main religion', 'majority',
                                     'biggest', 'largest', 'most common',
                                     'major religion', 'primary', 'practic',
                                     'religion is', 'religions are']),
            'deities':             (['religion.religion.deities'],
                                    ['deity', 'deities', 'god', 'gods', 'goddess',
                                     'worship', 'diety']),
            'texts':               (['religion.religion.texts'],
                                    ['text', 'book', 'scripture', 'holy book',
                                     'sacred text', 'bible']),
            'person_religion':     (['people.person.religion'],
                                    ['who', 'person', 'man', 'woman']),
        },
        'ambiguity_note': 'predominant% vs person vs deities vs texts',
    },
    'BORDER_CONTAIN': {
        'slots': {
            'contains':         (['location.location.contains'],
                                 ['contain', 'include', 'consist of', 'made up',
                                  'has', 'have', 'with', 'composed of', 'made of',
                                  'are in the location']),
            'containedby':      (['location.location.containedby'],
                                 ['inside', 'within', 'located', 'part of', 'where is',
                                  'a part of', 'what part', 'situated in', 'located in',
                                  'is in']),
            'adjoins':          (['adjoining_relationship.adjoins'],
                                 ['border', 'next to', 'neighbor', 'neighboring',
                                  'sharing', 'shares a', 'adjacent', 'adjoin']),
            'partially_contained': (['partially_contain'],
                                    ['partial', 'partly', 'bisect', 'divid', 'cross',
                                     'through']),
        },
        'ambiguity_note': 'directional parent/child + partial + adjoin; mostly disambiged',
    },
    'GOVT_FORM_HOLDER': {
        'slots': {
            'form_of_government': (['form_of_government'],
                                   ['form of government', 'type of government',
                                    'government type', 'governmental type',
                                    'kind of government', 'system of government',
                                    'political system', 'governent', 'government is',
                                    'run by', 'what type', 'form of gov']),
            'office_holder':      (['government_position_held.office_holder',
                                   'politician.government_positions_held'],
                                   ['who', 'leader', 'governor', 'president',
                                    'prime minister', 'minister', 'man', 'woman',
                                    'brother', 'holds', 'held', 'head of', 'ruler',
                                    'king', 'queen', 'chairman', 'chairperson']),
        },
        'ambiguity_note': 'system-of-govt vs leader; disambiged by person-word vs system-word',
    },
}

# Flatten slot matchers
CONCEPTS_SLOTS = {}
for cname, cdef in CONCEPTS.items():
    for slot, (kws, disambig) in cdef['slots'].items():
        CONCEPTS_SLOTS[slot] = (kws, disambig)

# Slot to concept mapping
SLOT_TO_CONCEPT = {}
for cname, cdef in CONCEPTS.items():
    for slot in cdef['slots']:
        SLOT_TO_CONCEPT[slot] = cname


def answer_rels(s: str) -> List[str]:
    """Extract answer relations from SPARQL (triples where ?x is subject or object)."""
    s = s or ''
    return (re.findall(r'ns:([\w.]+)\s+\?x\s*[\.;\}]', s)
            + re.findall(r'\?x\s+ns:([\w.]+)\s+', s))


def classify_ambiguity(rels: List[str], question: str) -> Dict[str, Any]:
    """Classify multi-slot concept ambiguity for one case.

    Returns:
        {
            'concept': str | None,
            'slot': str | None,
            'grade': 'hard' | 'soft' | 'disambig' | None,
            'is_hard': bool,
            'is_minority_slot': bool,  # hard + picked minority (irreducible)
            'n_slots': int,
        }
    """
    ql = (question or '').lower()
    picked = None
    concept_name = None

    # Find which slot was picked
    for slot, (kws, _) in CONCEPTS_SLOTS.items():
        if any(any(k in r for k in kws) for r in rels):
            picked = slot
            concept_name = SLOT_TO_CONCEPT.get(slot)
            break

    if picked is None or concept_name is None:
        return {'concept': None, 'slot': None, 'grade': None,
                'is_hard': False, 'is_minority_slot': False, 'n_slots': 0}

    cdef = CONCEPTS[concept_name]
    n_slots = len(cdef['slots'])

    # Check if question has disambiguation keyword for picked slot
    picked_kws = cdef['slots'][picked][1]
    picked_signal = any(d in ql for d in picked_kws)

    # Check if question has keyword for a DIFFERENT slot
    other_kws = []
    for slot, (_, disambig) in cdef['slots'].items():
        if slot != picked:
            other_kws += disambig
    other_signal = any(d in ql for d in other_kws)

    # Grade
    if picked_signal:
        grade = 'disambig'
    elif other_signal:
        grade = 'soft'
    else:
        grade = 'hard'

    return {
        'concept': concept_name,
        'slot': picked,
        'grade': grade,
        'is_hard': grade == 'hard',
        'n_slots': n_slots,
    }


def hidden_time(sparql: str, question: str) -> bool:
    """Detect hidden-time criterion: dateTime literal year not in question."""
    d = re.findall(r'"([^"]+)"\^\^xsd:dateTime', sparql or '')
    if not d:
        return False
    date_years = set(dd[:4] for dd in d)
    q_years = set(re.findall(r'\b(1[6-9]\d{2}|20\d{2})\b', question or ''))
    has_word = any(k in (question or '').lower() for k in
                   ('current', ' now', 'latest', 'last ', 'most recent', 'recent',
                    'currently'))
    return not (date_years & q_years) and not has_word


def has_not_exists(sparql: str) -> bool:
    """Detect NOT-EXISTS clause."""
    return 'NOT EXISTS' in (sparql or '').upper()


def detect_date_filter_multicandidate(sparql: str, question: str,
                                      n_candidates: int) -> Tuple[bool, str]:
    """Detect date-filter + multi-candidate artifact.

    Returns (is_suspect, reason):
    - suspect if: NOT-EXISTS clause + likely CVT date masking + many candidates
    - CVT date masking: SPARQL has date filter on CVT node
    """
    if not has_not_exists(sparql):
        return False, ""

    # Check for CVT date patterns in SPARQL
    # CVT nodes often have predicates like 'people.person.date_of_birth',
    # 'government.government_position_held.start_date', etc.
    has_date_filter = bool(re.search(r'date[_\w]+\s*[<>]=?\s*["\d]', sparql or '', re.I))

    # Many candidates = broader search space (more likely to be artifact)
    many_candidates = n_candidates > 5

    if has_date_filter and many_candidates:
        return True, f"NOT-EXISTS + date-filter + {n_candidates} candidates"
    elif has_date_filter:
        return True, f"NOT-EXISTS + date-filter (candidates={n_candidates})"
    elif many_candidates:
        return True, f"NOT-EXISTS + many candidates ({n_candidates})"

    return False, ""


# ===========================================================================
# Load data
# ===========================================================================

def load_trajectories(path: Path) -> List[Dict[str, Any]]:
    """Load trajectory JSONL file."""
    records = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except Exception as e:
                print(f"  warning: skipped malformed line: {e}")
    return records


def load_sparql(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load SPARQL labels (CWQ format: {ID, question, sparql})."""
    data = json.loads(path.read_text())
    return {x['ID']: x for x in data}


def load_gold_pkl(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load gold pkl file."""
    samples = pickle.loads(path.read_bytes())
    return {s.get('id') or s.get('question_id', ''): s for s in samples}


def build_ambiguity_index(sparql_data: Dict[str, Dict[str, Any]],
                          gold_pkl: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build ambiguity index for all cases.

    Returns:
        {
            case_id: {
                'hard_ambiguity': bool,
                'hard_minority_slot': bool,  # hard + picked minority slot (irreducible)
                'concept': str | None,
                'slot': str | None,
                'hidden_time': bool,
                'not_exists': bool,
            }
        }
    """
    index = {}

    # First pass: compute slot distribution for each concept
    concept_slot_counts: Dict[str, Counter] = defaultdict(Counter)
    for cid, sp in sparql_data.items():
        s = sp.get('sparql', '')
        rels = answer_rels(s)
        for slot, (kws, _) in CONCEPTS_SLOTS.items():
            if any(any(k in r for k in kws) for r in rels):
                concept = SLOT_TO_CONCEPT.get(slot)
                if concept:
                    concept_slot_counts[concept][slot] += 1

    # Determine majority slot for each concept
    majority_slots = {}
    for concept, counter in concept_slot_counts.items():
        if counter:
            majority_slots[concept] = counter.most_common(1)[0][0]

    # Second pass: classify each case
    for cid, sp in sparql_data.items():
        s = sp.get('sparql', '')
        q = sp.get('question', '')
        rels = answer_rels(s)

        amb = classify_ambiguity(rels, q)

        # Check if hard case picked minority slot (irreducible)
        is_minority = False
        if amb['is_hard'] and amb['concept']:
            maj_slot = majority_slots.get(amb['concept'])
            is_minority = maj_slot and amb['slot'] != maj_slot

        index[cid] = {
            'hard_ambiguity': amb['is_hard'],
            'hard_minority_slot': is_minority,  # irreducible
            'concept': amb['concept'],
            'slot': amb['slot'],
            'n_slots': amb['n_slots'],
            'hidden_time': hidden_time(s, q),
            'not_exists': has_not_exists(s),
        }

    return index


# ===========================================================================
# Filtering
# ===========================================================================

FilterReason = {
    'unreachable': 'gt_hit=False (gold not in candidate pool)',
    'hard_ambiguity': 'hard multi-slot ambiguity (no disambig signal)',
    'hard_minority': 'hard ambiguity + minority slot (irreducible)',
    'date_filter': 'NOT-EXISTS + date-filter + many candidates (artifact)',
}


def apply_filters(records: List[Dict[str, Any]],
                  ambiguity_index: Dict[str, Dict[str, Any]],
                  sparql_data: Dict[str, Dict[str, Any]],
                  filters: Set[str]) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], List[str]]], Dict[str, int]]:
    """Apply filters to trajectory records.

    Args:
        records: trajectory records
        ambiguity_index: precomputed ambiguity index
        sparql_data: SPARQL labels for date-filter detection
        filters: which filters to enable {'gt_hit', 'ambiguity', 'date_filter'}

    Returns:
        (clean_records, filtered_records, filter_counts)
        - clean_records: records that passed all filters
        - filtered_records: list of (record, [reasons]) for filtered records
        - filter_counts: {reason: count} for statistics
    """
    clean = []
    filtered = []  # list of (record, [reasons])
    filter_counts = defaultdict(int)  # reason -> count

    for rec in records:
        cid = rec.get('case_id', '')
        reasons = []

        # Filter 1: gt_hit=False (unreachable)
        # Only filter if gt_hit is explicitly False (not None/missing)
        if 'gt_hit' in filters:
            gt_hit = rec.get('gt_hit')
            if gt_hit is False:  # Explicit False, not None/missing
                reasons.append('unreachable')

        # Get ambiguity info
        amb = ambiguity_index.get(cid, {})

        # Filter 2: hard-irreducible ambiguity
        if 'ambiguity' in filters:
            if amb.get('hard_minority_slot'):
                reasons.append('hard_minority')
            elif amb.get('hard_ambiguity'):
                reasons.append('hard_ambiguity')

        # Filter 3: date-filter + multi-candidate
        if 'date_filter' in filters and cid in sparql_data:
            sp = sparql_data[cid]
            n_cands = len(rec.get('answer_candidates', []))
            is_suspect, _ = detect_date_filter_multicandidate(
                sp.get('sparql', ''), sp.get('question', ''), n_cands)
            if is_suspect:
                reasons.append('date_filter')

        if reasons:
            filtered.append((rec, reasons))
            for r in reasons:
                filter_counts[r] += 1
        else:
            clean.append(rec)

    return clean, filtered, dict(filter_counts)


# ===========================================================================
# Statistics and reporting
# ===========================================================================

def compute_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute statistics over trajectory records."""
    n = len(records)
    if n == 0:
        return {'n': 0}

    scores = {
        'total_score': [],
        'S_plan': [],
        'S_select': [],
        'S_reason': [],
        'llm_f1': [],
    }
    for r in records:
        for k in scores:
            v = r.get(k)
            if v is not None:
                scores[k].append(v)

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    return {
        'n': n,
        'total_score_avg': avg(scores['total_score']),
        'S_plan_avg': avg(scores['S_plan']),
        'S_select_avg': avg(scores['S_select']),
        'S_reason_avg': avg(scores['S_reason']),
        'llm_f1_avg': avg(scores['llm_f1']),
    }


def write_report(output_path: Path,
                  total_n: int,
                  clean_stats: Dict[str, Any],
                  filter_counts: Dict[str, int],
                  ambiguity_index: Dict[str, Dict[str, Any]],
                  filters: Set[str]):
    """Write Chinese statistics report."""
    lines = []

    def add(s=''):
        lines.append(s)

    add("=" * 70)
    add("GT-SUSPECT 过滤报告 (GT-suspect Filter Report)")
    add("=" * 70)
    add()
    add(f"输入轨迹总数: {total_n}")
    add(f"启用的过滤器: {', '.join(sorted(filters)) if filters else '无'}")
    add()

    # Clean set stats
    add("-" * 70)
    add("干净集统计 (Clean Set Statistics)")
    add("-" * 70)
    add(f"干净集大小: {clean_stats['n']}")
    add(f"干净集占比: {100*clean_stats['n']/total_n:.1f}%" if total_n else "0%")
    add()
    add("分数统计:")
    # Handle empty clean set (no score keys)
    if clean_stats.get('total_score_avg') is not None:
        add(f"  total_score 平均值: {clean_stats['total_score_avg']:.3f}")
        add(f"  S_plan 平均值:     {clean_stats['S_plan_avg']:.3f}")
        add(f"  S_select 平均值:   {clean_stats['S_select_avg']:.3f}")
        add(f"  S_reason 平均值:   {clean_stats['S_reason_avg']:.3f}")
        add(f"  llm_f1 平均值:     {clean_stats['llm_f1_avg']:.3f}")
    else:
        add("  (干净集为空，无分数统计)")
    add()

    # Filtered breakdown
    add("-" * 70)
    add("过滤维度细分 (Filtered by Dimension)")
    add("-" * 70)

    total_filtered = sum(filter_counts.values())
    add(f"总剔除数: {total_filtered}")
    add(f"总剔除占比: {100*total_filtered/total_n:.1f}%" if total_n else "0%")
    add()

    for reason in sorted(filter_counts, key=lambda x: -filter_counts[x]):
        count = filter_counts[reason]
        desc = FilterReason.get(reason, reason)
        add(f"{desc}:")
        add(f"  剔除数量: {count} ({100*count/total_n:.1f}%)" if total_n else "0")

    add()

    # Ambiguity breakdown (from full index)
    add("-" * 70)
    add("歧义检测统计 (Ambiguity Detection Statistics)")
    add("-" * 70)

    hard_amb = [cid for cid, v in ambiguity_index.items() if v.get('hard_ambiguity')]
    hard_min = [cid for cid, v in ambiguity_index.items() if v.get('hard_minority_slot')]
    hidden_time = [cid for cid, v in ambiguity_index.items() if v.get('hidden_time')]
    not_exists = [cid for cid, v in ambiguity_index.items() if v.get('not_exists')]

    n_total = len(ambiguity_index)
    add(f"数据集总数: {n_total}")
    add()
    add(f"多槽 hard 歧义: {len(hard_amb)} ({100*len(hard_amb)/n_total:.1f}%)" if n_total else "0")
    add(f"  - 不可约 (minority slot): {len(hard_min)} ({100*len(hard_min)/n_total:.1f}%)" if n_total else "0")
    add(f"  - 可默认 (majority slot): {len(hard_amb)-len(hard_min)} ({100*(len(hard_amb)-len(hard_min))/n_total:.1f}%)" if n_total else "0")
    add(f"hidden-time 隐藏时间: {len(hidden_time)} ({100*len(hidden_time)/n_total:.1f}%)" if n_total else "0")
    add(f"NOT-EXISTS 子句: {len(not_exists)} ({100*len(not_exists)/n_total:.1f}%)" if n_total else "0")
    add()

    # Conclusion
    add("=" * 70)
    add("结论 (Conclusion)")
    add("=" * 70)
    clean_ratio = clean_stats['n'] / total_n if total_n else 0
    if clean_ratio >= 0.8:
        add(f"干净集占比较高 ({clean_ratio:.1%})，数据质量良好。")
    elif clean_ratio >= 0.5:
        add(f"干净集占比中等 ({clean_ratio:.1%})，噪声主要来自: ")
        if filter_counts:
            top_reason = max(filter_counts.items(), key=lambda x: x[1])
            add(f"  - {FilterReason.get(top_reason[0], top_reason[0])} ({top_reason[1]} cases)")
    else:
        add(f"干净集占比较低 ({clean_ratio:.1%})，数据噪声严重，建议检查数据源。")

    add()
    add("主要噪声来源:")
    if filter_counts:
        sorted_reasons = sorted(filter_counts.items(), key=lambda x: -x[1])
        for reason, count in sorted_reasons[:3]:
            add(f"  - {FilterReason.get(reason, reason)}: {count} ({100*count/total_n:.1f}%)" if total_n else "0")

    add()
    add("过滤是否过激评估:")
    add("  (建议抽样检查剔除的 case 确认是否真的噪声)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"报告已写入: {output_path}")


# ===========================================================================
# Main
# ===========================================================================

def main():
    p = argparse.ArgumentParser(
        description="Filter GT-suspect cases from RL trajectories")
    p.add_argument('--trajectories', type=Path, required=True,
                   help='Input trajectory JSONL file')
    p.add_argument('--cwq-pkl', type=Path, default=None,
                   help='Gold pkl file (for gt_hit verification)')
    p.add_argument('--sparql', type=Path, required=True,
                   help='SPARQL labels JSON (test.json)')
    p.add_argument('--output', type=Path, required=True,
                   help='Output clean trajectories JSONL')
    p.add_argument('--report', type=Path, required=True,
                   help='Output statistics report (.txt)')
    p.add_argument('--suspect-output', type=Path, default=None,
                   help='Optional: write filtered suspect cases to separate file')
    p.add_argument('--no-gt-hit', dest='gt_hit', action='store_false', default=True,
                   help='Disable gt_hit filter')
    p.add_argument('--no-ambiguity', dest='ambiguity', action='store_false', default=True,
                   help='Disable ambiguity filter')
    p.add_argument('--no-date-filter', dest='date_filter', action='store_false', default=True,
                   help='Disable date-filter filter')
    p.add_argument('--only-hard-minority', action='store_true',
                   help='Only filter hard-minority (irreducible) ambiguity, not all hard')

    args = p.parse_args()

    # Build filter set
    filters = set()
    if args.gt_hit:
        filters.add('gt_hit')
    if args.ambiguity:
        filters.add('ambiguity')
    if args.date_filter:
        filters.add('date_filter')

    print("加载数据...")
    trajectories = load_trajectories(args.trajectories)
    print(f"  轨迹记录: {len(trajectories)}")

    sparql_data = load_sparql(args.sparql)
    print(f"  SPARQL 标签: {len(sparql_data)}")

    gold_data = None
    if args.cwq_pkl and args.cwq_pkl.exists():
        gold_data = load_gold_pkl(args.cwq_pkl)
        print(f"  Gold pkl: {len(gold_data)}")

    print("\n构建歧义索引...")
    ambiguity_index = build_ambiguity_index(sparql_data, gold_data or {})

    print("\n应用过滤器...")
    clean, filtered, filter_counts = apply_filters(trajectories, ambiguity_index, sparql_data, filters)

    # Compute statistics
    clean_stats = compute_statistics(clean)

    # Write outputs
    print(f"\n写入干净集: {len(clean)} records -> {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        for rec in clean:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    # Optionally write suspect cases
    if args.suspect_output and filtered:
        print(f"写入可疑集: {len(filtered)} records -> {args.suspect_output}")
        with open(args.suspect_output, 'w', encoding='utf-8') as f:
            for rec, reasons in filtered:
                # Add filter reasons to record
                rec_copy = dict(rec)
                rec_copy['_filter_reasons'] = reasons
                f.write(json.dumps(rec_copy, ensure_ascii=False) + '\n')

    # Write report
    write_report(args.report, len(trajectories), clean_stats, filter_counts,
                 ambiguity_index, filters)

    print("\n完成!")
    print(f"  干净集: {clean_stats['n']}/{len(trajectories)} ({100*clean_stats['n']/len(trajectories):.1f}%)" if trajectories else "0%")


if __name__ == '__main__':
    main()
