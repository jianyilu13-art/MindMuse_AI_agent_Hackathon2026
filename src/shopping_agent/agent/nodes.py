"""Small state-transition operations. Routing belongs in routing.py."""

from __future__ import annotations

from dataclasses import dataclass

from shopping_agent.llm.parsing import RuleBasedShoppingSemantics, ShoppingSemantics
from shopping_agent.processing import apply_hard_constraints, deduplicate_products, rank_products
from shopping_agent.tools import AddToCartTool, MockAddToCartTool, MockProductSearchTool, MockReviewTool, ProductSearchTool, ReviewTool

from .state import ShoppingState


@dataclass(frozen=True)
class ShoppingServices:
    search: ProductSearchTool
    reviews: ReviewTool
    cart: AddToCartTool
    semantics: ShoppingSemantics

    @classmethod
    def mock(cls) -> "ShoppingServices":
        return cls(MockProductSearchTool(), MockReviewTool(), MockAddToCartTool(), RuleBasedShoppingSemantics())


class ShoppingNodes:
    def __init__(self, services: ShoppingServices) -> None:
        self.services = services

    def interpret_user_input(self, state: ShoppingState) -> dict:
        message = state["last_user_message"]
        decision = self.services.semantics.classify(message, state["raw_products"])
        update: dict = {"last_user_message": "", "user_intent": decision.intent, "selected_product_id": decision.selected_product_id}
        if decision.intent in ("search", "change_requirements"):
            update.update({"pending_requirement_text": message, "awaiting_user_input": False, "assistant_message": None})
        elif decision.intent == "more_results":
            update.update({"displayed": False, "awaiting_user_input": False, "assistant_message": None})
        return update

    def extract_requirements(self, state: ShoppingState) -> dict:
        requirements = self.services.semantics.extract_requirements(state["pending_requirement_text"] or "", state["requirements"])
        return {
            "requirements": requirements, "pending_requirement_text": None, "search_required": True,
            "search_completed": False, "raw_products": [], "qualified_products": [], "reviews": {},
            "reviews_attempted": False, "review_error": None, "ranked_products": [], "display_offset": 0,
            "displayed": False, "user_intent": "none",
        }

    def ask_clarification(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        if requirements is None or requirements.missing_fields:
            missing = requirements.missing_fields if requirements else ["product or category"]
            message = _clarification_for(missing[0])
        else:
            message = "No products meet your hard constraints. Would you like to raise your budget, change the delivery deadline, or relax a required feature?"
        return {"assistant_message": message, "awaiting_user_input": True, "user_intent": "clarify"}

    def search_products(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        assert requirements is not None
        raw_products = deduplicate_products(self.services.search.search(requirements))
        qualified = apply_hard_constraints(raw_products, requirements)
        return {"raw_products": raw_products, "qualified_products": qualified, "search_required": False,
                "search_completed": True, "reviews_attempted": False, "ranked_products": [], "displayed": False}

    def fetch_reviews(self, state: ShoppingState) -> dict:
        try:
            reviews = self.services.reviews.fetch(state["qualified_products"])
            return {"reviews": reviews, "reviews_attempted": True, "review_error": None}
        except Exception as error:  # A review outage is non-fatal by design.
            return {"reviews": {}, "reviews_attempted": True, "review_error": str(error)}

    def rank_products(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        assert requirements is not None
        return {"ranked_products": rank_products(state["qualified_products"], requirements, state["reviews"])}

    def display_results(self, state: ShoppingState) -> dict:
        start, size = state["display_offset"], state["page_size"]
        page = state["ranked_products"][start : start + size]
        if not page:
            message = "There are no more matching products. You can change your requirements or finish."
        else:
            lines = [f"{item.product.id}: {item.product.title} — {item.product.currency} {item.product.price:.2f}" for item in page]
            message = "\n".join(lines) + "\nReply 'more', change your requirements, or name a product to purchase."
        return {"assistant_message": message, "display_offset": start + len(page), "displayed": True, "awaiting_user_input": True, "user_intent": "none"}

    def add_to_cart(self, state: ShoppingState) -> dict:
        selected_id = state["selected_product_id"]
        selected = next((item.product for item in state["ranked_products"] if item.product.id == selected_id), None)
        selected = selected or (state["ranked_products"][0].product if state["ranked_products"] else None)
        if selected is None:
            return {"assistant_message": "Please search for products before adding one to the cart.", "awaiting_user_input": True, "user_intent": "none"}
        result = self.services.cart.add(selected)
        return {"cart_result": result, "assistant_message": result.message, "awaiting_user_input": True, "user_intent": "none"}

    def terminate(self, state: ShoppingState) -> dict:
        return {"finished": True, "assistant_message": "Thanks for shopping with me!", "awaiting_user_input": False}


def _clarification_for(missing_field: str) -> str:
    """Ask for one concrete missing field so the shopper can answer easily."""
    questions = {
        "product or category": "What product or category would you like to shop for?",
        "maximum budget": "What's your maximum budget?",
        "required features or preferred brands": "Any required features or preferred brands?",
    }
    return questions[missing_field]
