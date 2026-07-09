"""Logical path construction and materialization for mode-level traversal."""
from __future__ import annotations

import os
from collections import defaultdict
from typing import List, Optional

from kgqa.core.utils import normalize
from kgqa.traversal.cvt import is_cvt_like
from kgqa.traversal.path_utils import compress_paths, _is_noisy_path_relation


# Directional traversal switch. Freebase stores directed relations as distinct
# names (e.g. location.location.contains vs location.location.containedby) with
# NO .inv twin, so building an undirected adjacency (adding the reverse edge
# h<-t) is semantically wrong: it turns "A containedby B" (A belongs to B) into
# a bogus "B containedby A". Set KGQA_DIRECTED_TRAVERSAL=1 to respect edge
# direction (only h -> t), which removes the hub-snowball noise (e.g. Pacific
# Ocean's dozens of contained islands pulled in when traversing containedby).
DIRECTED_TRAVERSAL = os.getenv("KGQA_DIRECTED_TRAVERSAL", "0") == "1"


def _build_adj(h_ids, r_ids, t_ids, with_edge_idx=False, skip_rel_ids=None):
    """Build the traversal adjacency.

    When DIRECTED_TRAVERSAL is set, edges are directed (h -> t only). Otherwise
    undirected (both directions), preserving the original behavior.
    """
    adj = {}
    skip = skip_rel_ids or set()
    if with_edge_idx:
        for edge_idx, (h, r, t) in enumerate(zip(h_ids, r_ids, t_ids)):
            if r in skip:
                continue
            adj.setdefault(h, []).append((t, r, edge_idx))
            if not DIRECTED_TRAVERSAL:
                adj.setdefault(t, []).append((h, r, edge_idx))
    else:
        for h, r, t in zip(h_ids, r_ids, t_ids):
            if r in skip:
                continue
            adj.setdefault(h, []).append((t, r))
            if not DIRECTED_TRAVERSAL:
                adj.setdefault(t, []).append((h, r))
    return adj


def _extract_candidate_names_from_paths(paths, ents, anchor_idx, breakpoint_indices, limit=20):
    counts = _candidate_name_counts_from_paths(paths, ents, anchor_idx, breakpoint_indices)
    return [name for name, _ in counts[:limit]]


def _candidate_name_counts_from_paths(paths, ents, anchor_idx, breakpoint_indices):
    counts = defaultdict(int)
    bp_set = breakpoint_indices if breakpoint_indices else set()
    for path in paths:
        nodes = path.get("nodes", [])
        start_pos = 0
        if bp_set:
            for pos, node_idx in enumerate(nodes):
                if node_idx in bp_set and node_idx != anchor_idx:
                    start_pos = pos + 1
                    break
        node_iter = nodes[start_pos:] if start_pos else nodes
        for node_idx in node_iter:
            if node_idx == anchor_idx or node_idx in bp_set:
                continue
            if 0 <= node_idx < len(ents):
                name = ents[node_idx]
                if is_cvt_like(name):
                    continue
                key = normalize(name)
                if len(key) < 2:
                    continue
                counts[name] += 1
    return list(counts.items())


def build_mode_level_logical_paths(anchor_idx, step_relations, h_ids, r_ids, t_ids,
                                   ents, rels_list, breakpoint_indices,
                                   beam_width=80, max_hops_per_step=2,
                                   max_states=1200, max_raw_paths_per_pattern=24,
                                   relation_list=None):
    """Traverse relation modes first and keep bounded witness paths.

    The model selects logical modes before raw path materialization, so this
    routine keeps one short witness plus a few siblings per mode instead of
    enumerating every raw entity path up front.
    """
    if anchor_idx is None or not step_relations:
        return []

    noisy_rel_ids = set()
    if relation_list is not None:
        for ri, rname in enumerate(relation_list):
            if _is_noisy_path_relation(rname):
                noisy_rel_ids.add(ri)

    adj = _build_adj(h_ids, r_ids, t_ids, with_edge_idx=True, skip_rel_ids=noisy_rel_ids)

    def _hit_paths(state, target_rels, step_idx):
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        hits = []

        def _make_hit(extra_nodes, extra_rels, extra_edges, hit_rel):
            return {
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),
                "covered_steps": state["covered_steps"] | frozenset({step_idx}),
                "terminal_rels": state["terminal_rels"] + (hit_rel,),
                "skipped_steps": state["skipped_steps"],
                "endpoint_steps": state.get("endpoint_steps", frozenset()),
                "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
                "depth": state["depth"] + len(extra_rels),
            }

        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if rel1 in target_rels:
                hits.append(_make_hit((nb1,), (rel1,), (e1,), rel1))
                # CVT transparency: a 1-hop target hit landing on a CVT mediator
                # must continue through the CVT to its target-relation out-edges.
                # A CVT-mediated fact carries BOTH the in- and out-relations
                # (e.g. people.person.education -> CVT -> education.education.
                # institution); matching only the in-edge leaves the CVT a dead
                # end and loses the answer behind it. This within-step 2-hop
                # (max_hops_per_step>=2) mirrors the CVT-bridging already in
                # _anchor_outgoing_rel_ids / expand_through_cvt.
                if (max_hops_per_step >= 2 and 0 <= nb1 < len(ents)
                        and is_cvt_like(ents[nb1])):
                    used1 = used_edges | frozenset({e1})
                    for nb2, rel2, e2 in adj.get(nb1, ()):
                        if e2 in used1:
                            continue
                        if rel2 in target_rels:
                            hits.append(_make_hit((nb1, nb2), (rel1, rel2),
                                                   (e1, e2), rel2))
                continue
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if rel2 in target_rels:
                    hits.append(_make_hit((nb1, nb2), (rel1, rel2), (e1, e2), rel2))
        return hits

    endpoint_targets = set(breakpoint_indices or ()) - {anchor_idx, None}
    nonempty_step_indices = [i for i, rels_for_step in enumerate(step_relations) if rels_for_step]
    endpoint_bridge_step = nonempty_step_indices[-1] if nonempty_step_indices else None

    def _endpoint_bridge_paths(state, step_idx):
        if not endpoint_targets or step_idx != endpoint_bridge_step:
            return []
        nodes = state["nodes"]
        rels = state["relations"]
        used_edges = state["used_edges"]
        end = nodes[-1]
        if end in endpoint_targets:
            return []

        hits = []
        for nb1, rel1, e1 in adj.get(end, ()):
            if e1 in used_edges:
                continue
            if nb1 in endpoint_targets:
                hits.append((1, (nb1,), (rel1,), (e1,)))
                continue
            if max_hops_per_step < 2:
                continue
            used1 = used_edges | frozenset({e1})
            for nb2, rel2, e2 in adj.get(nb1, ()):
                if e2 in used1:
                    continue
                if nb2 in endpoint_targets:
                    hits.append((2, (nb1, nb2), (rel1, rel2), (e1, e2)))

        if not hits:
            return []
        min_depth = min(depth for depth, _, _, _ in hits)
        bridged = []
        endpoint_marker = -100000 - step_idx
        for _, extra_nodes, extra_rels, extra_edges in hits:
            if len(extra_nodes) != min_depth:
                continue
            bridged.append({
                "nodes": nodes + tuple(extra_nodes),
                "relations": rels + tuple(extra_rels),
                "used_edges": used_edges | frozenset(extra_edges),
                "covered_steps": state["covered_steps"] | frozenset({step_idx}),
                "terminal_rels": state["terminal_rels"] + (endpoint_marker,),
                "skipped_steps": state["skipped_steps"],
                "endpoint_steps": state.get("endpoint_steps", frozenset()) | frozenset({step_idx}),
                "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
                "depth": state["depth"] + len(extra_rels),
            })
        return bridged

    def _state_rank(state):
        return (
            -len(state["covered_steps"]),
            len(state["skipped_steps"]),
            state["depth"],
            state["terminal_rels"],
            state["nodes"][-1],
        )

    def _prune_states(states):
        grouped = {}
        for state in states:
            sig = (state["terminal_rels"], state["nodes"][-1], state["covered_steps"], state["skipped_steps"])
            prev = grouped.get(sig)
            if prev is None or _state_rank(state) < _state_rank(prev):
                grouped[sig] = state
        return sorted(grouped.values(), key=_state_rank)[:max_states]

    active = [{
        "nodes": (anchor_idx,),
        "relations": (),
        "used_edges": frozenset(),
        "covered_steps": frozenset(),
        "terminal_rels": (),
        "skipped_steps": frozenset(),
        "endpoint_steps": frozenset(),
        "domain_fallback_steps": frozenset(),
        "depth": 0,
    }]
    summary_states = []

    for step_idx, rels_for_step in enumerate(step_relations):
        target_rels = set(rels_for_step or ())
        if not target_rels:
            continue

        next_active = []
        for state in active:
            hits = _hit_paths(state, target_rels, step_idx)
            if hits:
                next_active.extend(hits)
            else:
                endpoint_hits = _endpoint_bridge_paths(state, step_idx)
                if endpoint_hits:
                    next_active.extend(endpoint_hits)
                elif state["depth"] > 0:
                    # Hit-and-stop: a failed step should preserve the best
                    # path reached so far, not append same-domain exploratory
                    # edges and present them as if the step was matched.
                    skipped = dict(state)
                    skipped["skipped_steps"] = state["skipped_steps"] | frozenset({step_idx})
                    next_active.append(skipped)

        if not next_active:
            break
        active = _prune_states(next_active)
        summary_states.extend(s for s in active if s["depth"] > 0)

    if not summary_states:
        return []

    raw_summaries = []
    seen_raw = set()
    for state in sorted(summary_states, key=_state_rank):
        path = {
            "nodes": list(state["nodes"]),
            "relations": list(state["relations"]),
            "depth": state["depth"],
            "covered_steps": state["covered_steps"],
            "matched_relations": frozenset(state["relations"]),
            "terminal_relations": state["terminal_rels"],
            "skipped_steps": state["skipped_steps"],
            "endpoint_steps": state.get("endpoint_steps", frozenset()),
            "domain_fallback_steps": state.get("domain_fallback_steps", frozenset()),
            "_used_edges": state["used_edges"],
            "_mode_summary": True,
        }
        sig = (tuple(path["nodes"]), tuple(path["relations"]))
        if sig in seen_raw:
            continue
        seen_raw.add(sig)
        raw_summaries.append(path)

    logical_paths = compress_paths(raw_summaries, ents, rels_list, anchor_idx, breakpoint_indices)
    for lp in logical_paths:
        raw_paths = lp.get("raw_paths", [])
        lp["path_count"] = len(raw_paths)
        lp["mode_summary"] = True
        lp["materialized"] = False
        skipped = set()
        covered = set()
        for rp in raw_paths:
            skipped.update(rp.get("skipped_steps", frozenset()))
            covered.update(rp.get("covered_steps", frozenset()))
        lp["skipped_steps"] = frozenset(skipped)
        lp["covered_steps"] = frozenset(covered)
        lp["endpoint_steps"] = frozenset().union(
            *(rp.get("endpoint_steps", frozenset()) for rp in raw_paths)
        ) if raw_paths else frozenset()
        lp["domain_fallback_steps"] = frozenset().union(
            *(rp.get("domain_fallback_steps", frozenset()) for rp in raw_paths)
        ) if raw_paths else frozenset()
        if len(raw_paths) > max_raw_paths_per_pattern:
            lp["raw_paths"] = raw_paths[:max_raw_paths_per_pattern]
        candidate_counts = _candidate_name_counts_from_paths(
            raw_paths, ents, anchor_idx, breakpoint_indices)
        lp["candidate_counts"] = dict(candidate_counts)
        lp["candidates"] = [name for name, _ in candidate_counts[:20]]
    return logical_paths


def materialize_selected_logical_patterns(selected_patterns, ents, rels_list,
                                          h_ids, r_ids, t_ids, anchor_idx,
                                          breakpoint_indices,
                                          max_paths_per_pattern=200,
                                          max_count_per_pattern=10000):
    """After mode selection, enumerate raw paths for each selected exact witness mode."""
    if not selected_patterns or anchor_idx is None:
        return selected_patterns

    adj = _build_adj(h_ids, r_ids, t_ids, with_edge_idx=True)

    materialized = []
    for lp in selected_patterns:
        witness = lp.get("best_raw_path") or {}
        rel_seq = tuple(witness.get("relations", []))
        if not rel_seq:
            materialized.append(lp)
            continue

        found_paths = []
        path_count = 0
        stack = [(anchor_idx, (anchor_idx,), (), frozenset(), 0)]
        while stack:
            node, nodes, rels, used_edges, pos = stack.pop()
            if pos == len(rel_seq):
                path_count += 1
                if len(found_paths) < max_paths_per_pattern:
                    found_paths.append({
                        "nodes": list(nodes),
                        "relations": list(rels),
                        "depth": len(rels),
                        "covered_steps": witness.get("covered_steps", frozenset()),
                        "matched_relations": frozenset(rels),
                    })
                if path_count >= max_count_per_pattern:
                    break
                continue

            target_rel = rel_seq[pos]
            for nb, rel, edge_idx in adj.get(node, ()):
                if edge_idx in used_edges or rel != target_rel:
                    continue
                stack.append((
                    nb,
                    nodes + (nb,),
                    rels + (rel,),
                    used_edges | frozenset({edge_idx}),
                    pos + 1,
                ))

        if not found_paths:
            materialized.append(lp)
            continue

        found_paths.sort(key=lambda p: (p["depth"], p["nodes"]))
        new_lp = dict(lp)
        new_lp["raw_paths"] = found_paths
        new_lp["best_raw_path"] = found_paths[0]
        new_lp["path_count"] = path_count
        new_lp["path_count_capped"] = path_count >= max_count_per_pattern
        new_lp["materialized"] = True
        count_suffix = f"{path_count}{'+' if new_lp['path_count_capped'] else ''}"
        readable = new_lp.get("readable", "")
        if readable and "materialized paths=" not in readable:
            new_lp["readable"] = f"{readable}  [materialized paths={count_suffix}]"
        candidate_counts = _candidate_name_counts_from_paths(
            found_paths, ents, anchor_idx, breakpoint_indices)
        new_lp["candidate_counts"] = dict(candidate_counts)
        new_lp["candidates"] = [name for name, _ in candidate_counts[:20]]
        materialized.append(new_lp)
    return materialized
