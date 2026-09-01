"""State-transition operations for the shopping agent."""

from __future__ import annotations

from dataclasses import dataclass

from shopping_agent.llm.model import GroqModel
from shopping_agent.llm.parsing import (
    GroqShoppingSemantics,
    ShoppingSemantics,
)
from shopping_agent.processing import (
    apply_hard_constraints,
    deduplicate_products,
    rank_products,
)
from shopping_agent.tools import (
    AddToCartTool,
    MockAddToCartTool,
    MockProductSearchTool,
    MockReviewTool,
    ProductSearchTool,
    ReviewTool,
)
from shopping_agent.tools.add_to_cart import CartResult
from shopping_agent.schemas import RequirementAssessment

from .state import ShoppingState


class ShoppingServices:
    """External and semantic services used by the graph."""

    def __init__(
        self,
        search: ProductSearchTool,
        reviews: ReviewTool,
        cart: AddToCartTool,
        semantics: ShoppingSemantics,
    ) -> None:
        self.search = search
        self.reviews = reviews
        self.cart = cart
        self.semantics = semantics

    @classmethod
    def mock(
        cls,
        semantics: ShoppingSemantics | None = None,
    ) -> "ShoppingServices":
        """Create services with mock commerce integrations."""

        return cls(
            search=MockProductSearchTool(),
            reviews=MockReviewTool(),
            cart=MockAddToCartTool(),
            semantics=semantics or GroqShoppingSemantics(GroqModel()),
        )


class ShoppingNodes:
    """Individual state-transition operations."""

    def __init__(self, services: ShoppingServices) -> None:
        self.services = services

    def interpret_user_input(self, state: ShoppingState) -> dict:
        """Classify the latest user message."""

        message = state["last_user_message"]

        known_products = [
            item.product
            for item in state["ranked_products"]
        ]

        if not known_products:
            known_products = state["raw_products"]

        decision = self.services.semantics.interpret_input(
            message=message,
            requirements=state["requirements"],
            products=known_products,
        )

        update: dict = {
            "last_user_message": "",
            "input_status": "interpreted",
            "user_intent": decision.intent,
            "selected_product_id": decision.selected_product_id,
            "assistant_message": None,
            "last_error": None,
        }

        if decision.intent == "finish":
            update["user_intent"] = "finish"
            return update

        if decision.intent == "purchase":
            update["purchase_status"] = "requested"
            update["awaiting_user_input"] = False
            return update

        if decision.intent == "more_results":
            update.update(
                {
                    "presentation_status": "ready",
                    "awaiting_user_input": False,
                    "user_intent": "none",
                }
            )
            return update

        if decision.should_extract_requirements:
            update.update(
                {
                    "pending_requirement_text": message,
                    "awaiting_user_input": False,
                    "user_intent": "none",
                }
            )

        return update

    def extract_requirements(self, state: ShoppingState) -> dict:
        """Extract category-specific requirements using the LLM."""

        extracted = self.services.semantics.extract_requirements(
            message=state["pending_requirement_text"] or "",
            current=state["requirements"],
        )

        requirements = extracted.requirements
        assessment = extracted.assessment

        missing = list(
            dict.fromkeys(
                assessment.missing_required_information
            )
        )

        requirement_status = (
            "ready"
            if assessment.sufficient_for_search and not missing
            else "incomplete"
        )

        return {
            "requirements": requirements,
            "product_category": requirements.category,
            "pending_requirement_text": None,
            "suggested_attributes": assessment.suggested_attributes,
            "missing_required_information": missing,
            "missing_dynamic_attributes": [
                name
                for name in missing
                if name not in {"max_price", "arrival_by"}
            ],
            "optional_preferences": assessment.optional_preferences,
            "clarification_context": assessment.clarification_context,
            "requirement_status": requirement_status,
            "search_required": requirement_status == "ready",
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
            "presentation_status": "not_ready",
            "selected_product_id": None,
            "purchase_status": "none",
            "user_intent": "none",
            "assistant_message": None,
            "awaiting_user_input": False,
            "last_error": None,
        }

    def ask_clarification(self, state: ShoppingState) -> dict:
        """Ask only for missing dynamic attributes or constraints."""

        requirements = state["requirements"]

        missing = list(
            dict.fromkeys(
                state["missing_required_information"]
                + state["missing_dynamic_attributes"]
            )
        )

        if (
            state["search_completed"]
            and not state["qualified_products"]
        ):
            missing = ["a requirement to relax or change"]
            context = (
                "The completed search returned no products matching "
                "the current requirements."
            )
        else:
            context = state["clarification_context"]

        assessment = RequirementAssessment(
            sufficient_for_search=False,
            missing_required_information=missing,
            optional_preferences=state["optional_preferences"],
            suggested_attributes=state["suggested_attributes"],
            clarification_context=context,
        )

        message = self.services.semantics.write_clarification(
            assessment=assessment,
            requirements=requirements,
        )

        return {
            "assistant_message": message,
            "awaiting_user_input": True,
            "user_intent": "clarify",
            "missing_required_information": missing,
            "missing_dynamic_attributes": [
                name
                for name in missing
                if name not in {"max_price", "arrival_by"}
            ],
        }

    def search_products(self, state: ShoppingState) -> dict:
        """Search and apply deterministic hard constraints."""

        requirements = state["requirements"]

        if requirements is None:
            return {
                "assistant_message": (
                    "I need more shopping details before searching."
                ),
                "awaiting_user_input": True,
                "last_error": "Requirements are missing.",
            }

        raw_products = deduplicate_products(
            self.services.search.search(requirements)
        )

        qualified_products = apply_hard_constraints(
            products=raw_products,
            requirements=requirements,
        )

        return {
            "raw_products": raw_products,
            "qualified_products": qualified_products,
            "search_required": False,
            "search_completed": True,
            "search_result_status": (
                "results" if qualified_products else "no_results"
            ),
            "review_status": (
                "pending" if qualified_products else "not_needed"
            ),
            "ranking_status": "not_needed",
            "ranked_products": [],
            "presentation_status": "not_ready",
            "display_offset": 0,
            "missing_dynamic_attributes": [],
        }

    def fetch_reviews(self, state: ShoppingState) -> dict:
        """Fetch product reviews without making review failure fatal."""

        try:
            reviews = self.services.reviews.fetch(
                state["qualified_products"]
            )

            return {
                "reviews": reviews,
                "review_status": "completed",
                "review_error": None,
                "ranking_status": "pending",
            }
        except Exception as error:
            return {
                "reviews": {},
                "review_status": "failed",
                "review_error": str(error),
                "ranking_status": "pending",
            }

    def rank_products(self, state: ShoppingState) -> dict:
        """Rank products using deterministic product data."""

        requirements = state["requirements"]

        if requirements is None:
            return {
                "ranking_status": "completed",
                "ranked_products": [],
                "presentation_status": "ready",
            }

        ranked_products = rank_products(
            products=state["qualified_products"],
            requirements=requirements,
            reviews=state["reviews"],
        )

        return {
            "ranked_products": ranked_products,
            "ranking_status": "completed",
            "presentation_status": "ready",
        }

    def display_results(self, state: ShoppingState) -> dict:
        """Display one page of ranked products."""

        start = state["display_offset"]
        size = state["page_size"]
        page = state["ranked_products"][start : start + size]

        if not page:
            message = (
                "There are no more matching products. "
                "You can change your requirements or finish."
            )
        else:
            lines: list[str] = []

            for item in page:
                product = item.product

                delivery = (
                    f"arrives by {product.arrival_date.isoformat()}"
                    if product.arrival_date
                    else "arrival date unavailable"
                )

                lines.append(
                    f"{product.id}: "
                    f"{product.title} — "
                    f"{product.currency} {product.price:.2f} — "
                    f"{delivery}"
                )

            message = "\n".join(lines)
            message += (
                "\nReply 'more', change your requirements, "
                "or name a product to purchase."
            )

        return {
            "assistant_message": message,
            "display_offset": start + len(page),
            "presentation_status": (
                "displayed" if page else "exhausted"
            ),
            "awaiting_user_input": True,
            "user_intent": "none",
        }

    def add_to_cart(self, state: ShoppingState) -> dict:
        """Add the selected product to the cart."""

        selected_product_id = state["selected_product_id"]

        selected_product = next(
            (
                item.product
                for item in state["ranked_products"]
                if item.product.id == selected_product_id
            ),
            None,
        )

        if selected_product is None:
            return {
                "assistant_message": (
                    "I could not identify that product. "
                    "Please provide the product ID."
                ),
                "awaiting_user_input": True,
                "purchase_status": "failed",
                "user_intent": "none",
            }

        result: CartResult = self.services.cart.add(selected_product)

        return {
            "cart_result": result,
            "assistant_message": result.message,
            "awaiting_user_input": True,
            "purchase_status": (
                "completed" if result.success else "failed"
            ),
            "user_intent": "none",
        }

    def terminate(self, state: ShoppingState) -> dict:
        """Finish the conversation."""

        return {
            "finished": True,
            "assistant_message": "Thanks for shopping with me!",
            "awaiting_user_input": False,
        }