"""LangGraph assembly for the reactive shopping controller."""

from langgraph.graph import END, START, StateGraph

from .nodes import ShoppingNodes, ShoppingServices
from .routing import NextAction, next_action
from .state import ShoppingState


def build_shopping_graph(
    services: ShoppingServices | None = None,
):
    """Build and compile the reactive shopping graph."""

    nodes = ShoppingNodes(
        services=services or ShoppingServices.mock()
    )

    graph = StateGraph(ShoppingState)

    actions = {
        "interpret_user_input": nodes.interpret_user_input,
        "extract_requirements": nodes.extract_requirements,
        "ask_clarification": nodes.ask_clarification,
        "search_products": nodes.search_products,
        "fetch_reviews": nodes.fetch_reviews,
        "rank_products": nodes.rank_products,
        "display_results": nodes.display_results,
        "add_to_cart": nodes.add_to_cart,
        "terminate": nodes.terminate,
    }

    for action_name, action_node in actions.items():
        graph.add_node(action_name, action_node)

    path_map: dict[str, str] = {
        action_name: action_name
        for action_name in actions
    }
    path_map["end"] = END

    graph.add_conditional_edges(
        START,
        next_action,
        path_map,
    )

    for action_name in actions:
        graph.add_conditional_edges(
            action_name,
            next_action,
            path_map,
        )

    return graph.compile()