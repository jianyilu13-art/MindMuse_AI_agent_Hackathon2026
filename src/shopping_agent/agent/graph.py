"""LangGraph assembly for the reactive shopping controller."""

from langgraph.graph import END, START, StateGraph

from .nodes import ShoppingNodes, ShoppingServices
from .routing import NextAction, next_action
from .state import ShoppingState


def build_shopping_graph(services: ShoppingServices | None = None):
    """Build a graph that re-evaluates `next_action` after every node."""
    nodes = ShoppingNodes(services or ShoppingServices.from_environment())
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
    for name, node in actions.items():
        graph.add_node(name, node)

    path_map = {name: name for name in actions}
    path_map["end"] = END
    graph.add_conditional_edges(START, next_action, path_map)
    for name in actions:
        graph.add_conditional_edges(name, next_action, path_map)
    return graph.compile()
