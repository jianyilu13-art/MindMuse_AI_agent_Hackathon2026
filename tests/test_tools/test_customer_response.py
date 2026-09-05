"""The customer-facing feedback assembly (back half's final output)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from shopping_agent.schemas import PickTier, Product, UserRequirements, Weights
from shopping_agent.tools.context import new_session, clear_all
from shopping_agent.tools.customer_response import (
    build_customer_response,
    render_customer_response,
    present_to_customer,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_all()
    yield
    clear_all()


def _p(pid, price, rating, attrs, delivery="Ships in 2 days", returns="30-day returns"):
    return Product(
        id=pid,
        platform=pid.split(":")[0],
        title=pid.split(":")[1],
        url=f"https://example.test/{pid}",
        image_url=f"https://img.example.test/{pid}.jpg",
        price=Decimal(str(price)),
        rating=rating,
        review_count=250,
        delivery_estimate=delivery,
        return_policy_text=returns,
        warranty_text="1-year manufacturer warranty",
        attributes=attrs,
    )


def _reqs(budget="150"):
    return UserRequirements(
        product_query="running shoes",
        budget=Decimal(budget),
        currency="SGD",
        preferences=["cushioned", "lightweight", "breathable"],
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
    )


def _session():
    session = new_session("demo", requirements=_reqs())
    session.add_candidates([
        _p("amazon:Pegasus", 139, 4.5, {"features": "cushioned lightweight breathable"}),
        _p("shopee:Duramo", 89, 4.2, {"features": "lightweight"}),
        _p("amazon:Gel-Cumulus", 158, 4.8, {"features": "cushioned lightweight"}),
    ])
    return session


def test_response_has_all_pieces():
    session = _session()
    resp = build_customer_response(session, today=date(2026, 9, 4))

    assert resp.cards, "expected cards"
    top = resp.cards[0]
    # basic info
    assert top.title and top.platform and top.price.startswith("SGD")
    assert top.rating is not None
    assert top.image_url  # product image carried through
    # ranking reason present
    assert top.reason
    # availability (pickup / delivery) line
    assert top.availability
    # after-sales derived from listing text
    assert top.after_sales and "Returns" in top.after_sales
    # a checkout link + note
    assert top.checkout_url and top.checkout_note
    # footer makes the 'no order placed' promise
    assert "ordered" in resp.footer.lower()


def test_tiers_live_in_this_layer():
    session = _session()
    resp = build_customer_response(session, today=date(2026, 9, 4))
    tiers = [c.tier for c in resp.cards if c.tier]
    assert PickTier.BEST_OVERALL in tiers
    # the over-budget, higher-rated shoe shows as a functional-match upgrade
    upgrade = next((c for c in resp.cards if c.tier == PickTier.BEST_UPGRADE), None)
    assert upgrade is not None
    assert upgrade.match_label == "functional match"


def test_amazon_gets_add_to_cart_note_others_dont():
    session = _session()
    resp = build_customer_response(session, today=date(2026, 9, 4))
    by_platform = {c.platform: c for c in resp.cards}
    assert "Amazon cart" in by_platform["amazon"].checkout_note
    if "shopee" in by_platform:
        assert "product page" in by_platform["shopee"].checkout_note.lower()


def test_render_is_a_string_with_tier_headers():
    session = _session()
    session.customer_response = None
    out = present_to_customer.func("demo") if hasattr(present_to_customer, "func") else present_to_customer("demo")
    assert "BEST OVERALL" in out
    assert "🔗" in out  # checkout link rendered
    assert session.customer_response is not None


def test_empty_session_is_graceful():
    session = new_session("empty", requirements=_reqs())
    resp = build_customer_response(session)
    assert resp.cards == []
