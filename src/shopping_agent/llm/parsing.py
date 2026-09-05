"""LLM-backed conversion of a shopper turn into structured state."""

from __future__ import annotations

import json
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from shopping_agent.agent.prompts import (
    CLARIFICATION_PROMPT,
    INPUT_INTERPRETATION_PROMPT,
    REQUIREMENT_EXTRACTION_PROMPT,
    SHOPPING_AGENT_SYSTEM_PROMPT,
)
from shopping_agent.llm.model import GroqModel
from shopping_agent.schemas import Product, RequirementAssessment, UserRequirements

Intent = Literal["search", "change_requirements", "more_results", "purchase", "compare", "finish", "clarify"]


class InputInterpretation(BaseModel):
    intent: Intent = "search"
    selected_product_id: str | None = None
    selected_product_ids: list[str] = Field(default_factory=list)
    should_extract_requirements: bool = False


class RequirementExtraction(BaseModel):
    requirements: UserRequirements = Field(default_factory=UserRequirements)
    assessment: RequirementAssessment = Field(default_factory=RequirementAssessment)
    relaxed_fields: list[str] = Field(default_factory=list)


class ShoppingSemantics(Protocol):
    def interpret_input(self, message: str, requirements: UserRequirements | None, products: list[Product], conversation_context: str = "") -> InputInterpretation: ...
    def extract_requirements(self, message: str, current: UserRequirements | None) -> RequirementExtraction: ...
    def write_clarification(self, assessment: RequirementAssessment, requirements: UserRequirements | None) -> str: ...


class GroqShoppingSemantics:
    """The graph's semantic boundary; routing never parses natural language."""

    def __init__(self, model: GroqModel) -> None:
        self.model = model

    def interpret_input(self, message: str, requirements: UserRequirements | None, products: list[Product], conversation_context: str = "") -> InputInterpretation:
        product_context = [
            {
                "id": product.id,
                "title": product.title,
                "price": product.price,
                "currency": product.currency,
                "platform": product.platform,
            }
            for product in products[:10]
        ]
        response = self.model.generate(SHOPPING_AGENT_SYSTEM_PROMPT, INPUT_INTERPRETATION_PROMPT.format(
            message=message, current_requirements=requirements.model_dump() if requirements else {},
            products=product_context, conversation_context=conversation_context,
        ))
        return InputInterpretation.model_validate(_json_object(response))

    def extract_requirements(self, message: str, current: UserRequirements | None) -> RequirementExtraction:
        response = self.model.generate(SHOPPING_AGENT_SYSTEM_PROMPT, REQUIREMENT_EXTRACTION_PROMPT.format(
            message=message, current_requirements=current.model_dump() if current else {},
        ))
        extracted = RequirementExtraction.model_validate(_json_object(response))
        extracted.requirements = _merge_requirements(current, extracted.requirements, extracted.relaxed_fields)
        return extracted

    def write_clarification(self, assessment: RequirementAssessment, requirements: UserRequirements | None) -> str:
        response = self.model.generate(SHOPPING_AGENT_SYSTEM_PROMPT, CLARIFICATION_PROMPT.format(
            requirements=requirements.model_dump() if requirements else {},
            missing_required_information=assessment.missing_required_information,
            optional_preferences=assessment.optional_preferences,
            clarification_context=assessment.clarification_context,
        ))
        return str(_json_object(response).get("clarification_question") or "Could you share a little more so I can search accurately?")


def _json_object(text: str) -> dict:
    """Accept JSON emitted with or without a Markdown fence."""
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object.")
    return json.loads(cleaned[start : end + 1])


def _merge_requirements(current: UserRequirements | None, patch: UserRequirements, relaxed_fields: list[str] | None = None) -> UserRequirements:
    """Apply stated fields without mistaking omitted fields for a request to erase them."""
    merged = current.model_dump() if current else {}
    values = patch.model_dump()
    merged.update({key: value for key, value in values.items() if value not in (None, [], {})})
    field_aliases = {
        "budget": "max_price",
        "price": "max_price",
        "max price": "max_price",
        "minimum": "min_price",
        "min price": "min_price",
        "brand": "preferred_brands",
        "platform": "preferred_platforms",
    }
    for field in relaxed_fields or []:
        normalized = field.strip().lower().replace("_", " ")
        target = field_aliases.get(normalized, normalized.replace(" ", "_"))
        if target in {"min_price", "max_price", "size", "query", "arrival_by"}:
            merged[target] = None
        elif target in {"preferred_brands", "preferred_platforms", "must_have", "ranking_priorities", "no_preference_fields"}:
            merged[target] = []
        else:
            merged.setdefault("attributes", {}).pop(target, None)
    # An explicit lack of preference supersedes a previously stated positive preference.
    no_preference = set(values["no_preference_fields"])
    field_map = {"brand": "preferred_brands", "brands": "preferred_brands", "platform": "preferred_platforms", "platforms": "preferred_platforms"}
    for preference, field in field_map.items():
        if preference in no_preference:
            merged[field] = []
    return UserRequirements.model_validate(merged)
