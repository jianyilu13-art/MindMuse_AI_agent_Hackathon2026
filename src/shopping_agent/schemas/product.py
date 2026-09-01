"""Product models used by search, filtering, ranking, and cart operations."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """A marketplace product with normalized dynamic attributes."""

    id: str
    title: str
    price: float = Field(ge=0)
    currency: str = "USD"
    platform: str
    url: str

    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    arrival_date: date | None = None

    # Product-specific data such as sizes, tastes, materials, and use cases.
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def normalize_attribute_keys(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize attribute names for reliable matching."""

        normalized: dict[str, Any] = {}

        for key, attribute_value in value.items():
            normalized_key = key.strip().lower().replace(" ", "_")
            normalized[normalized_key] = attribute_value

        return normalized


class RankedProduct(BaseModel):
    """A product enriched with a deterministic ranking score."""

    product: Product
    score: float
    reasons: list[str] = Field(default_factory=list)