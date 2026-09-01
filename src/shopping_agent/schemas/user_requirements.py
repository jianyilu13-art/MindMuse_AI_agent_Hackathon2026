"""Structured shopping requirements and dynamic product attribute proposals."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AttributeType = Literal[
    "string",
    "number",
    "boolean",
    "date",
    "string_list",
    "number_list",
]


class ProductAttributeProposal(BaseModel):
    """An attribute proposed by the LLM for the current product category."""

    name: str
    attribute_type: AttributeType = "string"
    required: bool = False
    reason: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class UserRequirements(BaseModel):
    """Facts and preferences stated by the shopper."""

    query: str | None = None
    category: str | None = None

    # Kept for backward compatibility with the original implementation.
    size: str | None = None

    # Dynamic category-specific attributes.
    attributes: dict[str, Any] = Field(default_factory=dict)

    # Common shopping constraints.
    max_price: float | None = Field(default=None, gt=0)
    arrival_by: date | None = None

    # Existing structured preferences.
    must_have: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    preferred_platforms: list[str] = Field(default_factory=list)
    no_preference_fields: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if not value:
            return None

        return value.strip().lower().replace(" ", "_")

    @field_validator("size")
    @classmethod
    def strip_size(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class RequirementAssessment(BaseModel):
    """LLM assessment of the current product requirements."""

    sufficient_for_search: bool = False
    missing_required_information: list[str] = Field(default_factory=list)
    optional_preferences: list[str] = Field(default_factory=list)

    suggested_attributes: list[ProductAttributeProposal] = Field(
        default_factory=list
    )

    clarification_context: str | None = None