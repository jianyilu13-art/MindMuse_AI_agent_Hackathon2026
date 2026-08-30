"""pickup tool -- fulfilment / availability.

The four target platforms have no public store-pickup API, so this tool derives
availability from (a) delivery fields already on the listing and (b) a seeded
local inventory fixture that stands in for a retail-partner feed. The
listing-derived ship/locker paths are real; the store-pickup path is simulated
(state this honestly in the demo).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from shopping_agent.schemas import PickupInfo, PickupMethod, Product
from shopping_agent.tools._registry import tool

# Default location of the seeded inventory feed. Overridable in tests / config.
DEFAULT_INVENTORY_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "local_inventory.json"
)


# --------------------------------------------------------------------------
# date parsing
# --------------------------------------------------------------------------
def parse_target_date(text: str, *, today: Optional[date] = None) -> date:
    """Parse 'today' / 'tomorrow' / 'in N days' / ISO 'YYYY-MM-DD' relative to
    `today` (injectable for tests). Raises ValueError on unparseable input."""
    if text is None:
        raise ValueError("target date is None")
    today = today or date.today()
    s = text.strip().lower()

    if s in ("today", "now"):
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)

    m = re.fullmatch(r"in\s+(\d+)\s+days?", s)
    if m:
        return today + timedelta(days=int(m.group(1)))

    # ISO date
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    raise ValueError(f"could not parse target date: {text!r}")


# --------------------------------------------------------------------------
# delivery-estimate parsing (from listing text)
# --------------------------------------------------------------------------
def parse_delivery_days(delivery_estimate: Optional[str]) -> Optional[int]:
    """Pull a worst-case day count out of raw text like 'Ships in 2-4 days'.
    Returns the upper bound (conservative). None if nothing parseable."""
    if not delivery_estimate:
        return None
    nums = [int(n) for n in re.findall(r"\d+", delivery_estimate)]
    if not nums:
        return None
    return max(nums)


# --------------------------------------------------------------------------
# local inventory
# --------------------------------------------------------------------------
def _load_inventory(path: Optional[Path] = None) -> dict:
    path = path or DEFAULT_INVENTORY_PATH
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {"stores": [], "inventory": []}


def _store_pickup_candidate(product_id: str, inventory: dict, *, today: date) -> Optional[dict]:
    """Return the soonest in-stock store row for a product, or None."""
    rows = [
        r
        for r in inventory.get("inventory", [])
        if r.get("product_id") == product_id and r.get("in_stock")
    ]
    if not rows:
        return None
    best = min(rows, key=lambda r: r.get("ready_in_hours") or 0)
    stores = {s["store_id"]: s for s in inventory.get("stores", [])}
    store = stores.get(best.get("store_id"), {})
    ready_days = math.ceil((best.get("ready_in_hours") or 0) / 24)
    return {
        "ready_by": today + timedelta(days=ready_days),
        "location": store.get("location") or store.get("name"),
    }


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------
def check_pickup_availability(
    product: Product,
    target_date: date,
    location: str = "Singapore",
    *,
    today: Optional[date] = None,
    inventory: Optional[dict] = None,
) -> PickupInfo:
    """Pure core. Priority order:
      1. local inventory hit that can be ready by target_date -> store_pickup
      2. otherwise -> ship + ETA from listing (unavailable if later than target)
    Any error -> PickupInfo(method=ship, confidence=low, source='fallback').
    """
    today = today or date.today()
    try:
        inv = inventory if inventory is not None else _load_inventory()

        # 1. store pickup
        store = _store_pickup_candidate(product.id, inv, today=today)
        if store and store["ready_by"] <= target_date:
            return PickupInfo(
                product_id=product.id,
                platform=product.platform,
                method=PickupMethod.STORE_PICKUP,
                available_by=store["ready_by"],
                location=store["location"],
                confidence=0.85,
                source="local_inventory",
                note="Ready for in-store pickup (simulated partner feed).",
            )

        # 2. shipping, from listing text
        days = parse_delivery_days(product.delivery_estimate)
        if days is not None:
            eta = today + timedelta(days=days)
            if eta <= target_date:
                return PickupInfo(
                    product_id=product.id,
                    platform=product.platform,
                    method=PickupMethod.SHIP,
                    available_by=eta,
                    location=location,
                    confidence=0.7,
                    source="listing",
                    note=f"Estimated delivery in {days} days.",
                )
            return PickupInfo(
                product_id=product.id,
                platform=product.platform,
                method=PickupMethod.UNAVAILABLE,
                available_by=eta,
                location=location,
                confidence=0.7,
                source="listing",
                note=f"Earliest delivery ({eta.isoformat()}) is after the target date.",
            )

        # no delivery info at all -> can't confirm timing
        return PickupInfo(
            product_id=product.id,
            platform=product.platform,
            method=PickupMethod.SHIP,
            available_by=None,
            location=location,
            confidence=0.3,
            source="fallback",
            note="No delivery estimate on the listing; timing unknown.",
        )
    except Exception as exc:  # never break the agent loop
        return PickupInfo(
            product_id=getattr(product, "id", "unknown"),
            platform=getattr(product, "platform", "unknown"),
            method=PickupMethod.SHIP,
            available_by=None,
            confidence=0.1,
            source="fallback",
            note=f"pickup check failed: {exc}",
        )


@tool
def check_pickup(product_id: str, platform: str, date: str) -> str:
    """Check whether a product can be picked up / delivered by a given date.

    `date` may be natural language ('tomorrow', 'in 3 days') or ISO. Reads the
    product from shared state, writes a PickupInfo back, and returns a compact
    summary for the agent.
    """
    from shopping_agent.tools.context import get_session

    session = get_session()
    product = session.get_product(product_id)
    location = (
        session.requirements.shipping_location
        if session.requirements
        else "Singapore"
    )
    try:
        target = parse_target_date(date)
    except ValueError as exc:
        return f"Couldn't understand the date {date!r}: {exc}"

    info = check_pickup_availability(product, target_date=target, location=location)
    session.pickups[product_id] = info

    when = info.available_by.isoformat() if info.available_by else "unknown date"
    if info.method == PickupMethod.STORE_PICKUP:
        return f"Store pickup available by {when} at {info.location}."
    if info.method == PickupMethod.LOCKER:
        return f"Locker/collect available by {when}."
    if info.method == PickupMethod.UNAVAILABLE:
        return f"Not available by {date} — earliest is {when}. {info.note}"
    return f"Ships, arriving around {when}. {info.note}"
