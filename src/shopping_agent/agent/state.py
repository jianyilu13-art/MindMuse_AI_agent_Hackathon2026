"""Observable state for the LangGraph shopping agent.

Built on the unified contract (`UserRequirements`, `Product`,
`CustomerResponse`), so the graph, the tools and the UI all share one schema.
The state is what gives the agent memory: `requirements` persists across turns
and is *patched* by each turn rather than rebuilt.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

from shopping_agent.schemas import CustomerResponse, Product, UserRequirements

Intent = Literal["new_search", "refine", "answer", "chitchat", "quit"]


class AgentState(TypedDict, total=False):
    # conversation
    message: str                       # the current user turn
    history: list[dict[str, str]]      # [{role, content}, …]
    intent: Intent
    last_question: str                 # what we asked previously (for context)
    asked: list[str]                   # requirement fields already asked about
    reply: str                         # assistant text for this turn
    awaiting_input: bool
    finished: bool

    # remembered request (the memory)
    requirements: Optional[UserRequirements]

    # working data
    candidates: list[Product]
    response: Optional[CustomerResponse]
    session_id: str
    llm: Any
    error: Optional[str]


def initial_state(session_id: str = "default", llm: Any = None) -> AgentState:
    return {
        "message": "",
        "history": [],
        "intent": "new_search",
        "last_question": "",
        "asked": [],
        "reply": "",
        "awaiting_input": True,
        "finished": False,
        "requirements": None,
        "candidates": [],
        "response": None,
        "session_id": session_id,
        "llm": llm,
        "error": None,
    }
