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
    for product in state.get("visible_products", []):
        item = ranked_by_id.get(product.id)
        product_data = product.model_dump(mode="json")
        product_data["score"] = item.score if item else None
        product_data["reasons"] = item.reasons if item else []
        products.append(product_data)

    suggestions = []
    for proposal in state.get("suggested_attributes", []):
        value = _requirement_value(requirements, proposal.name)
        suggestions.append(
            {
                **proposal.model_dump(mode="json"),
                "provided": value not in (None, "", [], {}),
            }
        )

    search_input = state.get("search_tool_input")

    return {
        "assistant_message": state.get("assistant_message"),
        "finished": state.get("finished", False),
        "awaiting_user_input": state.get("awaiting_user_input", False),
        "product_category": state.get("product_category"),
        "requirements": requirement_data,
        "suggested_attributes": suggestions,
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
        "search_tool_input": (
            search_input.model_dump(mode="json")
            if search_input
            else None
        ),
        "last_error": state.get("last_error"),
    }


def _requirement_value(requirements, name: str):
    """Read a requirement value for the attribute status badge."""

    if requirements is None:
        return None

    if name == "size":
        return requirements.size or requirements.attributes.get("size")

    if name == "max_price":
        return requirements.max_price

    if name == "arrival_by":
        return requirements.arrival_by

    return requirements.attributes.get(name)
