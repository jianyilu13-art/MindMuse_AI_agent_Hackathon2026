"""LangGraph assembly for the Muse shopping agent.

    understand ──▶ ask ──▶ search ──▶ recommend ──▶ END
         │          │
         │          └─(needs a detail)──▶ END (wait for the user)
         ├─(chitchat)──▶ END
         └─(quit)──▶ END

One invocation = one user turn. The caller keeps the returned state and passes
it back with the next message, which is what gives the agent memory across
turns (`requirements` is patched, never rebuilt).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from . import nodes
from .routing import after_ask, after_understand
from .state import AgentState, initial_state


def build_graph():
    """Compile the shopping graph."""
    g = StateGraph(AgentState)

    g.add_node("understand", nodes.understand)
    g.add_node("ask", nodes.ask)
    g.add_node("search", nodes.search)
    g.add_node("recommend", nodes.recommend)
    g.add_node("chitchat", nodes.chitchat)

    g.add_edge(START, "understand")
    g.add_conditional_edges(
        "understand",
        after_understand,
        {"ask": "ask", "chitchat": "chitchat", "end": END},
    )
    g.add_conditional_edges(
        "ask", after_ask, {"wait": END, "search": "search"}
    )
    g.add_edge("search", "recommend")
    g.add_edge("recommend", END)
    g.add_edge("chitchat", END)

    return g.compile()


_GRAPH = None


def get_graph():
    """Compile once and reuse."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_turn(state: AgentState, message: str) -> AgentState:
    """Advance the conversation by one user turn and return the new state."""
    history = list(state.get("history", []))
    history.append({"role": "user", "content": message})

    incoming: AgentState = {**state, "message": message, "reply": "", "history": history}
    result: Any = get_graph().invoke(incoming)

    new_state: AgentState = {**incoming, **result}
    if new_state.get("reply"):
        history = list(new_state.get("history", []))
        history.append({"role": "assistant", "content": new_state["reply"]})
        new_state["history"] = history
    return new_state


__all__ = ["build_graph", "get_graph", "run_turn", "AgentState", "initial_state"]
