"""eBay API adapter template."""

from __future__ import annotations

import os

from shopping_agent.schemas import Product, Review

from .base import ShoppingPlatform


class EbayPlatform(ShoppingPlatform):
    def __init__(self) -> None:
        self.api_key = os.getenv("EBAY_API_KEY")
        self.base_url = os.getenv("EBAY_BASE_URL")

    def search_products(self, query: str) -> list[Product]:
        """TODO: Call eBay and map its response to ``Product`` values."""
        raise NotImplementedError("eBay search API integration has not been implemented.")

    def fetch_reviews(self, product: Product) -> list[Review]:
        """TODO: Call eBay and map its response to ``Review`` values."""
        raise NotImplementedError("eBay review API integration has not been implemented.")

    def check_arrival(self, product: Product) -> str:
        """TODO: Look up eBay delivery information."""
        raise NotImplementedError("eBay arrival API integration has not been implemented.")

    def add_to_cart(self, product: Product) -> bool:
        """TODO: Add the product through the eBay API."""
        raise NotImplementedError("eBay cart API integration has not been implemented.")
