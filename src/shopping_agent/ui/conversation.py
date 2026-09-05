"""Conversational requirement gathering for the Muse UI.

A small, rule-based dialogue manager (no LLM, no langgraph) that collects a
UserRequirements over several turns — product, size (for wearables), budget,
preferences — then runs the *real* integration pipeline and holds the result.

It works on the unified contract, so it drops straight onto the integration
branch without dragging in a second schema/agent. A real LLM planner could
replace `handle_message` later; the pipeline call stays the same.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from shopping_agent.pipeline import run_shopping
from shopping_agent.schemas import CustomerResponse, UserRequirements, Weights

GREETING = (
    "Hi! I'm Muse, your shopping assistant. What are you looking to buy today?"
)

# soft-preference vocabulary we can recognise inline (keeps the chat feeling smart)
_KNOWN_PREFS = [
    "cushioned", "lightweight", "breathable", "waterproof", "wireless", "wired",
    "noise cancelling", "noise-cancelling", "long battery", "fast charging",
    "compact", "durable", "premium", "gaming", "mechanical", "ergonomic",
    "stainless", "organic", "slim", "quiet",
]
_SIZE_CATEGORIES = ("shoe", "shoes", "sneaker", "boot", "trainer", "runner",
                    "shirt", "dress", "jacket", "jeans", "clothing", "apparel")
_FILLER = re.compile(
    r"\b(i\s*(?:want|need|am\s*looking\s*for|'?m\s*looking\s*for)|looking\s*for|"
    r"find(?:\s*me)?|buy|get\s*me|please|some|a|an|the)\b",
    re.I,
)
_SKIP = {"skip", "none", "no", "no thanks", "any", "anything", "n/a", "-", "no preference"}
_QUIT = {"quit", "exit", "bye", "stop"}


@dataclass
class ChatSession:
    messages: list[dict[str, str]] = field(
        default_factory=lambda: [{"role": "assistant", "content": GREETING}]
    )
    stage: str = "need_product"
    product_query: Optional[str] = None
    size: Optional[str] = None
    budget: Optional[Decimal] = None
    deadline: Optional[date] = None
    prefs: list[str] = field(default_factory=list)
    asked: set[str] = field(default_factory=set)
    response: Optional[CustomerResponse] = None
    done: bool = False


# --------------------------------------------------------------------------
# parsing helpers
# --------------------------------------------------------------------------
def _extract_budget(text: str) -> Optional[Decimal]:
    m = re.search(r"(?:under|below|budget(?:\s*of)?|max|<|\$|s\$)\s*\$?\s*(\d+(?:\.\d+)?)", text, re.I)
    if not m:
        m = re.fullmatch(r"\s*\$?\s*(\d+(?:\.\d+)?)\s*", text)  # a bare number reply
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def _extract_deadline(text: str) -> Optional[date]:
    from datetime import timedelta

    low = text.lower()
    today = date.today()
    if "tomorrow" in low:
        return today + timedelta(days=1)
    m = re.search(r"in\s+(\d+)\s+days?", low)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", low)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def _extract_size(text: str) -> Optional[str]:
    m = re.search(r"\b(?:size\s*)?((?:eu|uk|us)\s*\d{1,2}(?:\.\d)?)\b", text, re.I)
    if m:
        return m.group(1).upper().replace("  ", " ")
    m = re.search(r"\bsize\s+([a-z0-9.]+)\b", text, re.I)
    return m.group(1) if m else None


def _extract_prefs(text: str) -> list[str]:
    found = [p for p in _KNOWN_PREFS if p in text.lower()]
    # de-dupe hyphen/space variants
    norm = []
    for p in found:
        key = p.replace("-", " ")
        if key not in norm:
            norm.append(key)
    return norm


def _split_prefs(text: str) -> list[str]:
    parts = re.split(r"[,/]| and ", text)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in _SKIP]


def _needs_size(product_query: str) -> bool:
    return any(w in product_query.lower() for w in _SIZE_CATEGORIES)


def _clean_product(text: str) -> str:
    """Strip budget/size/filler so the product query is just the product."""
    t = re.sub(r"(?:under|below|budget(?:\s*of)?|max|<)\s*\$?\s*\d+(?:\.\d+)?", " ", text, flags=re.I)
    t = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", t)
    t = re.sub(r"\b(?:size\s*)?(?:eu|uk|us)\s*\d{1,2}(?:\.\d)?\b", " ", t, flags=re.I)
    t = re.sub(r"\bsize\s+[a-z0-9.]+\b", " ", t, flags=re.I)
    for p in _KNOWN_PREFS:
        t = re.sub(rf"\b{re.escape(p)}\b", " ", t, flags=re.I)
    t = _FILLER.sub(" ", t)
    t = re.sub(r"\bin\s+\d+\s+days?\b|\btomorrow\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.-")


def _is_skip(text: str) -> bool:
    return text.strip().lower() in _SKIP


def is_quit(text: str) -> bool:
    return text.strip().lower() in _QUIT


# --------------------------------------------------------------------------
# dialogue
# --------------------------------------------------------------------------
def _say(session: ChatSession, content: str) -> None:
    session.messages.append({"role": "assistant", "content": content})


def _run_pipeline(session: ChatSession) -> None:
    reqs = UserRequirements(
        product_query=session.product_query or "",
        size=session.size,
        budget=session.budget,
        deadline=session.deadline,
        preferences=session.prefs,
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
        max_results=3,
    )
    session.response = run_shopping(reqs, session_id="chat")
    session.stage = "results"
    n = len(session.response.cards)
    if n:
        _say(session, f"Here are my top {n} picks for you — see the cards below. "
                      "Tell me a new product or say 'quit' to finish.")
    else:
        _say(session, session.response.headline + " Want to relax the budget or try another product?")


def _advance(session: ChatSession) -> None:
    """Ask for the next missing slot, or run the pipeline when ready."""
    if not session.product_query:
        session.stage = "need_product"
        _say(session, "Sure — what product or category are you shopping for?")
        return
    if _needs_size(session.product_query) and not session.size and "size" not in session.asked:
        session.asked.add("size")
        session.stage = "need_size"
        _say(session, "Got it. What size do you need? (or say 'skip')")
        return
    if session.budget is None and "budget" not in session.asked:
        session.asked.add("budget")
        session.stage = "need_budget"
        _say(session, "What's your budget in SGD? (or say 'skip')")
        return
    if not session.prefs and "prefs" not in session.asked:
        session.asked.add("prefs")
        session.stage = "need_prefs"
        _say(session, "Any preferences? e.g. cushioned, lightweight (or 'skip')")
        return
    _run_pipeline(session)


def _absorb(session: ChatSession, text: str) -> None:
    """Pull any budget/size/deadline/preferences stated inline into the session."""
    b = _extract_budget(text)
    if b is not None:
        session.budget = b
        session.asked.add("budget")
    d = _extract_deadline(text)
    if d is not None:
        session.deadline = d
    s = _extract_size(text)
    if s is not None:
        session.size = s
        session.asked.add("size")
    inline_prefs = _extract_prefs(text)
    if inline_prefs:
        for p in inline_prefs:
            if p not in session.prefs:
                session.prefs.append(p)
        session.asked.add("prefs")


def handle_message(session: ChatSession, text: str) -> None:
    """Advance the conversation by one user turn (mutates the session)."""
    text = (text or "").strip()
    if not text:
        return
    session.messages.append({"role": "user", "content": text})

    if is_quit(text):
        session.done = True
        _say(session, "Thanks for shopping with Muse! Nothing was ordered — come back anytime.")
        return

    stage = session.stage
    if stage in ("need_product", "results"):
        # a fresh product turn (initial or a new search after results)
        if stage == "results":
            session.response = None  # starting a new search
        _absorb(session, text)
        product = _clean_product(text)
        if product:
            session.product_query = product
    elif stage == "need_size":
        if not _is_skip(text):
            session.size = _extract_size(text) or text.strip()
        _absorb(session, text)
    elif stage == "need_budget":
        if not _is_skip(text):
            b = _extract_budget(text)
            if b is not None:
                session.budget = b
    elif stage == "need_prefs":
        if not _is_skip(text):
            session.prefs = _split_prefs(text) or _extract_prefs(text)

    _advance(session)
