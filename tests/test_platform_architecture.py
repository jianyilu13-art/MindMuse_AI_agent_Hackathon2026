"""Unit tests for provider boundaries; no external API credentials are needed."""

from __future__ import annotations

from datetime import date

import pytest

from shopping_agent.llm.model import GroqModel
from shopping_agent.platforms import PLATFORMS, ShoppingPlatform, get_platform
from shopping_agent.schemas import Product, Review, UserRequirements
from shopping_agent.tools import MockAddToCartTool, MockProductSearchTool
from shopping_agent.tools_real import RealAddToCartTool, RealProductSearchTool, fetch_reviews


class FakePlatform(ShoppingPlatform):
    def __init__(self) -> None:
        self.product = Product(
            id="fake-1", title="Fake item", price=10, platform="fake", url="https://fake.test/1",
            arrival_date=date(2026, 9, 2),
        )

    def search_products(self, query: str) -> list[Product]:
        return [self.product]

    def fetch_reviews(self, product: Product) -> list[Review]:
        return [Review(product_id=product.id, rating=5, text="Works well")]

    def check_arrival(self, product: Product) -> str:
        return "2026-09-02"

    def add_to_cart(self, product: Product) -> bool:
        return True


def test_registered_platforms_implement_the_common_interface() -> None:
    assert set(PLATFORMS) == {"shopee", "lazada", "amazon", "ebay"}
    assert all(isinstance(get_platform(name), ShoppingPlatform) for name in PLATFORMS)


def test_registry_rejects_unknown_platform() -> None:
    with pytest.raises(ValueError, match="Unsupported shopping platform"):
        get_platform("unknown")


def test_mock_tools_remain_usable() -> None:
    product = MockProductSearchTool().search(UserRequirements(query="headphones"))[0]
    assert MockAddToCartTool().add(product).success is True


def test_real_tools_route_through_injected_platform_adapter() -> None:
    platform = FakePlatform()
    resolver = lambda name: platform
    products = RealProductSearchTool(resolver).search(UserRequirements(query="item", preferred_platforms=["fake"]))
    assert products == [platform.product]
    assert fetch_reviews(platform.product, platform_resolver=resolver)[0].text == "Works well"
    assert RealAddToCartTool(resolver).add(platform.product).success is True


def test_groq_model_can_be_configured_without_a_key_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    model = GroqModel(model="test-model", temperature=0, max_tokens=12)
    assert (model.model, model.temperature, model.max_tokens, model.client) == ("test-model", 0, 12, None)


def test_user_requirements_validation_and_normalization() -> None:
    requirements = UserRequirements(query="  running shoes  ", max_price=100, ranking_priorities=["price"])
    assert requirements.query == "running shoes"
    assert requirements.ranking_priorities == ["price"]
    with pytest.raises(ValueError):
        UserRequirements(max_price=0)
