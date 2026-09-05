"""Full pipeline: requirements -> search -> recommend -> back half -> response."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from shopping_agent.schemas import PickTier, UserRequirements, Weights
from shopping_agent.pipeline import run_shopping
from shopping_agent.tools.context import clear_all, get_session


@pytest.fixture(autouse=True)
def _clean():
    clear_all()
    yield
    clear_all()


def _reqs():
    return UserRequirements(
        product_query="running shoes",
        category="running_shoes",
        budget=Decimal("150"),
        deadline=date.today() + timedelta(days=4),
        preferences=["cushioned", "lightweight", "breathable"],
        must_have=["running"],
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
        max_results=3,
    )


def test_pipeline_runs_end_to_end_offline():
    resp = run_shopping(_reqs(), session_id="e2e")
    assert resp.cards, "expected customer-facing cards"
    assert "ordered" in resp.footer.lower()

    # session captured every stage
    session = get_session("e2e")
    assert session.candidates                 # search ran
    assert session.recommendation.status == "ok"
    assert session.cart_results               # back half ran


def test_preference_weighting_picks_best_fit_not_cheapest():
    resp = run_shopping(_reqs(), session_id="e2e")
    overall = next(c for c in resp.cards if c.tier == PickTier.BEST_OVERALL)
    # Nike matches all three preferences -> should win under preference weight,
    # even though it is not the cheapest.
    assert "Nike" in overall.title
    assert overall.match_pct >= 60


def test_amazon_gets_real_add_to_cart_link():
    resp = run_shopping(_reqs(), session_id="e2e")
    amazon = next(c for c in resp.cards if "amazon" in c.platform.lower())
    assert "cart/add" in amazon.checkout_url          # real add-to-cart endpoint
    assert "Amazon cart" in amazon.checkout_note


def test_over_budget_upgrade_is_functional_match():
    resp = run_shopping(_reqs(), session_id="e2e")
    upgrade = next((c for c in resp.cards if c.tier == PickTier.BEST_UPGRADE), None)
    if upgrade:  # only asserted when a qualifying upgrade exists
        assert upgrade.match_label == "functional match"
        assert "over budget" in upgrade.reason.lower()
