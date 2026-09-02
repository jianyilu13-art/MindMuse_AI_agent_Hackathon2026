"""Shopee API adapter template.

Teammates should implement this class without changing the agent or real tools.
"""

from __future__ import annotations

import os

from shopping_agent.schemas import Product, Review

from .base import ShoppingPlatform


class ShopeePlatform(ShoppingPlatform):
    def __init__(self) -> None:
        self.api_key = os.getenv("SHOPEE_API_KEY")
        self.base_url = os.getenv("SHOPEE_BASE_URL")

    def search_products(self, query: str) -> list[Product]:
        """TODO: Call Shopee and map its response to ``Product`` values."""
        raise NotImplementedError("Shopee search API integration has not been implemented.")

    def fetch_reviews(self, product: Product) -> list[Review]:
        """TODO: Call Shopee and map its response to ``Review`` values."""
        raise NotImplementedError("Shopee review API integration has not been implemented.")

    def check_arrival(self, product: Product) -> str:
        """TODO: Look up Shopee delivery information."""
        raise NotImplementedError("Shopee arrival API integration has not been implemented.")

    def add_to_cart(self, product: Product) -> bool:
        """TODO: Add the product through the Shopee API."""
        raise NotImplementedError("Shopee cart API integration has not been implemented.")
