"""Pure routing decisions driven by structured shopping state."""

from typing import Literal

from .state import ShoppingState


NextAction = Literal[
    "interpret_user_input",
    "extract_requirements",
    "ask_clarification",
    "search_products",
    "fetch_reviews",
    "rank_products",
    "display_results",
    "add_to_cart",
    "terminate",
    "end",
]


def next_action(state: ShoppingState) -> NextAction:
    """Return the next graph operation without mutating state."""

    if state["finished"]:
        return "end"

    if state["input_status"] == "uninterpreted":
        return "interpret_user_input"

    if state["awaiting_user_input"]:
        return "end"

    if state["user_intent"] == "finish":
        return "terminate"

    if state["purchase_status"] == "requested":
        return "add_to_cart"

    if state["pending_requirement_text"] is not None:
        return "extract_requirements"

    if state["requirement_status"] != "ready":
        return "ask_clarification"

    if state["missing_dynamic_attributes"]:
        return "ask_clarification"

    if state["search_required"]:
        return "search_products"

    if state["search_result_status"] == "no_results":
        return "ask_clarification"

    if state["review_status"] == "pending":
        return "fetch_reviews"

    if state["ranking_status"] == "pending":
        return "rank_products"

    if state["presentation_status"] == "ready":
        return "display_results"

    return "end"