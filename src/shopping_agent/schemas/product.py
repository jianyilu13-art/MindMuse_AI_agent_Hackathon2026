"""Product / candidate schema.

This is the shared spine of the pipeline. The `search` / `compare` tools (owned
by another teammate) produce a list of `Product` objects; the back-half tools
(recommendation / pickup / customer_service / cart) consume them.

Only the fields the back-half tools rely on are documented as required here.
Coordinate field names with the search/compare owner before locking this.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class Product(BaseModel):
    """A single candidate product returned by search/compare."""

    # --- identity (from search/compare) ---
    id: str = Field(..., description="Stable id, e.g. 'amazon:B0ABC123'")
    platform: str = Field(..., description="amazon | ebay | lazada | shopee")
    title: str
    url: str = Field(..., description="Canonical product page URL")
    image_url: Optional[str] = None

    # --- price (from search/compare, original currency) ---
    price: Decimal = Field(..., description="Item price in original currency")
    currency: str = Field("SGD", description="ISO currency code")
    shipping_cost: Decimal = Field(Decimal("0"), description="Shipping in same currency")

    # --- signals (from search/compare, may be missing) ---
    rating: Optional[float] = Field(None, description="0-5 average rating")
    review_count: Optional[int] = None
    ships_from: Optional[str] = None
    delivery_estimate: Optional[str] = Field(
        None, description="Raw delivery text, e.g. 'Ships in 2-4 days'"
    )

    # --- listing text (used by customer_service, may be missing) ---
    return_policy_text: Optional[str] = None
    warranty_text: Optional[str] = None
    description: Optional[str] = None

    # --- misc ---
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="brand, model, specs, etc."
    )
    raw: dict[str, Any] = Field(
        default_factory=dict, description="Original payload for debugging"
    )

    def total_price(self) -> Decimal:
        """Item + shipping, original currency. Assumes both are same currency."""
        return self.price + self.shipping_cost
