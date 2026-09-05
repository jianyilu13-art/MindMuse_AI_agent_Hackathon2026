"""LLM reasoning for the agent — the three jobs a rule engine can't do well.

  1. `interpret`      user turn -> intent + a *patch* of the requirements, so
                      "actually make it black" edits the existing request
                      instead of starting a new search.
  2. `next_question`  a category-aware follow-up (shoes -> size, laptop ->
                      RAM/screen), instead of one hard-coded question list.
  3. `screen`         semantic relevance check on search results, so brand,
                      colour and category mismatches are dropped.

Every function takes `llm=None` and falls back to a deterministic path, so the
app still runs (and tests stay offline) without a key.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from shopping_agent.llm.parsing import structured_output
from shopping_agent.schemas import Product, UserRequirements

# --------------------------------------------------------------------------
# 1. interpret a turn: intent + incremental patch
# --------------------------------------------------------------------------
INTENT_VALUES = ("new_search", "refine", "answer", "chitchat", "quit")


class RequirementPatch(BaseModel):
    """Only the fields the user actually mentioned this turn. Everything else
    stays as it was — this is what gives the agent conversational memory."""

    product_query: Optional[str] = None
    category: Optional[str] = None
    size: Optional[str] = None
    budget: Optional[float] = None
    preferences: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    # attributes the user explicitly dropped, e.g. "no colour preference"
    cleared_fields: list[str] = Field(default_factory=list)


class TurnInterpretation(BaseModel):
    intent: str = "new_search"
    patch: RequirementPatch = Field(default_factory=RequirementPatch)
    reply: str = ""


_INTERPRET_PROMPT = """The shopper said: "{message}"

Current request so far (JSON):
{current}

Decide:
- intent: one of new_search (a different product), refine (change/add a detail
  about the SAME product, e.g. "make it black", "raise budget to 200"),
  answer (answering the question we just asked), chitchat, quit.
- patch: ONLY the fields mentioned in this message. Leave everything else out —
  the rest of the request is remembered. Put concrete product attributes such as
  colour, material, storage, screen size in `attributes` (e.g. {{"color": "black"}}).
  List fields the shopper explicitly no longer cares about in `cleared_fields`.
- reply: one short, friendly sentence acknowledging what changed (no product
  recommendations here).

We just asked: "{last_question}"
"""


_COLOURS = ("black", "white", "red", "blue", "green", "grey", "gray", "pink",
            "silver", "gold", "beige", "navy", "purple", "yellow", "orange")


def _rule_interpret(message: str, current: Optional[UserRequirements]) -> TurnInterpretation:
    """Deterministic fallback: reuse the regex extractors from the UI's rule
    parser so the agent still fills requirements with no LLM configured."""
    from shopping_agent.ui.conversation import (
        _clean_product,
        _extract_budget,
        _extract_prefs,
        _extract_size,
        _is_skip,
    )

    low = (message or "").lower()
    if any(w in low for w in ("quit", "exit", "bye", "stop")):
        return TurnInterpretation(intent="quit")

    patch = RequirementPatch()
    budget = _extract_budget(message)
    if budget is not None:
        patch.budget = float(budget)
    size = _extract_size(message)
    if size:
        patch.size = size
    prefs = _extract_prefs(message)
    if prefs:
        patch.preferences = prefs
    colour = next((c for c in _COLOURS if c in low), None)
    if colour:
        patch.attributes = {"color": colour}

    refine_words = ("change", "instead", "actually", "make it", "rather",
                    "raise", "lower", "cheaper", "换", "改", "而是")
    is_refine = current is not None and any(w in low for w in refine_words)

    product = "" if _is_skip(message) else _clean_product(message)
    # only treat it as a new product when we don't already have one
    if product and (current is None or not (current.product_query or "").strip()):
        patch.product_query = product

    if is_refine:
        return TurnInterpretation(intent="refine", patch=patch)
    return TurnInterpretation(
        intent="new_search" if current is None else "answer", patch=patch
    )


def interpret(
    message: str,
    current: Optional[UserRequirements],
    last_question: str = "",
    llm: Any = None,
) -> TurnInterpretation:
    """Understand one user turn against the remembered request."""
    if llm is None:
        return _rule_interpret(message, current)
    prompt = _INTERPRET_PROMPT.format(
        message=message,
        current=current.model_dump_json(indent=2) if current else "{}",
        last_question=last_question or "(nothing yet)",
    )
    try:
        out = structured_output(llm, "interpret", prompt, TurnInterpretation)
        if out.intent not in INTENT_VALUES:
            out.intent = "new_search"
        return out
    except Exception:
        return _rule_interpret(message, current)


def apply_patch(current: Optional[UserRequirements], patch: RequirementPatch) -> UserRequirements:
    """Merge a patch onto the remembered requirements (the memory step).
    List fields extend without duplicates; attributes merge key-by-key."""
    from decimal import Decimal

    base = current.model_dump() if current else {"product_query": ""}

    for field in ("product_query", "category", "size"):
        value = getattr(patch, field)
        if value:
            base[field] = value
    if patch.budget is not None:
        base["budget"] = Decimal(str(patch.budget))

    for field in ("preferences", "preferred_brands", "must_have"):
        incoming = getattr(patch, field)
        if incoming:
            existing = list(base.get(field) or [])
            for item in incoming:
                if item and item.lower() not in [e.lower() for e in existing]:
                    existing.append(item)
            base[field] = existing

    if patch.attributes:
        merged = dict(base.get("attributes") or {})
        merged.update(patch.attributes)
        base["attributes"] = merged

    for field in patch.cleared_fields:
        if field in ("budget", "size", "category"):
            base[field] = None
        elif field in ("preferences", "preferred_brands", "must_have"):
            base[field] = []
        elif base.get("attributes") and field in base["attributes"]:
            base["attributes"] = {k: v for k, v in base["attributes"].items() if k != field}

    if not base.get("product_query"):
        base["product_query"] = (current.product_query if current else "") or ""
    return UserRequirements.model_validate(base)


# --------------------------------------------------------------------------
# 2. category-aware follow-up question
# --------------------------------------------------------------------------
class FollowUp(BaseModel):
    field: str = Field("", description="requirement field or attribute key to fill")
    question: str = Field("", description="one short question to ask the shopper")
    ready_to_search: bool = False


_QUESTION_PROMPT = """You are helping a shopper describe what they want.

Request so far (JSON):
{current}

Questions already asked: {asked}

If you have enough to search well (product plus at least a budget or a couple of
meaningful details), set ready_to_search=true and leave question empty.
Otherwise ask ONE short question for the single most useful missing detail for
THIS product category — e.g. size for shoes, RAM/screen size for laptops,
capacity for a kettle. Never re-ask something already asked. Name the field you
are filling (a UserRequirements field like budget/size, or an attribute key like
"ram", "color").
"""

_GENERIC_ORDER = [
    ("budget", "What's your budget in SGD? (or say 'skip')"),
    ("preferences", "Any preferences or features that matter? (or 'skip')"),
]


def next_question(
    current: UserRequirements, asked: list[str], llm: Any = None
) -> FollowUp:
    """Pick the next question to ask, tailored to the product category."""
    if llm is None:
        for field, question in _GENERIC_ORDER:
            if field in asked:
                continue
            if field == "budget" and current.budget is not None:
                continue
            if field == "preferences" and current.preferences:
                continue
            return FollowUp(field=field, question=question)
        return FollowUp(ready_to_search=True)

    prompt = _QUESTION_PROMPT.format(
        current=current.model_dump_json(indent=2), asked=", ".join(asked) or "(none)"
    )
    try:
        out = structured_output(llm, "next_question", prompt, FollowUp)
        if not out.ready_to_search and not out.question.strip():
            out.ready_to_search = True
        if out.field and out.field in asked:  # never repeat a question
            return FollowUp(ready_to_search=True)
        return out
    except Exception:
        return next_question(current, asked, llm=None)


# --------------------------------------------------------------------------
# 3. semantic screening of search results
# --------------------------------------------------------------------------
class ScreenResult(BaseModel):
    keep_ids: list[str] = Field(default_factory=list)


_SCREEN_PROMPT = """The shopper wants:
{current}

Candidate products (id · title · seller · price):
{candidates}

Return keep_ids: the ids that genuinely match the request. Drop items that are
the wrong category (accessories, cases, spare parts when a device was asked
for), the wrong brand when brands were specified, or that contradict a stated
attribute such as colour or size. Keep anything you are unsure about.
"""


def _rule_screen(products: list[Product], reqs: UserRequirements) -> list[Product]:
    """Deterministic screening: brand match, stated attribute match, and a
    loose category-relevance check against the query words."""
    def text(p: Product) -> str:
        return f"{p.title} {' '.join(str(v) for v in p.attributes.values())}".lower()

    kept = []
    query_words = [w for w in (reqs.product_query or "").lower().split() if len(w) > 2]
    for p in products:
        blob = text(p)
        if reqs.preferred_brands:
            if not any(b.lower() in blob for b in reqs.preferred_brands):
                continue
        # stated attributes (colour, material, …) must not be contradicted
        ok = True
        for key, value in (reqs.attributes or {}).items():
            if key in (reqs.no_preference_fields or []):
                continue
            if isinstance(value, str) and value and value.lower() not in blob:
                ok = False
                break
        if not ok:
            continue
        # loose relevance: at least one meaningful query word appears
        if query_words and not any(w in blob for w in query_words):
            continue
        kept.append(p)
    return kept or products  # never screen everything away


def screen(
    products: list[Product], reqs: UserRequirements, llm: Any = None, limit: int = 20
) -> list[Product]:
    """Drop results that don't genuinely match the request."""
    if not products:
        return products
    rule_kept = _rule_screen(products, reqs)
    if llm is None:
        return rule_kept

    subset = rule_kept[:limit]
    listing = "\n".join(
        f"{p.id} · {p.title[:90]} · {p.platform} · {p.currency} {p.price}" for p in subset
    )
    prompt = _SCREEN_PROMPT.format(
        current=reqs.model_dump_json(indent=2), candidates=listing
    )
    try:
        out = structured_output(llm, "screen", prompt, ScreenResult)
        keep = {i for i in out.keep_ids}
        filtered = [p for p in subset if p.id in keep]
        return filtered or rule_kept
    except Exception:
        return rule_kept
