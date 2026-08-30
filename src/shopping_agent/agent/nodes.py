"""Small state-transition operations. Routing belongs in routing.py."""

from __future__ import annotations

from dataclasses import dataclass

from shopping_agent.llm.model import GroqModel
from shopping_agent.llm.parsing import GroqShoppingSemantics, ShoppingSemantics
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
    def mock(cls, semantics: ShoppingSemantics | None = None) -> "ShoppingServices":
        """Mock external commerce tools while retaining LLM-based interpretation."""
        return cls(MockProductSearchTool(), MockReviewTool(), MockAddToCartTool(), semantics or GroqShoppingSemantics(GroqModel()))


class ShoppingNodes:
    def __init__(self, services: ShoppingServices) -> None:
        self.services = services

    def interpret_user_input(self, state: ShoppingState) -> dict:
        message = state["last_user_message"]
        decision = self.services.semantics.interpret_input(message, state["requirements"], state["raw_products"])
        update: dict = {
            "last_user_message": "", "input_status": "interpreted", "user_intent": decision.intent,
            "selected_product_id": decision.selected_product_id, "purchase_status": "requested" if decision.intent == "purchase" else state["purchase_status"],
        }
        if decision.should_extract_requirements:
            update.update({"pending_requirement_text": message, "awaiting_user_input": False, "assistant_message": None})
        elif decision.intent == "more_results":
            update.update({"presentation_status": "ready", "awaiting_user_input": False, "assistant_message": None, "user_intent": "none"})
        return update

    def extract_requirements(self, state: ShoppingState) -> dict:
        extracted = self.services.semantics.extract_requirements(state["pending_requirement_text"] or "", state["requirements"])
        requirements = extracted.requirements
        return {
            "requirements": requirements, "pending_requirement_text": None,
            "requirement_status": "ready" if extracted.assessment.sufficient_for_search else "incomplete",
            "missing_required_information": extracted.assessment.missing_required_information,
            "optional_preferences": extracted.assessment.optional_preferences,
            "clarification_context": extracted.assessment.clarification_context,
            "search_required": extracted.assessment.sufficient_for_search,
            "search_completed": False, "search_result_status": "not_searched", "raw_products": [], "qualified_products": [], "reviews": {},
            "review_status": "not_needed", "review_error": None, "ranking_status": "not_needed", "ranked_products": [], "display_offset": 0,
            "presentation_status": "not_ready", "purchase_status": "none", "user_intent": "none",
        }

    def ask_clarification(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        if state["search_completed"] and not state["qualified_products"]:
            missing = ["a requirement to relax or change"]
            context = "The completed search returned no products matching the current requirements."
        else:
            missing = state["missing_required_information"]
            context = state["clarification_context"]
        from shopping_agent.schemas import RequirementAssessment
        message = self.services.semantics.write_clarification(RequirementAssessment(
            sufficient_for_search=False, missing_required_information=missing,
            optional_preferences=state["optional_preferences"], clarification_context=context,
        ), requirements)
        return {"assistant_message": message, "awaiting_user_input": True, "user_intent": "clarify"}

    def search_products(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        assert requirements is not None
        raw_products = deduplicate_products(self.services.search.search(requirements))
        qualified = apply_hard_constraints(raw_products, requirements)
        return {"raw_products": raw_products, "qualified_products": qualified, "search_required": False,
                "search_completed": True, "search_result_status": "results" if qualified else "no_results", "review_status": "pending" if qualified else "not_needed",
                "ranking_status": "not_needed", "ranked_products": [], "presentation_status": "not_ready"}

    def fetch_reviews(self, state: ShoppingState) -> dict:
        try:
            reviews = self.services.reviews.fetch(state["qualified_products"])
            return {"reviews": reviews, "review_status": "completed", "review_error": None, "ranking_status": "pending"}
        except Exception as error:  # A review outage is non-fatal by design.
            return {"reviews": {}, "review_status": "failed", "review_error": str(error), "ranking_status": "pending"}

    def rank_products(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        assert requirements is not None
        return {"ranked_products": rank_products(state["qualified_products"], requirements, state["reviews"]), "ranking_status": "completed", "presentation_status": "ready"}

    def display_results(self, state: ShoppingState) -> dict:
        start, size = state["display_offset"], state["page_size"]
        page = state["ranked_products"][start : start + size]
        if not page:
            message = "There are no more matching products. You can change your requirements or finish."
        else:
            lines = [f"{item.product.id}: {item.product.title} — {item.product.currency} {item.product.price:.2f}" for item in page]
            message = "\n".join(lines) + "\nReply 'more', change your requirements, or name a product to purchase."
        return {"assistant_message": message, "display_offset": start + len(page), "presentation_status": "displayed" if page else "exhausted", "awaiting_user_input": True, "user_intent": "none"}

    def add_to_cart(self, state: ShoppingState) -> dict:
        selected_id = state["selected_product_id"]
        selected = next((item.product for item in state["ranked_products"] if item.product.id == selected_id), None)
        selected = selected or (state["ranked_products"][0].product if state["ranked_products"] else None)
        if selected is None:
            return {"assistant_message": "Please search for products before adding one to the cart.", "awaiting_user_input": True, "purchase_status": "failed", "user_intent": "none"}
        result = self.services.cart.add(selected)
        return {"cart_result": result, "assistant_message": result.message, "awaiting_user_input": True, "purchase_status": "completed", "user_intent": "none"}

    def terminate(self, state: ShoppingState) -> dict:
        return {"finished": True, "assistant_message": "Thanks for shopping with me!", "awaiting_user_input": False}
