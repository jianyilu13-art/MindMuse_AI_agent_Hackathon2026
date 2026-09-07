"""Provider-neutral product structures."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    title: str
    price: float = Field(ge=0)
    currency: str = "USD"
    platform: str
    url: str
    arrival_date: date | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    description: str = ""
    original_price: float | None = Field(default=None, ge=0)
    # Aggregated shopping search generally cannot verify inventory quantity.
    stock: int | None = Field(default=None, ge=0)
    available: bool = True
    image_url: str | None = None
    seller: str | None = None
    shipping_info: str | None = None
    promotion: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    # Provider payload is retained for traceability without making ranking depend on it.
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class RankedProduct(BaseModel):
    product: Product
    score: float
    reasons: list[str] = Field(default_factory=list)
