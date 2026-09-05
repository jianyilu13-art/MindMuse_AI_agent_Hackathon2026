"""State-transition operations for the shopping agent."""

from __future__ import annotations

from shopping_agent.llm.model import GroqModel
from shopping_agent.llm.parsing import (
    GroqShoppingSemantics,
    RuleBasedShoppingSemantics,
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
    build_shopping_tool_input,
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
        """Create local commerce services with Groq when configured.

        The search, review, and cart integrations remain deterministic mocks
        until marketplace adapters are supplied. Semantic operations use
        Groq whenever ``GROQ_API_KEY`` is present; otherwise a small local
        adapter keeps the demo and UI runnable without credentials.
        """

        if semantics is None:
            semantics = cls._semantic_service_from_env()

        return cls(
            search=MockProductSearchTool(),
            reviews=MockReviewTool(),
            cart=MockAddToCartTool(),
            semantics=semantics,
        )

    @classmethod
    def from_env(
        cls,
        *,
        search: ProductSearchTool | None = None,
        reviews: ReviewTool | None = None,
        cart: AddToCartTool | None = None,
    ) -> "ShoppingServices":
        """Create the default application services from environment config."""

        return cls(
            search=search or MockProductSearchTool(),
            reviews=reviews or MockReviewTool(),
            cart=cart or MockAddToCartTool(),
            semantics=cls._semantic_service_from_env(),
        )

    @staticmethod
    def _semantic_service_from_env() -> ShoppingSemantics:
        """Select the real Groq adapter or the local no-key fallback."""

        try:
            return GroqShoppingSemantics(GroqModel())
        except ValueError as error:
            if "GROQ_API_KEY" not in str(error):
                raise

        return RuleBasedShoppingSemantics()


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

        try:
            decision = self.services.semantics.interpret_input(
                message=message,
                requirements=state["requirements"],
                products=known_products,
            )
        except Exception as error:
            return {
                "last_user_message": "",
                "input_status": "interpreted",
                "assistant_message": _semantic_error_message(error),
                "awaiting_user_input": True,
                "last_error": str(error),
            }

        update: dict = {
            "last_user_message": "",
            "input_status": "interpreted",
            "user_intent": decision.intent,
            "selected_product_id": decision.selected_product_id,
            "assistant_message": None,
            "last_error": None,
            "awaiting_user_input": False,
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

        try:
            extracted = self.services.semantics.extract_requirements(
                message=state["pending_requirement_text"] or "",
                current=state["requirements"],
            )
        except Exception as error:
            return {
                "assistant_message": _semantic_error_message(error),
                "awaiting_user_input": True,
                "pending_requirement_text": None,
                "last_error": str(error),
            }

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
            "search_tool_input": None,
            "raw_products": [],
            "qualified_products": [],
            "reviews": {},
            "review_status": "not_needed",
            "review_error": None,
            "ranking_status": "not_needed",
            "ranked_products": [],
            "display_offset": 0,
            "visible_products": [],
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

        try:
            question = self.services.semantics.write_clarification(
                assessment=assessment,
                requirements=requirements,
            )
        except Exception:
            question = _fallback_clarification_question(
                missing=missing,
                category=(
                    requirements.category
                    if requirements and requirements.category
                    else None
                ),
            )

        no_results = (
            state["search_completed"]
            and not state["qualified_products"]
        )

        message = (
            question
            if no_results
            else _format_attribute_guidance(
                question=question,
                assessment=assessment,
                requirements=requirements,
            )
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

        search_request = build_shopping_tool_input(requirements)

        try:
            raw_products = deduplicate_products(
                self.services.search.search(search_request)
            )
        except Exception as error:
            return {
                "search_tool_input": search_request,
                "assistant_message": (
                    "I could not complete the product search. "
                    "Please try again or adjust your requirements."
                ),
                "awaiting_user_input": True,
                "last_error": str(error),
            }

        qualified_products = apply_hard_constraints(
            products=raw_products,
            requirements=requirements,
        )

        return {
            "raw_products": raw_products,
            "qualified_products": qualified_products,
            "search_required": False,
            "search_completed": True,
            "search_tool_input": search_request,
            "search_result_status": (
                "results" if qualified_products else "no_results"
            ),
            "review_status": (
                "pending" if qualified_products else "not_needed"
            ),
            "ranking_status": "not_needed",
            "ranked_products": [],
            "presentation_status": "not_ready",
            "visible_products": [],
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
            "visible_products": [item.product for item in page],
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


def _semantic_error_message(error: Exception) -> str:
    """Turn provider/configuration failures into an actionable UI message."""

    detail = str(error).strip()

    if "GROQ_API_KEY" in detail:
        return (
            "Groq is not configured yet. Add GROQ_API_KEY to your .env file, "
            "restart the app, and try again."
        )

    return (
        "I could not understand that shopping request because the language "
        "model is temporarily unavailable. Please try again."
    )


def _fallback_clarification_question(
    *,
    missing: list[str],
    category: str | None,
) -> str:
    """Provide a useful question even if the final wording call fails."""

    labels = {
        "size": "your size",
        "taste": "your preferred taste",
        "usage": "how you plan to use it",
        "max_price": "your maximum budget",
        "arrival_by": "your latest acceptable arrival date",
        "category": "the product you want to buy",
    }
    requested = [
        labels.get(item, item.replace("_", " "))
        for item in missing
    ]

    if not requested:
        return "Could you share another requirement or preference?"

    prefix = f"For {category.replace('_', ' ')}, " if category else ""
    return f"{prefix}could you provide {', '.join(requested)}?"


def _format_attribute_guidance(
    *,
    question: str,
    assessment: RequirementAssessment,
    requirements,
) -> str:
    """Render the required/optional split in a human-readable message."""

    category = (
        requirements.category.replace("_", " ")
        if requirements and requirements.category
        else "this product"
    )

    proposals = assessment.suggested_attributes
    required = [proposal for proposal in proposals if proposal.required]
    optional = [proposal for proposal in proposals if not proposal.required]

    known_required_names = {proposal.name for proposal in required}
    for name in assessment.missing_required_information:
        if name not in known_required_names:
            required.append(
                type(proposals[0])(
                    name=name,
                    attribute_type="string",
                    required=True,
                    reason=None,
                )
                if proposals
                else _make_attribute_proposal(name)
            )

    if not required and not optional:
        return question

    lines = [
        f"To search for {category}, please share:",
        "",
        "Required attributes:",
    ]

    if required:
        lines.extend(
            _format_proposal_line(
                proposal,
                requirements,
            )
            for proposal in required
        )
    else:
        lines.append("- None — I can search with the details provided.")

    lines.extend(["", "Optional attributes:"])

    if optional:
        lines.extend(
            _format_proposal_line(
                proposal,
                requirements,
            )
            for proposal in optional
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "You can provide all the details you know in one message.",
            "",
            question,
        ]
    )
    return "\n".join(lines)


def _make_attribute_proposal(name: str):
    """Create a generic proposal for an extra required field."""

    from shopping_agent.schemas import ProductAttributeProposal

    return ProductAttributeProposal(
        name=name,
        attribute_type="string",
        required=True,
    )


def _format_proposal_line(proposal, requirements) -> str:
    """Format one attribute with its reason and current-value status."""

    value = _requirement_value(requirements, proposal.name)
    status = " (provided)" if value not in (None, "", [], {}) else ""
    reason = f": {proposal.reason}" if proposal.reason else ""
    return f"- {proposal.name}{status}{reason}"


def _requirement_value(requirements, name: str):
    """Read a named dynamic attribute from the current requirements."""

    if requirements is None:
        return None

    if name == "size":
        return requirements.size or requirements.attributes.get("size")

    if name == "max_price":
        return requirements.max_price

    if name == "arrival_by":
        return requirements.arrival_by

    return requirements.attributes.get(name)
