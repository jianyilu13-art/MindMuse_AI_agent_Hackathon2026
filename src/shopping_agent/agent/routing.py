"""Pure routing decisions driven solely by the latest shared state."""

from typing import Literal

from .state import ShoppingState

NextAction = Literal[
    "interpret_user_input", "extract_requirements", "ask_clarification", "search_products",
    "fetch_reviews", "rank_products", "display_results", "add_to_cart", "terminate", "end",
]


def next_action(state: ShoppingState) -> NextAction:
    """Select exactly one next operation; this never creates a full plan."""
    if state["last_user_message"].strip():
        return "interpret_user_input"
    if state["finished"]:
        return "end"
    if state["user_intent"] == "finish":
        return "terminate"
    if state["awaiting_user_input"]:
        return "end"
    if state["user_intent"] == "purchase":
        return "add_to_cart"
    if state["pending_requirement_text"] is not None:
        return "extract_requirements"
    requirements = state["requirements"]
    if requirements is None or requirements.missing_fields:
        return "ask_clarification"
    if state["search_required"] or not state["search_completed"]:
        return "search_products"
    if not state["qualified_products"]:
        return "ask_clarification"
    if not state["reviews_attempted"]:
        return "fetch_reviews"
    if not state["ranked_products"]:
        return "rank_products"
    if not state["displayed"]:
        return "display_results"
    return "end"
