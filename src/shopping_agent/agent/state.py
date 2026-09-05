"""Complete observable state used by the reactive shopping router."""

from __future__ import annotations

from typing import Literal, TypedDict

from shopping_agent.schemas import (
    Product,
    ProductAttributeProposal,
    RankedProduct,
    ReviewSummary,
    ShoppingToolInput,
    UserRequirements,
)
from shopping_agent.tools.add_to_cart import CartResult


UserIntent = Literal[
    "search",
    "change_requirements",
    "more_results",
    "purchase",
    "finish",
    "clarify",
    "none",
]

InputStatus = Literal["uninterpreted", "interpreted"]
RequirementStatus = Literal["unknown", "incomplete", "ready"]
SearchResultStatus = Literal["not_searched", "results", "no_results"]
ReviewStatus = Literal["not_needed", "pending", "completed", "failed"]
RankingStatus = Literal["not_needed", "pending", "completed"]
PresentationStatus = Literal[
    "not_ready",
    "ready",
    "displayed",
    "exhausted",
]
PurchaseStatus = Literal["none", "requested", "completed", "failed"]


class ShoppingState(TypedDict):
    """State shared by every node in the shopping graph."""

    # Current conversation turn.
    last_user_message: str
    input_status: InputStatus
    pending_requirement_text: str | None
    user_intent: UserIntent
    awaiting_user_input: bool
    finished: bool

    # Dynamic product understanding.
    product_category: str | None
    suggested_attributes: list[ProductAttributeProposal]
    missing_dynamic_attributes: list[str]

    # LLM-owned requirement interpretation.
    requirements: UserRequirements | None
    requirement_status: RequirementStatus
    missing_required_information: list[str]
    optional_preferences: list[str]
    clarification_context: str | None

    # Search lifecycle.
    search_required: bool
    search_completed: bool
    search_result_status: SearchResultStatus
    search_tool_input: ShoppingToolInput | None
    raw_products: list[Product]
    qualified_products: list[Product]

    # Review and ranking lifecycle.
    reviews: dict[str, ReviewSummary]
    review_status: ReviewStatus
    review_error: str | None
    ranking_status: RankingStatus
    ranked_products: list[RankedProduct]

    # Presentation and action state.
    display_offset: int
    page_size: int
    visible_products: list[Product]
    presentation_status: PresentationStatus
    selected_product_id: str | None
    purchase_status: PurchaseStatus
    cart_result: CartResult | None

    # Output and error state.
    assistant_message: str | None
    last_error: str | None


def initial_state(message: str = "") -> ShoppingState:
    """Create a serializable state that can resume on the next user turn."""

    return {
        "last_user_message": message,
        "input_status": "uninterpreted" if message else "interpreted",
        "pending_requirement_text": None,
        "user_intent": "none",
        "awaiting_user_input": False,
        "finished": False,
        "product_category": None,
        "suggested_attributes": [],
        "missing_dynamic_attributes": [],
        "requirements": None,
        "requirement_status": "unknown",
        "missing_required_information": [],
        "optional_preferences": [],
        "clarification_context": None,
        "search_required": False,
        "search_completed": False,
        "search_result_status": "not_searched",
        "search_tool_input": None,
        "raw_products": [],
        "qualified_products": [],
        "reviews": {},
        "review_status": "not_needed",
        "review_error": None,
        "ranking_status": "not_needed",
        "ranked_products": [],
        "display_offset": 0,
        "page_size": 3,
        "visible_products": [],
        "presentation_status": "not_ready",
        "selected_product_id": None,
        "purchase_status": "none",
        "cart_result": None,
        "assistant_message": None,
        "last_error": None,
    }
