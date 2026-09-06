"""Small state-transition operations. Routing belongs in routing.py."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from math import inf
import os
from time import monotonic

from shopping_agent.llm.model import GroqModel
from shopping_agent.llm.parsing import GroqShoppingSemantics, ShoppingSemantics
from shopping_agent.processing import apply_hard_constraints, deduplicate_products, rank_products
from shopping_agent.tools import AddToCartTool, MockAddToCartTool, MockProductSearchTool, MockReviewTool, ProductSearchTool, ReviewTool
from shopping_agent.schemas import BestPick, CommunityFeedbackSummary, Product, UserRequirements

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
            "best_picks": [],
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
                    + "\nYou can increase your budget or relax a requirement to search again."
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
                "ranking_status": "not_needed", "ranked_products": [], "best_picks": [], "presentation_status": "not_ready"}

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

    def select_best_picks(self, state: ShoppingState) -> dict:
        """Select three decision-oriented recommendations without calling the LLM."""
        ranked = state["ranked_products"]
        if not ranked:
            return {"best_picks": []}

        requirements = state["requirements"]
        assert requirements is not None

        def critical_match_confidence(product: Product) -> float:
            """Give unknown critical fields less confidence than verified ones."""
            checks = 0
            confirmed = 0
            product_text = f"{product.title} {product.description} {' '.join(str(value) for value in product.attributes.values())}".casefold()
            if requirements.size:
                checks += 1
                sizes = {item.strip() for item in str(product.attributes.get("sizes", "")).split(",") if item.strip()}
                if requirements.size in sizes:
                    confirmed += 1
            for name, value in requirements.attributes.items():
                if not value:
                    continue
                checks += 1
                normalized_name = name.casefold().replace("_", " ")
                normalized_value = value.casefold().strip()
                if normalized_name in {"gender", "sex"}:
                    if normalized_value in {"female", "woman", "women", "womens"}:
                        confirmed += int(any(term in product_text for term in ("female", "woman", "women", "womens")))
                    elif normalized_value in {"male", "man", "men", "mens"}:
                        confirmed += int(any(term in product_text for term in ("male", "man", "men", "mens")))
                    else:
                        confirmed += int(normalized_value in product_text)
                else:
                    confirmed += int(normalized_value in product_text)
            return confirmed / checks if checks else 1.0

        priorities = {priority.casefold() for priority in requirements.ranking_priorities}
        preferred_platforms = {platform.casefold() for platform in requirements.preferred_platforms}

        def functional(product: Product) -> float:
            """Quality and preference score; intentionally excludes price."""
            score = (product.rating or 0) * 10 + min(product.review_count or 0, 1000) / 100
            if product.platform.casefold() in preferred_platforms:
                score += 5
            if "rating" in priorities:
                score += (product.rating or 0) * 5
            if "reviews" in priorities:
                score += min(product.review_count or 0, 1000) / 100
            if (
                ("delivery" in priorities or "arrival" in priorities)
                and product.arrival_date
                and requirements.arrival_by
            ):
                score += max((requirements.arrival_by - product.arrival_date).days, 0)
            return score

        def effective_score(rp) -> float:
            return rp.score * critical_match_confidence(rp.product)

        # Existing rank order remains the primary signal. Confidence only
        # prevents an unverified critical attribute from being treated as a
        # confirmed match when two products compete for the overall slot.
        overall_rp = max(ranked, key=lambda rp: (effective_score(rp), rp.score))
        overall = overall_rp.product
        overall_price = overall.price
        top_score = overall_rp.score or 1.0
        overall_confidence = critical_match_confidence(overall)

        def match_pct(score: float, denominator: float = top_score) -> int:
            if denominator <= 0:
                return 0
            return max(0, min(100, round(min(score / denominator, 1.0) * 100)))

        overall_reasons = list(overall_rp.reasons[:3])
        if overall_confidence < 1:
            overall_reasons.append("Some critical product details are unverified")
        picks = [BestPick(
            tier="overall",
            product=overall,
            match_pct=match_pct(overall_rp.score * overall_confidence),
            match_label="match",
            headline="Strongest match across your requirements, preferences, quality, and budget.",
            reasons=overall_reasons,
        )]
        selected_ids = {overall.id}

        prices = [rp.product.price for rp in ranked if rp.product.price > 0]
        price_reference = requirements.max_price or (max(prices) if prices else overall_price) or 1

        def value_score(rp) -> float:
            match_component = effective_score(rp) / max(top_score, 1.0)
            quality_component = functional(rp.product) * critical_match_confidence(rp.product) / max(functional(overall), 1.0)
            price_efficiency = max(0.0, min(1.0, 1 - rp.product.price / price_reference))
            return 0.55 * match_component + 0.30 * quality_component + 0.15 * price_efficiency

        value_candidates = [rp for rp in ranked if rp.product.id not in selected_ids and rp.product.price < overall_price]
        if value_candidates:
            value_rp = max(value_candidates, key=value_score)
            saving = overall_price - value_rp.product.price
            picks.append(BestPick(
                tier="value",
                product=value_rp.product,
                match_pct=match_pct(effective_score(value_rp)),
                match_label="match",
                headline=f"Best match/quality trade-off at a lower cost; saves {value_rp.product.currency} {saving:.2f} versus the top pick.",
                reasons=[*value_rp.reasons[:2], "Preserves strong shopper fit while costing less"],
            ))
            selected_ids.add(value_rp.product.id)

        ceiling = requirements.max_price * 1.15 if requirements.max_price else inf
        overall_functional = functional(overall) * overall_confidence
        overall_rating = overall.rating or 0
        overall_reviews = overall.review_count or 0
        upgrade_candidates = [
            rp for rp in ranked
            if rp.product.id not in selected_ids
            and rp.product.price > overall_price
            and rp.product.price <= ceiling
        ]

        def is_meaningful_upgrade(rp) -> bool:
            product = rp.product
            candidate_functional = functional(product) * critical_match_confidence(product)
            rating_improved = (product.rating or 0) >= overall_rating + 0.2
            reviews_improved = (product.review_count or 0) > overall_reviews * 1.5
            functional_gain = candidate_functional - overall_functional
            return (
                (rating_improved or reviews_improved or functional_gain >= max(2.0, overall_functional * 0.05))
                and critical_match_confidence(product) >= overall_confidence
            )

        upgrade_pool = [rp for rp in upgrade_candidates if is_meaningful_upgrade(rp)]
        if upgrade_pool:
            upgrade_rp = max(upgrade_pool, key=lambda rp: functional(rp.product) * critical_match_confidence(rp.product))
            upgrade = upgrade_rp.product
            upgrade_functional = functional(upgrade) * critical_match_confidence(upgrade)
            improvement_reasons = ["Noticeably stronger quality or review evidence"]
            if (upgrade.rating or 0) >= overall_rating + 0.2:
                improvement_reasons.append("Higher rating")
            if (upgrade.review_count or 0) > overall_reviews * 1.5:
                improvement_reasons.append("Stronger review confidence")
            picks.append(BestPick(
                tier="upgrade",
                product=upgrade,
                match_pct=match_pct(upgrade_functional, overall_functional or 1.0),
                match_label="functional match",
                headline="Pricier, but noticeably better reviews/quality within your requirements.",
                reasons=improvement_reasons,
            ))

        return {"best_picks": picks}

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
