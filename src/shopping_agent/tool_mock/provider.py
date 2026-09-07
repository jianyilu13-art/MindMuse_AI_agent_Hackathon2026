"""Mock implementation of the shared commerce tool boundary."""
from __future__ import annotations

from shopping_agent.schemas import Product, UserRequirements
from .catalog import products


class MockShoppingProvider:
    def __init__(self) -> None:
        self._catalogue = products()
        self._cart: list[str] = []

    def search_products(self, requirements: UserRequirements) -> list[Product]:
        words = set((requirements.query or "").lower().split())
        matches = []
        for product in self._catalogue:
            haystack = " ".join([product.title, product.description, *product.attributes.values()]).lower()
            if not words or any(word in haystack for word in words):
                matches.append(product.model_copy(deep=True))
        return matches

    def get_product_details(self, product_id: str) -> Product | None:
        return next((item.model_copy(deep=True) for item in self._catalogue if item.id == product_id), None)

    def check_stock(self, product_id: str) -> dict[str, int | bool | str]:
        product = self.get_product_details(product_id)
        if product is None:
            return {"found": False, "available": False, "stock": 0}
        return {"found": True, "available": product.available, "stock": product.stock}

    def add_to_cart(self, product_id: str) -> bool:
        product = self.get_product_details(product_id)
        if product is None or not product.available:
            return False
        self._cart.append(product_id)
        return True

    def view_cart(self) -> list[Product]:
        return [item for product_id in self._cart if (item := self.get_product_details(product_id))]
