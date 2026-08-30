"""Scaffold sanity tests -- these pass today and guard the contract.

The behaviour tests for each tool live alongside (xfail until implemented).
"""

from datetime import date
from decimal import Decimal

from shopping_agent.schemas import (
    CartResult,
    CartStatus,
    PickupInfo,
    PickupMethod,
    Product,
    Recommendation,
    UserRequirements,
    Weights,
)
from shopping_agent.llm.parsing import FakeLLM, structured_output


def test_fixtures_load(candidates):
    assert len(candidates) == 4
    assert all(isinstance(c, Product) for c in candidates)


def test_product_total_price(candidates):
    lazada = next(c for c in candidates if c.platform == "lazada")
    assert lazada.total_price() == Decimal("75.50")  # 72.00 + 3.50


def test_weights_normalize():
    w = Weights(price=2, speed=1, preference=1).normalized()
    assert abs(w.price + w.speed + w.preference - 1.0) < 1e-9
    assert abs(w.price - 0.5) < 1e-9


def test_weights_zero_falls_back_to_equal():
    w = Weights(price=0, speed=0, preference=0).normalized()
    assert abs(w.price - 1 / 3) < 1e-9


def test_pickup_meets_deadline_logic():
    pi = PickupInfo(
        product_id="x", platform="amazon", method=PickupMethod.STORE_PICKUP,
        available_by=date(2026, 9, 1),
    )
    assert pi.meets_deadline(date(2026, 9, 2)) is True
    assert pi.meets_deadline(date(2026, 8, 31)) is False
    assert pi.meets_deadline(None) is True
    unavail = PickupInfo(product_id="x", platform="amazon", method=PickupMethod.UNAVAILABLE)
    assert unavail.meets_deadline(None) is False


def test_fake_llm_returns_canned_object():
    fake = FakeLLM(responses={"greet": Recommendation(status="empty", reason="none")})
    out = structured_output(fake, "greet", "prompt", Recommendation)
    assert out.status == "empty"
    assert fake.calls == [("greet", "prompt")]


def test_cart_result_never_defaults_to_ordered():
    # There is no 'ordered' status by design.
    assert set(s.value for s in CartStatus) == {"prepared", "unsupported"}


def test_user_requirements_rejects_zero_results():
    import pytest

    with pytest.raises(Exception):
        UserRequirements(product_query="x", max_results=0)
