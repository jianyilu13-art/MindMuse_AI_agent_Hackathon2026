"""Structured-output helper + a fake LLM for tests.

Wraps an LLM call so callers get a validated pydantic object back (with a
repair/retry on malformed output). `FakeLLM` lets the whole back-half be tested
with no network and no cost: it returns canned structured objects keyed by a
tag you pass in.
"""

from __future__ import annotations

from typing import Any, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    """Deterministic stand-in. `responses` maps a tag -> the object (or dict)
    to return from `structured(...)`."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []  # (tag, prompt) for assertions

    def structured(self, tag: str, prompt: str, schema: Type[T]) -> T:
        self.calls.append((tag, prompt))
        if tag not in self.responses:
            raise KeyError(f"FakeLLM has no canned response for tag {tag!r}")
        value = self.responses[tag]
        return value if isinstance(value, schema) else schema.model_validate(value)


def structured_output(llm: Any, tag: str, prompt: str, schema: Type[T]) -> T:
    """Call `llm` and coerce its output into `schema`.

    Any provider exposing `.structured(tag, prompt, schema)` works — `FakeLLM`
    in tests, `GroqLLM` (see `llm.model`) in production.
    """
    if hasattr(llm, "structured"):
        return llm.structured(tag, prompt, schema)
    raise TypeError(f"llm {type(llm).__name__} has no .structured(tag, prompt, schema)")
