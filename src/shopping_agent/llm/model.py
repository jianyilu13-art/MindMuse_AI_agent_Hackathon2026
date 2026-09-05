"""Groq LLM provider behind the project's `structured(tag, prompt, schema)`
interface — the same one `FakeLLM` implements, so every caller (tools, agent
nodes) is provider-agnostic and testable without network.

`get_llm()` returns a provider when GROQ_API_KEY is configured, else None. A
None llm makes every caller fall back to its deterministic path, so the app
still runs with no key.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of a model response (handles ```json
    fences and stray prose around the object)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM response contained no JSON object")
    return match.group(0)


class GroqLLM:
    """Structured-output wrapper around Groq chat completions."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, temperature: float = 0.2):
        from groq import Groq  # imported lazily so the package stays optional

        self._client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def structured(self, tag: str, prompt: str, schema: Type[T]) -> T:
        """Ask the model for JSON matching `schema` and validate it.
        Raises on failure — callers catch and fall back deterministically."""
        system = (
            "You are a precise shopping assistant. Reply with ONLY a JSON object "
            "matching this JSON schema — no prose, no code fences:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        return schema.model_validate_json(_extract_json(content))


def get_llm() -> Optional[Any]:
    """The configured LLM, or None when no key is set (deterministic mode)."""
    from shopping_agent.config import load_env

    load_env()
    key = os.getenv("GROQ_API_KEY") or None
    if not key:
        return None
    try:
        return GroqLLM(key)
    except Exception:
        return None  # never let provider setup break the app
