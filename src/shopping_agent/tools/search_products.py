"""Product-search interfaces and deterministic mock implementations."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from shopping_agent.schemas import Product, UserRequirements


class ProductSearchTool(Protocol):
    """Interface for marketplace product search."""

    def search(
        self,
        requirements: UserRequirements,
    ) -> list[Product]:
        ...


class MockProductSearchTool:
    """Return category-aware products for local development and tests."""

    def search(
        self,
        requirements: UserRequirements,
    ) -> list[Product]:
        category = (
            requirements.category or "general"
        ).strip().lower()

        query = requirements.query or "product"

        if category in {"shoe", "shoes", "footwear"}:
            return self._search_shoes(query)

        if category in {"food", "snack", "snacks"}:
            return self._search_food(query)

        if category in {"laptop", "laptops", "computer", "computers"}:
            return self._search_laptops(query)

        return self._search_general(query)

    def _search_shoes(
        self,
        query: str,
    ) -> list[Product]:
        return [
            Product(
                id="mock-shoe-1",
                title=f"{query.title()} Running Pro",
                price=79.99,
                platform="mock-market",
                url="https://example.test/products/shoe-1",
                rating=4.6,
                review_count=340,
                arrival_date=date(2026, 9, 2),
                attributes={
                    "brand": "Stride",
                    "sizes": ["40", "41", "42"],
                    "usage": ["running"],
                    "color": ["black"],
                    "material": ["mesh"],
                },
            ),
            Product(
                id="mock-shoe-2",
                title=f"{query.title()} Everyday",
                price=49.99,
                platform="mock-market",
                url="https://example.test/products/shoe-2",
                rating=4.2,
                review_count=112,
                arrival_date=date(2026, 9, 6),
                attributes={
                    "brand": "UrbanStep",
                    "sizes": ["41", "42", "43"],
                    "usage": ["walking", "casual"],
                    "color": ["white"],
                    "material": ["synthetic"],
                },
            ),
            Product(
                id="mock-shoe-3",
                title=f"{query.title()} Premium",
                price=149.99,
                platform="mock-market",
                url="https://example.test/products/shoe-3",
                rating=4.8,
                review_count=810,
                arrival_date=date(2026, 9, 1),
                attributes={
                    "brand": "Stride",
                    "sizes": ["39", "40", "41", "42"],
                    "usage": ["running", "training"],
                    "color": ["blue"],
                    "material": ["mesh", "foam"],
                },
            ),
        ]

    def _search_food(
        self,
        query: str,
    ) -> list[Product]:
        return [
            Product(
                id="mock-food-1",
                title=f"Spicy {query.title()} Mix",
                price=12.99,
                platform="mock-market",
                url="https://example.test/products/food-1",
                rating=4.5,
                review_count=210,
                arrival_date=date(2026, 9, 2),
                attributes={
                    "taste": ["spicy"],
                    "dietary_restrictions": ["vegetarian"],
                    "allergens": ["peanut"],
                    "package_size": "500g",
                },
            ),
            Product(
                id="mock-food-2",
                title=f"Sweet {query.title()} Mix",
                price=10.99,
                platform="mock-market",
                url="https://example.test/products/food-2",
                rating=4.3,
                review_count=145,
                arrival_date=date(2026, 9, 4),
                attributes={
                    "taste": ["sweet"],
                    "dietary_restrictions": ["vegetarian"],
                    "allergens": [],
                    "package_size": "400g",
                },
            ),
            Product(
                id="mock-food-3",
                title=f"Healthy {query.title()} Pack",
                price=18.99,
                platform="mock-market",
                url="https://example.test/products/food-3",
                rating=4.7,
                review_count=390,
                arrival_date=date(2026, 9, 7),
                attributes={
                    "taste": ["savory"],
                    "dietary_restrictions": ["vegan", "gluten_free"],
                    "allergens": [],
                    "package_size": "600g",
                },
            ),
        ]

    def _search_laptops(
        self,
        query: str,
    ) -> list[Product]:
        return [
            Product(
                id="mock-laptop-1",
                title=f"{query.title()} Developer",
                price=999.00,
                platform="mock-market",
                url="https://example.test/products/laptop-1",
                rating=4.7,
                review_count=510,
                arrival_date=date(2026, 9, 3),
                attributes={
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "usage": ["programming", "office"],
                    "processor": "M-series",
                },
            ),
            Product(
                id="mock-laptop-2",
                title=f"{query.title()} Creator",
                price=1499.00,
                platform="mock-market",
                url="https://example.test/products/laptop-2",
                rating=4.8,
                review_count=720,
                arrival_date=date(2026, 9, 6),
                attributes={
                    "ram_gb": 32,
                    "storage_gb": 1024,
                    "usage": ["programming", "video_editing"],
                    "processor": "M-series Pro",
                },
            ),
            Product(
                id="mock-laptop-3",
                title=f"{query.title()} Everyday",
                price=699.00,
                platform="mock-market",
                url="https://example.test/products/laptop-3",
                rating=4.2,
                review_count=180,
                arrival_date=date(2026, 9, 2),
                attributes={
                    "ram_gb": 8,
                    "storage_gb": 256,
                    "usage": ["office", "web_browsing"],
                    "processor": "Entry-level",
                },
            ),
        ]

    def _search_general(
        self,
        query: str,
    ) -> list[Product]:
        return [
            Product(
                id="mock-product-1",
                title=f"{query.title()} Standard",
                price=39.99,
                platform="mock-market",
                url="https://example.test/products/general-1",
                rating=4.2,
                review_count=100,
                arrival_date=date(2026, 9, 3),
                attributes={
                    "quality": ["standard"],
                },
            ),
            Product(
                id="mock-product-2",
                title=f"{query.title()} Premium",
                price=89.99,
                platform="mock-market",
                url="https://example.test/products/general-2",
                rating=4.6,
                review_count=240,
                arrival_date=date(2026, 9, 5),
                attributes={
                    "quality": ["premium"],
                },
            ),
        ]