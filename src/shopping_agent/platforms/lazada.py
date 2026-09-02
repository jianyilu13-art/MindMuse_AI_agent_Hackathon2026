"""Lazada API adapter template."""

from __future__ import annotations

import os

from shopping_agent.schemas import Product, Review

from .base import ShoppingPlatform


class LazadaPlatform(ShoppingPlatform):
    def __init__(self) -> None:
        self.api_key = os.getenv("LAZADA_API_KEY")
        self.base_url = os.getenv("LAZADA_BASE_URL")

    def search_products(self, query: str) -> list[Product]:
        """TODO: Call Lazada and map its response to ``Product`` values."""
        raise NotImplementedError("Lazada search API integration has not been implemented.")

    def fetch_reviews(self, product: Product) -> list[Review]:
        """TODO: Call Lazada and map its response to ``Review`` values."""
        raise NotImplementedError("Lazada review API integration has not been implemented.")

    def check_arrival(self, product: Product) -> str:
        """TODO: Look up Lazada delivery information."""
        raise NotImplementedError("Lazada arrival API integration has not been implemented.")

    def add_to_cart(self, product: Product) -> bool:
        """TODO: Add the product through the Lazada API."""
        raise NotImplementedError("Lazada cart API integration has not been implemented.")
