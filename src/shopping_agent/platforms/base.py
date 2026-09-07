"""Provider-independent contract for marketplace API adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shopping_agent.schemas import Product, Review


class ShoppingPlatform(ABC):
    """Operations a marketplace adapter must expose to the real tool layer."""

    @abstractmethod
    def search_products(self, query: str) -> list[Product]:
        """Search products on this platform."""
        raise NotImplementedError

    @abstractmethod
    def fetch_reviews(self, product: Product) -> list[Review]:
        """Fetch reviews for a product."""
        raise NotImplementedError

    @abstractmethod
    def check_arrival(self, product: Product) -> str:
        """Check estimated delivery information."""
        raise NotImplementedError

    @abstractmethod
    def add_to_cart(self, product: Product) -> bool:
        """Add a product to the platform cart."""
        raise NotImplementedError
