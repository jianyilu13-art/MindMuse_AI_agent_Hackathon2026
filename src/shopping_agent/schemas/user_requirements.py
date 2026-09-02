"""Structured shopping requirements and the LLM's completeness assessment."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class UserRequirements(BaseModel):
    """Facts and preferences stated by the shopper (not inferred defaults)."""
    query: str | None = None
    size: str | None = None
    max_price: float | None = Field(default=None, gt=0)
    arrival_by: date | None = None
    must_have: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    preferred_platforms: list[str] = Field(default_factory=list)
    ranking_priorities: list[str] = Field(default_factory=list)
    no_preference_fields: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class RequirementAssessment(BaseModel):
    """LLM judgement about what this particular shopping task still needs."""

    sufficient_for_search: bool = False
    missing_required_information: list[str] = Field(default_factory=list)
    optional_preferences: list[str] = Field(default_factory=list)
    clarification_context: str | None = None
