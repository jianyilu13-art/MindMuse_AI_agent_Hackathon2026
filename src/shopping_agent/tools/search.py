"""search -- front-half product search, adapted to the unified contract.

Wraps the SearchAPI.io / Google Shopping approach (one API, all sellers) and
normalises every result into the *unified* Product schema (Decimal price,
top-level image_url / delivery_estimate, seller name as platform).

Runs in two modes so the whole pipeline is testable with no network / no key:
  - SEARCHAPI_API_KEY set  -> real Google Shopping search
  - otherwise              -> a seeded offline fixture (same normalisation path)

Owned by the front-half teammate; this file is the integration-ready version
that produces exactly what the back-half tools consume.
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from shopping_agent.schemas import Product, UserRequirements

SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
_OFFLINE_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "searchapi_results.json"
)


# --------------------------------------------------------------------------
# query building
# --------------------------------------------------------------------------
def build_query(reqs: UserRequirements) -> str:
    """Turn structured requirements into a shopping search string."""
    parts: list[str] = []
    if reqs.product_query:
        parts.append(reqs.product_query)
    elif reqs.category:
        parts.append(reqs.category.replace("_", " "))
    if reqs.size:
        parts.append(f"size {reqs.size}")
    parts.extend(reqs.preferred_brands)
    for name, value in reqs.attributes.items():
        if value is None or name in reqs.no_preference_fields:
            continue
        readable = name.replace("_", " ")
        if isinstance(value, (list, tuple, set)):
            value = " ".join(str(v) for v in value)
        parts.append(f"{readable} {value}")
    return " ".join(str(p) for p in parts).strip()


# --------------------------------------------------------------------------
# raw fetch (real API or offline fixture)
# --------------------------------------------------------------------------
def _fetch_raw(query: str, api_key: Optional[str]) -> list[dict[str, Any]]:
    if not api_key:
        try:
            data = json.loads(_OFFLINE_FIXTURE.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        return data.get("shopping_results", [])

    import requests  # lazy: only needed for the real path

    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": api_key,
        "gl": "sg",
        "hl": "en",
    }
    resp = requests.get(SEARCHAPI_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("shopping_results", [])


# --------------------------------------------------------------------------
# normalisation -> unified Product
# --------------------------------------------------------------------------
def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _safe_float(value: Any) -> Optional[float]:
    d = _to_decimal(value)
    return float(d) if d is not None else None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(re.sub(r"[^\d]", "", str(value)) or 0)
    except (TypeError, ValueError):
        return None


def _shipping_from_delivery(delivery: Any) -> Decimal:
    """Google Shopping puts 'Free delivery' / '+S$4.90 delivery' in `delivery`."""
    if not delivery:
        return Decimal("0")
    text = str(delivery).lower()
    if "free" in text:
        return Decimal("0")
    amount = _to_decimal(delivery)
    return amount if amount is not None else Decimal("0")


def _split_delivery(delivery: Any) -> tuple[Optional[str], Optional[str]]:
    """Google Shopping's `delivery` field mixes two unrelated things: a *time*
    ('Get it by Tomorrow', 'Delivery in 2-3 days') and a *cost* ('Free delivery',
    '+S$3.90 delivery'). Only a time belongs in `delivery_estimate` — feeding a
    cost string to the day-parser turns '+S$3.90' into '90 days'. Returns
    (time_estimate, cost_note)."""
    if not delivery:
        return None, None
    text = str(delivery).strip()
    low = text.lower()
    is_cost = "$" in text or "free" in low
    is_time = any(w in low for w in ("day", "tomorrow", "week", "month", "arriv", "get it"))
    if is_time and not is_cost:
        return text, None
    return None, text


def normalize(raw_results: list[dict[str, Any]]) -> list[Product]:
    """Convert raw Google Shopping rows into unified Product objects."""
    products: list[Product] = []
    for index, item in enumerate(raw_results):
        title = item.get("title")
        price = _to_decimal(item.get("extracted_price") or item.get("price"))
        if not title or price is None:
            continue

        pid = str(
            item.get("product_id")
            or item.get("product_token")
            or item.get("position")
            or f"searchapi-{index}"
        )
        platform = str(item.get("source") or item.get("seller") or "Google Shopping")
        url = item.get("link") or item.get("product_link") or ""
        image_url = item.get("thumbnail") or item.get("image")
        delivery = item.get("delivery")

        delivery_estimate, delivery_note = _split_delivery(delivery)

        attributes: dict[str, Any] = {}
        if item.get("extensions"):
            attributes["extensions"] = item["extensions"]
        if delivery_note:
            attributes["delivery_note"] = delivery_note
        # keep an ASIN if the source exposes one (enables the real add-to-cart link)
        if item.get("asin"):
            attributes["asin"] = item["asin"]

        products.append(
            Product(
                id=pid,
                platform=platform,
                title=str(title),
                url=str(url),
                image_url=image_url,
                price=price,
                currency="SGD",
                shipping_cost=_shipping_from_delivery(delivery),
                rating=_safe_float(item.get("rating")),
                review_count=_safe_int(item.get("reviews") or item.get("review_count")),
                delivery_estimate=delivery_estimate,
                attributes=attributes,
                raw=item,
            )
        )
    return products


# --------------------------------------------------------------------------
# public entrypoint
# --------------------------------------------------------------------------
def search_products(
    reqs: UserRequirements, *, api_key: Optional[str] = None
) -> list[Product]:
    """Search + normalise. No filtering/ranking here — that's the recommendation
    layer's job. Returns unified Product objects the back half can consume."""
    if api_key is None:
        from shopping_agent.config import searchapi_key

        api_key = searchapi_key()
    raw = _fetch_raw(build_query(reqs), api_key)
    return normalize(raw)
