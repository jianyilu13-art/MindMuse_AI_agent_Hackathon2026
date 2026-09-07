"""Successful in-memory cart adapter."""

from shopping_agent.schemas import Product
from shopping_agent.tools.add_to_cart import CartResult


class MockCart:
    def add(self, product: Product) -> CartResult:
        return CartResult(success=True, cart_reference=f"test-cart-{product.id}", message=f"Added {product.title} to the test cart.")
