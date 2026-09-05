"""LLM-backed conversion of shopper messages into structured state."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Literal, Protocol

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
        response = _ask_json(
            self.model,
            INPUT_INTERPRETATION_PROMPT.format(
                message=message,
                current_requirements=(
                    requirements.model_dump(mode="json")
                    if requirements
                    else {}
                ),
                products=[
                    product.model_dump(mode="json") for product in products
                ],
            ),
        )

        interpretation = InputInterpretation.model_validate(
            _json_object(response)
        )

        if (
            interpretation.intent in {"search", "change_requirements", "clarify"}
            and not interpretation.should_extract_requirements
        ):
            interpretation.should_extract_requirements = True

        return interpretation

    def extract_requirements(
        self,
        message: str,
        current: UserRequirements | None,
    ) -> RequirementExtraction:
        response = _ask_json(
            self.model,
            REQUIREMENT_EXTRACTION_PROMPT.format(
                message=message,
                current_requirements=(
                    current.model_dump(mode="json") if current else {}
                ),
            ),
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
        response = _ask_json(
            self.model,
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
            ),
        )

        value = _json_object(response).get("clarification_question")

        if isinstance(value, str) and value.strip():
            return value.strip()

        return "Could you share a little more so I can search accurately?"


class RuleBasedShoppingSemantics:
    """Small offline fallback used when a Groq key is not configured.

    This is deliberately limited to keeping the demo usable. A configured
    application always selects :class:`GroqShoppingSemantics` instead.
    """

    def interpret_input(
        self,
        message: str,
        requirements: UserRequirements | None,
        products: list[Product],
    ) -> InputInterpretation:
        normalized = message.lower().strip().rstrip(".!?")

        if normalized in {"exit", "quit", "finish", "done"}:
            return InputInterpretation(intent="finish")

        if normalized in {
            "more",
            "show me more",
            "show more",
            "more results",
        }:
            return InputInterpretation(intent="more_results")

        selected_product_id = _find_product_id(normalized, products)

        if "second" in normalized or "2nd" in normalized:
            if len(products) > 1:
                selected_product_id = products[1].id
            elif products:
                selected_product_id = products[0].id

        if any(
            token in normalized
            for token in {"buy", "purchase", "cart", "add"}
        ):
            return InputInterpretation(
                intent="purchase",
                selected_product_id=selected_product_id,
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
        category = _detect_category(normalized) or (
            current.category if current else None
        )

        if normalized.strip() in {
            "relax",
            "change requirements",
            "change my requirements",
        }:
            requirements = current or UserRequirements(category=category)
            return RequirementExtraction(
                requirements=requirements,
                assessment=RequirementAssessment(
                    sufficient_for_search=False,
                    missing_required_information=[
                        "a requirement to relax or change"
                    ],
                    clarification_context=(
                        "The shopper wants to change the current search."
                    ),
                ),
            )

        attributes = _extract_attributes(normalized, category)
        size = attributes.get("size")
        max_price = _extract_price(normalized)
        arrival_by = _extract_arrival_date(normalized)
        no_preferences = _extract_no_preferences(normalized)

        requirements = UserRequirements(
            query=_fallback_query(message, category, current),
            category=category,
            attributes=attributes,
            max_price=max_price,
            arrival_by=arrival_by,
            no_preference_fields=no_preferences,
        )

        if size is not None:
            requirements.size = str(size)

        requirements = _merge_requirements(current, requirements)
        suggestions = _default_attribute_proposals(category or "")
        missing = [
            proposal.name
            for proposal in suggestions
            if proposal.required
            and not _has_requirement_value(requirements, proposal.name)
        ]

        if not requirements.category:
            missing.insert(0, "category")

        return RequirementExtraction(
            requirements=requirements,
            assessment=RequirementAssessment(
                sufficient_for_search=bool(
                    requirements.category and not missing
                ),
                missing_required_information=list(dict.fromkeys(missing)),
                optional_preferences=[
                    proposal.name
                    for proposal in suggestions
                    if not proposal.required
                    and not _has_requirement_value(
                        requirements,
                        proposal.name,
                    )
                ],
                suggested_attributes=suggestions,
                clarification_context=(
                    f"More information is needed for {category}."
                    if missing
                    else None
                ),
            ),
        )

    def write_clarification(
        self,
        assessment: RequirementAssessment,
        requirements: UserRequirements | None,
    ) -> str:
        missing = assessment.missing_required_information

        if "a requirement to relax or change" in missing:
            return (
                "Which requirement would you like to relax or change? "
                "For example, you can change the size, budget, color, or style."
            )

        labels = {
            "category": "the product you want to buy",
            "size": "your size",
            "taste": "your preferred taste",
            "usage": "how you plan to use it",
            "max_price": "your maximum budget",
            "arrival_by": "your latest acceptable arrival date",
        }
        requested = [
            labels.get(item, item.replace("_", " "))
            for item in missing
        ]

        if not requested:
            return "Could you share another requirement or preference?"

        category = (
            requirements.category.replace("_", " ")
            if requirements and requirements.category
            else "this product"
        )
        return f"For {category}, could you provide {', '.join(requested)}?"


def _ask_json(model: GroqModel, prompt: str) -> str:
    """Ask for JSON while remaining compatible with simple test doubles."""

    try:
        return model.ask(prompt, json_mode=True)
    except TypeError:
        # Older injected model doubles may not expose the optional keyword.
        return model.ask(prompt)


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
        attributes = dict(patch.attributes)

        if patch.size is not None:
            attributes.setdefault("size", patch.size)
        elif attributes.get("size") is not None:
            patch.size = str(attributes["size"])

        for field_name in patch.no_preference_fields:
            attributes.pop(field_name, None)
            if field_name == "size":
                patch.size = None
            elif field_name == "max_price":
                patch.max_price = None
            elif field_name == "arrival_by":
                patch.arrival_by = None

        patch.attributes = attributes
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
    patch_attributes = patch_values.get("attributes") or {}
    merged_attributes.update(patch_attributes)
    merged["attributes"] = merged_attributes

    if patch_attributes.get("size") is not None and patch_values.get("size") is None:
        merged["size"] = str(patch_attributes["size"])

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

        if field_name == "size":
            merged["size"] = None
        elif field_name == "max_price":
            merged["max_price"] = None
        elif field_name == "arrival_by":
            merged["arrival_by"] = None

    return UserRequirements.model_validate(merged)


def _normalize_assessment(
    assessment: RequirementAssessment,
    requirements: UserRequirements,
) -> RequirementAssessment:
    """Ensure assessment fields are consistent with extracted requirements."""

    if not assessment.suggested_attributes and requirements.category:
        assessment.suggested_attributes = _default_attribute_proposals(
            requirements.category
        )

    suggested_names = {
        proposal.name for proposal in assessment.suggested_attributes
    }

    missing = []

    for name in assessment.missing_required_information:
        if name in suggested_names or name in {
            "category",
            "max_price",
            "arrival_by",
        }:
            missing.append(name)

    for proposal in assessment.suggested_attributes:
        if proposal.required and not _has_requirement_value(
            requirements,
            proposal.name,
        ):
            missing.append(proposal.name)

    assessment.missing_required_information = list(dict.fromkeys(missing))

    if requirements.category is None:
        if "category" not in assessment.missing_required_information:
            assessment.missing_required_information.insert(0, "category")
        assessment.sufficient_for_search = False
        assessment.clarification_context = (
            assessment.clarification_context
            or "The product category is not clear enough to search."
        )

    if assessment.missing_required_information:
        assessment.sufficient_for_search = False

    assessment.optional_preferences = [
        proposal.name
        for proposal in assessment.suggested_attributes
        if not proposal.required
        and not _has_requirement_value(requirements, proposal.name)
    ]

    return assessment


def _has_requirement_value(
    requirements: UserRequirements,
    name: str,
) -> bool:
    """Check whether a requirement is explicitly available or waived."""

    if name in requirements.no_preference_fields:
        return True

    if name == "category":
        return bool(requirements.category)

    if name == "size":
        return bool(
            requirements.size
            or requirements.attributes.get("size")
        )

    if name == "max_price":
        return requirements.max_price is not None

    if name == "arrival_by":
        return requirements.arrival_by is not None

    value = requirements.attributes.get(name)
    return value not in (None, "", [], {})


def _default_attribute_proposals(
    category: str,
) -> list[ProductAttributeProposal]:
    """Keep the conversation useful if a model omits the proposal list."""

    normalized = category.lower().replace(" ", "_")

    if normalized in {
        "shoe",
        "shoes",
        "footwear",
        "running_shoes",
        "sneakers",
    }:
        return [
            ProductAttributeProposal(
                name="size",
                required=True,
                reason="Shoe size is essential for fit.",
            ),
            ProductAttributeProposal(
                name="style",
                required=False,
                reason="Style helps distinguish running, casual, and formal shoes.",
            ),
            ProductAttributeProposal(
                name="color",
                required=False,
                reason="Color narrows the visual preference.",
            ),
            ProductAttributeProposal(
                name="material",
                required=False,
                reason="Material affects comfort and durability.",
            ),
        ]

    if normalized in {"food", "snack", "snacks", "groceries"}:
        return [
            ProductAttributeProposal(
                name="taste",
                required=True,
                reason="Taste is important for a useful food recommendation.",
            ),
            ProductAttributeProposal(
                name="dietary_restrictions",
                required=False,
                reason="Dietary restrictions can improve safety and fit.",
            ),
            ProductAttributeProposal(
                name="allergens_to_avoid",
                required=False,
                reason="Allergen information can prevent unsuitable options.",
            ),
        ]

    if normalized in {
        "laptop",
        "laptops",
        "computer",
        "computers",
        "notebook",
    }:
        return [
            ProductAttributeProposal(
                name="usage",
                required=True,
                reason="Usage determines the required performance and features.",
            ),
            ProductAttributeProposal(
                name="ram_gb",
                attribute_type="number",
                required=False,
                reason="RAM affects multitasking performance.",
            ),
            ProductAttributeProposal(
                name="storage_gb",
                attribute_type="number",
                required=False,
                reason="Storage affects how many files and apps you can keep.",
            ),
        ]

    return []


def _detect_category(message: str) -> str | None:
    """Detect common demo categories for the offline fallback."""

    if any(
        token in message
        for token in ("shoe", "sneaker", "footwear", "running")
    ):
        return "shoes"

    if any(
        token in message
        for token in ("food", "snack", "meal", "grocer")
    ):
        return "food"

    if any(
        token in message
        for token in ("laptop", "computer", "notebook")
    ):
        return "laptop"

    return None


def _extract_attributes(
    message: str,
    category: str | None,
) -> dict[str, Any]:
    """Extract a small set of obvious values for the offline fallback."""

    attributes: dict[str, Any] = {}

    size_match = re.search(
        r"(?:size|eu|us)\s*[:=-]?\s*(\d{1,3}(?:\.\d+)?)",
        message,
    )
    if size_match:
        attributes["size"] = size_match.group(1)
    elif category == "shoes":
        standalone_size = re.fullmatch(
            r"\s*(\d{2}(?:\.\d+)?)\s*",
            message,
        )
        if standalone_size:
            attributes["size"] = standalone_size.group(1)

    known_values = {
        "usage": (
            "running",
            "walking",
            "casual",
            "training",
            "programming",
            "office",
            "gaming",
            "travel",
        ),
        "style": (
            "running",
            "casual",
            "formal",
            "athletic",
            "minimalist",
        ),
        "color": (
            "black",
            "white",
            "blue",
            "red",
            "green",
            "purple",
            "pink",
            "grey",
            "gray",
        ),
        "material": (
            "mesh",
            "leather",
            "foam",
            "synthetic",
            "cotton",
            "wool",
        ),
        "taste": (
            "spicy",
            "sweet",
            "salty",
            "savory",
            "savoury",
            "sour",
        ),
        "brand": (
            "nike",
            "adidas",
            "asics",
            "puma",
            "new balance",
            "apple",
            "lenovo",
            "dell",
        ),
    }

    for attribute_name, candidates in known_values.items():
        for candidate in candidates:
            if candidate in message:
                attributes[attribute_name] = candidate
                break

    dietary = [
        value
        for value in ("vegan", "vegetarian", "gluten-free", "gluten_free")
        if value in message
    ]
    if dietary:
        attributes["dietary_restrictions"] = dietary

    ram_match = re.search(r"(?:ram|memory)\s*[:=-]?\s*(\d+)\s*gb", message)
    if ram_match:
        attributes["ram_gb"] = int(ram_match.group(1))

    storage_match = re.search(
        r"storage\s*[:=-]?\s*(\d+)\s*gb",
        message,
    )
    if storage_match:
        attributes["storage_gb"] = int(storage_match.group(1))

    return attributes


def _extract_price(message: str) -> float | None:
    """Extract a maximum price from common shopping phrasing."""

    match = re.search(
        r"(?:under|below|less\s+than|up\s+to|budget(?:\s+of)?|max(?:imum)?(?:\s+price)?)"
        r"\s*[:=-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)",
        message,
    )

    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_arrival_date(message: str) -> date | None:
    """Extract ISO or simple month-day arrival deadlines."""

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1))
        except ValueError:
            return None

    month_names = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    for month_name, month_number in month_names.items():
        match = re.search(
            rf"\b{month_name[:3]}(?:[a-z]+)?\s+(\d{{1,2}})\b",
            message,
        )
        if not match:
            continue

        try:
            return date(date.today().year, month_number, int(match.group(1)))
        except ValueError:
            return None

    return None


def _extract_no_preferences(message: str) -> list[str]:
    """Record explicit user waivers such as ``any color is fine``."""

    names = {
        "size",
        "style",
        "color",
        "material",
        "brand",
        "usage",
        "taste",
    }
    found: list[str] = []

    for name in names:
        if (
            f"any {name}" in message
            or f"no preference for {name}" in message
            or f"don't care about {name}" in message
            or f"do not care about {name}" in message
        ):
            found.append(name)

    return sorted(found)


def _fallback_query(
    message: str,
    category: str | None,
    current: UserRequirements | None,
) -> str:
    """Produce a stable query for the local product source."""

    if category == "shoes":
        return "running shoes" if "running" in message else "shoes"

    if category == "food":
        return "snacks" if "snack" in message else "food"

    if category == "laptop":
        return "laptop"

    if current and current.query:
        return current.query

    return message.strip()


def _find_product_id(
    message: str,
    products: list[Product],
) -> str | None:
    """Find an explicit product identifier in a user message."""

    for product in products:
        if product.id.lower() in message:
            return product.id

    return None
