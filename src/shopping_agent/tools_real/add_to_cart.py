"""Real cart orchestration routed through the product's platform adapter."""

from __future__ import annotations

from collections.abc import Callable

from shopping_agent.platforms import ShoppingPlatform, get_platform
from shopping_agent.schemas import Product
from shopping_agent.tools.add_to_cart import CartResult

PlatformResolver = Callable[[str], ShoppingPlatform]


def add_to_cart(product: Product, *, platform_resolver: PlatformResolver = get_platform) -> CartResult:
    """Add a product using its platform adapter and preserve the shared result schema."""
    added = platform_resolver(product.platform).add_to_cart(product)
    if added:
        return CartResult(success=True, message=f"Added {product.title} to the cart.")
    return CartResult(success=False, message=f"Could not add {product.title} to the cart.")


class RealAddToCartTool:
    def __init__(self, platform_resolver: PlatformResolver = get_platform) -> None:
        self.platform_resolver = platform_resolver

    def add(self, product: Product) -> CartResult:
        return add_to_cart(product, platform_resolver=self.platform_resolver)
