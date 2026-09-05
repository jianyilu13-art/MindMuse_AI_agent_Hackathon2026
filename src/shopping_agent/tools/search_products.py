"""Product-search interfaces and deterministic mock implementations."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from shopping_agent.schemas import (
    Product,
    ShoppingToolInput,
    UserRequirements,
)


class ProductSearchTool(Protocol):
    """Interface for marketplace product search."""

    def search(
        self,
        request: ShoppingToolInput,
    ) -> list[Product]:
        ...


def build_shopping_tool_input(
    requirements: UserRequirements,
) -> ShoppingToolInput:
    """Convert agent-owned requirements into the stable tool contract.

    Common constraints are copied into ``attributes`` because the Framework
    tool should not need to understand the agent's ``UserRequirements`` model.
    Values are JSON-compatible so the exact request can be logged or sent over
    an API without another conversion step.
    """

    attributes = dict(requirements.attributes)

    if requirements.size:
        attributes.setdefault("size", requirements.size)

    if requirements.max_price is not None:
        attributes["max_price"] = requirements.max_price

    if requirements.arrival_by is not None:
        attributes["arrival_by"] = requirements.arrival_by.isoformat()

    if requirements.preferred_brands:
        attributes.setdefault(
            "brand",
            (
                requirements.preferred_brands[0]
                if len(requirements.preferred_brands) == 1
                else requirements.preferred_brands
            ),
        )

    if requirements.preferred_platforms:
        attributes.setdefault(
            "platform",
            (
                requirements.preferred_platforms[0]
                if len(requirements.preferred_platforms) == 1
                else requirements.preferred_platforms
            ),
        )

    if requirements.must_have:
        attributes.setdefault("must_have", list(requirements.must_have))

    return ShoppingToolInput(
        category=requirements.category or requirements.query or "general",
        attributes=attributes,
    )


class MockProductSearchTool:
    """Return category-aware products for local development and tests."""

    def search(
        self,
        request: ShoppingToolInput | UserRequirements,
    ) -> list[Product]:
        if isinstance(request, UserRequirements):
            request = build_shopping_tool_input(request)

        category = request.category.strip().lower()

        query = str(
            request.attributes.get("query")
            or category.replace("_", " ")
            or "product"
        )

        if category in {
            "shoe",
            "shoes",
            "footwear",
            "running_shoes",
            "sneakers",
        }:
            return self._search_shoes(query)

        if category in {"food", "snack", "snacks", "groceries"}:
            return self._search_food(query)

        if category in {
            "laptop",
            "laptops",
            "computer",
            "computers",
            "notebook",
        }:
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
                    "sizes": ["37", "38", "40", "41", "42"],
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
                    "sizes": ["37", "39", "40", "41", "42"],
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
