"""Interfaces for optional semantic review analysis."""

from typing import Protocol

from shopping_agent.schemas import Review, ReviewSummary


class ReviewAnalyzer(Protocol):
    def summarize(self, product_id: str, reviews: list[Review]) -> ReviewSummary: ...
