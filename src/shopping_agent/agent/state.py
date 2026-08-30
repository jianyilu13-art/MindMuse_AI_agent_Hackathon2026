"""The complete observable state used by the reactive router."""

from __future__ import annotations

from typing import Literal, TypedDict

from shopping_agent.schemas import Product, RankedProduct, ReviewSummary, UserRequirements
from shopping_agent.tools.add_to_cart import CartResult


UserIntent = Literal["search", "change_requirements", "more_results", "purchase", "finish", "clarify", "none"]
InputStatus = Literal["uninterpreted", "interpreted"]
RequirementStatus = Literal["unknown", "incomplete", "ready"]
SearchResultStatus = Literal["not_searched", "results", "no_results"]
ReviewStatus = Literal["not_needed", "pending", "completed", "failed"]
RankingStatus = Literal["not_needed", "pending", "completed"]
PresentationStatus = Literal["not_ready", "ready", "displayed", "exhausted"]
PurchaseStatus = Literal["none", "requested", "completed", "failed"]


class ShoppingState(TypedDict):
    # The router uses input_status, never raw message contents.
    last_user_message: str
    input_status: InputStatus
    pending_requirement_text: str | None
    user_intent: UserIntent
    awaiting_user_input: bool
    finished: bool

    # LLM-owned requirement interpretation.
    requirements: UserRequirements | None
    requirement_status: RequirementStatus
    missing_required_information: list[str]
    optional_preferences: list[str]
    clarification_context: str | None

    # Search and enrichment lifecycle.
    search_required: bool
    search_completed: bool
    search_result_status: SearchResultStatus
    raw_products: list[Product]
    qualified_products: list[Product]
    reviews: dict[str, ReviewSummary]
    review_status: ReviewStatus
    review_error: str | None
    ranking_status: RankingStatus
    ranked_products: list[RankedProduct]

    # Presentation/action observations
    display_offset: int
    page_size: int
    presentation_status: PresentationStatus
    selected_product_id: str | None
    purchase_status: PurchaseStatus
    cart_result: CartResult | None
    assistant_message: str | None
    last_error: str | None


def initial_state(message: str = "") -> ShoppingState:
    """Create a serializable state that can be resumed with a new message."""
    return {
        "last_user_message": message,
        "input_status": "uninterpreted" if message else "interpreted",
        "pending_requirement_text": None,
        "user_intent": "none",
        "awaiting_user_input": False,
        "finished": False,
        "requirements": None,
        "requirement_status": "unknown",
        "missing_required_information": [],
        "optional_preferences": [],
        "clarification_context": None,
        "search_required": False,
        "search_completed": False,
        "search_result_status": "not_searched",
        "raw_products": [],
        "qualified_products": [],
        "reviews": {},
        "review_status": "not_needed",
        "review_error": None,
        "ranking_status": "not_needed",
        "ranked_products": [],
        "display_offset": 0,
        "page_size": 3,
        "presentation_status": "not_ready",
        "selected_product_id": None,
        "purchase_status": "none",
        "cart_result": None,
        "assistant_message": None,
        "last_error": None,
    }
