"""Pydantic tool schemas for SEQ — formal parameter definitions with type-level
validation. When the model's JSON doesn't match the schema, specific field-level
errors are reported (not generic 'parse failure'), guiding the model to fix the
exact field.

These models also serve as the canonical documentation of each tool's interface
(the prompt can reference them directly)."""
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from pydantic import BaseModel, Field, field_validator, ValidationError


# ── Tool argument schemas ──────────────────────────────────────────────────

class Subgraph(BaseModel):
    """One subgraph in the plan: anchored by a named entity, with ordered facts."""
    id: str = ""
    anchor: str = ""
    facts: List[List[str]] = Field(default_factory=list,
        description="each fact: [head, sub-question, tail]")


class PlanArgs(BaseModel):
    """Arguments for the `plan` tool (declares the retrieval plan)."""
    subgraphs: List[Subgraph] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list,
        description="every named entity from the question")
    answer: str = Field(default="",
        description="the answer ?variable, e.g. '?answer'")
    answer_type: str = Field(default="",
        description="ONE word for what the question asks for (person, movie, country, "
                    "language, year, number, ...) — derived from the question's "
                    "interrogative; the answer entities must be of this type")

    @field_validator("answer")
    @classmethod
    def answer_must_be_variable(cls, v: str) -> str:
        if v and not v.strip().startswith("?"):
            raise ValueError(f"must be a ?variable (e.g. '?answer'), got '{v}'")
        return v.strip()


class RetrieveRelationsArgs(BaseModel):
    """Arguments for `retrieve_relations`."""
    center: List[str] = Field(default_factory=list,
        description="['?variable'] for non-initial facts, or ['named entity'] for fact 1")
    question: str = Field(default="",
        description="the fact's sub-question, verbatim from the plan")


class RetrieveSubgraphArgs(BaseModel):
    """Arguments for `retrieve_subgraph`."""
    center: List[str] = Field(default_factory=list,
        description="['?variable'] or ['named entity']")
    relations: List[str] = Field(default_factory=list,
        description="selected structural relations from retrieve_relations")
    sg: Optional[str] = Field(default=None,
        description="subgraph id, e.g. 'sg1'")


class AnswerArgs(BaseModel):
    """Arguments for `answer`."""
    entities: List[str] = Field(default_factory=list,
        description="answer entity names from the retrieved evidence")


# ── Schema registry ────────────────────────────────────────────────────────

SCHEMAS: Dict[str, type[BaseModel]] = {
    "plan":              PlanArgs,
    "decompose":         PlanArgs,          # backward-compat
    "retrieve_relations": RetrieveRelationsArgs,
    "retrieve_subgraph":  RetrieveSubgraphArgs,
    "answer":            AnswerArgs,
}

# backward-compat param-name mapping (old → new), applied before validation
PARAM_MAP: Dict[str, Dict[str, str]] = {
    "retrieve_relations": {"entities": "center", "entity": "center"},
    "retrieve_subgraph":  {"entities": "center", "entity": "center",
                           "fact_id": "sg", "step": "sg"},
}


def validate_args(tool_name: str, args: Dict[str, Any]) -> Tuple[Optional[dict], Optional[str]]:
    """Validate args against the tool's Pydantic schema.

    Returns ``(validated_args, error_msg)``:
      * On success: validated_args is the normalized dict (new param names, defaults
        filled); error_msg is None.
      * On failure: validated_args is None; error_msg is a specific, actionable
        message naming the exact field and what's wrong.

    Also applies backward-compat param-name mapping (entities→center, fact_id→sg)
    so old-style args still validate.
    """
    model = SCHEMAS.get(tool_name)
    if not model:
        return args, None  # unknown tool — skip validation, let dispatch handle

    # apply backward-compat param mapping
    mapping = PARAM_MAP.get(tool_name, {})
    mapped: Dict[str, Any] = {}
    for k, v in args.items():
        mapped[mapping.get(k, k)] = v

    # COERCE before rejecting (V21 audit: 33 schema rejections were scalars
    # where lists are expected — JSON/hybrid turns land here as bare strings;
    # the flat parser's pipe-lists already coerce. Coerce str→[str].)
    for lf in ("entities", "center", "relations"):
        if lf in mapped and isinstance(mapped[lf], str):
            mapped[lf] = [mapped[lf]]

    try:
        validated = model(**mapped)
        return validated.model_dump(exclude_none=True), None
    except ValidationError as e:
        parts = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            msg = err["msg"]
            # Pydantic 2 prefixes "Value error, " — strip for readability
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            parts.append(f"`{loc}`: {msg}")
        return None, (f"Tool `{tool_name}` schema error — {'; '.join(parts)}. "
                      f"Fix the flagged field(s) and re-emit ONE `tool:` line.")
    except Exception as e:
        return None, f"Tool `{tool_name}` args error: {str(e)[:200]}"


# ── Prompt-facing schema documentation ─────────────────────────────────────

SCHEMA_DOC = """
## Tool parameter schemas (formal)

```
plan:
  subgraphs:  list of {id: str, anchor: str, facts: list of [head:str, sub-question:str, tail:str]}
  entities:   list of str  — every named entity from the question
  answer:     str           — a ?variable (e.g. "?answer")

retrieve_relations:
  center:     list of str   — ["?variable"] or ["named entity"] (fact 1 only)
  question:   str           — the fact's sub-question verbatim

retrieve_subgraph:
  center:     list of str   — ["?variable"] or ["named entity"]
  relations:  list of str   — selected relations from retrieve_relations
  sg:         str (optional)— subgraph id, e.g. "sg1"

answer:
  entities:   list of str   — answer entity names from the evidence
```

Each field is validated: missing required fields, wrong types, and invalid values
are reported with the specific field name and what's expected.
"""
