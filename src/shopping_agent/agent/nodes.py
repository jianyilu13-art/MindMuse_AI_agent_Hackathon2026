"""Small state-transition operations. Routing belongs in routing.py."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from time import monotonic

from shopping_agent.llm.model import GroqModel
from shopping_agent.llm.parsing import GroqShoppingSemantics, ShoppingSemantics
from shopping_agent.processing import apply_hard_constraints, deduplicate_products, rank_products
from shopping_agent.tools import AddToCartTool, MockAddToCartTool, MockProductSearchTool, MockReviewTool, ProductSearchTool, ReviewTool
from shopping_agent.schemas import CommunityFeedbackSummary

from .state import ShoppingState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShoppingServices:
    search: ProductSearchTool
    reviews: ReviewTool
    cart: AddToCartTool
    semantics: ShoppingSemantics
    community: object | None = None

    @classmethod
    def mock(cls, semantics: ShoppingSemantics | None = None) -> "ShoppingServices":
        """Mock external commerce tools while retaining LLM-based interpretation."""
        return cls(MockProductSearchTool(), MockReviewTool(), MockAddToCartTool(), semantics or GroqShoppingSemantics(GroqModel()))

    @classmethod
    def from_environment(cls, semantics: ShoppingSemantics | None = None) -> "ShoppingServices":
        """Use SearchAPI in the application runtime; mocks remain explicit for tests."""
        mode = os.getenv("SHOPPING_TOOL_MODE", "searchapi").strip().lower()
        if mode == "mock":
            return cls.mock(semantics)
        if mode in {"searchapi", "real"}:
            from shopping_agent.tools_real import OpenProductLinkTool, SearchAPIClient, SearchAPICommunityFeedbackTool, SearchAPIProductSearchTool, SearchAPIReviewTool

            client = SearchAPIClient()

            return cls(
                SearchAPIProductSearchTool(client),
                SearchAPIReviewTool(),
                OpenProductLinkTool(),
                semantics or GroqShoppingSemantics(GroqModel()),
                SearchAPICommunityFeedbackTool(client),
            )
        raise ValueError("SHOPPING_TOOL_MODE must be either 'searchapi' or 'mock'.")


class ShoppingNodes:
    def __init__(self, services: ShoppingServices) -> None:
        self.services = services

    def interpret_user_input(self, state: ShoppingState) -> dict:
        message = state["last_user_message"]
        # Positional references ("the second one") are relative to the page the
        # shopper actually saw, not the provider's raw result ordering.
        known_products = state["displayed_products"] or state["raw_products"]
        conversation_context = "\n".join(
            f"{turn['role']}: {turn['content']}" for turn in state["conversation_turns"][-6:]
        )
        if state.get("assistant_message"):
            conversation_context += f"\nassistant: {state['assistant_message']}"
        decision = self.services.semantics.interpret_input(
            message, state["requirements"], known_products, conversation_context
        )
        update: dict = {
            "last_user_message": "", "input_status": "interpreted", "user_intent": decision.intent,
            "selected_product_id": decision.selected_product_id, "purchase_status": "requested" if decision.intent == "purchase" else state["purchase_status"],
            "comparison_product_ids": decision.selected_product_ids,
            "search_required": (
                True
                if decision.intent == "search"
                and not decision.should_extract_requirements
                and state["requirements"] is not None
                and state["search_result_status"] != "no_results"
                else state["search_required"]
            ),
        }
        turns = [*state["conversation_turns"], {"role": "user", "content": message}]
        update["conversation_turns"] = turns
        if decision.should_extract_requirements:
            update.update({"pending_requirement_text": message, "awaiting_user_input": False, "assistant_message": None})
        elif decision.intent == "more_results":
            update.update({"presentation_status": "ready", "awaiting_user_input": False, "assistant_message": None, "user_intent": "none"})
        return update

    def extract_requirements(self, state: ShoppingState) -> dict:
        extracted = self.services.semantics.extract_requirements(state["pending_requirement_text"] or "", state["requirements"])
        requirements = extracted.requirements
        missing_required_information = list(extracted.assessment.missing_required_information)
        clarification_context = extracted.assessment.clarification_context
        requirement_ready = extracted.assessment.sufficient_for_search and not missing_required_information
        return {
            "requirements": requirements, "pending_requirement_text": None,
            "requirement_status": "ready" if requirement_ready else "incomplete",
            "missing_required_information": missing_required_information,
            "optional_preferences": extracted.assessment.optional_preferences,
            "clarification_context": clarification_context,
            "search_required": requirement_ready,
            "search_completed": False, "search_result_status": "not_searched", "raw_products": [], "qualified_products": [], "reviews": {}, "community_feedback": {}, "community_status": "not_needed", "displayed_products": [],
            "review_status": "not_needed", "review_error": None, "ranking_status": "not_needed", "ranked_products": [], "display_offset": 0,
            "presentation_status": "not_ready", "purchase_status": "none", "user_intent": "none",
        }

    def ask_clarification(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        if state["search_completed"] and not state["qualified_products"]:
            alternatives = state["raw_products"][:3]
            if alternatives:
                lines = [
                    f"- {product.title} — {product.currency} {product.price:.2f}"
                    for product in alternatives
                ]
                message = (
                    "I couldn't find products matching all your requirements. "
                    "Here are the closest results:\n"
                    + "\n".join(lines)
                    + "\nYou can add or relax a requirement to search again."
                )
            else:
                message = (
                    "I couldn't find products matching your requirements. "
                    "You can add or relax a requirement to search again."
                )
            return {
                "assistant_message": message,
                "displayed_products": alternatives,
                "awaiting_user_input": True,
                "user_intent": "clarify",
                "presentation_status": "displayed",
            }
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
        logger.info("shopping_tool=search_products arguments=%s", requirements.model_dump(mode="json"))
        started = monotonic()
        raw_products = deduplicate_products(self.services.search.search(requirements))
        qualified = apply_hard_constraints(raw_products, requirements)
        logger.info("shopping_tool=search_products results=%d qualified=%d", len(raw_products), len(qualified))
        logger.info("shopping_timing operation=product_search elapsed_ms=%.1f", (monotonic() - started) * 1000)
        return {"raw_products": raw_products, "qualified_products": qualified, "search_required": False,
                "search_completed": True, "search_result_status": "results" if qualified else "no_results", "review_status": "pending" if qualified else "not_needed",
                "ranking_status": "not_needed", "ranked_products": [], "presentation_status": "not_ready"}

    def fetch_reviews(self, state: ShoppingState) -> dict:
        try:
            started = monotonic()
            logger.info("shopping_tool=fetch_reviews product_count=%d", len(state["qualified_products"]))
            review_started = monotonic()
            reviews = self.services.reviews.fetch(state["qualified_products"])
            logger.info("shopping_timing operation=review_retrieval elapsed_ms=%.1f", (monotonic() - review_started) * 1000)
            logger.info("shopping_timing operation=evidence elapsed_ms=%.1f", (monotonic() - started) * 1000)
            return {"reviews": reviews, "community_feedback": {}, "review_status": "completed", "review_error": None, "ranking_status": "pending"}
        except Exception as error:  # A review outage is non-fatal by design.
            return {"reviews": {}, "review_status": "failed", "review_error": str(error), "ranking_status": "pending"}

    def rank_products(self, state: ShoppingState) -> dict:
        requirements = state["requirements"]
        assert requirements is not None
        started = monotonic()
        ranked = rank_products(state["qualified_products"], requirements, state["reviews"])
        logger.info("shopping_timing operation=ranking elapsed_ms=%.1f", (monotonic() - started) * 1000)
        return {"ranked_products": ranked, "ranking_status": "completed", "presentation_status": "ready"}

    def display_results(self, state: ShoppingState) -> dict:
        start, size = state["display_offset"], state["page_size"]
        page = state["ranked_products"][start : start + size]
        if not page:
            message = "There are no more matching products. You can change your requirements or finish."
        else:
            lines = [f"{index}. {item.product.title} — {item.product.currency} {item.product.price:.2f}" for index, item in enumerate(page, start=start + 1)]
            message = "\n".join(lines) + "\nReply 'more', change your requirements, or name a product to purchase."
        products = [item.product for item in page]
        return {"assistant_message": message, "displayed_products": products, "display_offset": start + len(page), "presentation_status": "displayed" if page else "exhausted", "awaiting_user_input": True, "user_intent": "none"}

    def add_to_cart(self, state: ShoppingState) -> dict:
        selected_id = state["selected_product_id"]
        selected = next((item.product for item in state["ranked_products"] if item.product.id == selected_id), None)
        selected = selected or (state["ranked_products"][0].product if state["ranked_products"] else None)
        if selected is None:
            return {"assistant_message": "Please search for products before adding one to the cart.", "awaiting_user_input": True, "purchase_status": "failed", "user_intent": "none"}
        logger.info("shopping_tool=add_to_cart product_id=%s", selected.id)
        result = self.services.cart.add(selected)
        return {"cart_result": result, "assistant_message": result.message, "awaiting_user_input": True, "purchase_status": "completed", "user_intent": "none"}

    def compare_products(self, state: ShoppingState) -> dict:
        products = [product for product in state["displayed_products"] if product.id in state["comparison_product_ids"]]
        if len(products) < 2:
            return {"assistant_message": "Please name two products from the currently displayed results to compare.", "awaiting_user_input": True, "user_intent": "none"}
        lines = [f"{product.title}: {product.currency} {product.price:.2f}; {product.rating or 'no'} rating; {product.shipping_info or 'delivery unavailable'}" for product in products]
        return {"assistant_message": "Comparison:\n" + "\n".join(lines), "awaiting_user_input": True, "user_intent": "none"}

    def terminate(self, state: ShoppingState) -> dict:
        return {"finished": True, "assistant_message": "Thanks for shopping with me!", "awaiting_user_input": False}
