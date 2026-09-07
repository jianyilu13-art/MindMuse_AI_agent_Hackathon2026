"""Amazon API adapter template."""

from __future__ import annotations

import os

from shopping_agent.schemas import Product, Review

from .base import ShoppingPlatform


class AmazonPlatform(ShoppingPlatform):
    def __init__(self) -> None:
        self.api_key = os.getenv("AMAZON_API_KEY")
        self.base_url = os.getenv("AMAZON_BASE_URL")

    def search_products(self, query: str) -> list[Product]:
        """TODO: Call Amazon and map its response to ``Product`` values."""
        raise NotImplementedError("Amazon search API integration has not been implemented.")

    def fetch_reviews(self, product: Product) -> list[Review]:
        """TODO: Call Amazon and map its response to ``Review`` values."""
        raise NotImplementedError("Amazon review API integration has not been implemented.")

    def check_arrival(self, product: Product) -> str:
        """TODO: Look up Amazon delivery information."""
        raise NotImplementedError("Amazon arrival API integration has not been implemented.")

    def add_to_cart(self, product: Product) -> bool:
        """TODO: Add the product through the Amazon API."""
        raise NotImplementedError("Amazon cart API integration has not been implemented.")
