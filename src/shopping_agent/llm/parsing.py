"""LLM-backed conversion of shopper messages into structured state."""

from __future__ import annotations

import json
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from shopping_agent.agent.prompts import (
    CLARIFICATION_PROMPT,
    INPUT_INTERPRETATION_PROMPT,
    REQUIREMENT_EXTRACTION_PROMPT,
)
from shopping_agent.llm.model import GroqModel
from shopping_agent.schemas import (
    Product,
    ProductAttributeProposal,
    RequirementAssessment,
    UserRequirements,
)


Intent = Literal[
    "search",
    "change_requirements",
    "more_results",
    "purchase",
    "finish",
    "clarify",
]


class InputInterpretation(BaseModel):
    """Interpretation of the shopper's latest message."""

    intent: Intent = "search"
    selected_product_id: str | None = None
    should_extract_requirements: bool = False


class RequirementExtraction(BaseModel):
    """Extracted requirements and dynamic attribute assessment."""

    requirements: UserRequirements = Field(default_factory=UserRequirements)
    assessment: RequirementAssessment = Field(
        default_factory=RequirementAssessment
    )


class ShoppingSemantics(Protocol):
    """Semantic boundary used by the shopping graph."""

    def interpret_input(
        self,
        message: str,
        requirements: UserRequirements | None,
        products: list[Product],
    ) -> InputInterpretation:
        ...

    def extract_requirements(
        self,
        message: str,
        current: UserRequirements | None,
    ) -> RequirementExtraction:
        ...

    def write_clarification(
        self,
        assessment: RequirementAssessment,
        requirements: UserRequirements | None,
    ) -> str:
        ...


class GroqShoppingSemantics:
    """Use Groq to interpret shopper language and extract requirements."""

    def __init__(self, model: GroqModel) -> None:
        self.model = model

    def interpret_input(
        self,
        message: str,
        requirements: UserRequirements | None,
        products: list[Product],
    ) -> InputInterpretation:
        response = self.model.ask(
            INPUT_INTERPRETATION_PROMPT.format(
                message=message,
                current_requirements=(
                    requirements.model_dump() if requirements else {}
                ),
                products=[
                    product.model_dump(mode="json") for product in products
                ],
            )
        )

        return InputInterpretation.model_validate(_json_object(response))

    def extract_requirements(
        self,
        message: str,
        current: UserRequirements | None,
    ) -> RequirementExtraction:
        response = self.model.ask(
            REQUIREMENT_EXTRACTION_PROMPT.format(
                message=message,
                current_requirements=(
                    current.model_dump(mode="json") if current else {}
                ),
            )
        )

        extracted = RequirementExtraction.model_validate(
            _json_object(response)
        )

        extracted.requirements = _merge_requirements(
            current,
            extracted.requirements,
        )

        extracted.assessment = _normalize_assessment(
            extracted.assessment,
            extracted.requirements,
        )

        return extracted

    def write_clarification(
        self,
        assessment: RequirementAssessment,
        requirements: UserRequirements | None,
    ) -> str:
        response = self.model.ask(
            CLARIFICATION_PROMPT.format(
                category=(
                    requirements.category
                    if requirements and requirements.category
                    else "unknown"
                ),
                requirements=(
                    requirements.model_dump(mode="json")
                    if requirements
                    else {}
                ),
                suggested_attributes=[
                    item.model_dump(mode="json")
                    for item in assessment.suggested_attributes
                ],
                missing_required_information=(
                    assessment.missing_required_information
                ),
                optional_preferences=assessment.optional_preferences,
                clarification_context=assessment.clarification_context,
            )
        )

        value = _json_object(response).get("clarification_question")

        if isinstance(value, str) and value.strip():
            return value.strip()

        return "Could you share a little more so I can search accurately?"


def _json_object(text: str) -> dict:
    """Accept JSON emitted with or without a Markdown code fence."""

    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json") :]

    if cleaned.startswith("```"):
        cleaned = cleaned[len("```") :]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object.")

    return json.loads(cleaned[start : end + 1])


def _merge_requirements(
    current: UserRequirements | None,
    patch: UserRequirements,
) -> UserRequirements:
    """Merge newly stated values without erasing existing requirements."""

    if current is None:
        return patch

    merged = current.model_dump()

    patch_values = patch.model_dump()

    scalar_fields = {
        "query",
        "category",
        "size",
        "max_price",
        "arrival_by",
    }

    for field_name in scalar_fields:
        value = patch_values.get(field_name)

        if value is not None:
            merged[field_name] = value

    merged_attributes = dict(merged.get("attributes") or {})
    merged_attributes.update(patch_values.get("attributes") or {})
    merged["attributes"] = merged_attributes
    
    if merged.get("size") is not None:
        merged_attributes["size"] = merged["size"]

    if merged.get("size") is None and merged_attributes.get("size"):
        merged["size"] = str(merged_attributes["size"])

    merged["attributes"] = merged_attributes

    for field_name in [
        "must_have",
        "preferred_brands",
        "preferred_platforms",
    ]:
        values = patch_values.get(field_name) or []

        if values:
            merged[field_name] = values

    existing_no_preferences = set(
        merged.get("no_preference_fields") or []
    )
    existing_no_preferences.update(
        patch_values.get("no_preference_fields") or []
    )
    merged["no_preference_fields"] = sorted(existing_no_preferences)

    for field_name in merged["no_preference_fields"]:
        if field_name in merged["attributes"]:
            merged["attributes"].pop(field_name, None)

    return UserRequirements.model_validate(merged)


def _normalize_assessment(
    assessment: RequirementAssessment,
    requirements: UserRequirements,
) -> RequirementAssessment:
    """Ensure assessment fields are consistent with extracted requirements."""

    suggested_names = {
        proposal.name for proposal in assessment.suggested_attributes
    }

    missing = [
        name
        for name in assessment.missing_required_information
        if name in suggested_names or name in {"max_price", "arrival_by"}
    ]

    assessment.missing_required_information = list(dict.fromkeys(missing))

    if requirements.category is None:
        assessment.sufficient_for_search = False
        assessment.clarification_context = (
            assessment.clarification_context
            or "The product category is not clear enough to search."
        )

    if assessment.missing_required_information:
        assessment.sufficient_for_search = False

    return assessment