"""Front-half search adapter: query building + normalisation to unified Product."""

from __future__ import annotations

from decimal import Decimal

from shopping_agent.schemas import UserRequirements
from shopping_agent.tools.search import build_query, normalize, search_products


RAW = [
    {
        "title": "Nike Pegasus, cushioned",
        "source": "Amazon.sg",
        "link": "https://amazon.sg/dp/B0X",
        "asin": "B0X",
        "thumbnail": "https://img/x.jpg",
        "extracted_price": 139.0,
        "rating": 4.5,
        "reviews": 800,
        "delivery": "Free delivery",
    },
    {
        "title": "Adidas Duramo",
        "source": "Lazada",
        "link": "https://lazada.sg/d",
        "price": "S$89.00",
        "rating": 4.2,
        "reviews": 210,
        "delivery": "+S$3.90 delivery",
    },
    {"title": "No price row", "source": "X"},  # dropped: no price
]


def test_normalize_to_unified_product():
    products = normalize(RAW)
    assert len(products) == 2  # priceless row dropped

    nike = products[0]
    assert isinstance(nike.price, Decimal) and nike.price == Decimal("139")
    assert nike.currency == "SGD"
    assert nike.image_url == "https://img/x.jpg"      # top-level, not in attributes
    assert nike.platform == "Amazon.sg"                # seller name preserved
    assert nike.attributes.get("asin") == "B0X"
    assert nike.shipping_cost == Decimal("0")          # free delivery


def test_delivery_cost_is_not_read_as_time():
    # '+S$3.90 delivery' must NOT become '90 days'; it's a cost note.
    duramo = normalize(RAW)[1]
    assert duramo.delivery_estimate is None
    assert duramo.attributes.get("delivery_note") == "+S$3.90 delivery"
    assert duramo.shipping_cost == Decimal("3.90")


def test_delivery_time_is_kept_as_estimate():
    products = normalize([
        {"title": "T", "source": "S", "extracted_price": 10, "delivery": "Get it by Tomorrow"},
        {"title": "U", "source": "S", "extracted_price": 10, "delivery": "Delivery in 2-3 days"},
    ])
    assert products[0].delivery_estimate == "Get it by Tomorrow"
    assert products[1].delivery_estimate == "Delivery in 2-3 days"


def test_build_query_combines_fields():
    reqs = UserRequirements(
        product_query="running shoes",
        size="42",
        preferred_brands=["Nike"],
        attributes={"color": "black"},
    )
    q = build_query(reqs).lower()
    assert "running shoes" in q and "size 42" in q and "nike" in q and "black" in q


def test_offline_search_uses_fixture(monkeypatch):
    # no API key -> offline fixture path, still returns real Products
    monkeypatch.delenv("SEARCHAPI_API_KEY", raising=False)
    products = search_products(UserRequirements(product_query="running shoes"))
    assert products and all(p.price > 0 for p in products)
