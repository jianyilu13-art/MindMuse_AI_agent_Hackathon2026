"""Public agent API with lazy imports to keep submodules independent."""

__all__ = [
    "ShoppingServices",
    "ShoppingState",
    "build_shopping_graph",
    "initial_state",
]


def __getattr__(name: str):
    """Load public objects only when they are requested."""

    if name == "build_shopping_graph":
        from .graph import build_shopping_graph

        return build_shopping_graph

    if name == "ShoppingServices":
        from .nodes import ShoppingServices

        return ShoppingServices

    if name in {"ShoppingState", "initial_state"}:
        from .state import ShoppingState, initial_state

        return {
            "ShoppingState": ShoppingState,
            "initial_state": initial_state,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
