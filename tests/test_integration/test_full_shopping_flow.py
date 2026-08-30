"""End-to-end state-driven flows using test-only external and LLM adapters."""

from __future__ import annotations

from langgraph.graph import END

from shopping_agent.agent import ShoppingServices, build_shopping_graph, initial_state
from shopping_agent.agent.routing import next_action
from tests.mocks.mock_cart import MockCart
from tests.mocks.mock_reviews import MockRunningShoeReviews
from tests.mocks.mock_search import MockRunningShoeSearch
from tests.mocks.mock_semantics import ScriptedShoppingSemantics


def services() -> ShoppingServices:
    return ShoppingServices(MockRunningShoeSearch(), MockRunningShoeReviews(), MockCart(), ScriptedShoppingSemantics())


def send(graph, state, message: str):
    state.update(last_user_message=message, input_status="uninterpreted", awaiting_user_input=False, assistant_message=None)
    return graph.invoke(state, {"recursion_limit": 20})


def test_missing_requirements_then_search_reviews_rank_and_display() -> None:
    graph = build_shopping_graph(services())
    state = send(graph, initial_state(), "I want running shoes.")
    assert state["requirement_status"] == "incomplete"
    assert state["awaiting_user_input"] is True
    assert "size" in state["assistant_message"].lower()

    state = send(graph, state, "Size 42, any brand, under $100.")
    assert state["requirement_status"] == "ready"
    assert state["search_result_status"] == "results"
    assert state["review_status"] == "completed"
    assert state["ranking_status"] == "completed"
    assert state["presentation_status"] == "displayed"
    assert state["ranked_products"]

    # Paging is a presentation transition, not a fresh search.
    state["display_offset"] = 0
    state["page_size"] = 1
    state = send(graph, state, "Show me more.")
    assert state["search_result_status"] == "results"
    assert state["presentation_status"] == "displayed"


def test_no_results_requests_change_then_searches_again() -> None:
    graph = build_shopping_graph(services())
    state = send(graph, initial_state(), "I want running shoes under $20, size 42.")
    assert state["search_completed"] is True
    assert state["search_result_status"] == "no_results"
    assert state["qualified_products"] == []
    assert state["awaiting_user_input"] is True
    assert "increase" in state["assistant_message"].lower()

    state = send(graph, state, "Okay, increase it to $80.")
    assert state["search_result_status"] == "results"
    assert state["presentation_status"] == "displayed"


def test_requirement_change_and_purchase_take_different_routes() -> None:
    graph = build_shopping_graph(services())
    state = send(graph, initial_state(), "I want running shoes under $20, size 42.")
    state = send(graph, state, "Okay, increase it to $80.")

    state = send(graph, state, "Actually, I want something cheaper under $90.")
    assert state["requirements"].max_price == 90
    assert state["search_result_status"] == "results"

    state = send(graph, state, "I want the second one.")
    assert state["purchase_status"] == "completed"
    assert state["cart_result"].success is True
    assert state["cart_result"].cart_reference.startswith("test-cart-")


def test_router_only_returns_declared_actions_and_ends_waiting_turns() -> None:
    state = initial_state()
    state["awaiting_user_input"] = True
    assert next_action(state) == "end"
    assert END == "__end__"
