"""Interfaces for optional LLM trade-off explanations after deterministic ranking."""

from typing import Protocol

from shopping_agent.schemas import RankedProduct, UserRequirements


class RankingExplainer(Protocol):
    def explain(self, products: list[RankedProduct], requirements: UserRequirements) -> dict[str, list[str]]: ...
