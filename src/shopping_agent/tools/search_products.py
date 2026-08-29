from __future__ import annotations

from datetime import date
from typing import Protocol

from shopping_agent.schemas import Product, UserRequirements


class ProductSearchTool(Protocol):
    def search(self, requirements: UserRequirements) -> list[Product]: ...


class MockProductSearchTool:
    """Replace with a marketplace aggregator once API adapters are available."""

    def search(self, requirements: UserRequirements) -> list[Product]:
        query = requirements.query or "product"
        return [
            Product(id="mock-headphones-1", title=f"{query.title()} Pro Wireless", price=79.99,
                    platform="mock-market", url="https://example.test/products/1", rating=4.6,
                    review_count=340, arrival_date=date(2026, 9, 2), attributes={"features": "wireless noise cancelling"}),
            Product(id="mock-headphones-2", title=f"{query.title()} Everyday", price=49.99,
                    platform="mock-market", url="https://example.test/products/2", rating=4.2,
                    review_count=112, arrival_date=date(2026, 9, 5), attributes={"features": "wireless lightweight"}),
            Product(id="mock-headphones-3", title=f"{query.title()} Premium", price=149.99,
                    platform="mock-market", url="https://example.test/products/3", rating=4.8,
                    review_count=810, arrival_date=date(2026, 9, 1), attributes={"features": "wireless noise cancelling"}),
        ]
