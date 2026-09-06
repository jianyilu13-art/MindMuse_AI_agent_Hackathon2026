"""Curated recommendation tiers shown above the normal ranked results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .product import Product


class BestPick(BaseModel):
    tier: Literal["overall", "value", "upgrade"]
    product: Product
    match_pct: int = Field(ge=0, le=100)
    match_label: str
    headline: str
    reasons: list[str] = Field(default_factory=list)
