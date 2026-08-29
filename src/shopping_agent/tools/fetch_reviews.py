from typing import Protocol

from shopping_agent.schemas import Product, ReviewSummary


class ReviewTool(Protocol):
    def fetch(self, products: list[Product]) -> dict[str, ReviewSummary]: ...


class MockReviewTool:
    def fetch(self, products: list[Product]) -> dict[str, ReviewSummary]:
        return {
            product.id: ReviewSummary(
                product_id=product.id,
                sentiment="positive",
                highlights=["Reviewers praise comfort and value."],
                concerns=["Mock review data."],
            )
            for product in products
        }
