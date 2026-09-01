"""Deterministic semantic adapter used by integration tests."""

from __future__ import annotations

from datetime import date
from typing import Any

from shopping_agent.llm.parsing import (
    InputInterpretation,
    RequirementExtraction,
    ShoppingSemantics,
)
from shopping_agent.schemas import (
    Product,
    ProductAttributeProposal,
    RequirementAssessment,
    UserRequirements,
)


class ScriptedShoppingSemantics(ShoppingSemantics):
    """Simulate structured LLM responses without calling Groq."""

    def interpret_input(
        self,
        message: str,
        requirements: UserRequirements | None,
        products: list[Product],
    ) -> InputInterpretation:
        normalized = message.lower().strip().rstrip(".!?")

        if normalized in {"exit", "quit", "finish", "done"}:
            return InputInterpretation(
                intent="finish",
                should_extract_requirements=False,
            )

        if normalized in {
            "more",
            "show me more",
            "show more",
            "more results",
        }:
            return InputInterpretation(
                intent="more_results",
                should_extract_requirements=False,
            )

        if "second" in normalized and products:
            selected_product_id = (
                products[1].id
                if len(products) > 1
                else products[0].id
            )

            return InputInterpretation(
                intent="purchase",
                selected_product_id=selected_product_id,
                should_extract_requirements=False,
            )

        if (
            "buy" in normalized
            or "purchase" in normalized
            or "cart" in normalized
        ):
            selected_product_id = _find_product_id(
                normalized,
                products,
            )

            return InputInterpretation(
                intent="purchase",
                selected_product_id=selected_product_id,
                should_extract_requirements=False,
            )

        return InputInterpretation(
            intent="change_requirements",
            should_extract_requirements=True,
        )

    def extract_requirements(
        self,
        message: str,
        current: UserRequirements | None,
    ) -> RequirementExtraction:
        normalized = message.lower()

        category = _detect_category(normalized)
        attributes: dict[str, Any] = {}

        if "size 42" in normalized or "size: 42" in normalized:
            attributes["size"] = "42"

        if "42" in normalized and category == "shoes":
            attributes["size"] = "42"

        if "spicy" in normalized:
            attributes["taste"] = "spicy"

        if "sweet" in normalized:
            attributes["taste"] = "sweet"

        if "vegetarian" in normalized:
            attributes["dietary_restrictions"] = ["vegetarian"]

        if "vegan" in normalized:
            attributes["dietary_restrictions"] = ["vegan"]

        if "programming" in normalized:
            attributes["usage"] = "programming"

        if "running" in normalized:
            attributes["usage"] = "running"

        max_price = _extract_price(normalized)
        arrival_by = _extract_arrival_date(normalized)

        requirements = UserRequirements(
            query=_extract_query(message),
            category=category,
            attributes=attributes,
            max_price=max_price,
            arrival_by=arrival_by,
        )

        if "size" in attributes:
            requirements.size = str(attributes["size"])

        suggested_attributes = _suggest_attributes(category)

        missing_required_information = [
            proposal.name
            for proposal in suggested_attributes
            if proposal.required
            and not _has_attribute(
                requirements,
                proposal.name,
            )
        ]

        assessment = RequirementAssessment(
            sufficient_for_search=(
                category is not None
                and not missing_required_information
            ),
            missing_required_information=(
                missing_required_information
            ),
            optional_preferences=[
                proposal.name
                for proposal in suggested_attributes
                if not proposal.required
                and not _has_attribute(
                    requirements,
                    proposal.name,
                )
            ],
            suggested_attributes=suggested_attributes,
            clarification_context=(
                f"More information is needed for {category}."
                if missing_required_information
                else None
            ),
        )

        return RequirementExtraction(
            requirements=requirements,
            assessment=assessment,
        )

    def write_clarification(
        self,
        assessment: RequirementAssessment,
        requirements: UserRequirements | None,
    ) -> str:
        category = (
            requirements.category
            if requirements and requirements.category
            else "this product"
        )

        missing = assessment.missing_required_information

        if not missing:
            return (
                "Could you share another requirement or preference?"
            )

        labels = {
            "size": "your size",
            "taste": "your preferred taste",
            "usage": "how you plan to use it",
            "max_price": "your maximum budget",
            "arrival_by": "your latest acceptable arrival date",
        }

        questions = [
            labels.get(attribute, attribute.replace("_", " "))
            for attribute in missing
        ]

        joined = ", ".join(questions)

        return (
            f"For {category}, could you provide {joined}?"
        )


def _detect_category(message: str) -> str | None:
    if any(
        word in message
        for word in ["shoe", "shoes", "sneaker", "running"]
    ):
        return "shoes"

    if any(
        word in message
        for word in ["food", "snack", "snacks", "meal"]
    ):
        return "food"

    if any(
        word in message
        for word in ["laptop", "computer", "notebook"]
    ):
        return "laptop"

    return None


def _suggest_attributes(
    category: str | None,
) -> list[ProductAttributeProposal]:
    if category == "shoes":
        return [
            ProductAttributeProposal(
                name="size",
                attribute_type="string",
                required=True,
                reason="Shoe size is required for a useful search.",
            ),
            ProductAttributeProposal(
                name="usage",
                attribute_type="string",
                required=False,
                reason="Usage improves shoe recommendations.",
            ),
        ]

    if category == "food":
        return [
            ProductAttributeProposal(
                name="taste",
                attribute_type="string",
                required=True,
                reason="Taste is important for food recommendations.",
            ),
            ProductAttributeProposal(
                name="dietary_restrictions",
                attribute_type="string_list",
                required=False,
                reason="Dietary restrictions improve safety.",
            ),
        ]

    if category == "laptop":
        return [
            ProductAttributeProposal(
                name="usage",
                attribute_type="string",
                required=True,
                reason="Usage determines the required laptop features.",
            ),
        ]

    return []


def _has_attribute(
    requirements: UserRequirements,
    attribute_name: str,
) -> bool:
    if attribute_name == "size":
        return bool(requirements.size)

    if attribute_name == "max_price":
        return requirements.max_price is not None

    if attribute_name == "arrival_by":
        return requirements.arrival_by is not None

    value = requirements.attributes.get(attribute_name)

    return value not in (None, "", [], {})


def _extract_price(message: str) -> float | None:
    tokens = message.replace("$", " ").split()

    for index, token in enumerate(tokens):
        if token in {"under", "below", "budget"}:
            if index + 1 >= len(tokens):
                continue

            candidate = tokens[index + 1].replace(",", "")

            try:
                return float(candidate)
            except ValueError:
                continue

    return None


def _extract_arrival_date(
    message: str,
) -> date | None:
    if "september 5" in message or "sep 5" in message:
        return date(2026, 9, 5)

    if "september 4" in message or "sep 4" in message:
        return date(2026, 9, 4)

    if "september 3" in message or "sep 3" in message:
        return date(2026, 9, 3)

    return None


def _extract_query(message: str) -> str:
    normalized = message.lower()

    if "shoe" in normalized or "sneaker" in normalized:
        return "running shoes"

    if "snack" in normalized or "food" in normalized:
        return "snacks"

    if "laptop" in normalized or "computer" in normalized:
        return "laptop"

    return message.strip()


def _find_product_id(
    message: str,
    products: list[Product],
) -> str | None:
    for product in products:
        if product.id.lower() in message:
            return product.id

    return None

def _merge_test_requirements(
    current: UserRequirements | None,
    patch: UserRequirements,
) -> UserRequirements:
    """Merge test requirements across multiple user turns."""

    if current is None:
        return patch

    merged = current.model_dump()
    patch_values = patch.model_dump()

    for field_name in [
        "query",
        "category",
        "size",
        "max_price",
        "arrival_by",
    ]:
        value = patch_values.get(field_name)

        if value is not None:
            merged[field_name] = value

    attributes = dict(merged.get("attributes") or {})
    attributes.update(patch_values.get("attributes") or {})

    if merged.get("size") is not None:
        attributes["size"] = merged["size"]

    if merged.get("size") is None and attributes.get("size"):
        merged["size"] = str(attributes["size"])

    merged["attributes"] = attributes

    for field_name in [
        "must_have",
        "preferred_brands",
        "preferred_platforms",
        "no_preference_fields",
    ]:
        values = patch_values.get(field_name) or []

        if values:
            merged[field_name] = values

    return UserRequirements.model_validate(merged)