"""User requirements + ranking weights.

Produced by the agent (parsing the user's request into structured form) and
consumed by the recommendation tool.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Weights(BaseModel):
    """How the user wants price / speed / preference traded off.

    Values are normalised to sum to 1.0 (see `normalized`).
    """

    price: float = 0.34
    speed: float = 0.33
    preference: float = 0.33

    def normalized(self) -> "Weights":
        total = self.price + self.speed + self.preference
        if total <= 0:
            # degenerate input -> equal weighting
            return Weights(price=1 / 3, speed=1 / 3, preference=1 / 3)
        return Weights(
            price=self.price / total,
            speed=self.speed / total,
            preference=self.preference / total,
        )


class UserRequirements(BaseModel):
    """Structured shopping request."""

    product_query: str = Field(..., description="What the user wants to buy")
    budget: Optional[Decimal] = Field(None, description="Max acceptable total price")
    currency: str = "SGD"
    deadline: Optional[date] = Field(None, description="Must arrive / be ready by")
    shipping_location: str = "Singapore"
    pickup_required: bool = Field(
        False, description="User needs in-store pickup / collect, not just delivery"
    )
    preferences: list[str] = Field(
        default_factory=list, description="Free-text prefs, e.g. ['USB-C', 'long battery']"
    )
    weights: Weights = Field(default_factory=Weights)
    max_results: int = 4

    @model_validator(mode="after")
    def _check(self) -> "UserRequirements":
        if self.max_results < 1:
            raise ValueError("max_results must be >= 1")
        return self
