"""End-to-end tests for dynamic product attributes and delivery filtering."""

from __future__ import annotations

from langgraph.graph import END

from shopping_agent.agent import (
    ShoppingServices,
    build_shopping_graph,
    initial_state,
)
from shopping_agent.agent.routing import next_action
from shopping_agent.tools import (
    MockAddToCartTool,
    MockProductSearchTool,
    MockReviewTool,
)
from tests.mocks.mock_semantics import ScriptedShoppingSemantics


def create_services() -> ShoppingServices:
    """Create deterministic services for integration tests."""

    return ShoppingServices(
        search=MockProductSearchTool(),
        reviews=MockReviewTool(),
        cart=MockAddToCartTool(),
        semantics=ScriptedShoppingSemantics(),
    )


def send_message(
    graph,
    state,
    message: str,
):
    """Send one user message through the existing graph state."""

    state.update(
        {
            "last_user_message": message,
            "input_status": "uninterpreted",
            "awaiting_user_input": False,
            "assistant_message": None,
        }
    )

    return graph.invoke(
        state,
        {
            "recursion_limit": 20,
        },
    )


def test_shoes_request_asks_for_shoe_specific_attribute() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want running shoes.",
    )

    assert state["product_category"] == "shoes"
    assert state["requirement_status"] == "incomplete"
    assert state["missing_dynamic_attributes"] == ["size"]
    assert state["awaiting_user_input"] is True
    assert "size" in state["assistant_message"].lower()


def test_food_request_asks_for_food_specific_attribute() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want snacks.",
    )

    assert state["product_category"] == "food"
    assert state["requirement_status"] == "incomplete"
    assert state["missing_dynamic_attributes"] == ["taste"]
    assert state["awaiting_user_input"] is True
    assert "taste" in state["assistant_message"].lower()


def test_shoe_attributes_allow_search_after_user_answers() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want running shoes.",
    )

    state = send_message(
        graph,
        state,
        (
            "I want running shoes, size 42, "
            "under $100, and they must arrive by September 5."
        ),
    )

    assert state["product_category"] == "shoes"
    assert state["requirements"] is not None
    assert state["requirements"].attributes["size"] == "42"
    assert state["requirements"].arrival_by is not None
    assert state["requirement_status"] == "ready"
    assert state["missing_dynamic_attributes"] == []
    assert state["search_result_status"] == "results"
    assert state["presentation_status"] == "displayed"


def test_arrival_deadline_filters_late_products() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        (
            "I want running shoes, size 42, "
            "under $200, and they must arrive by September 5."
        ),
    )

    assert state["search_completed"] is True
    assert state["requirements"] is not None
    assert state["requirements"].arrival_by is not None

    assert all(
        product.arrival_date is not None
        and product.arrival_date
        <= state["requirements"].arrival_by
        for product in state["qualified_products"]
    )

    assert "mock-shoe-2" not in {
        product.id
        for product in state["qualified_products"]
    }


def test_dynamic_attribute_filter_matches_product_attributes() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want running shoes, size 42, for running, under $200.",
    )

    assert state["requirements"] is not None
    assert state["requirements"].attributes["size"] == "42"
    assert state["requirements"].attributes["usage"] == "running"

    assert state["qualified_products"]

    for product in state["qualified_products"]:
        assert "42" in product.attributes["sizes"]
        assert "running" in product.attributes["usage"]


def test_more_results_does_not_trigger_a_new_search() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want running shoes, size 42, under $200.",
    )

    first_search_ids = [
        product.id
        for product in state["raw_products"]
    ]
    first_offset = state["display_offset"]

    state = send_message(
        graph,
        state,
        "Show me more.",
    )

    assert state["search_result_status"] == "results"
    assert state["raw_products"]
    assert [
        product.id
        for product in state["raw_products"]
    ] == first_search_ids
    assert state["display_offset"] >= first_offset


def test_purchase_uses_explicitly_selected_product() -> None:
    graph = build_shopping_graph(create_services())

    state = send_message(
        graph,
        initial_state(),
        "I want running shoes, size 42, under $200.",
    )

    state = send_message(
        graph,
        state,
        "I want the second one.",
    )

    assert state["purchase_status"] == "completed"
    assert state["cart_result"] is not None
    assert state["cart_result"].success is True
    assert state["cart_result"].cart_reference.startswith(
        "mock-cart-"
    )


def test_router_ends_when_waiting_for_user_input() -> None:
    state = initial_state()
    state["awaiting_user_input"] = True

    assert next_action(state) == "end"
    assert END == "__end__"