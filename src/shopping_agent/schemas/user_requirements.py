"""Validated requirements supplied by a shopper."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class UserRequirements(BaseModel):
    query: str | None = None
    max_price: float | None = Field(default=None, gt=0)
    arrival_by: date | None = None
    must_have: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    preferred_platforms: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @property
    def missing_fields(self) -> list[str]:
        """Minimum information needed before the first marketplace search."""
        missing: list[str] = []
        if not self.query:
            missing.append("product or category")
        if self.max_price is None:
            missing.append("maximum budget")
        if not self.must_have and not self.preferred_brands:
            missing.append("required features or preferred brands")
        return missing
