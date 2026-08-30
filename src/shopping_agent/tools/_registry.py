"""`@tool` decorator shim.

Uses langchain_core's `@tool` when available so the agent can bind these
directly. Falls back to a no-op decorator so the package imports and tests run
without langchain installed.
"""

from __future__ import annotations

try:  # pragma: no cover - exercised by environment, not tests
    from langchain_core.tools import tool  # type: ignore
except Exception:  # langchain not installed

    def tool(fn=None, **_kwargs):  # type: ignore
        """No-op stand-in for langchain_core.tools.tool."""

        def _wrap(f):
            return f

        return _wrap(fn) if callable(fn) else _wrap


__all__ = ["tool"]
