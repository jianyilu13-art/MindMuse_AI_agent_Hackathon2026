"""Real delivery lookup routed through the product's platform adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from shopping_agent.platforms import ShoppingPlatform, get_platform
from shopping_agent.schemas import Product

PlatformResolver = Callable[[str], ShoppingPlatform]


def check_arrival(product: Product, *, platform_resolver: PlatformResolver = get_platform) -> str:
    """Return the provider's delivery estimate for a product."""
    return platform_resolver(product.platform).check_arrival(product)


class RealArrivalCheckTool:
    def __init__(self, platform_resolver: PlatformResolver = get_platform) -> None:
        self.platform_resolver = platform_resolver

    def check_arrival(self, product: Product) -> str:
        return check_arrival(product, platform_resolver=self.platform_resolver)

    def arrives_by(self, product: Product, deadline: date) -> bool:
        """Compatibility helper for the mock arrival-tool protocol.

        Platform adapters return their textual estimate; deterministic deadline
        filtering continues to use ``Product.arrival_date`` in the graph.
        """
        if product.arrival_date is None:
            return False
        return product.arrival_date <= deadline
