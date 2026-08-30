"""Behaviour spec / acceptance tests for the back-half tools.

These pin the intended behaviour of the pure core functions (no LLM, no I/O).
The `@tool` entrypoints themselves still raise NotImplementedError until the
agent-team state adapter lands.
"""

from datetime import date
from decimal import Decimal

import pytest

from shopping_agent.processing.scoring import minmax_normalize, preference_score
from shopping_agent.schemas import (
    PickupMethod,
    ReviewSummary,
    UserRequirements,
    Weights,
)
from shopping_agent.tools.cart import prepare_cart
from shopping_agent.tools.pickup import (
    check_pickup_availability,
    parse_delivery_days,
    parse_target_date,
)
from shopping_agent.tools.recommendation import rank_candidates


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def test_minmax_degenerate_returns_half():
    assert minmax_normalize([5.0], higher_is_better=True) == [0.5]
    assert minmax_normalize([3.0, 3.0, 3.0], higher_is_better=True) == [0.5, 0.5, 0.5]
    assert minmax_normalize([], higher_is_better=True) == []


def test_minmax_cheaper_is_better():
    out = minmax_normalize([100.0, 200.0], higher_is_better=False)
    assert out[0] > out[1]
    assert out == [1.0, 0.0]


def test_preference_score_no_prefs_is_neutral():
    assert preference_score({"brand": "X"}, [], {}) == 0.5


def test_preference_score_attribute_match():
    attrs = {"connector": "USB-C", "battery_hours": 40}
    assert preference_score(attrs, ["USB-C"], {}) == 1.0
    assert preference_score(attrs, ["waterproof"], {}) == 0.0


# --------------------------------------------------------------------------
# pickup
# --------------------------------------------------------------------------
def test_parse_target_date():
    assert parse_target_date("tomorrow", today=date(2026, 8, 29)) == date(2026, 8, 30)
    assert parse_target_date("in 3 days", today=date(2026, 8, 29)) == date(2026, 9, 1)
    assert parse_target_date("today", today=date(2026, 8, 29)) == date(2026, 8, 29)
    assert parse_target_date("2026-09-05") == date(2026, 9, 5)


def test_parse_target_date_bad_input_raises():
    with pytest.raises(ValueError):
        parse_target_date("sometime next month")


def test_parse_delivery_days_upper_bound():
    assert parse_delivery_days("Ships in 2-4 days") == 4
    assert parse_delivery_days("Ships in 1-2 days") == 2
    assert parse_delivery_days(None) is None
    assert parse_delivery_days("no numbers here") is None


def test_pickup_prefers_local_stock(candidates):
    amazon = next(c for c in candidates if c.platform == "amazon")
    info = check_pickup_availability(
        amazon, target_date=date(2026, 8, 30), today=date(2026, 8, 29)
    )
    assert info.method == PickupMethod.STORE_PICKUP  # orchard, ready in 4h
    assert info.available_by == date(2026, 8, 30)


def test_pickup_ships_when_no_local_stock(candidates):
    lazada = next(c for c in candidates if c.platform == "lazada")  # not in inventory
    info = check_pickup_availability(
        lazada, target_date=date(2026, 9, 30), today=date(2026, 8, 29)
    )
    assert info.method == PickupMethod.SHIP
    assert info.available_by == date(2026, 9, 10)  # today + 12 days (upper bound)


def test_pickup_unavailable_when_eta_after_target(candidates):
    lazada = next(c for c in candidates if c.platform == "lazada")
    info = check_pickup_availability(
        lazada, target_date=date(2026, 8, 31), today=date(2026, 8, 29)
    )
    assert info.method == PickupMethod.UNAVAILABLE


# --------------------------------------------------------------------------
# recommendation
# --------------------------------------------------------------------------
def test_recommendation_ranks_and_respects_budget(candidates):
    reqs = UserRequirements(
        product_query="wireless earbuds",
        budget=Decimal("150"),
        weights=Weights(price=0.5, speed=0.3, preference=0.2),
        max_results=3,
    )
    rec = rank_candidates(candidates, reqs, today=date(2026, 8, 29))
    ids = [i.product_id for i in rec.items]
    assert "ebay:EB77EARX" not in ids            # 180 + 12 shipping > 150 budget
    assert rec.items[0].rank == 1
    assert len(rec.items) <= 3
    # scores all in range
    for item in rec.items:
        for s in (item.scores.price_score, item.scores.speed_score, item.scores.preference_score):
            assert 0.0 <= s <= 1.0


def test_recommendation_empty_when_all_over_budget(candidates):
    reqs = UserRequirements(product_query="x", budget=Decimal("10"))
    rec = rank_candidates(candidates, reqs, today=date(2026, 8, 29))
    assert rec.status == "empty"
    assert rec.reason


def test_recommendation_golden_order_price_priority(candidates):
    # Price-dominant weighting -> cheapest in-budget item ranks first.
    reqs = UserRequirements(
        product_query="earbuds",
        budget=Decimal("150"),
        weights=Weights(price=1.0, speed=0.0, preference=0.0),
    )
    rec = rank_candidates(candidates, reqs, today=date(2026, 8, 29))
    assert rec.items[0].product_id == "lazada:LZ88EAR22"  # 75.50 total, cheapest


def test_recommendation_preference_influences_rank(candidates):
    reqs = UserRequirements(
        product_query="earbuds",
        preferences=["ANC"],
        weights=Weights(price=0.0, speed=0.0, preference=1.0),
    )
    rec = rank_candidates(candidates, reqs, today=date(2026, 8, 29))
    assert rec.items[0].product_id == "shopee:SP4521EAR"  # only one with anc attr


def test_recommendation_pickup_required_filters(candidates):
    # Only amazon + shopee are in local inventory; require pickup -> ebay/lazada drop.
    from shopping_agent.tools.pickup import check_pickup_availability

    target = date(2026, 8, 31)
    today = date(2026, 8, 29)
    pickups = {
        c.id: check_pickup_availability(c, target_date=target, today=today)
        for c in candidates
    }
    reqs = UserRequirements(
        product_query="earbuds", pickup_required=True, deadline=target
    )
    rec = rank_candidates(candidates, reqs, pickup_infos=pickups, today=today)
    ids = {i.product_id for i in rec.items}
    assert ids <= {"amazon:B0EARBUD01", "shopee:SP4521EAR"}


# --------------------------------------------------------------------------
# cart
# --------------------------------------------------------------------------
def test_cart_amazon_uses_real_add_url(candidates):
    amazon = next(c for c in candidates if c.platform == "amazon")
    res = prepare_cart(amazon, quantity=1)
    assert res.status.value == "prepared"
    assert "cart/add" in res.checkout_url.lower()
    assert "ASIN.1=B0EARBUD01" in res.checkout_url
    # never claims an order was placed
    assert "nothing has been ordered" in res.next_step_instructions.lower()


def test_cart_subtotal(candidates):
    shopee = next(c for c in candidates if c.platform == "shopee")
    res = prepare_cart(shopee, quantity=2)
    assert res.subtotal == Decimal("190.00")  # 95.00 * 2, no shipping


def test_cart_handoff_for_non_amazon(candidates):
    lazada = next(c for c in candidates if c.platform == "lazada")
    res = prepare_cart(lazada)
    assert res.status.value == "prepared"
    assert res.checkout_url == lazada.url
