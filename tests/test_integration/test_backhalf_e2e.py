"""End-to-end test of the back-half tools through the session adapter.

Simulates what the agent does: load candidates + requirements into a session,
then call the four @tool entrypoints and assert on their string output and the
structured objects written back to the session.
"""

from datetime import date
from decimal import Decimal

import pytest

from shopping_agent.schemas import CartStatus, UserRequirements, Weights
from shopping_agent.tools import add_to_cart, check_pickup, customer_service, recommend_products
from shopping_agent.tools.context import clear_all, get_session, new_session


@pytest.fixture(autouse=True)
def _clean_sessions():
    clear_all()
    yield
    clear_all()


@pytest.fixture
def loaded_session(candidates):
    session = new_session(
        "demo",
        requirements=UserRequirements(
            product_query="wireless earbuds",
            budget=Decimal("150"),
            weights=Weights(price=0.5, speed=0.3, preference=0.2),
            max_results=3,
        ),
    )
    session.add_candidates(candidates)
    return session


def test_recommend_products_end_to_end(loaded_session):
    out = recommend_products.func("demo") if hasattr(recommend_products, "func") else recommend_products("demo")
    assert "BEST OVERALL" in out and "Full ranking" in out
    rec = get_session("demo").recommendation
    assert rec is not None and rec.status == "ok"
    assert "ebay:EB77EARX" not in [i.product_id for i in rec.items]  # over budget


def test_check_pickup_end_to_end(loaded_session):
    _call(check_pickup, "amazon:B0EARBUD01", "amazon", "tomorrow")
    info = get_session("demo").pickups["amazon:B0EARBUD01"]
    assert info.method.value in ("store_pickup", "ship")


def test_check_pickup_bad_date_is_graceful(loaded_session):
    out = _call(check_pickup, "amazon:B0EARBUD01", "amazon", "whenever")
    assert "understand the date" in out.lower()


def test_add_to_cart_end_to_end(loaded_session):
    out = _call(add_to_cart, "amazon:B0EARBUD01", "amazon")
    assert "checkout link" in out.lower()
    assert "nothing has been ordered" in out.lower()
    res = get_session("demo").cart_results["amazon:B0EARBUD01"]
    assert res.status == CartStatus.PREPARED


def test_customer_service_end_to_end(loaded_session):
    out = _call(customer_service, "amazon:B0EARBUD01", "what's the return policy?")
    assert "policy" in out.lower()
    assert get_session("demo").cs_results["amazon:B0EARBUD01"].intent == "policy"


def test_full_flow(loaded_session):
    # recommend -> pickup on the winner -> customer service -> cart
    rec_out = _call(recommend_products, "demo")
    assert "BEST OVERALL" in rec_out and "Full ranking" in rec_out
    winner = get_session("demo").recommendation.items[0].product_id
    _call(check_pickup, winner, winner.split(":")[0], "in 5 days")
    _call(customer_service, winner, "what should I check when it arrives?")
    cart_out = _call(add_to_cart, winner, winner.split(":")[0])
    assert "checkout link" in cart_out.lower()


def _call(tool, *args):
    """Call a tool whether or not langchain wrapped it (langchain tools expose
    .func / .invoke; the no-op shim leaves them as plain functions)."""
    if hasattr(tool, "func"):
        return tool.func(*args)
    return tool(*args)
