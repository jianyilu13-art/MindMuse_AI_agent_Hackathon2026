"""Semantic input interpretation behind a provider-neutral interface."""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel

from shopping_agent.agent.prompts import INTENT_PROMPT, REQUIREMENT_EXTRACTION_PROMPT
from shopping_agent.llm.model import GroqModel
from shopping_agent.schemas import Product, UserRequirements


Intent = Literal["search", "change_requirements", "more_results", "purchase", "finish", "clarify"]


class SemanticDecision(BaseModel):
    intent: Intent = "search"
    selected_product_id: str | None = None


class ShoppingSemantics(Protocol):
    def classify(self, message: str, products: list[Product]) -> SemanticDecision: ...
    def extract_requirements(self, message: str, current: UserRequirements | None) -> UserRequirements: ...


class RuleBasedShoppingSemantics:
    """Offline default; swap this for GroqShoppingSemantics in production."""

    def classify(self, message: str, products: list[Product]) -> SemanticDecision:
        text = message.lower()
        if any(word in text for word in ("bye", "done", "finish", "no thanks")):
            return SemanticDecision(intent="finish")
        if any(word in text for word in ("more", "next", "show additional")):
            return SemanticDecision(intent="more_results")
        if any(word in text for word in ("buy", "purchase", "add to cart")):
            selected = next((product.id for product in products if product.id.lower() in text), None)
            return SemanticDecision(intent="purchase", selected_product_id=selected)
        if any(word in text for word in ("change", "instead", "different", "under", "below")):
            return SemanticDecision(intent="change_requirements")
        return SemanticDecision(intent="search")

    def extract_requirements(self, message: str, current: UserRequirements | None) -> UserRequirements:
        budget = re.search(r"(?:under|below|budget(?: of)?|\$)\s*\$?(\d+(?:\.\d{1,2})?)", message, re.I)
        values = current.model_dump() if current else {}
        if budget:
            values["max_price"] = float(budget.group(1))

        text = message.strip().rstrip(".?!")
        brands = re.findall(r"\b(sony|bose|apple|samsung|jbl|sennheiser|beats)\b", text, re.I)
        if brands:
            values["preferred_brands"] = _merge_words(values.get("preferred_brands", []), brands)

        features = re.findall(r"\b(wireless|wired|noise cancelling|waterproof|lightweight|gaming)\b", text, re.I)
        if features:
            values["must_have"] = _merge_words(values.get("must_have", []), features)

        # A short budget/feature/brand answer is an answer to a clarification,
        # not a replacement for the already-known product category.
        if not values.get("query"):
            query = re.sub(r"^(?:please\s+)?(?:find|search for|i want|i need)\s+", "", text, flags=re.I)
            query = re.sub(r"(?:under|below|budget(?:\s+of)?)?\s*\$?\d+(?:\.\d{1,2})?", "", query, flags=re.I)
            query = re.sub(r"\b(?:wireless|wired|noise cancelling|waterproof|lightweight|gaming|sony|bose|apple|samsung|jbl|sennheiser|beats|preferred)\b", "", query, flags=re.I)
            query = re.sub(r"\s+", " ", query).strip(" ,.-")
            if query:
                values["query"] = query
        return UserRequirements.model_validate(values)


class GroqShoppingSemantics:
    """Optional Groq implementation. The graph only depends on ShoppingSemantics."""

    def __init__(self, model: GroqModel) -> None:
        self.model = model

    def classify(self, message: str, products: list[Product]) -> SemanticDecision:
        response = self.model.ask(INTENT_PROMPT.format(message=message, products=[p.model_dump() for p in products]))
        return SemanticDecision.model_validate_json(_json_object(response))

    def extract_requirements(self, message: str, current: UserRequirements | None) -> UserRequirements:
        response = self.model.ask(REQUIREMENT_EXTRACTION_PROMPT.format(message=message, current_requirements=current.model_dump() if current else {}))
        patch = UserRequirements.model_validate_json(_json_object(response))
        values = current.model_dump() if current else {}
        values.update({key: value for key, value in patch.model_dump().items() if value not in (None, [], {})})
        return UserRequirements.model_validate(values)


def _json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM response did not contain a JSON object.")
    return match.group(0)


def _merge_words(existing: list[str], additions: list[str]) -> list[str]:
    """Preserve order while preventing repeated features or brands."""
    merged = [item.lower() for item in existing]
    for item in additions:
        if item.lower() not in merged:
            merged.append(item.lower())
    return merged
