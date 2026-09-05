"""Session context adapter for the back-half tools.

The `@tool` entrypoints take small arguments (ids, short strings) — never the
full candidate list — and read/write the heavy objects here instead. This is a
deliberately thin, in-memory stand-in so the tools run end-to-end today against
fixtures.

When the agent team lands real LangGraph state, only THIS file changes: point
`get_session` at the graph state. The tool signatures and core logic stay put.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

from shopping_agent.schemas import (
    CartResult,
    CustomerResponse,
    CustomerServiceResult,
    PickupInfo,
    Product,
    Recommendation,
    ReviewSummary,
    UserRequirements,
)


@dataclass
class Session:
    """Everything the back-half tools share for one shopping conversation."""

    session_id: str
    requirements: Optional[UserRequirements] = None
    candidates: dict[str, Product] = field(default_factory=dict)
    review_summaries: dict[str, ReviewSummary] = field(default_factory=dict)
    pickups: dict[str, PickupInfo] = field(default_factory=dict)
    recommendation: Optional[Recommendation] = None
    cs_results: dict[str, CustomerServiceResult] = field(default_factory=dict)
    cart_results: dict[str, CartResult] = field(default_factory=dict)
    customer_response: Optional[CustomerResponse] = None
    llm: Any = None  # FakeLLM in tests; real provider (Groq) later. None -> deterministic fallbacks.

    def add_candidates(self, products: list[Product]) -> None:
        for p in products:
            self.candidates[p.id] = p

    def get_product(self, product_id: str) -> Product:
        try:
            return self.candidates[product_id]
        except KeyError:
            raise KeyError(f"product {product_id!r} not in session {self.session_id!r}")


_STORE: dict[str, Session] = {}
_CURRENT: ContextVar[Optional[str]] = ContextVar("current_session", default=None)


def new_session(session_id: str = "default", **kwargs: Any) -> Session:
    """Create (or reset) a session and make it current."""
    session = Session(session_id=session_id, **kwargs)
    _STORE[session_id] = session
    _CURRENT.set(session_id)
    return session


def set_current(session_id: str) -> None:
    if session_id not in _STORE:
        raise KeyError(f"no such session {session_id!r}")
    _CURRENT.set(session_id)


def get_session(session_id: Optional[str] = None) -> Session:
    """Resolve a session by id, or the current one if id is None."""
    sid = session_id or _CURRENT.get()
    if sid is None:
        raise RuntimeError(
            "no active session — call new_session(...) or pass session_id"
        )
    if sid not in _STORE:
        raise KeyError(f"no such session {sid!r}")
    return _STORE[sid]


def clear_all() -> None:
    """Test helper: wipe the store."""
    _STORE.clear()
    _CURRENT.set(None)
