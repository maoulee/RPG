"""SEQ ReAct loop — the per-fact sequential pipeline (parallel to react_loop).

Copies react_loop's GENERIC turn body (parse → validate → dispatch → append) and
rewires three things only:
  - state machine  → seq_harness (INIT → decompose → RESOLVE_FACT loop → ANSWER)
  - dispatch       → seq_tools (decompose grounds f1; resolve_fact walks one hop +
                     auto-penetrates CVTs + grounds the next fact on real entities)
  - system prompt  → SEQ_AGENTS.md

parse_react_output / _to_tool_calls / _call_single_with_reasoning / build_context /
_ctx_to_result_dict are REUSED from the SAPS code paths unchanged. SAPS react_loop,
harness, tools, AGENTS.md are not touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp

from kgqa.agent.loop import build_context, _ctx_to_result_dict
from kgqa.core.utils import strip_reasoning_leak
from kgqa.agent.seq_harness import (
    SeqAgentState, validate as seq_validate, _allowed_hint as seq_allowed_hint,
    commit_due, blocking_facts, norm_fact_key,
)
from kgqa.agent import seq_tools as ST
from kgqa.agent.seq_schemas import validate_args
from kgqa.agent.react_loop import parse_react_output, _to_tool_calls  # reuse verbatim

_AGENT_DIR = Path(__file__).resolve().parent

# Model checkpoint declaration: `[fid ✓] ?var = [v1 | v2 | ...]` (| -separated values,
# the same separator as the tree display — avoids comma-in-entity-name collisions).
# Later declarations override earlier ones (a fact may be re-resolved with tighter bindings).
_CKPT_RE = re.compile(r'\[[^\]]*?✓\]\s*(\?\w+)\s*=\s*\[([^\]]*)\]')

# Plan-contract v2 closure declarations (2026-08-21): a fact may be CLOSED without
# bindings — `[fid ✗ empty]` (no advancing relation/content in the reachable pool)
# or `[fid ✗ moot]` (the terminal variable was already bound by earlier evidence).
# Closures free the model from the complete-every-fact contract (the Ramble/VP
# specimen looped 16 rounds on a dead-end fact and scored empty).
_CKPT_CLOSE_RE = re.compile(r'\[([^\]]*?)✗\s*(empty|moot)\]')


def _canonical_decl_fid(ctx, raw: str, var: str) -> str:
    """Canonical declared fact id for a checkpoint declaration's fid slot.

    The model sometimes copies the DOC PLACEHOLDER (`[fid ✓]`, `[fid ✗ empty]`)
    instead of a real fact id — the declaration then lands under a junk key
    that fact_key_map/norm_fact_key never resolve, so completion accounting
    misses the fact and the EVIDENCE COMMIT never fires (22% of fuse-on cohort
    trajectories, 2026-08-22). Resolution: real ids pass through fact_key_map;
    the placeholder family resolves via the DECLARED VARIABLE against the
    plan's fact_edges (the open fact having that var on either side), falling
    back to the single declared fact for var-less ✗ closures. The mapping is
    memoized per raw key on ctx so re-statements hit the same freeze-lock
    entry regardless of how the open/declared sets shift later."""
    k = (raw or "").strip()
    if not k:
        return k
    alias = getattr(ctx, "_fid_alias", None)
    if alias is None:
        alias = {}; ctx._fid_alias = alias
    if k in alias:
        return alias[k]
    km = getattr(ctx, "fact_key_map", None) or {}
    fids = getattr(ctx, "fact_ids", None) or []
    if k in km:
        alias[k] = km[k]
        return km[k]
    if k in fids or "." in k:
        alias[k] = k
        return k
    if k.lower() in ("fid", "f", "fact", "id"):
        edges = getattr(ctx, "fact_edges", None) or {}
        taken = set(getattr(ctx, "declared_facts", None) or {}) | \
            set(getattr(ctx, "closed_facts", None) or {})
        # tail-exact first: a ✓ declaration binds the fact's OUTPUT side; a
        # chain var (f1 tail ?x, f2 head ?x) is ambiguous under plain
        # membership but unique under tail-matching
        tail_m = [f for f, ht in edges.items()
                  if var and len(ht) >= 2 and ht[1] == var and f not in taken]
        any_m = [f for f, ht in edges.items()
                 if var and var in ht and f not in taken]
        pick = None
        if len(tail_m) == 1:
            pick = tail_m[0]
        elif len(any_m) == 1:
            pick = any_m[0]
        elif not var and len(fids) == 1:
            pick = fids[0]      # var-less ✗ closure on a single-fact plan
        if pick:
            alias[k] = pick
            return pick
    return k


def _update_var_bindings(ctx, content: str) -> None:
    """Parse the model's checkpoint declarations and merge into ctx.var_bindings
    (?variable -> bound entity names). The model declares the curated binding for a
    variable after the retrieve_subgraph that resolves it; downstream tool calls that
    reference `?var` are expanded from this map (seq_tools._expand_entities).
    Closure declarations (`[fid ✗ empty|moot]`) are recorded in ctx.closed_facts —
    they bind nothing, but the harness (and later hints) can distinguish "fact
    resolved" from "fact closed" from "fact still open"."""
    if not content:
        return
    vb = getattr(ctx, "var_bindings", None)
    if vb is None:
        ctx.var_bindings = vb = {}
    cf = getattr(ctx, "closed_facts", None)
    if cf is None:
        ctx.closed_facts = cf = {}
    for m in _CKPT_CLOSE_RE.finditer(content):
        cf[_canonical_decl_fid(ctx, m.group(1), "")] = m.group(2)
    for m in _CKPT_RE.finditer(content):
        var, vals = m.group(1), m.group(2)
        parts = [p.strip() for p in re.split(r'\s*\|\s*', vals) if p.strip()]
        # CVT-BINDING GUARD (2026-08-21, Angelina awards specimen): the model
        # bound raw m./g. event nodes as variable values. Events are records,
        # never entities — strip them and flag for a harness reminder on the
        # next turn (the prose note alone did not stop the behavior).
        from kgqa.traversal.cvt import is_cvt_like as _is_cvt
        cvt_bound = [p for p in parts if _is_cvt(p)]
        _all_cvt = False
        if cvt_bound:
            ctx.cvt_binding_flag = True
            parts = [p for p in parts if not _is_cvt(p)]
            _all_cvt = not parts and var.startswith("?")
        # PER-SUBGRAPH HALLUCINATION CHECK (2026-08-21, user proposal): every
        # binding of [fid ✓] must have appeared in THAT subgraph's displayed
        # evidence (ctx.fact_evidence[fid]). Entities from other subgraphs or
        # thin air (Costner specimen: Twilight merged into sg1.f1) are stripped
        # and reported — the model re-declares from the correct subgraph.
        # VARIABLE FREEZING (2026-08-21, user ruling): a VALID ✓ declaration
        # locks the fact's bindings; a later re-declaration without a NEW
        # retrieve_subgraph for that fid is rejected (the Costner specimen
        # mutated sg1.f1 at answer time). The lock opens only when fresh
        # evidence for the same fid arrives (fact_evidence_seq advanced).
        fid_m = re.match(r"\[([^\]]*?)✓\]", m.group(0))
        _fid_key = _canonical_decl_fid(
            ctx, (fid_m.group(1) or "").strip() if fid_m else "", var)
        if _all_cvt and _fid_key:
            # CVT-CHAIN DEADLOCK (Norwood specimen): every value was an
            # event — this variable can never bind, and a later fact
            # planned to walk from it is stranded. Remember (var, fid) so
            # the unbound-variable error can point at the moot-closure
            # exit instead of the generic re-declare instruction (which
            # looped declare→error for 16 turns before this).
            if getattr(ctx, "cvt_empty_var", None) is None:
                ctx.cvt_empty_var = (var, _fid_key)
        _decl = getattr(ctx, "declared_facts", None)
        if _decl is None:
            _decl = {}; ctx.declared_facts = _decl
        _cur_seq = getattr(ctx, "fact_evidence_seq", {}).get(_fid_key, 0)
        # PER-SUBGRAPH HALLUCINATION FILTER runs BEFORE the freeze check: the
        # standing fact_bindings store POST-filter values, so the idempotence
        # comparison below must see the same filtered shape (otherwise a
        # faithful re-statement of a once-filtered declaration misreads as a
        # value change).
        fe = getattr(ctx, "fact_evidence", {}).get(_fid_key) if _fid_key else None
        halluc = []
        if fe:
            from kgqa.core.utils import normalize as _norm
            keep = []
            for p in parts:
                if any(_norm(p) == e or (len(_norm(p)) >= 4 and _norm(p) in e)
                       or (len(e) >= 4 and e in _norm(p)) for e in fe):
                    keep.append(p)
                else:
                    halluc.append(p)
            parts = keep
        if _fid_key in _decl and _decl[_fid_key] == _cur_seq:
            # IDEMPOTENT RE-STATEMENT (Stop-motion specimen, 2026-08-19): the
            # model often re-states a standing declaration verbatim (possibly
            # re-ordered) when composing the §18 answer checklist. That is NOT
            # a hallucination — reject only when the VALUE SET actually moves.
            from kgqa.core.utils import normalize as _nz2
            _fb = getattr(ctx, "fact_bindings", {}).get(_fid_key) or []
            _new_s, _old_s = {_nz2(p) for p in parts}, {_nz2(p) for p in _fb}
            if _new_s == _old_s:
                continue                  # identical re-statement: keep the lock silently
            if _new_s <= _old_s:
                # REFINEMENT (Belgium specimen, 2026-08-22): narrowing the
                # standing set to a SUBSET is discrimination, not hallucination —
                # the two-stage analysis may collapse [W-Europe|Europe|Eurasia|
                # N-Hemisphere] to [Europe]. Accept and update the lock.
                _fbind = getattr(ctx, "fact_bindings", None)
                if _fbind is not None:
                    _fbind[_fid_key] = list(parts)
                vb[var] = list(parts)
                continue
            ctx.frozen_binding_flag = (_fid_key, parts[:8])
            ctx.halluc_binding_flag = None    # the whole declaration is rejected; one message
            continue                      # frozen: no new evidence, keep the lock
        if halluc:
            ctx.halluc_binding_flag = (_fid_key, halluc[:8])
        if parts:
            vb[var] = parts
            _decl[_fid_key] = _cur_seq    # (re)lock at the current evidence seq
            # PATTERN-STATE (user design 2026-09-10): a variable declared from
            # this fact's subgraph carries THAT walk's node set — a later
            # single-?var retrieval continues over it as a prefix mask (the
            # bindings are the pattern's tails; their walks must not re-traverse
            # the territory the declaring walk already covered).
            _fpat = (getattr(ctx, "fid_pattern", None) or {}).get(_fid_key)
            if _fpat and _fpat.get("nodes"):
                _ps = getattr(ctx, "pattern_state", None)
                if _ps is None:
                    _ps = ctx.pattern_state = {}
                _prev = _ps.get(var)
                if _prev is None:
                    _ps[var] = {"nodes": _fpat["nodes"]}
                else:
                    _ps[var] = {"nodes": _prev["nodes"] | _fpat["nodes"]}
            # PER-FID binding store (join support): vb is keyed by VARIABLE, so
            # a second subgraph declaring the same var overwrites the first —
            # the harness join below needs each fact's OWN values to intersect.
            _fbind = getattr(ctx, "fact_bindings", None)
            if _fbind is None:
                _fbind = {}; ctx.fact_bindings = _fbind
            _fvars = getattr(ctx, "fact_vars", None)
            if _fvars is None:
                _fvars = {}; ctx.fact_vars = _fvars
            _fbind[_fid_key] = list(parts)
            _fvars[_fid_key] = var
            # Seed declared bindings into subgraph_entities. The model curated these from
            # a prior retrieve_subgraph (the checkpoint marks the fact resolved); they ARE
            # valid centers. Without seeding, the boundary check rejects bindings that
            # appeared in the dense tree but weren't accumulated into the subgraph set
            # (display/accumulate mismatch) — e.g. ?religion=[Catholicism|...] then
            # retrieve_relations(center:?religion) failed "not in retrieved subgraph".
            # Only seed bindings that resolve to a graph entity (hallucinated names stay out).
            se = getattr(ctx, "subgraph_entities", None)
            if se is not None and getattr(ctx, "ents", None):
                from kgqa.core.utils import normalize as _norm
                # multi-map: a name can match several indices (text+non_text dup); add ALL
                from collections import defaultdict as _dd
                n2i_all = _dd(list)
                for _i, _e in enumerate(ctx.ents):
                    if _e:
                        n2i_all[_norm(_e)].append(_i)
                for p in parts:
                    for idx in n2i_all.get(_norm(p), ()):
                        se.add(idx)

    # SYSTEM JOIN (user ruling, 2026-08-19): when TWO OR MORE subgraphs bind the
    # SAME variable (multi-anchor constraint plans, e.g. 'genre Stop motion'
    # and 'Miley Cyrus films' both → ?films), every constraint must hold — the
    # effective binding is the INTERSECTION, not the last declaration. Compute
    # it harness-side and expose via ctx.var_joins (injected as a system note
    # next turn) so the model never has to eyeball 40-item lists.
    _fbind = getattr(ctx, "fact_bindings", None) or {}
    _fvars = getattr(ctx, "fact_vars", None) or {}
    if _fbind:
        from kgqa.core.utils import normalize as _nj
        from collections import defaultdict as _dj
        _by_var = _dj(list)
        for _f, _v in _fvars.items():
            if _f in _fbind:
                _by_var[_v].append(_f)
        _joins = getattr(ctx, "var_joins", None)
        if _joins is None:
            _joins = {}; ctx.var_joins = _joins
        for _v, _fids in _by_var.items():
            if len(_fids) < 2:
                continue
            _fids = sorted(_fids)
            _sets = []
            _orig = {}
            for _f in _fids:
                _s, _o = set(), {}
                for p in _fbind[_f]:
                    k = _nj(p)
                    _s.add(k); _o.setdefault(k, p)
                _sets.append(_s); _orig.update(_o)
            _inter = sorted(_sets[0].intersection(*_sets[1:]))
            _inter_orig = [_orig[k] for k in _inter]   # original casing for display/rescue
            _prev = _joins.get(_v)
            _cur_join = (tuple(_fids), tuple(_inter_orig))
            if _prev != _cur_join:
                ctx.join_flag = (_v, _fids, _inter_orig)
            _joins[_v] = _cur_join
            # EMPTY intersections are NOT enforced (Thundera specimen, 2026-08-19):
            # a checkpoint declaration is a CURATED list, not a complete
            # enumeration — sg1 may list only representative bindings while the
            # gold sits in the un-listed remainder. Forcing vb=[] on an empty
            # intersection converted four previously-perfect cases to empties.
            # NON-empty enforcement REMOVED too (V2.1, 2026-08-22): missing
            # evidence ≠ negative evidence — the join report informs, the
            # answer stage decides under the support policy; the harness no
            # longer hard-collapses bindings.
            if _inter_orig:
                pass    # support computed at EVIDENCE COMMIT; vb untouched


def _parse_flat(content: str):
    """Parse a flat key:value tool-call format (no JSON braces/brackets).
    Each line is 'key: value'. Lists use '|'. Facts use 'head | sub-question | tail'.
    Subgraph fields: 'sgN.anchor: value', 'sgN.fM: head | sub-question | tail'.

    This is inherently more stable than JSON: no brace/bracket matching, each line
    is independent (robust to reasoning-leak corruption — a leaked line doesn't
    break the structure). The model outputs this format; the parser constructs the
    args dict, which is then validated by Pydantic."""
    lines = content.split('\n')
    tool_name = None
    kv: dict = {}
    sg_data: dict = {}   # {sg_id: {'anchor': str, 'facts': list}}
    _last_list_key = None

    for line in lines:
        line = line.strip().strip('`').strip()
        if not line or line.startswith('#') or line.startswith('```') or line.startswith('json'):
            continue
        # continuation line for a wrapped list value: long entity lists fold across
        # lines in generation ('\n | Theologian | Writer ...'); without this the
        # answer parser keeps only the first line's entities (observed: 9-entity
        # FINAL_BINDINGS emitted, 4 parsed → F1 0.2 instead of 0.8).
        if line.startswith('|') and _last_list_key and isinstance(kv.get(_last_list_key), list):
            more = [p.strip() for p in line.strip('|').split('|') if p.strip()]
            kv[_last_list_key].extend(more)
            continue
        if line.lower().startswith('tool:'):
            tool_name = line.split(':', 1)[1].strip()
            continue
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()

        # subgraph fields: sgN.anchor / sgN.fM / sgN.fM.covers (V2.1 contract)
        if '.' in key and key.split('.')[0].lower().startswith('sg'):
            parts = key.split('.', 1)
            sg_id, field = parts[0], parts[1]
            sg = sg_data.setdefault(sg_id, {'anchor': '', 'facts': [], 'covers': {}})
            if field.lower() == 'anchor':
                sg['anchor'] = val
            elif field.lower().startswith('f'):
                if '.' in field:   # sgN.fM.covers: R1 — contract linkage, not a fact
                    fnum = field.split('.', 1)[0]
                    sg['covers'][fnum.lower()] = val.strip()
                else:
                    fact = [p.strip() for p in val.split('|')]
                    if len(fact) >= 3:
                        sg['facts'].append(fact[:3])
            _last_list_key = None
            continue
        # V2.1 Question Contract requirement lines: R1.kind / R1.text / D1.kind …
        if re.match(r'^[RD]\d+\.(kind|text)$', key, re.I):
            rid, rfield = key.split('.', 1)
            req = kv.setdefault('_requirements', {})
            req.setdefault(rid.upper(), {})[rfield.lower()] = val
            _last_list_key = None
            continue

        # regular key:value — list fields accept pipe-separated, JSON-array syntax,
        # or a bare value. JSON-array handling is essential: the base model often
        # writes `center: ["Harvard Art Museum"]` or `entities: []` (JSON syntax)
        # inside the flat format. Without this, the value is stored as the literal
        # string '["Harvard Art Museum"]' (one entity named '["Harvard..."]') and
        # `entities: []` becomes ['[]'] (which the scorer's empty-normalization
        # bug then read as a perfect match for any gold).
        list_keys = ('entities', 'center', 'relations', 'candidates')
        if key.lower() in list_keys:
            if val.startswith('[') and val.endswith(']'):
                try:
                    parsed = json.loads(val)
                    kv[key] = [str(x).strip() for x in parsed if str(x).strip()] \
                        if isinstance(parsed, list) else val
                except json.JSONDecodeError:
                    kv[key] = val
            elif '|' in val:
                kv[key] = [v.strip() for v in val.split('|') if v.strip()]
            else:
                kv[key] = val
            _last_list_key = key
        else:
            kv[key] = val
            _last_list_key = None

    if not tool_name:
        return None, None

    # construct args dict based on tool_name
    def _as_list(v):
        return v if isinstance(v, list) else ([v] if v else [])

    if tool_name in ('plan', 'decompose'):
        subgraphs = [{'id': sg_id, 'anchor': sg['anchor'], 'facts': sg['facts'],
                      'covers': sg.get('covers', {})}
                     for sg_id, sg in sorted(sg_data.items())]
        return tool_name, {
            'subgraphs': subgraphs,
            'requirements': kv.get('_requirements'),
            'entities': _as_list(kv.get('entities')),
            'answer': kv.get('answer', ''),
            'answer_type': kv.get('answer_type', ''),
        }
    if tool_name == 'retrieve_relations':
        return tool_name, {
            'center': _as_list(kv.get('center')),
            'question': kv.get('question', ''),
        }
    if tool_name == 'retrieve_subgraph':
        return tool_name, {
            'center': _as_list(kv.get('center')),
            'relations': _as_list(kv.get('relations')),
            'sg': kv.get('sg', ''),
        }
    if tool_name == 'answer':
        return tool_name, {'entities': _as_list(kv.get('entities'))}
    return tool_name, kv


def _parse_with_repair(content: str):
    """parse_react_output with conservative JSON repair + multi-tool retry.
    Layered:
      1. strict parse (whole content — parse_react_output does bracket-balance + ?var quoting).
      2. trailing-comma repair (whole content).
      3. multi-tool retry: the model's reasoning may LEAK mid-JSON (vLLM reasoning_end_str
         force-injected at thinking-budget exhaustion), corrupting the first `tool:` segment.
         The model often re-emits a CLEAN `tool:` line after the leak — scan ALL `tool:`
         occurrences, try each segment, return the first that yields a valid tool. This
         eliminates the ~52 decompose rejections caused by the reasoning-leak-on-long-payload.
      4. flat format: no JSON braces — each line is an independent key:value pair.
         Inherently stable (reasoning-leak corrupts one line, not the whole structure).
         The model may output flat format OR corrupted JSON — this catches both.
    SAPS parse_react_output is left untouched."""
    # 1. strict parse (whole content)
    tool, args = parse_react_output(content)
    if tool:
        return tool, args
    # 2. trailing-comma repair
    repaired = re.sub(r',(\s*[}\]])', r'\1', content)
    if repaired != content:
        tool, args = parse_react_output(repaired)
        if tool:
            return tool, args
    # 3. multi-tool retry: reasoning-leak may corrupt the first tool: JSON mid-write;
    #    the model often re-emits a clean version. Try each tool: occurrence.
    for m in re.finditer(r'tool:\s*\{', content):
        segment = content[m.start():]
        tool, args = parse_react_output(segment)
        if tool:
            return tool, args
        seg_repaired = re.sub(r',(\s*[}\]])', r'\1', segment)
        if seg_repaired != segment:
            tool, args = parse_react_output(seg_repaired)
            if tool:
                return tool, args
    # 4. flat format fallback: no JSON — each line is key:value (robust to leaks).
    tool, args = _parse_flat(content)
    if tool:
        return tool, args
    return None, None




def seq_agents_md() -> str:
    """The SEQ system prefix (loaded once per process). SEQ_PROMPT=V21 selects
    the V2.1 evidence-grounded prototype (contract/extend/commit/two-stage)."""
    import os
    _p = os.environ.get("SEQ_PROMPT", "").upper()
    if _p in ("V21", "V2.1"):
        return (_AGENT_DIR / "SEQ_AGENTS_V21.md").read_text()
    if _p in ("V22", "V2.2"):
        return (_AGENT_DIR / "SEQ_AGENTS_V22.md").read_text()
    if _p in ("V23", "V2.3"):
        return (_AGENT_DIR / "SEQ_AGENTS_V23.md").read_text()
    return (_AGENT_DIR / "SEQ_AGENTS.md").read_text()


_ZH_Q_CACHE: Dict[str, dict] = {}


def _zh_question_for(case_id: str) -> str:
    """Chinese restatement for this case from the SEQ_ZH_QUESTION annotation
    file ({case_id: {q, gold, zh}}), or "" when unset/unmatched."""
    path = os.environ.get("SEQ_ZH_QUESTION", "")
    if not path or not case_id:
        return ""
    if path not in _ZH_Q_CACHE:
        try:
            with open(path) as f:
                _ZH_Q_CACHE[path] = json.load(f)
        except Exception as e:
            print(f"  ⚠ SEQ_ZH_QUESTION load failed ({path}): {e}", flush=True)
            _ZH_Q_CACHE[path] = {}
    entry = _ZH_Q_CACHE[path].get(case_id) or {}
    return str(entry.get("zh") or "")


class SeqReactCase:
    """One case's evolving state through the SEQ per-fact loop."""

    def __init__(self, sample, pilot_row, idx):
        self.ctx = build_context(sample, pilot_row, idx)
        self.state = SeqAgentState()
        self.messages: List[Dict[str, Any]] = []
        self.failed = False
        self.failure_reason = ""
        self.done = False
        self._empty_answer_retried = False
        # anti-loop: track consecutive identical tool calls so a stuck model (re-issuing
        # the same retrieve_relations/subgraph) is nudged to converge instead of burning
        # the turn budget (root cause of 2209/1864 empty-FAILs).
        self._last_tool_sig = None
        self._tool_repeat = 0
        self._init_messages()

    def loop_nudge(self) -> str:
        tool = self._last_tool_sig[0] if self._last_tool_sig else "the tool"
        return (
            f"⚠ You already called `{tool}` with these EXACT arguments, and the result was already "
            f"returned to you — calling it again returns the same evidence and cannot advance the fact. "
            f"Act on the result you already have, choosing the branch that fits: (a) SELECT a structural "
            f"relation from the candidate_relations and call `retrieve_subgraph`; (b) if no relation "
            f"advances this fact, CLOSE it — declare `[fid ✗ empty]` — and move to the next fact; "
            f"(c) if the evidence you ALREADY have answers the question (earlier facts may have "
            f"delivered the terminal variable — declare `[fid ✗ moot]` for the rest) — declare the "
            f"bindings and call `answer`. Do not re-call `{tool}` with the same arguments.")

    def state_aware_hint(self) -> str:
        """A prefix for the allowed-tools hint, based on the LAST tool call.
        Prevents the model from re-calling a tool it just called — the generic
        'retrieve_relations FIRST' hint confuses it into re-calling retrieve_relations
        when it should proceed to retrieve_subgraph."""
        if not self._last_tool_sig:
            return ""
        last_tool = self._last_tool_sig[0]
        if last_tool == "retrieve_relations":
            return ("You have candidate_relations from your last retrieve_relations call. "
                    "NOW pick ALL structural bridge relations that encode the same semantic "
                    "fact — submit them TOGETHER in one retrieve_subgraph call. "
                    "Do NOT re-call retrieve_relations.\n")
        if last_tool == "retrieve_subgraph":
            return ("You just retrieved a subgraph. Declare the checkpoint for the fact: "
                    "`[fid ✓] ?var = [bindings]` if resolved; `[fid ✗ empty]` if the pool "
                    "holds no advancing relation; `[fid ✗ moot]` if earlier evidence "
            "already bound this fact's target. Then call retrieve_relations for the "
            "next OPEN fact — or answer as soon as the QUESTION's variable is bound.\n")
        return ""

    def _maybe_inject_evidence_commit(self) -> None:
        """BINDING LEDGER → EVIDENCE COMMIT (V2.1; COMMIT-WIDENING 2026-08-22).

        Trigger: commit_due — the READY predicate (all declared facts CLOSED
        (retrieved or ✗ closure), OR answer var bound with no OPEN fact able to
        change it). SEQ_WIDE_COMMIT=off falls back to the legacy all_retrieved.
        Idempotent via ctx._ledger_injected (PLAN EXTEND / RESTART reset it).
        Two-stage gating: sets _analysis_pending so the next answer call is
        STAGE-GATED into ANSWER_ANALYSIS first.

        CANDIDATES come from state.answer_var (the plan's declared answer
        variables) — the old last-bound-var guess printed the wrong variable's
        values under early binding. The heuristic survives ONLY as a display
        fallback when no declared answer var has bindings, and then the
        SUPPORT_BY_REQUIREMENT matrix is skipped (a guessed var yields a wrong
        support matrix)."""
        if (self.state.state != "RETRIEVE"
                or getattr(self.ctx, "_ledger_injected", False)):
            return
        if not commit_due(self.state,
                          getattr(self.ctx, "closed_facts", None) or {},
                          getattr(self.ctx, "fact_bindings", None) or {},
                          getattr(self.ctx, "var_joins", None) or {}):
            return
        _fb = getattr(self.ctx, "fact_bindings", None) or {}
        _fv = getattr(self.ctx, "fact_vars", None) or {}
        _joins = getattr(self.ctx, "var_joins", None) or {}
        from collections import defaultdict as _dl
        _by_var = _dl(list)
        for _f, _v in _fv.items():
            if _f in _fb:
                _by_var[_v].append(_f)
        if not _by_var:
            return    # nothing committed to show — no analysis stage to gate

        def _vals_for(_v, _fids):
            if _v in _joins and _joins[_v][1]:
                return list(_joins[_v][1])
            _ordered = sorted(_fids)
            return _fb[_ordered[-1]] if _ordered else []

        _avs = [v for v in (getattr(self.state, "answer_var", None) or []) if v]
        _live = [v for v in _avs if _by_var.get(v) and _vals_for(v, _by_var[v])]
        _guessed = False
        if not _live:
            # no declared answer var is bound — display fallback to the last
            # bound var; SUPPORT lines suppressed (wrong-matrix risk)
            for _v, _fids in _by_var.items():
                if _vals_for(_v, _fids):
                    _live = [_v]
                    _guessed = True
        self.ctx._ledger_injected = True
        _lines = []
        for _v in _live:
            _vals = _vals_for(_v, _by_var[_v])
            _lines.append(f"CANDIDATES ({_v}): [{' | '.join(_vals[:40])}]"
                          + (f" …({len(_vals)})" if len(_vals) > 40 else ""))
        # SUPPORT_BY_REQUIREMENT from the contract covers mapping — only when the
        # answer var is the plan-declared one (not the fallback guess)
        _reqs = getattr(self.state, "requirements", None) or {}
        _cov = getattr(self.state, "fact_covers", None) or {}
        if _reqs and _cov and _live and not _guessed:
            from kgqa.core.utils import normalize as _nz2
            _answer_var = _live[0]
            _req_sets = {}
            for _f, _rid in _cov.items():
                if _f in _fv and _fv[_f] == _answer_var and _f in _fb:
                    _set = { _nz2(x) for x in _fb[_f] }
                    _req_sets.setdefault(_rid, set()).update(_set)
            for _rid, _sup in _req_sets.items():
                _rt = (_reqs.get(_rid) or {}).get("text", "")[:60]
                _lines.append(f"SUPPORT {_rid} ({_rt}): "
                              f"{len(_sup)} candidate(s) positively supported")
            if len(_req_sets) > 1:
                _full = set.intersection(*_req_sets.values())
                _lines.append(f"FULL-SUPPORT (all requirements): "
                              f"{len(_full)} candidate(s)")
        _led = ("=== EVIDENCE COMMIT ===\n  " + "\n  ".join(_lines)
                + "\n  (UNRESOLVED ≠ CONTRADICTED: a requirement whose "
                "fact closed empty gives NO positive support — it does "
                "not erase candidates supported elsewhere.)"
                "\n  COUNT CONTRACT: CASE A — any candidate fully supported → "
                "submit ALL fully-supported; CASE B — none fully supported → "
                "submit the single best-supported. Never mix full and partial."
                "\n  Next: emit ANSWER_ANALYSIS (BASE_CANDIDATES / "
                "REQUIREMENT_CHECK / COUNT_CONTRACT / PROVISIONAL_FINAL) — do "
                "NOT call answer yet.")
        self.messages.append({"role": "user", "content": _led})
        self.ctx.trajectory.append({"role": "tool", "content": _led[:300]})
        self.ctx._analysis_pending = True

    def _init_messages(self):
        q = f"Question: {self.ctx.question}"
        # SEQ_ZH_QUESTION (2026-09-07): annotation JSON {case_id: {q, gold, zh}}.
        # Ambiguous English phrasings steer the plan wrong (WebQTrn-493: "Where
        # in the Greenwich Mean Time Zone is Belgium located?" read as "list the
        # locations in GMT" instead of "which CONTINENT"); the Chinese
        # restatement pins the intended reading. Injection is question-text
        # only — never the gold.
        zh = _zh_question_for(getattr(self.ctx, "case_id", "") or "")
        if zh:
            q += f"\n(中文重述，以这一版语义为准 / Chinese restatement, treat as authoritative: {zh})"
        self.messages = [
            {"role": "system", "content": seq_agents_md()},
            {"role": "user", "content": q},
        ]

    async def prelink(self, session, top_k: int = 6):
        """Plan-前置: 用数据自带的 qentity（清洁问题实体，正确 FB 名）作为锚点参考注入
        question + 植入 ctx.subgraph_entities。解决模型抽取错实体名的问题（'Vienna,
        Austria'→'Vienna'；GTE 噪声 'National Anthem'→'Tiến Quân Ca'）。qentity 覆盖 100%、
        泄漏 2%、idx 100% 有效。
        Plan-contract v2 (2026-08-21, user ruling B): 邻居关系样本按【原始问题】GTE 排序
        （此前 sorted()[:3] 字母序在问题正轴上反向采样——Ron Howard 电影题采样出
        award.*），锚点实体同样按问题相关性排序。注入语义限定为锚点参考，不覆盖问题
        主语（Lala/Carmelo 标本：q_entity 与问题主语不符时，以问题为准）。"""
        ctx = self.ctx
        qe_names = ctx.sample.get("q_entity") or []
        qe_idxs = ctx.sample.get("q_entity_id_list") or []
        if not qe_names:
            return
        se = getattr(ctx, "subgraph_entities", None)
        pairs = []
        for name, idx in zip(qe_names, qe_idxs):
            if not isinstance(idx, int) or not (0 <= idx < len(ctx.ents)):
                continue
            rel_ids = set()
            for k in range(len(ctx.h_ids)):
                if (ctx.h_ids[k] == idx or ctx.t_ids[k] == idx) and 0 <= ctx.r_ids[k] < len(ctx.rels):
                    rel_ids.add(ctx.r_ids[k])
            pairs.append((name, rel_ids))
            if se is not None:
                se.add(idx)
        if not pairs:
            return
        # rank the anchors themselves against the ORIGINAL question (user ruling:
        # 锚点与关系都按问题排序)
        try:
            from kgqa.stages.stage2_entity import gte_retrieve
            from kgqa.core.utils import phase_timer
            names_list = [n for n, _ in pairs]
            with phase_timer("gte"):   # prelink anchor ranking — phase-attributed
                rows = await gte_retrieve(session, ctx.question, names_list,
                                          candidate_texts=names_list, top_k=len(names_list))
            if rows:
                rank = {r.get("candidate"): i for i, r in enumerate(rows)}
                pairs.sort(key=lambda p: rank.get(p[0], len(rank)))
        except Exception:
            pass   # keep dataset order — the names still anchor
        out = []
        for name, rel_ids in pairs:
            top_rels: list = []
            if session is not None and rel_ids:
                try:
                    # NOISE-FILTERED hint pool (Minister-of-State specimen, 2026-08-22):
                    # the retrieval pool drops structural noise (_is_noisy_path_relation)
                    # but the prelink hints ranked the RAW neighbor set —
                    # common.topic.notable_for won the top-3 slot while the
                    # semantically-right government.* relations sat unranked
                    # behind it, misdirecting the plan. Align the hint pool
                    # with the retrieval pool: same noise classes, both layers.
                    from kgqa.traversal.path_utils import _is_noisy_path_relation as _noisy
                    _clean = {i for i in rel_ids
                              if 0 <= i < len(ctx.rels)
                              and not _noisy(ctx.rels[i])}
                    if not _clean:
                        _clean = rel_ids
                    from kgqa.agent.tools import _gte_for_triple
                    ranked = await _gte_for_triple(
                        ctx, session, name, ctx.question, "", pool_relids=_clean)
                    top_rels = [ctx.rels[i] for i in ranked[:3]
                                if 0 <= i < len(ctx.rels)]
                except Exception:
                    top_rels = []
            out.append({"name": name, "neighbor_relations": top_rels})
        lines = [f"  - {o['name']}" + (f" (question-ranked relations: {' | '.join(o['neighbor_relations'])})"
                  if o['neighbor_relations'] else "") for o in out]
        self.messages[1]["content"] += (
            "\n\nQuestion entities (canonical graph names — use these spellings as your "
            "anchors when they match the entities the question names; an entity listed "
            "here that is NOT the question's subject is context, never a mandate to "
            "pivot to it). The relations beside each are a QUESTION-RANKED sample of "
            "that entity's neighbors — an anchor reference, not the retrieval pool: "
            "the authoritative relation set always comes from retrieve_relations:\n"
            + "\n".join(lines))

    @property
    def is_active(self):
        return not self.done and not self.failed

    def allowed_tools_hint(self):
        hint = seq_allowed_hint(self.state)
        # plan-contract v2: keep the turn-0 question analysis in force — every hint
        # that permits answering also restates the declared answer-type contract.
        at = getattr(self.ctx, "plan_answer_type", "")
        if at and "answer" in hint:
            hint += (f" ANSWER-TYPE CONTRACT: {at} — the final answer entities must be "
                     f"of this type (the question asks for a {at}).")
        return hint


    async def _search_join_paths(self, unconsumed, session,
                                 max_paths=3, max_hops=4, n_cands=8,
                                 targets=None):
        """JOIN PATH SEARCH on the full case graph, calibrated per user
        ruling 2026-09-08 #2: (a) the path domain is RETRIEVABLE relations —
        noisy/hub edges are excluded (the Band-of-Brothers->German
        coincidence bridge cannot appear); (b) SHORTEST paths win; (c) the
        final ordering is GTE relevance against the question."""
        try:
            from collections import defaultdict, deque
            from kgqa.traversal.k_queue import _is_noisy_path_relation
            deg = defaultdict(int)
            ents, rels = self.ctx.ents, self.ctx.rels
            for h, r, t in zip(self.ctx.h_ids, self.ctx.r_ids, self.ctx.t_ids):
                hn = str(ents[h]) if 0 <= h < len(ents) else str(h)
                tn = str(ents[t]) if 0 <= t < len(ents) else str(t)
                if hn != tn:
                    deg[hn] += 1
                    deg[tn] += 1
            # HUB CAP (user calibration: the path domain is RETRIEVABLE
            # relations — coincidence bridges cross high-degree plumbing
            # nodes like Band-of-Brothers->German Language; a node with
            # degree > HUB_DEG is not a retrievable bridge)
            HUB_DEG = 120
            # endpoints (the unconsumed starts + the target anchors) are
            # exempt — a plan anchor is naturally high-degree (Darth Vader
            # 172); the cap exists for INTERMEDIATE plumbing nodes only
            _pe0 = [str(e).strip() for e in (getattr(self.ctx, "plan_entities", None) or [])]
            _keep = {str(u).strip() for u in unconsumed} | set(_pe0)
            adj = defaultdict(set)
            rel_of = defaultdict(set)
            for h, r, t in zip(self.ctx.h_ids, self.ctx.r_ids, self.ctx.t_ids):
                hn = str(ents[h]) if 0 <= h < len(ents) else str(h)
                tn = str(ents[t]) if 0 <= t < len(ents) else str(t)
                rn = (str(rels[r]) if 0 <= r < len(rels) else "?")
                if (hn == tn or _is_noisy_path_relation(rn)
                        or (deg[hn] > HUB_DEG and hn not in _keep)
                        or (deg[tn] > HUB_DEG and tn not in _keep)):
                    continue
                adj[hn].add(tn)
                adj[tn].add(hn)
                rel_of[frozenset((hn, tn))].add(rn.rsplit(".", 1)[-1])
            if not adj:
                return ""
            # user calibration 2026-09-08 #3: the join target is the OTHER
            # PLAN ANCHORS (start-entity to start-entity closure — 75th
            # Ranger Regiment ↔ Darth Vader), NOT the candidate pool: we
            # bridge UNCLOSED retrieval graphs between different starting
            # entities, not entity-to-answer
            _pe = [str(e).strip() for e in (getattr(self.ctx, "plan_entities", None) or [])]
            _cons = {str(c).strip().lower()
                     for c in (getattr(self.ctx, "consumed_anchors", None) or set())}
            reached = {e for e in _pe if e.lower() in _cons}
            reached -= {str(u).strip() for u in unconsumed}
            if targets is not None:
                # CONNECTIVITY MODE (2026-09-09): every anchor consumed —
                # search anchor→anchor directly (user ruling: start-entity
                # to start-entity closure) instead of unconsumed→consumed
                reached = {str(t).strip() for t in targets}
            cands, seen_sig = [], set()
            for unc in unconsumed[:2]:
                ucs = str(unc).strip()
                if ucs not in adj:
                    continue
                prev = {ucs: None}
                q = deque([ucs])
                hit_layer, depth = None, 0
                while q and hit_layer is None and depth < max_hops:
                    cur = list(q)
                    q.clear()
                    depth += 1
                    nxt = []
                    for x in cur:
                        for y in adj[x]:
                            if y in prev:
                                continue
                            prev[y] = x
                            nxt.append(y)
                            q.append(y)
                    hits = [y for y in nxt if y in reached]
                    if hits:
                        hit_layer = hits
                        break
                if hit_layer is None:
                    continue
                for tgt in hit_layer:
                    path = [tgt]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    path.reverse()
                    if len(path) > max_hops + 1:
                        continue
                    sig = frozenset(path)
                    if sig in seen_sig:
                        continue
                    seen_sig.add(sig)
                    hops = []
                    for a, b in zip(path, path[1:]):
                        rs = "/".join(sorted(rel_of.get(frozenset((a, b)), ("?",)))[:2])
                        hops.append(f"{a[:24]} --{rs}--> {b[:24]}")
                    cands.append("  ".join(hops))
                    if len(cands) >= n_cands:
                        break
            if not cands:
                return ""
            try:
                from kgqa.stages.stage2_entity import gte_retrieve
                rows = await gte_retrieve(
                    session, str(getattr(self.ctx, "question", "") or ""),
                    cands, top_k=len(cands))
                ordered = [r.get("candidate") for r in (rows or [])
                           if r.get("candidate") in cands]
                ordered += [c for c in cands if c not in ordered]
                cands = ordered
            except Exception:
                pass                    # GTE unavailable → shortest-first as-is
            return "\n".join(f"  {i+1}. {x}" for i, x in enumerate(cands[:max_paths]))
        except Exception:
            return ""

    def _unconsumed_edge_hint(self, unconsumed, max_rels=3, max_vals=6):
        """RETRIEVAL HINT for unconsumed plan entities (user audit
        2026-09-08: the join bridge may not exist as a named path, and even
        when it does it can be a semantically irrelevant coincidence — the
        ACTIONABLE fallback is the unconsumed entity's OWN one-hop
        relations with their CVT attribute values AGGREGATED PER KEY: the
        servicemembers edge's military_person roster lists every soldier
        including the gold). Structure-only, from the case arrays."""
        try:
            from collections import defaultdict
            from kgqa.traversal.path_utils import _is_noisy_path_relation as _noisy
            ents, rels = self.ctx.ents, self.ctx.rels
            unc = {str(u).strip() for u in unconsumed}
            if not unc:
                return ""
            # NOISE-FILTERED relations (user audit 2026-09-17, WebQTrn-21:
            # degree-desc ranking put topic/webpage noise FIRST). Same
            # filter class as the prelink hint pool / retrieval pool.
            def _rel_ok(ri):
                return 0 <= ri < len(rels) and not _noisy(str(rels[ri]))
            mid_attrs = defaultdict(list)      # mid -> [(short_rel, value)]
            # unc -> rel -> attr_key -> vals (per-entity: labels must not mix)
            rel_keys = {u: defaultdict(lambda: defaultdict(list)) for u in unc}
            for h, r, t in zip(self.ctx.h_ids, self.ctx.r_ids, self.ctx.t_ids):
                hn = str(ents[h]) if 0 <= h < len(ents) else str(h)
                tn = str(ents[t]) if 0 <= t < len(ents) else str(t)
                rn = (str(rels[r]).rsplit(".", 1)[-1]
                      if 0 <= r < len(rels) else "?")
                hc, tc = hn[:2] in ("m.", "g."), tn[:2] in ("m.", "g.")
                if hc and not tc:
                    mid_attrs[hn].append((rn, tn))
                elif tc and not hc:
                    mid_attrs[tn].append((rn, hn))
            for h, r, t in zip(self.ctx.h_ids, self.ctx.r_ids, self.ctx.t_ids):
                if not _rel_ok(r):
                    continue
                hn = str(ents[h]) if 0 <= h < len(ents) else str(h)
                tn = str(ents[t]) if 0 <= t < len(ents) else str(t)
                rn = (str(rels[r]).rsplit(".", 1)[-1]
                      if 0 <= r < len(rels) else "?")
                for a, b in ((hn, tn), (tn, hn)):
                    if a not in rel_keys:
                        continue
                    if b[:2] in ("m.", "g."):
                        for ak, av in mid_attrs.get(b, []):
                            if av == a:
                                continue        # self-referential noise
                            lst = rel_keys[a][rn][ak]
                            if av not in lst:
                                lst.append(av)
                    else:
                        lst = rel_keys[a][rn][""]
                        if b not in lst:
                            lst.append(b)
            lines = []
            for u in unc:
                u_rels = rel_keys[u]
                top = sorted(u_rels.items(),
                             key=lambda kv: -sum(len(v) for v in kv[1].values()))[:max_rels]
                for rn, kmap in top:
                    parts = []
                    for ak, vals in sorted(kmap.items(), key=lambda kv: -len(kv[1])):
                        if not vals:
                            continue
                        shown = " | ".join(v[:40] for v in vals[:max_vals])
                        more = (f" …(+{len(vals)-max_vals})"
                                if len(vals) > max_vals else "")
                        parts.append((ak + "=" if ak else "") + shown + more)
                    if parts:
                        lines.append(f"'{u[:32]}' --{rn}--> " + " ; ".join(parts[:2]))
            return "\n".join(f"  {i+1}. {x}" for i, x in enumerate(lines[:max_rels * 2]))
        except Exception:
            return ""

    def _emit_tool_note(self, note: str):
        """Deliver a harness note as both a user message and a trajectory
        tool step (the standard dual-write for every gate/reminder/nudge)."""
        self.messages.append({"role": "user", "content": note})
        self.ctx.trajectory.append({"role": "tool", "content": note})

    def _anchors_disconnected(self, exclude=()) -> bool:
        """CONNECTIVITY ≠ CONSUMPTION (user audit 2026-09-09): a multi-center
        retrieve_subgraph consumes EVERY center, so the consumption latch can
        no longer detect the unclosed case — both sides consumed, yet no
        walked path links them. BFS the ACCUMULATED walk graph between the
        plan's anchor names; any anchor unreachable from the first → the
        join gate still owes its one-time check. `exclude` drops type-word
        entities (never retrieved by design) from the anchor set."""
        from collections import defaultdict, deque
        from kgqa.core.utils import normalize as _nz
        _ex = {str(e).strip().lower() for e in exclude}
        pe = [str(e).strip() for e in (getattr(self.ctx, "plan_entities", None) or [])
              if str(e).strip().lower() not in _ex]
        at = getattr(self.ctx, "accumulated_triples", None) or set()
        if len(pe) < 2:
            return False
        if not at:
            return True          # nothing walked at all — every anchor stranded
        adj = defaultdict(set)
        for h, _r, t in at:
            hn, tn = _nz(str(h)), _nz(str(t))
            if hn and tn and hn != tn:
                adj[hn].add(tn)
                adj[tn].add(hn)
        start = _nz(pe[0])
        seen = {start}
        q = deque([start])
        while q:
            cur = q.popleft()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        return any(_nz(e) not in seen for e in pe[1:])

    def _type_word_exempt(self, name):
        """A plan entity whose EVERY graph edge rides a noisy relation
        (type./common./webpage/topic…) is a TYPE WORD ('Prime minister',
        'Continent'), not a retrievable subject — exempting it from the
        unconsumed set stops the gate from demanding a retrieval that has
        no meaningful form (WebQTrn-21 specimen: answer already committed,
        gate still burned a round on webpage edges)."""
        try:
            from kgqa.traversal.path_utils import _is_noisy_path_relation as _noisy
            ents = self.ctx.ents
            n = str(name).strip()
            for h, r, t in zip(self.ctx.h_ids, self.ctx.r_ids, self.ctx.t_ids):
                for i in (h, t):
                    if 0 <= i < len(ents) and str(ents[i]) == n:
                        if 0 <= r < len(self.ctx.rels) \
                                and not _noisy(self.ctx.rels[r]):
                            return False    # has at least one structural edge
            return True                     # only noisy edges → type word
        except Exception:
            return False

    def _ma_gate_would_fire(self, parsed_args):
        """SYNC trigger test for the multi-anchor consumption gate (the
        latch lives here so the deferred async run cannot double-fire)."""
        if (not (parsed_args.get("entities") or [])
                or getattr(self.ctx, "_ma_gate_fired", False)):
            return False
        _pe = getattr(self.ctx, "plan_entities", None) or []
        _cons = {str(c).strip().lower()
                 for c in (getattr(self.ctx, "consumed_anchors", None) or set())}
        _tw = [e for e in _pe if self._type_word_exempt(e)]
        _unc = [e for e in _pe if str(e).strip().lower() not in _cons
                and e not in _tw]
        if len(_pe) < 2:
            return False
        if not _unc and not self._anchors_disconnected(exclude=_tw):
            # all consumed AND the accumulated walk graph already links the
            # anchors — consumption closed AND connectivity closed
            return False
        self.ctx._ma_gate_fired = True
        self.ctx._ma_gate_unc = _unc
        return True

    async def _ma_gate_check(self, tool_name, parsed_args, session):
        """MULTI-ANCHOR CONSUMPTION GATE + JOIN PATHS (2026-09-01/07/08).
        Async: the join search is GTE-ranked against the question (user
        calibration 2026-09-08 #2 — retrievable-relation domain, shortest
        first, GTE relevance ordering).
        CONNECTIVITY MODE (2026-09-09): when every anchor was consumed
        (multi-center calls consume all centers) but the accumulated walk
        graph never linked them, the gate still fires — anchor→anchor join
        paths, no retrieval hint (the entities WERE retrieved from)."""
        _unc = getattr(self.ctx, "_ma_gate_unc", None) or []
        _pe = [str(e).strip() for e in (getattr(self.ctx, "plan_entities", None) or [])]
        if not _unc:
            _jp = (await self._search_join_paths(_pe[:1], session,
                                                 targets=_pe[1:])
                   if len(_pe) >= 2 else "")
            _hint = ("CONNECTIVITY CHECK (one-time): every plan entity was "
                "retrieved from, but no walked path links their subgraphs "
                "yet. If the question needs the two sides CONNECTED (an "
                "entity on one side reachable from the other), judge these "
                "join paths and retrieve the bridge; if the sides answer "
                "independently (their candidate sets intersect), answer now.")
            if _jp:
                _hint += ("\n\nJOIN PATHS (shortest first, GTE-ranked against the "
                          "question — judge relevance):\n" + _jp)
            self.messages.append({"role": "user", "content": _hint})
            self.ctx.trajectory.append({"role": "tool", "content":
                "connectivity gate (all anchors consumed, subgraphs unlinked)"
                + ((f"\nJOIN PATHS:\n{_jp}") if _jp else "")})
            return
        _jp = await self._search_join_paths(_unc, session)
        _hint = ("UNCONSUMED ENTITIES (one-time check): declared "
            + " | ".join(f"'{e}'" for e in _unc[:3])
            + " never started any subgraph retrieval. If the answer needs "
            "their neighborhood, retrieve FROM them now. If constraints "
            "only, re-submit unchanged.")
        if _jp:
            _hint += ("\n\nJOIN PATHS (shortest first, GTE-ranked against the "
                      "question — judge relevance):\n" + _jp)
        _eh = self._unconsumed_edge_hint(_unc)
        if _eh:
            _hint += ("\n\nRETRIEVAL HINT (the unconsumed entity's own one-hop relations):\n" + _eh)
        self.messages.append({"role": "user", "content": _hint})
        # trajectory carries the FULL paths/hint (user audit 2026-09-08:
        # the short marker hid the bridges from credit adjudication and
        # human review; join paths hitting a subgraph's core relations
        # CREDIT that subgraph's behavior — the adjudicator reads them here)
        self.ctx.trajectory.append({"role": "tool", "content":
            "unconsumed-entities gate: " + " | ".join(_unc[:3])
            + ((f"\nJOIN PATHS:\n{_jp}") if _jp else "")
            + ((f"\nRETRIEVAL HINT:\n{_eh}") if _eh else "")})

    def rescue_terminal_answer(self):
        """Terminal rescue (harness fix P4): a case that exhausted its rounds with NO
        accepted answer often has the answer in hand — in a `tool: answer` call that a
        process-level rejection trapped (repeat gate / premature-answer / offpool), or in
        the §Answer checklist's ANSWER field. Recover it instead of scoring an empty
        answer. Only fires when nothing was accepted; never overwrites a real answer."""
        ctx = self.ctx
        if getattr(ctx, "llm_answer_str", "") or getattr(ctx, "llm_answer_preds", None):
            return
        # JOIN-AWARE RECOVERY (Stop-motion specimen, 2026-08-19): when subgraph
        # joins exist, the effective answer binding is the harness INTERSECTION.
        # Only NON-empty joins are authoritative (curated lists are not
        # exhaustive — an empty intersection is not a harness fact, Thundera);
        # recover the intersection instead of a raw one-side checkpoint list.
        _joins = getattr(ctx, "var_joins", None) or {}
        if _joins:
            _inter_all = [list(inter) for _fids, inter in _joins.values() if inter]
            if _inter_all and sum(len(x) for x in _inter_all):
                ents = [e for x in _inter_all for e in x]
                ctx.llm_answer_preds = ents
                ctx.llm_answer_str = " | ".join(ents)
                self._rescued = True
                return
        ents = self._last_answer_entities()
        ents = [strip_reasoning_leak(e).strip() for e in ents]
        ents = [e for e in ents if e]
        if not ents:
            return
        ctx.llm_answer_preds = ents
        ctx.llm_answer_str = " | ".join(ents)
        self._rescued = True

    def _last_answer_entities(self) -> list:
        """Best-effort answer recovery from the trajectory, newest first:
        1. the LAST `tool: answer` call's entities arg (JSON array or flat list),
        2. the LAST assistant `ANSWER:` checklist line,
        3. the LAST checkpoint binding `[..✓] ?var = [..]` — a case that exhausted
           rounds mid-retrieval usually has the answer entity set in its final
           checkpoint (the last fact of the plan is the answer-bearing one).
        MID STRIP (1923 specimen, 2026-09-09): event-node mids are NEVER
        answer values (the answer tool rejects them, §7.5 strips them from
        bindings) — but this recovery reads the RAW trajectory text, so a
        REJECTED all-mid answer call (or a §7.5-stripped checkpoint line)
        would re-leak the mids as the final answer, overriding both guards
        (rescued=True with an f1=0.00 mid list). Strip mids from every
        recovery source; an all-mid source falls through to the next."""
        import re as _re

        def _split_val(val: str) -> list:
            val = val.strip().strip('`')
            if val.startswith("[") and val.endswith("]"):
                try:
                    j = json.loads(val)
                    if isinstance(j, list):
                        return [str(x).strip() for x in j if str(x).strip()]
                except json.JSONDecodeError:
                    pass
            return [v.strip().strip('"\'') for v in re.split(r'\s*[|,]\s*', val) if v.strip()]

        for step in reversed(self.ctx.trajectory):
            if step.get("role") != "assistant":
                continue
            c = step.get("content") or ""
            for m in re.finditer(r'tool:\s*(?:\{\s*"tool"?\s*:\s*"answer"|answer)\b', c):
                tail = c[m.start():]
                em = re.search(r'"?entities"?\s*[:=]\s*(\[.*?\]|\S.*?)\s*(?:\n|$)', tail)
                if em:
                    _v = [e for e in _split_val(em.group(1))
                          if not _re.fullmatch(r"[mg]\.[0-9a-z_]{2,}", e.strip().lower())]
                    if _v:
                        return _v
            am = re.findall(r'^ANSWER:\s*(.+)$', c, re.MULTILINE)
            if am:
                _v = [e for e in _split_val(am[-1])
                      if not _re.fullmatch(r"[mg]\.[0-9a-z_]{2,}", e.strip().lower())]
                if _v:
                    return _v
            cm = list(_CKPT_RE.finditer(c))
            if cm:
                _v = [e for e in _split_val(cm[-1].group(2))
                      if not _re.fullmatch(r"[mg]\.[0-9a-z_]{2,}", e.strip().lower())]
                if _v:
                    return _v
        return []

    async def process_turn(self, session, raw_response, reasoning) -> str:
        """Process ONE turn's LLM output: append → bind vars → parse → validate →
        dispatch → record. Shared by the per-call runner (run_seq_react_case) and
        the batch runner (run_seq_react_batch) so both follow identical semantics.

        Returns "done" when the case is complete (answer accepted / failed), else
        "continue". The LLM call itself is the caller's responsibility — this method
        only consumes (raw_response, reasoning).

        THREE-PHASE COMPOSITION (perf-4, 2026-08-23): the turn is A
        (_parse_prepare: pure CPU — parse/bind/gate/validate, produces the tool
        request) → B (_execute_tool: IO — GTE / walk lanes) → C (_finalize: pure
        CPU — result landing, evidence merge, COMMIT injection, message
        assembly). process_turn keeps the sequential composition so the
        per-case runner, run_seq_react_batch and every test see IDENTICAL
        semantics; the round-level scheduler (seq_rollout / replay_dispatch)
        drives the phases directly so one round runs A for all cases, fires
        every GTE/walk request together, then runs C — the event loop does
        orchestration only (sync tax no longer interleaves as 500-coroutine
        fragments)."""
        prep = self._parse_prepare(raw_response, reasoning)
        if "_gate_deferred" in prep:
            await self._ma_gate_check(*prep["_gate_deferred"], session)
            return "continue"
        if "ret" in prep:
            return prep["ret"]
        result_str = await self._execute_tool(prep, session)
        return self._finalize(prep, result_str)

    def _parse_prepare(self, raw_response, reasoning) -> dict:
        """A段 (pure CPU): everything from ingress sanitization through the
        validated tool request. Early-exit paths complete their message/ctx
        side effects here and return {"ret": "continue"}; the tool path
        returns {"tool": name, "args": args, "raw": post-quoted content}."""
        # empty response — nudge, keep going
        if not raw_response or not raw_response.strip():
            self.messages.append({"role": "assistant", "content": ""})
            self.messages.append({"role": "user", "content": self.allowed_tools_hint()})
            return {"ret": "continue"}

        # ingress sanitizer (harness fix P5): strip the vLLM reasoning_end leak BEFORE
        # anything consumes the content — history, checkpoint bindings, tool parsing.
        # The phrase glues onto the last partial word mid-entity-list when the thinking
        # budget force-inject fires; downstream parsers must never see it.
        raw_response = strip_reasoning_leak(raw_response)

        asst_msg = {"role": "assistant", "content": raw_response}
        if reasoning:
            asst_msg["reasoning"] = reasoning
        self.messages.append(asst_msg)
        traj_step = {"role": "assistant", "content": raw_response}
        if reasoning:
            traj_step["reasoning"] = reasoning
        self.ctx.trajectory.append(traj_step)
        # NONE VERDICT → system restart (user ruling, 2026-08-22): the model
        # does NOT ask for a restart — it declares the exploration found
        # NOTHING answer-relevant (`[explore ✗ none]`), PARTIAL relevance
        # means continue (ladder levels 1-3). On the FIRST none the system
        # restarts the case ONCE: fresh conversation seeded with what the
        # first attempt tried. The second attempt MUST answer (a second none
        # is rejected — no variance loops); turn budget is shared.
        _rst = re.search(r"\[explore\s*(?:✗|x)\s*none([^\]]*)\]|\[explore:\s*none([^\]]*)\]",
                         raw_response, re.I)
        if _rst:
            diag = (_rst.group(1) or _rst.group(2) or "").strip(" —-")[:300]
            if getattr(self.ctx, "restarted", False):
                self.messages.append({"role": "user", "content":
                    "REJECTED: the restart was already used — this attempt MUST "
                    "answer. Submit the most justified entities from whatever "
                    "evidence exists (or an explicit empty answer). Declare "
                    "checkpoints (✓/✗) per fact and call answer."})
                self.ctx.trajectory.append({"role": "tool", "content":
                    "REJECTED none: must answer on the second attempt"})
                return {"ret": "continue"}
            self.ctx.restarted = True
            # what the first attempt tried — seed the lesson so attempt-2 plans
            # differently instead of resampling the same dead ends
            _tried = []
            for s in self.ctx.trajectory:
                c = s.get("content") or ""
                if s.get("role") == "assistant" and c.startswith("tool: retrieve_subgraph"):
                    m = re.search(r"relations:\s*(.+?)(?:\s+sg:|\s*$)", c, re.S)
                    if m:
                        _tried.extend(x.strip() for x in m.group(1).split("|") if x.strip())
            _tried = sorted(set(_tried))[:12]
            # reset conversation → [system, question+anchors]
            self.messages = self.messages[:2]
            self.state = SeqAgentState()
            # reset every accumulated case store.
            # TYPE-DISPATCHED reset (user audit 2026-09-19, 1379-s1 crash
            # family): walk_seen_entities/walk_extra are LIST-typed ctx
            # fields (seq_tools.py:4942/5178 init them as []) — resetting
            # them to {} made the first post-restart retrieve_subgraph
            # crash at the ledger append (seq_tools.py:4950) and persist.
            for f in ("var_bindings", "declared_facts", "fact_bindings",
                      "fact_vars", "var_joins", "closed_facts",
                      "fact_evidence", "fact_evidence_seq"):
                if hasattr(self.ctx, f):
                    setattr(self.ctx, f, {})
            for f in ("walk_seen_entities", "walk_extra"):
                if hasattr(self.ctx, f):
                    setattr(self.ctx, f, [])
            if hasattr(self.ctx, "accumulated_triples"):
                self.ctx.accumulated_triples = set()
            for f in ("cvt_binding_flag", "cvt_empty_var", "join_flag",
                      "halluc_binding_flag", "frozen_binding_flag"):
                if hasattr(self.ctx, f):
                    setattr(self.ctx, f, None)
            if hasattr(self.ctx, "plan_answer_type"):
                self.ctx.plan_answer_type = ""
            if hasattr(self.ctx, "plan_declared"):
                self.ctx.plan_declared = False
            # two-stage flags reset (COMMIT-WIDENING): the fresh attempt re-enters
            # retrieval — a stale ledger/analysis gate would dead-end it.
            self.ctx._ledger_injected = False
            self.ctx._analysis_pending = False
            self.ctx._analysis_done = False
            self._empty_answer_retried = False
            self._tool_repeat = 0
            self._last_tool_sig = None
            _lesson = (f"RESTART (the only one): your first attempt's verdict was "
                       f"NONE — nothing retrieved related to the answer"
                       + (f" ({diag})" if diag else "") + ".")
            if _tried:
                _lesson += (" Relations already tried (all dead ends): "
                            + " | ".join(_tried) + ".")
            _lesson += (" Plan a DIFFERENT decomposition. This second attempt "
                        "MUST produce an answer — none cannot be declared again; "
                        "if the evidence is again irrelevant, answer empty.")
            self.messages.append({"role": "user", "content": _lesson})
            self.ctx.trajectory.append({"role": "tool", "content":
                                        f"⌗ RESTART on none-verdict: {_lesson[:200]}"})
            return {"ret": "continue"}
        # PLAN EXTEND (V2.1, append-only): `[PLAN EXTEND]` + `covers: R2` +
        # sgN.anchor/sgN.fM lines APPEND facts covering an UNPLANNED contract
        # requirement. Validation: the requirement exists in the original
        # contract and no current fact covers it; the anchor is a question
        # entity or a bound variable. Successful earlier facts are never
        # rewritten — extension is the ONLY topology change after freeze.
        _ext = re.search(r"\[PLAN EXTEND\]\s*\n(.*)", raw_response, re.S)
        if _ext:
            ext_body = _ext.group(1)
            cov_m = re.search(r"covers:\s*(\S+)", ext_body)
            rid = cov_m.group(1).strip().upper() if cov_m else ""
            _reqs = getattr(self.state, "requirements", None) or {}
            _cov = getattr(self.state, "fact_covers", None) or {}
            _ents = set(self.state.entities or []) | set(
                v for v in (getattr(self.ctx, "var_bindings", None) or {}))
            new_sgs = re.findall(
                r"(sg\d+)\.anchor:\s*(.+?)\n\1\.(f\d+):\s*(.+?)\n", ext_body)
            anchored_ok = all(a.strip() in _ents or a.strip().startswith("?")
                              for _, a, _, _ in new_sgs)
            legal = (rid and rid in _reqs
                     and rid not in (_cov.values() if _cov else ())
                     and new_sgs and anchored_ok)
            if legal:
                _new_tails = []
                for sg_id, anchor, fnum, fact_line in new_sgs:
                    parts = [p.strip() for p in fact_line.split("|")]
                    if len(parts) < 3:
                        continue
                    n_existing = sum(1 for f in self.state.fact_ids)
                    fid = f"f{n_existing + 1}"
                    self.state.fact_ids.append(fid)
                    self.state.fact_texts[fid] = f"({parts[0]} | {parts[1]} | {parts[2]})"
                    self.state.fact_covers[fid] = rid
                    self.state.sg_plan[sg_id] = self.state.sg_plan.get(sg_id, 0) + 1
                    # COMMIT-WIDENING: register the appended fact in the key map /
                    # edge store so READY keeps judging the extended plan
                    self.state.fact_key_map[fid] = fid
                    self.state.fact_edges[fid] = (parts[0], parts[2])
                    self.state.sg_facts.setdefault(sg_id, []).append(fid)
                    self.state.fact_key_map[
                        f"{sg_id}.f{len(self.state.sg_facts[sg_id])}"] = fid
                    if parts[2].startswith("?"):
                        _new_tails.append(parts[2])
                if ("answer" in str((_reqs.get(rid) or {}).get("kind", "")).lower()
                        and _new_tails):
                    self.state.answer_var = list(self.state.answer_var) + [
                        v for v in _new_tails if v not in self.state.answer_var]
                # extension returns the case to retrieval mode: the committed
                # ledger is stale — re-inject once the extended facts close
                self.ctx._ledger_injected = False
                self.ctx._analysis_pending = False
                self.ctx._analysis_done = False
                self.state.retrieved_fids = [f for f in self.state.retrieved_fids]
                self.ctx.fact_ids = list(self.state.fact_ids)
                self.ctx.fact_texts = dict(self.state.fact_texts)
                self.ctx.fact_key_map = dict(getattr(self.state, "fact_key_map", None) or {})
                self.ctx.fact_edges = dict(getattr(self.state, "fact_edges", None) or {})
                _ext_msg = (f"⌗ PLAN EXTENDED: facts appended covering {rid}. "
                            "Continue retrieve_relations for the new facts; "
                            "existing facts are unchanged.")
                self.messages.append({"role": "user", "content": _ext_msg})
                self.ctx.trajectory.append({"role": "tool", "content": _ext_msg})
            else:
                _covd = [f"{f}→{rv}" for f, rv in (_cov or {}).items()]
                why = (f"requirement {rid} not in the original contract"
                       if rid and rid not in _reqs else
                       f"requirement {rid} is ALREADY covered (facts: {_covd}) — "
                       "extend only UNPLANNED requirements; if the evidence is "
                       "insufficient, repair RELATIONS on the covering fact instead"
                       if rid in (_cov.values() if _cov else ()) else
                       "no valid sgN.anchor/sgN.fM block, or anchor is not a "
                       "question entity / bound variable")
                self.messages.append({"role": "user", "content":
                    f"REJECTED PLAN EXTEND: {why}. Extension must cover an "
                    "UNPLANNED original requirement from a legal anchor."})
                self.ctx.trajectory.append({"role": "tool", "content":
                    "REJECTED PLAN EXTEND: " + why})

        # merge any checkpoint variable-bindings the model just declared, so the
        # dispatch below (and later turns) can expand `?var` in tool `entities`.
        _update_var_bindings(self.ctx, raw_response)
        # MULTI-TREE PROMPT (user audit 2026-09-17, 567_df97 specimen): the
        # first fact resolved is the moment to check the OTHER declared
        # entities — if one anchors no tree yet, prompt NOW, not at the
        # answer gate (by then a 49-member single tree has absorbed several
        # wasted filter layers; the join side never got its own cheap walk).
        if not getattr(self.ctx, "_multi_tree_prompted", False):
            _fb = getattr(self.ctx, "fact_bindings", None) or {}
            _pe = [str(e) for e in (getattr(self.ctx, "plan_entities", None) or [])]
            _cons = {str(c).strip().lower() for c in
                     (getattr(self.ctx, "consumed_anchors", None) or set())}
            _unanchored = [e for e in _pe
                           if e.strip().lower() not in _cons
                           and not self._type_word_exempt(e)]
            if _fb and len(_pe) >= 2 and _unanchored:
                self.ctx._multi_tree_prompted = True
                _mt = ("MULTI-TREE REMINDER: declared entity "
                       + " | ".join(f"'{e}'" for e in _unanchored[:2])
                       + " anchors no tree yet. Anchor it as its OWN subgraph"
                       " (retrieve_relations FROM it), then let SYSTEM JOIN"
                       " intersect the two sides — anchored retrieval"
                       " discriminates better than filter layers on one"
                       " tree.")
                self._emit_tool_note(_mt)
        # COMMIT-WIDENING: normalize this turn's closures (✗) and accepted
        # declarations (✓) into the state's done-sets — READY and completion
        # counting live in the harness, which sees state only. Pure `sgN`
        # declarations resolve to the group's first unfinished fact.
        self.state.closed_fids = {norm_fact_key(self.state, k)
                                  for k in (getattr(self.ctx, "closed_facts", None) or {})}
        self.state.declared_fids = {norm_fact_key(self.state, k)
                                    for k in (getattr(self.ctx, "fact_vars", None) or {})}
        # harness reminder: the model just bound CVT event nodes — events are
        # never entities; the binding was stripped, tell it what to bind instead.
        if getattr(self.ctx, "cvt_binding_flag", False):
            self.ctx.cvt_binding_flag = False
            _cvt_msg = ("⚠ Your checkpoint bound EVENT nodes (m./g. ids) as variable "
                        "values. An event node is an abstract RECORD — it names no "
                        "thing, so that binding was removed (see §7.5). The entities "
                        "INSIDE the event's bracket are the world: re-declare the "
                        "checkpoint binding, per variable, the attribute entity whose "
                        "KEY answers that variable (award question → the award= value, "
                        "residence → location=, who played → actor=).")
            self.messages.append({"role": "user", "content": _cvt_msg})
            self.ctx.trajectory.append({"role": "tool", "content": _cvt_msg})
        # harness reminder: the checkpoint re-declared a FROZEN fact without
        # new subgraph evidence — tell the model it is a hallucination.
        fb = getattr(self.ctx, "frozen_binding_flag", None)
        if fb:
            self.ctx.frozen_binding_flag = None
            _fz_msg = (f"⚠ Your checkpoint [{fb[0]} ✓] tried to change bindings "
                       f"({fb[1]}) WITHOUT any new subgraph retrieval for {fb[0]} — "
                       "this is a hallucination: the re-declaration was REJECTED and "
                       f"the original {fb[0]} bindings stand. A fact's values may only "
                       "come from its own subgraph's evidence (original or a fresh "
                       f"retrieval of {fb[0]}). If you need different values, retrieve "
                       "that subgraph again; otherwise answer from the standing "
                       "bindings.")
            self.messages.append({"role": "user", "content": _fz_msg})
            self.ctx.trajectory.append({"role": "tool", "content": _fz_msg})
        # harness reminder: the checkpoint bound entities ABSENT from the
        # declaring subgraph's evidence (cross-subgraph contamination / invented).
        hb = getattr(self.ctx, "halluc_binding_flag", None)
        if hb:
            self.ctx.halluc_binding_flag = None
            _fid, _bad = hb
            _hal_msg = (f"⚠ Your checkpoint [{_fid} ✓] bound entities that NEVER "
                        f"appeared in subgraph {_fid}'s displayed evidence: {_bad}. "
                        "They were removed. A fact's bindings come ONLY from ITS OWN "
                        f"subgraph's triples — do not merge entities from other "
                        f"subgraphs into this declaration. Re-declare from subgraph "
                        f"{_fid}'s evidence only.")
            self.messages.append({"role": "user", "content": _hal_msg})
            self.ctx.trajectory.append({"role": "tool", "content": _hal_msg})
        # SYSTEM JOIN note: multiple subgraphs now bind the same variable — the
        # harness intersected them. Tell the model the effective binding so it
        # answers with the intersection, never one side's full list.
        jf = getattr(self.ctx, "join_flag", None)
        if jf:
            self.ctx.join_flag = None
            _var, _fids, _inter = jf
            if _inter:
                _j_msg = (f"⌗ SYSTEM JOIN: {len(_fids)} subgraphs bind {_var} "
                          f"({', '.join(_fids)}) — EVERY constraint must hold. "
                          f"{_var} = {' ∩ '.join(_fids)} = "
                          f"[{' | '.join(_inter[:40])}]"
                          + (f" … ({len(_inter)} entities)" if len(_inter) > 40 else "")
                          + ". Answer with THESE entities only — submitting one "
                            "subgraph's unreduced list is a constraint violation.")
            else:
                _j_msg = (f"⌗ SYSTEM JOIN: {len(_fids)} subgraphs bind {_var} "
                          f"({', '.join(_fids)}) — EVERY constraint must hold. "
                          f"{_var} = {' ∩ '.join(_fids)} = EMPTY: the declared "
                          "lists share NO entity. CAUTION before answering empty: "
                          "a checkpoint list is CURATED, not exhaustive — if one "
                          "side listed only representative bindings, the true "
                          "answer may sit in its unlisted remainder. Re-examine "
                          "both subgraphs' triples (or re-retrieve the weaker "
                          "side) and answer by your own discrimination; do not "
                          "dump one side's list.")
            self.messages.append({"role": "user", "content": _j_msg})
            self.ctx.trajectory.append({"role": "tool", "content": _j_msg})

        # quote unquoted ?variables — ONLY for JSON format (flat format breaks if
        # quoted: answer: ?x → answer: "?x" → Pydantic sees '"?x"' not '?x')
        if re.search(r'tool:\s*\{', raw_response):
            raw_response = re.sub(r'(?<=[,\[\s:])\?(\w+)(?=[,\]\s}])', r'"?\1"', raw_response)

        tool_name, parsed_args = _parse_with_repair(raw_response)
        if not tool_name:
            # DIAGNOSTIC: report the SPECIFIC JSON parse error so the model can fix it
            _diag = None
            for m in re.finditer(r'tool:\s*(\{)', raw_response):
                _seg = raw_response[m.start(1):]
                _depth, _end = 0, 0
                for _i, _c in enumerate(_seg):
                    if _c == '{': _depth += 1
                    elif _c == '}': _depth -= 1
                    if _depth == 0 and _i > 0:
                        _end = _i + 1; break
                _candidate = _seg[:_end] if _end else _seg
                try:
                    json.loads(_candidate)
                except json.JSONDecodeError as je:
                    _diag = (f"The `tool:` JSON has a syntax error: {je.msg} at char {je.pos}. "
                             f"Re-emit ONE clean `tool:` line with complete, valid JSON.")
                    break
                except Exception:
                    _diag = "The `tool:` JSON could not be parsed. Re-emit ONE clean `tool:` line."
                    break
            if _diag:
                fmt_nudge = _diag
            elif re.search(r"ANSWER_ANALYSIS", raw_response):
                # The two-stage ANALYSIS turn is a LEGAL declaration, not garbage
                # — signal READY immediately (this early-return previously
                # prevented the tail-side signal from EVER firing).
                self.ctx._analysis_pending = False
                self.ctx._analysis_done = True
                self.messages.append({"role": "user", "content":
                    "ANSWER_READY — submit the final answer now from your analysis. "
                    "COUNT CONTRACT: CASE A = ALL fully-supported; CASE B = single best. "
                    "(FINAL_BINDINGS, then the answer call). Flat format:\n"
                    "tool: answer\nentities: A | B"})
                self.ctx.trajectory.append({"role": "tool", "content": "ANSWER_READY signal"})
                self._last_tool_sig = None; self._tool_repeat = 0
                return {"ret": "continue"}
            elif re.search(r"\[[^\]]*[✓✗]\]", raw_response):
                # checkpoint-only turn: the declarations were already merged by
                # _update_var_operations above — acknowledge, don't scold.
                # Var binding status rides along (ladder pack ②, 2026-08-24):
                # information, never enforcement — vars link facts, binding
                # is not forced.
                _fbv = getattr(self.ctx, "fact_bindings", None) or {}
                _fvv = getattr(self.ctx, "fact_vars", None) or {}
                _vstat = "; ".join(
                    f"{_v}=bound({len(_fbv[_f])})" if _fbv.get(_f)
                    else f"{_v}=unbound"
                    for _f, _v in list(_fvv.items())[:8])
                fmt_nudge = ("Checkpoints recorded. "
                             + (f"Subgraph vars: {_vstat}\n" if _vstat else "")
                             + "Now emit your next tool call, "
                             "flat format (one key per line):\n"
                             "tool: retrieve_relations\ncenter: <entity or ?var>\n"
                             "question: <sub-question>\n" + self.allowed_tools_hint())
            elif any(k in raw_response for k in ("CANDIDATES", "ANSWER:", "BASE_BINDINGS",
                                                 "FINAL_BINDINGS", "CONSTRAINT_CHECK",
                                                 "PROVISIONAL_FINAL")):
                fmt_nudge = ("Your content has the answer reasoning but no valid tool "
                             "call. Submit with flat format:\n"
                             "tool: answer\nentities: A | B")
            else:
                fmt_nudge = (f"No `tool:` call found. Emit flat format — one `tool:` "
                             f"line then key: value lines (no JSON needed):\n"
                             f"tool: retrieve_relations\ncenter: <entity>\n"
                             f"question: <sub-question>\n"
                             f"{self.allowed_tools_hint()}")
            self.messages.append({"role": "user", "content": fmt_nudge})
            self.ctx.trajectory.append({"role": "tool", "content": "(no tool call)"})
            self._last_tool_sig = None; self._tool_repeat = 0   # different action — reset anti-loop
            return {"ret": "continue"}

        parsed_args = parsed_args or {}
        _pre_val_args = parsed_args          # pre-schema parse (see merge below)
        validated_args, schema_err = validate_args(tool_name, parsed_args)
        if schema_err:
            self.messages.append({"role": "user", "content": f"REJECTED: {schema_err}"})
            self.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {schema_err}"})
            self._last_tool_sig = None; self._tool_repeat = 0
            return {"ret": "continue"}
        parsed_args = validated_args
        # PlanArgs (seq_schemas) declares no `requirements` / subgraph `covers`
        # fields — pydantic silently DROPS them at validation, cutting the
        # Question Contract linkage (fact_covers, PLAN EXTEND gate, SUPPORT
        # matrix, answer-kind answer_var inference) out of the live loop.
        # Restore them from the pre-validation parse (position-matched).
        if tool_name in ("plan", "decompose"):
            if not validated_args.get("requirements") and _pre_val_args.get("requirements"):
                validated_args["requirements"] = _pre_val_args["requirements"]
            for _src, _dst in zip(_pre_val_args.get("subgraphs") or [],
                                  validated_args.get("subgraphs") or []):
                if _src.get("covers") and not _dst.get("covers"):
                    _dst["covers"] = _src["covers"]
        # anti-loop: consecutive IDENTICAL tool calls
        sig = (tool_name, json.dumps(parsed_args, sort_keys=True, ensure_ascii=False))
        if getattr(self, "_last_tool_errored", False):
            # an ERRORED call was never "served" — the checkpoint-corrected
            # retry is legitimate, not a loop (25_db96/62_bce8 specimens:
            # unbound-center error → retry with checkpoint → REJECTED (repeat)
            # → hallucinated relations → dump-all)
            self._last_tool_sig = None
            self._tool_repeat = 0
            self._last_tool_errored = False
        if sig == self._last_tool_sig:
            self._tool_repeat += 1
        else:
            self._last_tool_sig = sig
            self._tool_repeat = 1
        # REJECT identical repeats (not just nudge) — prevents wasted turns.
        # The model re-calling retrieve_relations with the same args gets the same
        # candidates. Force it to proceed: pick relations → retrieve_subgraph, or
        # declare checkpoint → next fact, or answer.
        # `answer` is EXEMPT (harness fix P1): it is an idempotent TERMINAL tool — an
        # identical re-call is confirmation of intent, not a wasted retrieval. Rejecting
        # it trapped compliant retries (the model followed a prior rejection's "call
        # answer again" instruction straight into this gate, forever). The premature/
        # offpool answer rejections are one-shot by design; the retry must pass through.
        if self._tool_repeat >= 2 and tool_name != "answer":
            nudge = self.loop_nudge()
            self.messages.append({"role": "user", "content": nudge})
            self.ctx.trajectory.append({"role": "tool", "content": f"REJECTED (repeat): {nudge}"})
            return {"ret": "continue"}

        # NONE/REFUSAL LADDER (answer-layer pack ①, 2026-08-24; restored
        # 2026-09-07 against tests/test_commit_widening.py): a literal
        # None/refusal answer means the model declares the exploration
        # dead-ended — NOT an error to bounce through offpool. Routing:
        # FIRST refusal keeps the go-back right (fall back ONE level,
        # re-select the weakest subgraph's relations — never forced to
        # answer); SECOND refusal → answer from current support with the
        # bindings shown as basis; after the ONE restart a None/refusal IS
        # the explicit empty answer (restart contract — accepted).
        if tool_name == "answer":
            _ne = parsed_args.get("entities")
            if _ne is None:
                _ne = parsed_args.get("ANSWER") or parsed_args.get("answer") or []
            if isinstance(_ne, str):
                _ne = [e.strip() for e in _ne.replace("|", ",").split(",") if e.strip()]
            _s0 = str(_ne[0]).strip().lower() if isinstance(_ne, list) and len(_ne) == 1 else ""
            _refusal = (_s0 in ("none", "null", "nan")
                        or (_s0 and re.search(
                            r"unable to determine|cannot be determined|"
                            r"cannot determine|undetermined|no valid answer", _s0)))
            if _refusal:
                if getattr(self.ctx, "restarted", False):
                    # restart contract: explicit empty answer; rewrite the
                    # literal so the offpool check cannot reject it
                    parsed_args = dict(parsed_args)
                    parsed_args["entities"] = []
                else:
                    self.ctx._refusal_n = getattr(self.ctx, "_refusal_n", 0) + 1
                    if self.ctx._refusal_n == 1:
                        self._emit_tool_note(
                            "NONE → ladder: re-select relations; "
                            "[explore ✗ none] restarts once\n"
                            "You may fall back ONE level: re-select the weakest "
                            "subgraph's relation set (curated relation lists are "
                            "never exhaustive) and retrieve again. If nothing at "
                            "all was answer-relevant, declare [explore ✗ none] "
                            "to restart the case once.")
                        return {"ret": "continue"}
                    _fb = getattr(self.ctx, "fact_bindings", None) or {}
                    _fv = getattr(self.ctx, "fact_vars", None) or {}
                    _basis = "; ".join(f"{_fv[_f]}={list(_fb[_f])[:4]}"
                                       for _f in _fb if _f in _fv and _fb[_f])
                    self.ctx._analysis_pending = False
                    self._emit_tool_note(
                        "Second refusal — answer from current support NOW "
                        f"(bindings so far: {_basis or 'none'}).")
                    return {"ret": "continue"}
            elif (isinstance(_ne, list) and _ne
                    and not getattr(self.ctx, "_varmismatch_retried", False)):
                # VAR-MISMATCH GUARD (Stalin specimen, 2026-08-24): entities
                # drawn ENTIRELY from ANOTHER variable's bindings while the
                # declared answer var has its own — one-shot intercept; the
                # justified resubmit passes.
                _av = [str(v) for v in (getattr(self.state, "answer_var", None) or [])]
                _fv = getattr(self.ctx, "fact_vars", None) or {}
                _fb = getattr(self.ctx, "fact_bindings", None) or {}
                _aset = {str(x).strip().lower() for x in _ne}
                # intercept only when the answer var HAS its own bindings and
                # the submission is entirely some OTHER var's values (an
                # alias-var fallback has no answer-var bindings — passes)
                _own_union = {str(x).strip().lower()
                              for _v in _av
                              for _f, xv in _fb.items() if _fv.get(_f) == _v
                              for x in xv}
                _mvar = next((_v for _f, _v in _fv.items()
                              if _v not in _av
                              and _aset and _aset <= {str(x).strip().lower()
                                                      for x in (_fb.get(_f) or [])}),
                             None)
                if _mvar is not None and _own_union and not (_aset <= _own_union):
                    self.ctx._varmismatch_retried = True
                    self._emit_tool_note(
                        f"MECHANICAL MISMATCH: every submitted entity is a "
                        f"binding of {_mvar}, but the plan's answer variable "
                        f"is {' / '.join(_av) or 'unset'}, which has its own "
                        "bindings. Either submit the answer variable's "
                        "values, or — if the question genuinely asks for "
                        f"{_mvar}'s values — justify that and re-submit.")
                    return {"ret": "continue"}

        # EVIDENCE COMMIT trigger (COMMIT-WIDENING): fire the ledger the moment
        # the READY predicate holds — including the very turn the model tries to
        # answer on READY, so that answer hits the STAGE GATE below instead of
        # bypassing the two-stage path (the 42% direct-answer family).
        self._maybe_inject_evidence_commit()

        # TWO-STAGE ANSWER GATE (V2.1): the FIRST answer attempt after
        # EVIDENCE COMMIT is intercepted — the model must emit
        # ANSWER_ANALYSIS first; the harness then signals ANSWER_READY.
        # One-shot: a second attempt passes (budget escape).
        # Empty answers skip the gate (ladder pack ③, 2026-08-24): there is
        # nothing to analyze — an empty submission was already decided.
        _ans_entities = (parsed_args.get("entities")
                         or parsed_args.get("ANSWER")
                         or parsed_args.get("answer"))
        if (tool_name == "answer" and _ans_entities
                and getattr(self.ctx, "_analysis_pending", False)):
            self.ctx._analysis_pending = False
            if re.search(r"ANSWER_ANALYSIS[\s\S]{0,600}BASE_CANDIDATES", raw_response):
                # inline analysis satisfies the gate (baseline rule, 103/103
                # passed): the model answered WITH its analysis block —
                # accept it; re-analysis is where correct answers degrade
                # (626_01ad 1.0→0.25, 60_6b8e 0.94→0.5 specimens).
                self.ctx._analysis_done = True
            else:
                self.messages.append({"role": "user", "content":
                    "STAGE GATE: evidence is committed but not yet analyzed. "
                    "Emit ANSWER_ANALYSIS now (BASE_CANDIDATES / REQUIREMENT_"
                    "CHECK / COUNT_CONTRACT / PROVISIONAL_FINAL) — no answer call. "
                    "COUNT CONTRACT: CASE A = all fully-supported; CASE B = single "
                    "best-supported. The next turn will be ANSWER_READY."})
                self.ctx.trajectory.append({"role": "tool", "content":
                    "STAGE GATE: ANSWER_ANALYSIS required before answer"})
                return {"ret": "continue"}

        _ready, _missing = False, None
        if tool_name == "answer":
            _cf = getattr(self.ctx, "closed_facts", None) or {}
            _fb2 = getattr(self.ctx, "fact_bindings", None) or {}
            _vj2 = getattr(self.ctx, "var_joins", None) or {}
            _ready = commit_due(self.state, _cf, _fb2, _vj2)
            # restart contract: after the ONE restart, an empty answer IS
            # the terminal the contract mandates — never remind again
            if (not _ready and getattr(self.ctx, "restarted", False)
                    and not _ans_entities):
                _ready = True
            if not _ready:
                _missing = blocking_facts(self.state, _cf, _fb2, _vj2)

        # MULTI-ANCHOR CONSUMPTION GATE (V3.7g, 2026-09-01, restored
        # 2026-09-07): intercept the answer ONE round when declared plan
        # entities never anchored a retrieval — MUST run before seq_validate
        # transitions the state to DONE: intercepting after the transition
        # leaves state=DONE with done unset, and every later call dies as
        # "REJECTED: Conversation finished" until the round budget burns out
        # (24-zombie family in the 2026-09-07 full-fix run).
        # READY-EXEMPT (user audit 2026-09-17, WebQTrn-21 specimen): when
        # every fact is closed and the answer is due, an unconsumed type
        # word has no retrieval form anyway — the gate only burned a round
        # between EVIDENCE COMMIT and the accepted answer. Skip it on READY.
        if tool_name == "answer" and _ans_entities and not _ready \
                and self._ma_gate_would_fire(parsed_args):
            # deferred: the gate's join search is GTE-ranked (async) — the
            # caller runs it BEFORE anything else; state never transitions
            return {"ret": "continue", "_gate_deferred": (tool_name, parsed_args)}
        ok, err, new_state = seq_validate(
            self.state, _to_tool_calls(tool_name, parsed_args),
            ready=_ready, missing_facts=_missing)
        if not ok:
            self.messages.append({"role": "user", "content": f"REJECTED: {err}"})
            self.ctx.trajectory.append({"role": "tool", "content": f"REJECTED: {err}"})
            return {"ret": "continue"}
        self.state = new_state

        # PURITY-LOOP DETECTOR (user ruling, 2026-08-22): the repeat-gate
        # only catches EXACT repeats — the purity pattern is SAME fact/center
        # queried with DIFFERENT wordings (Brad Stevens tenure: 4 rephrasings
        # × 10 wasted turns). Track per-center question similarity; ≥3
        # similar-intent queries → FORCED Stop-Rule reminder; ≥5 → the
        # harness closes the fact itself (unresolved-after-repair).
        if tool_name == "retrieve_relations":
            from kgqa.core.utils import normalize as _qn
            _key = _qn(str((parsed_args.get("center") or [""])[0]))[:60]
            _qq = _qn(str(parsed_args.get("question") or ""))
            _hist = getattr(self.ctx, "_qsim_hist", None)
            if _hist is None:
                _hist = {}; self.ctx._qsim_hist = _hist
            _tok = frozenset(w for w in _qq.split() if len(w) >= 3)
            _sims = []
            for q, t in _hist.get(_key, []):
                if not _tok or not t:
                    continue
                inter = len(_tok & t)
                if inter < 3:
                    continue          # "this city"-level overlap is noise
                jac = inter / len(_tok | t)
                cont = inter / min(len(_tok), len(t))   # paraphrases keep
                if jac >= 0.45 or cont >= 0.6:          # content words but
                    _sims.append(q)                     # swap wh/verbs
            _hist.setdefault(_key, []).append((_qq, _tok))
            # streak: consecutive queries on this center similar to a prior one
            _st = getattr(self.ctx, "_qsim_streak", None) or {}
            _n = (_st.get(_key, 0) + 1) if _sims else 1
            _st[_key] = _n
            self.ctx._qsim_streak = _st
            if _n == 3:
                self.messages.append({"role": "user", "content":
                    "⚠ BEHAVIOR PATTERN: this is your 3rd similarly-worded query "
                    "for the same center. Re-asking with new wording is the "
                    "purity pattern — apply the Stop Rule: continue ONLY if the "
                    "missing evidence could change WHICH NAMED ENTITY you "
                    "return. Otherwise close the fact "
                    "`[fid ✗ unresolved-after-repair]` NOW and move on."})
                self.ctx.trajectory.append({"role": "tool", "content":
                    "⚠ purity-loop reminder (3rd similar query)"})
            elif _n >= 4:
                _fid = str(parsed_args.get("sg") or "") or next(
                    (f for f in reversed(self.state.fact_ids)
                     if f not in self.state.retrieved_fids), "")
                cf = getattr(self.ctx, "closed_facts", None)
                if cf is not None and _fid:
                    cf[_fid] = "unresolved-after-repair"
                self.messages.append({"role": "user", "content":
                    f"⌗ HARNESS CLOSURE: [{_fid} ✗ unresolved-after-repair] — "
                    "5 similar queries on the same center returned nothing new. "
                    "The fact is closed by the system. Move to the next open "
                    "fact or answer from the evidence you hold."})
                self.ctx.trajectory.append({"role": "tool", "content":
                    f"⌗ HARNESS CLOSURE: {_fid} closed (purity loop)"})

        # sync the decompose projection onto ctx so dispatch sees the fact structure
        self.ctx.fact_ids = list(self.state.fact_ids)
        self.ctx.fact_texts = dict(self.state.fact_texts)
        self.ctx.fact_key_map = dict(getattr(self.state, "fact_key_map", None) or {})
        self.ctx.fact_edges = dict(getattr(self.state, "fact_edges", None) or {})
        self.ctx._model_anchor = self.state.anchor or ""
        if tool_name in ("decompose", "plan"):
            # plan-contract v2: capture the declared answer-type word — the
            # question-analysis anchor (who→person, what year→year...). Echoed at
            # answer time so the turn-0 reading stays in force all episode.
            at = str(parsed_args.get("answer_type") or "").strip()
            if at:
                self.ctx.plan_answer_type = at
            from kgqa.agent.loop import _resolve_anchor
            _resolve_anchor(self.ctx)
        return {"tool": tool_name, "args": parsed_args, "raw": raw_response}

    async def _execute_tool(self, prep, session) -> str:
        """B段 (IO): execute the prepared tool request. Exceptions land here as
        the dispatch error result — same semantics as the original single try
        around ST.dispatch (the finalization steps still run on error)."""
        tool = prep["tool"]
        try:
            return await ST.dispatch(tool, prep["args"], self.ctx, session)
        except Exception as e:
            return json.dumps({"error": f"dispatch_{tool}: {e}"})

    def _finalize(self, prep, result_str) -> str:
        """C段 (pure CPU): land the tool result, merge evidence, fire the
        post-dispatch EVIDENCE COMMIT, assemble the messages."""
        tool_name = prep["tool"]
        parsed_args = prep["args"]
        raw_response = prep["raw"]
        # errored calls are not "served": flag for the repeat detector so the
        # corrected retry is not rejected as a loop (see _parse_prepare).
        # SEQ's _json_result renders errors as FLAT "error: ..." / "entity_error: ..."
        # text, not JSON — the old '{"error"' probe never matched, so the
        # unbound-?var error → checkpoint declaration → corrected re-call hit
        # the repeat gate and dead-ended (1278d3da s2 specimen)
        _head = result_str[:120].lstrip()
        if (_head.startswith('{"error"') or '"error"' in result_str[:80]
                or _head.startswith("error:") or _head.startswith("entity_error:")):
            self._last_tool_errored = True
        self.messages.append({"role": "user",
                              "content": f"Tool result ({tool_name}): {result_str}"})
        self.ctx.trajectory.append({"role": "tool", "name": tool_name,
                                    "content": result_str})

        # plan-phase rollback: validate() transitions INIT→RETRIEVE on PARSE
        # success, but the tool handler can still reject (gate mismatch). If a
        # plan/decompose call was rejected downstream and NO plan was ever
        # accepted (plan_declared False), roll the state machine back to INIT
        # so re-emitting the (corrected) plan stays legal. Otherwise the phase
        # gate blocks exactly the re-emission the rejection message demanded
        # (CH specimen). When a plan IS already declared, the rejection is the
        # immutability gate — state stays RETRIEVE so the workflow continues.
        if (tool_name in ("plan", "decompose")
                and self.state.state == "RETRIEVE"
                and not getattr(self.ctx, "plan_declared", False)
                and ('"error"' in result_str or "REJECTED" in result_str)):
            self.state.state = "INIT"

        # CVT-CHAIN LOOP BREAKER (Norwood specimen, 2026-08-22): when the same
        # stranded variable hits "can NEVER bind" twice, the model is looping
        # declare→error (observed: 16 wasted turns). The harness closes the
        # stranding fact as MOOT itself — the fact's target is inside the
        # event's brackets — and orders the workflow forward.
        if "can NEVER bind" in result_str:
            _cev = getattr(self.ctx, "cvt_empty_var", None)
            if _cev:
                self.ctx._cvt_loop_n = getattr(self.ctx, "_cvt_loop_n", 0) + 1
                if self.ctx._cvt_loop_n >= 2:
                    _var, _fid = _cev
                    cf = getattr(self.ctx, "closed_facts", None)
                    if cf is not None and _fid not in cf:
                        cf[_fid] = "moot"
                    _brk = (f"⌗ HARNESS CLOSURE: [{_fid} ✗ moot] — its variable "
                            f"{_var} can only ever bind EVENT nodes (§7.5), so the "
                            "fact is unanswerable as planned. The fact's target "
                            "is ALREADY visible inside the event's brackets "
                            "(attribute entities). Continue with the NEXT fact, "
                            "centering on an attribute entity from the brackets.")
                    self.messages.append({"role": "user", "content": _brk})
                    self.ctx.trajectory.append({"role": "tool", "content": _brk})
                    self.ctx._cvt_loop_n = 0

        # BINDING LEDGER → EVIDENCE COMMIT (V2.1, 2026-08-22; COMMIT-WIDENING:
        # trigger is the READY predicate, not all_retrieved — see the method).
        # Post-dispatch site: a retrieval that completed the evidence fires the
        # ledger on the SAME turn (the pre-gate site runs before validate, so it
        # cannot see this turn's retrieval).
        self._maybe_inject_evidence_commit()

        # two-stage answer: ANALYSIS emitted → signal ANSWER_READY
        if getattr(self.ctx, "_analysis_pending", False) and \
                re.search(r"ANSWER_ANALYSIS", raw_response):
            self.ctx._analysis_pending = False
            self.ctx._analysis_done = True
            self.messages.append({"role": "user", "content":
                "ANSWER_READY — submit the final answer now from your analysis "
                "(FINAL_BINDINGS + tool: answer). COUNT CONTRACT: CASE A = ALL "
                "fully-supported; CASE B = single best-supported. Do not reinterpret."})
            self.ctx.trajectory.append({"role": "tool", "content": "ANSWER_READY signal"})

        if self.state.state == "DONE":
            ans_entities = (parsed_args.get("entities") if tool_name == "answer" else None) or []
            pool = list(getattr(self.ctx, "all_candidates", []) or [])
            _joins_now = getattr(self.ctx, "var_joins", None) or {}
            if (tool_name == "answer" and not ans_entities
                    and not self._empty_answer_retried and pool):
                # (JOIN-empty rescue suppression REMOVED, Thundera specimen:
                #  curated lists are not exhaustive — an empty intersection is
                #  a completeness question for the MODEL, not a harness fact.)
                self._empty_answer_retried = True
                self.state.state = "RETRIEVE"   # roll back so `answer` is legal again
                self.messages.append({"role": "user", "content":
                    "Your answer was empty — an empty answer scores 0. Pick the entity (or "
                    "entities) MOST likely to answer the question from the evidence you have "
                    f"and call `answer` again. Candidate pool: {pool[:40]}."})
                return "continue"
            self.done = True
            return "done"
        return "continue"


async def run_seq_react_case(session: aiohttp.ClientSession, sample: Dict[str, Any],
                             pilot_row: Dict[str, Any], idx: int, args) -> Dict[str, Any]:
    """Run one case through the SEQ per-fact loop (content-only `tool:` protocol).

    Each turn: LLM returns free-form content; parse_react_output extracts the
    `tool:` anchor + JSON; seq_harness.validate + seq_tools.dispatch run it.
    """
    from kgqa.llm.client import _call_single_with_reasoning, THINKING_TOKEN_BUDGET as _tb

    rc = SeqReactCase(sample, pilot_row, idx)
    await rc.prelink(session)
    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)

    for _ in range(max_rounds):
        if not rc.is_active:
            break
        msgs = list(rc.messages)
        hint = rc.state_aware_hint() + rc.allowed_tools_hint()
        if rc._tool_repeat >= 2:  # stuck on the same call — force convergence
            hint = rc.loop_nudge() + "\n" + hint
        msgs.append({"role": "user", "content": hint})

        try:
            raw_response, reasoning = await _call_single_with_reasoning(
                session, msgs, max_tokens=max_tokens)
        except Exception as e:
            rc.failed = True
            rc.failure_reason = f"call_llm error: {e}"
            break

        if await rc.process_turn(session, raw_response, reasoning) == "done":
            break
    else:
        rc.failed = True
        rc.failure_reason = f"max_iters ({max_rounds}) reached at state {rc.state.state}"

    rc.rescue_terminal_answer()   # harness fix P4: recover trapped answers
    result = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
    result["decomposition_method"] = "seq_per_fact"
    if getattr(rc, "_rescued", False):
        result["terminal_rescue"] = True
    return result


async def run_seq_react_batch(cases_to_run, args):
    """Turn-synchronous SEQ batch runner — the production eval entry.

    Each round every active case advances exactly one turn: all cases' prompts are
    sent in ONE batched LLM call (``batch_call_llm_with_reasoning``, chunked to
    ``batch_chunk``), then each case's ``process_turn`` runs concurrently. This
    replaces the per-call path (``run_seq_react_case``) for evaluation: it is far
    faster (no per-turn HTTP round-trip per case) and avoids the per-call
    connection drops under concurrency that produced empty-answer regressions.

    ``cases_to_run``: list of ``(sample, pilot_row, idx)``. Returns
    ``[(sample, pilot_row, result_dict), ...]`` where result_dict carries
    ``agent_trajectory`` for dumping.
    """
    import time
    from kgqa.llm.client import THINKING_TOKEN_BUDGET as _tb
    from kgqa.llm.batch import batch_call_llm_with_reasoning

    total = len(cases_to_run)
    print(f"\n=== SEQ batch mode: {total} cases ===", flush=True)
    wall_start = time.perf_counter()

    react_cases = [SeqReactCase(s, pr, idx) for s, pr, idx in cases_to_run]
    max_rounds = int(getattr(args, "agent_max_iters", 16))
    max_tokens = int(getattr(args, "agent_max_tokens", 1024))
    if _tb > 0:
        max_tokens = max(max_tokens, _tb + 2560)
    batch_chunk = int(getattr(args, "batch_chunk", 25))

    async with aiohttp.ClientSession() as session:
        # plan-前置实体预检索（每 case 一次 GTE；并发受限避免 GTE 连接 reset）
        _pl_sem = asyncio.Semaphore(16)

        async def _pl(_rc):
            async with _pl_sem:
                await _rc.prelink(session)

        await asyncio.gather(*[_pl(rc) for rc in react_cases])

        for round_num in range(max_rounds):
            active = [rc for rc in react_cases if rc.is_active]
            if not active:
                break

            # build prompts (append allowed-tools hint + anti-loop nudge) — mirrors
            # the per-call runner's prompt assembly exactly.
            prompts = []
            for rc in active:
                hint = rc.state_aware_hint() + rc.allowed_tools_hint()
                if rc._tool_repeat >= 2:
                    hint = rc.loop_nudge() + "\n" + hint
                msgs = list(rc.messages)
                msgs.append({"role": "user", "content": hint})
                prompts.append(msgs)

            # batched LLM call (chunked — batch endpoint scales poorly past ~25)
            try:
                if len(prompts) <= batch_chunk:
                    contents, reasoning = await batch_call_llm_with_reasoning(
                        session, prompts, max_tokens=max_tokens)
                    chunk_results = [(contents, reasoning)]
                else:
                    chunks = [prompts[i:i + batch_chunk]
                              for i in range(0, len(prompts), batch_chunk)]

                    async def _b(chunk):
                        return await batch_call_llm_with_reasoning(
                            session, chunk, max_tokens=max_tokens)
                    chunk_results = await asyncio.gather(*[_b(c) for c in chunks])
            except Exception as e:
                print(f"  batch call failed: {e}", flush=True)
                for rc in active:
                    rc.failed = True
                    rc.failure_reason = f"batch_call error: {e}"
                break

            responses, responses_reasoning = [], []
            for cr_c, cr_r in chunk_results:
                responses.extend(cr_c)
                responses_reasoning.extend(cr_r)

            # process each case concurrently (dispatch is cheap except retrieve_*,
            # which is bounded in-process)
            dispatch_sem = asyncio.Semaphore(16)

            async def _proc(rc, raw, rsn):
                async with dispatch_sem:
                    if not raw:
                        # batch endpoint returns None on a per-prompt failure — treat
                        # like the per-call empty-response path: nudge and keep going.
                        rc.messages.append({"role": "assistant", "content": ""})
                        rc.messages.append(
                            {"role": "user", "content": rc.allowed_tools_hint()})
                        return
                    await rc.process_turn(session, raw, rsn)

            await asyncio.gather(*[_proc(rc, raw, rsn)
                                   for rc, raw, rsn in
                                   zip(active, responses, responses_reasoning)])

            done = sum(1 for rc in react_cases if rc.done)
            failed = sum(1 for rc in react_cases if rc.failed)
            print(f"  round {round_num + 1}: {len(active)} active → "
                  f"done={done} failed={failed}", flush=True)

    dt = time.perf_counter() - wall_start
    print(f"SEQ batch done: {total} cases in {dt:.0f}s ({dt / total:.1f}s/case)", flush=True)

    results: List[Tuple[Any, Any, Dict[str, Any]]] = []
    for (s, pr, idx), rc in zip(cases_to_run, react_cases):
        rc.rescue_terminal_answer()   # harness fix P4: recover trapped answers
        r = _ctx_to_result_dict(rc.ctx, rc.state, rc.failed, rc.failure_reason)
        r["decomposition_method"] = "seq_per_fact"
        r["agent_trajectory"] = rc.ctx.trajectory
        if getattr(rc, "_rescued", False):
            r["terminal_rescue"] = True
        results.append((s, pr, r))
    return results


async def run_round_dispatch(cases_raws, session):
    """Round-level scheduler (perf-4): A loop for ALL active cases → B fires
    every GTE/walk request together (the seq_tools collectors coalesce the
    whole round into few lane jobs; GTE GPU and walk CPU lanes overlap) →
    C loop for all. Per-case semantics IDENTICAL to process_turn — that
    method keeps the sequential composition for the per-case runner,
    run_seq_react_batch and every test; only the phase interleaving differs
    (the event loop does orchestration only, sync CPU no longer fragments
    into 500-coroutine interleave)."""
    import time as _time_mod
    _perf = _time_mod.perf_counter
    prepared = []
    _t0 = _perf()
    for rc, raw, reasoning in cases_raws:
        if rc.done or rc.failed:
            continue
        prep = rc._parse_prepare(raw, reasoning)
        if "_gate_deferred" in prep:
            await rc._ma_gate_check(*prep["_gate_deferred"], session)
            continue
        if "ret" in prep:
            continue      # early-exit path: message side effects done in A
        prepared.append((rc, prep))
    _tA = _perf()
    if not prepared:
        return
    bres = await asyncio.gather(
        *(rc._execute_tool(prep, session) for rc, prep in prepared),
        return_exceptions=True)
    _tB = _perf()
    for (rc, prep), br in zip(prepared, bres):
        # _execute_tool already renders tool errors as result strings; an
        # exception here is harness-level — render it the same way so the
        # finalization steps still run and the case continues instead of
        # taking the whole round down.
        if isinstance(br, BaseException):
            print(f"  ⚠ dispatch exception ({prep['tool']}): "
                  f"{type(br).__name__}: {br}", flush=True)
            br = json.dumps({"error": f"dispatch_{prep['tool']}: {br}"})
        rc._finalize(prep, br)
    _tC = _perf()
    from kgqa.core.utils import PHASE_TIMES
    PHASE_TIMES["rd_A"] = PHASE_TIMES.get("rd_A", 0.0) + (_tA - _t0)
    PHASE_TIMES["rd_B"] = PHASE_TIMES.get("rd_B", 0.0) + (_tB - _tA)
    PHASE_TIMES["rd_C"] = PHASE_TIMES.get("rd_C", 0.0) + (_tC - _tB)

