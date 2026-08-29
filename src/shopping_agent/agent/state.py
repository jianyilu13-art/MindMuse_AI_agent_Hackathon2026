"""The complete observable state used by the reactive router."""

from __future__ import annotations

from typing import Literal, TypedDict

from shopping_agent.schemas import Product, RankedProduct, ReviewSummary, UserRequirements
from shopping_agent.tools.add_to_cart import CartResult


UserIntent = Literal["search", "change_requirements", "more_results", "purchase", "finish", "clarify", "none"]


class ShoppingState(TypedDict):
    # Conversation/input
    last_user_message: str
    pending_requirement_text: str | None
    user_intent: UserIntent
    awaiting_user_input: bool
    finished: bool

    # Requirements and product observations
    requirements: UserRequirements | None
    search_required: bool
    search_completed: bool
    raw_products: list[Product]
    qualified_products: list[Product]
    reviews: dict[str, ReviewSummary]
    reviews_attempted: bool
    review_error: str | None
    ranked_products: list[RankedProduct]

    # Presentation/action observations
    display_offset: int
    page_size: int
    displayed: bool
    selected_product_id: str | None
    cart_result: CartResult | None
    assistant_message: str | None
    last_error: str | None


def initial_state(message: str = "") -> ShoppingState:
    """Create a serializable state that can be resumed with a new message."""
    return {
        "last_user_message": message,
        "pending_requirement_text": None,
        "user_intent": "none",
        "awaiting_user_input": False,
        "finished": False,
        "requirements": None,
        "search_required": False,
        "search_completed": False,
        "raw_products": [],
        "qualified_products": [],
        "reviews": {},
        "reviews_attempted": False,
        "review_error": None,
        "ranked_products": [],
        "display_offset": 0,
        "page_size": 3,
        "displayed": False,
        "selected_product_id": None,
        "cart_result": None,
        "assistant_message": None,
        "last_error": None,
    }
