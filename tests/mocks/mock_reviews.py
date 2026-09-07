"""In-memory review source keyed by product identity."""

from shopping_agent.schemas import Product, ReviewSummary


class MockRunningShoeReviews:
    _reviews = {
        "nike-pegasus-41": ("positive", ["Very comfortable for long runs."], ["Slightly narrow for some runners."]),
        "asics-gel-cumulus-26": ("positive", ["Excellent comfort and durable outsole."], ["Warm in humid weather."]),
        "new-balance-1080v13": ("positive", ["Plush cushioning for recovery runs."], ["Higher price than comparable shoes."]),
        "adidas-ultraboost-light": ("mixed", ["Springy and stylish."], ["Less stable for long distances."]),
    }

    def fetch(self, products: list[Product]) -> dict[str, ReviewSummary]:
        return {
            product.id: ReviewSummary(product_id=product.id, sentiment=self._reviews[product.id][0], highlights=self._reviews[product.id][1], concerns=self._reviews[product.id][2])
            for product in products
        }
