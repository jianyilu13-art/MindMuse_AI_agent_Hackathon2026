"""Small, provider-specific wrapper around Groq chat completions.

Keep all Groq setup in this module so the rest of the shopping agent only has
to pass prompts and consume text responses.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from time import monotonic
from typing import Literal, TypedDict

from dotenv import load_dotenv
from groq import APIError, Groq


logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    """A message in a chat-completion conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


class GroqModel:
    """Generate shopping-assistant responses with a Groq-hosted model."""

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1_024,
        client: Groq | None = None,
    ) -> None:
        load_dotenv()
        self.model = model or os.getenv("GROQ_MODEL")
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = client
        self.api_key = os.getenv("GROQ_API_KEY")

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        """Return the model's text answer for a complete conversation."""
        if self.client is None:
            if not self.api_key:
                raise ValueError(
                    "GROQ_API_KEY is missing. Add it to a .env file or set it in your shell."
                )
            if not self.model:
                raise ValueError("GROQ_MODEL is missing. Set it in .env to a Groq model available to your account.")
            self.client = Groq(api_key=self.api_key, timeout=30.0, max_retries=2)
        started = monotonic()
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=list(messages),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except APIError as error:
                raise RuntimeError(f"Groq request failed: {error}") from error

            content = response.choices[0].message.content
            if content:
                logger.info("shopping_timing operation=groq_completion elapsed_ms=%.1f", (monotonic() - started) * 1000)
                return content
            if attempt == 0:
                logger.warning("Groq returned empty content; retrying once.")

        raise RuntimeError("Groq returned an empty response after retrying.")

    def ask(self, prompt: str, *, system_prompt: str | None = None) -> str:
        """Convenience method for a single shopping-related prompt."""
        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.complete(messages)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a response from an explicit system and user prompt pair."""
        return self.ask(user_prompt, system_prompt=system_prompt)


DEFAULT_SHOPPING_SYSTEM_PROMPT = """You are a helpful shopping assistant.
Ask a short follow-up question when a requirement is missing. Never invent
product prices, stock, shipping dates, or review scores; use only product data
provided to you."""
