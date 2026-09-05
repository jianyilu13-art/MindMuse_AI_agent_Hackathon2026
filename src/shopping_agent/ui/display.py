"""Presentation helpers shared by the web UI and future frontends."""

from __future__ import annotations

from typing import Any

from shopping_agent.agent.state import ShoppingState


def state_to_view(state: ShoppingState) -> dict[str, Any]:
    """Convert internal Pydantic/LangGraph state into frontend JSON."""

    requirements = state.get("requirements")
    requirement_data = (
        requirements.model_dump(mode="json") if requirements else None
    )

    ranked_by_id = {
        item.product.id: item
        for item in state.get("ranked_products", [])
    }

    products: list[dict[str, Any]] = []
    for product in state.get("displayed_products", []):
        item = ranked_by_id.get(product.id)
        product_data = product.model_dump(mode="json")
        product_data["score"] = item.score if item else None
        product_data["reasons"] = item.reasons if item else []
        products.append(product_data)

    return {
        "assistant_message": state.get("assistant_message"),
        "finished": state.get("finished", False),
        "awaiting_user_input": state.get("awaiting_user_input", False),
        "requirements": requirement_data,
        "missing_required_information": state.get(
            "missing_required_information",
            [],
        ),
        "optional_preferences": state.get("optional_preferences", []),
        "products": products,
        "search_result_status": state.get(
            "search_result_status",
            "not_searched",
        ),
        "display_offset": state.get("display_offset", 0),
        "total_results": len(state.get("ranked_products", [])),
        "last_error": state.get("last_error"),
        "community_feedback": {key: value.model_dump(mode="json") for key, value in state.get("community_feedback", {}).items()},
    }
