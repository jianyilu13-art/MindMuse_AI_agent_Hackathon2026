"""Product review structures independent of any marketplace."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Review(BaseModel):
    product_id: str
    rating: float = Field(ge=1, le=5)
    text: str


class ReviewSummary(BaseModel):
    product_id: str
    sentiment: str = "unknown"
    highlights: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    available: bool = True
