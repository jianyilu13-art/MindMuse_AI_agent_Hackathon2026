"""Routing decisions for the shopping graph — kept out of the nodes so the
control flow is readable in one place."""

from __future__ import annotations

from .state import AgentState


def after_understand(state: AgentState) -> str:
    """quit -> end; otherwise decide whether we still need details."""
    if state.get("finished"):
        return "end"
    if state.get("intent") == "chitchat":
        return "chitchat"
    reqs = state.get("requirements")
    if reqs is None or not (reqs.product_query or "").strip():
        return "chitchat"          # nothing to shop for yet — prompt the user
    return "ask"


def after_ask(state: AgentState) -> str:
    """If the LLM still wants a detail we wait for the user; else we search."""
    return "wait" if state.get("awaiting_input") else "search"


def after_search(state: AgentState) -> str:
    return "recommend"
