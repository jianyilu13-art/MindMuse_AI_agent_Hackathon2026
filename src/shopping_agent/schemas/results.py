"""Output schemas produced by the back-half tools.

recommendation -> Recommendation
pickup         -> PickupInfo
customer_service -> CustomerServiceResult
cart           -> CartResult
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# recommendation
# --------------------------------------------------------------------------
class ScoreBreakdown(BaseModel):
    """Per-candidate scores, all normalised to 0-1 within the candidate set."""

    price_score: float = 0.0
    speed_score: float = 0.0
    preference_score: float = 0.0
    weighted_total: float = 0.0
    raw: dict[str, float] = Field(default_factory=dict, description="raw inputs, for debugging")


class RankedItem(BaseModel):
    product_id: str
    rank: int
    scores: ScoreBreakdown
    explanation: str = ""


class Recommendation(BaseModel):
    """Ranked shortlist + reason. `status='empty'` tells the agent to ask the
    user to relax constraints."""

    status: str = Field("ok", description="ok | empty")
    items: list[RankedItem] = Field(default_factory=list)
    reason: Optional[str] = Field(None, description="Why empty, if empty")


# --------------------------------------------------------------------------
# pickup
# --------------------------------------------------------------------------
class PickupMethod(str, Enum):
    STORE_PICKUP = "store_pickup"
    LOCKER = "locker"
    SHIP = "ship"
    UNAVAILABLE = "unavailable"


class PickupInfo(BaseModel):
    product_id: str
    platform: str
    method: PickupMethod
    available_by: Optional[date] = Field(None, description="Earliest ready/arrival date")
    location: Optional[str] = Field(None, description="Store / locker location, if any")
    confidence: float = Field(0.5, description="0-1")
    source: str = Field("", description="e.g. 'local_inventory' | 'listing' | 'fallback'")
    note: str = ""

    def meets_deadline(self, deadline: Optional[date]) -> bool:
        if self.method == PickupMethod.UNAVAILABLE:
            return False
        if deadline is None or self.available_by is None:
            return True
        return self.available_by <= deadline


# --------------------------------------------------------------------------
# customer_service
# --------------------------------------------------------------------------
class PolicySummary(BaseModel):
    returns: Optional[str] = None
    warranty: Optional[str] = None
    shipping_terms: Optional[str] = None


class CustomerServiceResult(BaseModel):
    """Whatever subset of the service capabilities the request triggered."""

    product_id: str
    intent: str = Field("", description="policy | question | checklist | other")
    policy: Optional[PolicySummary] = None
    drafted_question: Optional[str] = None
    checklist: list[str] = Field(default_factory=list)
    note: str = ""


# --------------------------------------------------------------------------
# cart
# --------------------------------------------------------------------------
class CartStatus(str, Enum):
    PREPARED = "prepared"     # deep link ready, user completes checkout
    UNSUPPORTED = "unsupported"  # platform has no add-to-cart link; plain URL given


class CartLine(BaseModel):
    product_id: str
    title: str = ""
    quantity: int = 1
    unit_price: Optional[Decimal] = None


class CartResult(BaseModel):
    """We never actually check out on a third-party platform; we prepare a
    handoff link and never claim an order was placed."""

    status: CartStatus
    platform: str
    checkout_url: str = Field("", description="Deep link the user opens to review & pay")
    lines: list[CartLine] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    currency: str = "SGD"
    next_step_instructions: str = ""
