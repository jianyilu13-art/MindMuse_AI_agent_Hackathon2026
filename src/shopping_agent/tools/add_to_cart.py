from typing import Protocol

from pydantic import BaseModel

from shopping_agent.schemas import Product


class CartResult(BaseModel):
    success: bool
    message: str
    cart_reference: str | None = None


class AddToCartTool(Protocol):
    def add(self, product: Product) -> CartResult: ...


class MockAddToCartTool:
    def add(self, product: Product) -> CartResult:
        return CartResult(success=True, cart_reference=f"mock-cart-{product.id}", message=f"Added {product.title} to the mock cart.")
