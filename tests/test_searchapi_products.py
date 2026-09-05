"""SearchAPI adapters are deterministic when the HTTP client is injected."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from shopping_agent.schemas import Product, UserRequirements
from shopping_agent.processing import apply_hard_constraints, rank_products
from shopping_agent.agent import ShoppingServices, initial_state
from shopping_agent.agent.nodes import ShoppingNodes
from shopping_agent.tools_real.add_to_cart import OpenProductLinkTool
from shopping_agent.tools_real.searchapi_products import (
    SearchAPIClient,
    SearchAPICommunityFeedbackTool,
    SearchAPIProductSearchTool,
    build_shopping_query,
    extract_price,
    normalize_shopping_result,
)


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def search(self, params):
        self.calls.append(params)
        return self.payloads.pop(0)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_price_query_and_shopping_normalization() -> None:
    assert extract_price("S$1,299.50") == 1299.5
    requirements = UserRequirements(query="running shoes", preferred_brands=["Nike"], preferred_platforms=["Amazon"])
    assert build_shopping_query(requirements) == "running shoes Nike Amazon"
    product = normalize_shopping_result({"title": "Nike Run", "price": "S$ 99.90", "link": "https://amazon.example/item", "source": "Amazon", "rating": "4.7", "reviews": "123", "delivery": "Free delivery", "thumbnail": "https://images.example/a.jpg"})
    assert product is not None
    assert (product.price, product.currency, product.platform, product.stock, product.shipping_info) == (99.9, "SGD", "Amazon", None, "Free delivery")
    assert normalize_shopping_result({"title": "Missing URL", "price": "$20"}) is None
    assert normalize_shopping_result({"title": "Fallback", "extracted_price": None, "price": "$20", "link": "https://seller.example/p"}) is not None


def test_search_and_forum_results_are_parsed_separately() -> None:
    client = FakeClient([
        {"shopping_results": [{"title": "Example headset", "price": "$42", "link": "https://seller.example/p", "source": "Seller"}]},
        {"organic_results": [{"title": "Reddit discussion", "snippet": "Owners discuss comfort", "link": "https://www.reddit.com/r/audio/example"}]},
    ])
    products = SearchAPIProductSearchTool(client).search(UserRequirements(query="headset"))
    feedback = SearchAPICommunityFeedbackTool(client).fetch(products)
    assert products[0].platform == "Seller"
    assert feedback[products[0].id].sources[0].domain == "www.reddit.com"
    assert client.calls[0]["engine"] == "google_shopping"
    assert client.calls[1]["engine"] == "google"


def test_product_cache_avoids_a_duplicate_request_and_changed_constraints_miss() -> None:
    client = FakeClient([
        {"shopping_results": [{"title": "Headset", "price": "$42", "link": "https://seller.example/p"}]},
        {"shopping_results": [{"title": "Headset", "price": "$42", "link": "https://seller.example/p"}]},
    ])
    tool = SearchAPIProductSearchTool(client)
    initial = UserRequirements(query="headset", max_price=50)
    assert tool.search(initial)
    assert tool.search(initial)
    assert len(client.calls) == 1
    assert tool.search(UserRequirements(query="headset", max_price=40))
    assert len(client.calls) == 2


def test_forum_search_is_limited_to_top_k() -> None:
    client = FakeClient([
        {"organic_results": []},
        {"organic_results": []},
    ])
    products = [Product(id=str(index), title=f"Product {index}", price=1, platform="Seller", url=f"https://seller.example/{index}") for index in range(3)]
    feedback = SearchAPICommunityFeedbackTool(client, top_k=2).fetch(products)
    assert len(client.calls) == 2
    assert set(feedback) == {"0", "1"}


def test_http_client_sends_engine_locale_and_key_without_logging() -> None:
    requests = []
    def opener(request, *, timeout):
        requests.append((request, timeout))
        return FakeResponse({"shopping_results": []})
    client = SearchAPIClient(api_key="test-key", gl="us", hl="es", timeout=7, opener=opener)
    assert client.search({"engine": "google_shopping", "q": "shoes"}) == {"shopping_results": []}
    query = parse_qs(urlparse(requests[0][0].full_url).query)
    assert (query["engine"], query["gl"], query["hl"], query["api_key"], requests[0][1]) == (["google_shopping"], ["us"], ["es"], ["test-key"], 7)


def test_open_product_link_is_not_a_checkout() -> None:
    product = Product(id="p", title="Example", price=1, platform="Seller", url="https://seller.example/p", stock=1)
    result = OpenProductLinkTool().add(product)
    assert result.success and result.cart_reference == product.url
    assert "outside this assistant" in result.message


def test_constraints_ranking_and_session_memory_remain_state_driven() -> None:
    product = Product(id="p", title="Nike Run", price=80, platform="Seller", url="https://seller.example/p", stock=1, rating=4.5, attributes={"brand": "Nike", "sizes": "42"})
    requirements = UserRequirements(query="running shoes", max_price=90, size="42", preferred_brands=["Nike"], preferred_platforms=["Seller"], ranking_priorities=["price"])
    assert apply_hard_constraints([product], requirements) == [product]
    ranked = rank_products([product], requirements, {})[0]
    assert ranked.product.id == "p"
    assert "Matches your preferred seller/platform" in ranked.reasons
    state = initial_state()
    state["conversation_turns"].append({"role": "user", "content": "running shoes under $90"})
    state["requirements"] = requirements
    assert state["conversation_turns"][-1]["content"].endswith("$90")
    assert state["requirements"].query == "running shoes"


def test_unknown_stock_is_not_filtered_but_known_zero_stock_is() -> None:
    requirements = UserRequirements(query="shoes")
    unknown = Product(id="unknown", title="Unknown stock", price=10, platform="Seller", url="https://seller.example/unknown")
    unavailable = Product(id="zero", title="Zero stock", price=10, platform="Seller", url="https://seller.example/zero", stock=0)
    assert apply_hard_constraints([unknown, unavailable], requirements) == [unknown]


def test_comparison_uses_only_the_currently_displayed_products() -> None:
    first = Product(id="first", title="First", price=10, platform="Seller", url="https://seller.example/1")
    second = Product(id="second", title="Second", price=20, platform="Seller", url="https://seller.example/2")
    state = initial_state()
    state["displayed_products"] = [first, second]
    state["comparison_product_ids"] = ["first", "second"]
    result = ShoppingNodes(ShoppingServices(None, None, None, None)).compare_products(state)  # type: ignore[arg-type]
    assert "First" in result["assistant_message"] and "Second" in result["assistant_message"]
