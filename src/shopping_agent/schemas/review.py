"""Review + review-summary schema.

`fetch_reviews` (front-half / shared) produces `Review` objects; the review
analysis step condenses them into a `ReviewSummary` that the recommendation
tool reads for the 'preference match' score.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Review(BaseModel):
    """A single raw review for a product."""

    product_id: str
    rating: Optional[float] = None
    text: str = ""
    author: Optional[str] = None


class ReviewSummary(BaseModel):
    """LLM-condensed view of many reviews for one product."""

    product_id: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    aspect_sentiment: dict[str, float] = Field(
        default_factory=dict,
        description="aspect -> sentiment in [-1, 1], e.g. {'battery': 0.8}",
    )
    sample_size: int = 0
    confidence: float = Field(0.0, description="0-1, low when few reviews")
    one_liner: str = ""
