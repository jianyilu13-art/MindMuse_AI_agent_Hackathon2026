"""Real review retrieval routed through the product's platform adapter."""

from __future__ import annotations

from collections.abc import Callable

from shopping_agent.platforms import ShoppingPlatform, get_platform
from shopping_agent.schemas import Product, Review, ReviewSummary

PlatformResolver = Callable[[str], ShoppingPlatform]


def fetch_reviews(product: Product, *, platform_resolver: PlatformResolver = get_platform) -> list[Review]:
    """Fetch provider-neutral reviews for one product."""
    return platform_resolver(product.platform).fetch_reviews(product)


class RealReviewTool:
    """Graph-compatible review tool; semantic review analysis remains an LLM concern."""

    def __init__(self, platform_resolver: PlatformResolver = get_platform) -> None:
        self.platform_resolver = platform_resolver

    def fetch_reviews(self, product: Product) -> list[Review]:
        return fetch_reviews(product, platform_resolver=self.platform_resolver)

    def fetch(self, products: list[Product]) -> dict[str, ReviewSummary]:
        """Expose raw review availability without inventing an LLM summary.

        The graph's existing review-tool contract returns summaries.  Until a review
        analysis service is configured, this preserves the reviews' presence while
        keeping all provider response handling in the platform adapter.
        """
        summaries: dict[str, ReviewSummary] = {}
        for product in products:
            reviews = self.fetch_reviews(product)
            summaries[product.id] = ReviewSummary(
                product_id=product.id,
                available=bool(reviews),
            )
        return summaries
