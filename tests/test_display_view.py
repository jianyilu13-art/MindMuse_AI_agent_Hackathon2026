"""The browser-facing view model.

`state_to_view` is the contract between the agent's internal state and the
frontend: the browser only ever sees these keys. The tests below pin that
contract — the key set, JSON-safe values, the ranking data joined onto each
displayed product, and the fallback that keeps a curated pick from rendering
without any explanation.
"""

from __future__ import annotations

from datetime import date

from shopping_agent.agent.state import initial_state
from shopping_agent.schemas import (
    BestPick,
    CommunityFeedback,
    CommunityFeedbackSummary,
    Product,
    RankedProduct,
    UserRequirements,
)
from shopping_agent.ui.display import state_to_view


def make_product(product_id: str = "p1", **overrides) -> Product:
    values = {
        "id": product_id,
        "title": f"Product {product_id}",
        "price": 100.0,
        "platform": "mock-market",
        "url": f"https://example.test/{product_id}",
    }
    values.update(overrides)
    return Product(**values)


# --------------------------------------------------------------------------
# contract shape
# --------------------------------------------------------------------------
EXPECTED_KEYS = {
    "assistant_message",
    "finished",
    "awaiting_user_input",
    "requirements",
    "missing_required_information",
    "optional_preferences",
    "products",
    "best_picks",
    "search_result_status",
    "display_offset",
    "total_results",
    "last_error",
    "community_feedback",
}


def test_view_exposes_the_expected_keys():
    assert set(state_to_view(initial_state())) == EXPECTED_KEYS


def test_initial_state_produces_safe_empty_defaults():
    view = state_to_view(initial_state())
    assert view["products"] == []
    assert view["best_picks"] == []
    assert view["requirements"] is None
    assert view["total_results"] == 0
    assert view["search_result_status"] == "not_searched"
    assert view["finished"] is False


def test_conversation_fields_are_passed_through():
    state = initial_state()
    state["assistant_message"] = "What size do you need?"
    state["awaiting_user_input"] = True
    state["last_error"] = "search timed out"

    view = state_to_view(state)
    assert view["assistant_message"] == "What size do you need?"
    assert view["awaiting_user_input"] is True
    assert view["last_error"] == "search timed out"


# --------------------------------------------------------------------------
# requirements serialisation
# --------------------------------------------------------------------------
def test_requirements_are_serialised_as_json_safe_values():
    state = initial_state()
    state["requirements"] = UserRequirements(
        query="running shoes", size="10", max_price=150.0,
        arrival_by=date(2026, 9, 20), must_have=["cushioned"],
    )

    requirements = state_to_view(state)["requirements"]
    assert requirements["query"] == "running shoes"
    assert requirements["must_have"] == ["cushioned"]
    # a date must reach the browser as a string, not a date object
    assert requirements["arrival_by"] == "2026-09-20"
    assert isinstance(requirements["arrival_by"], str)


def test_missing_and_optional_requirement_hints_are_exposed():
    state = initial_state()
    state["missing_required_information"] = ["size"]
    state["optional_preferences"] = ["colour", "brand"]

    view = state_to_view(state)
    assert view["missing_required_information"] == ["size"]
    assert view["optional_preferences"] == ["colour", "brand"]


# --------------------------------------------------------------------------
# displayed products join the ranking data
# --------------------------------------------------------------------------
def test_displayed_products_carry_their_score_and_reasons():
    product = make_product("p1")
    state = initial_state()
    state["displayed_products"] = [product]
    state["ranked_products"] = [
        RankedProduct(product=product, score=42.5, reasons=["Rating: 4.5/5"])
    ]

    entry = state_to_view(state)["products"][0]
    assert entry["id"] == "p1"
    assert entry["score"] == 42.5
    assert entry["reasons"] == ["Rating: 4.5/5"]


def test_unranked_displayed_product_is_still_shown():
    """Fallback results are displayed without ranking data rather than dropped."""
    state = initial_state()
    state["displayed_products"] = [make_product("unranked")]
    state["ranked_products"] = []

    entry = state_to_view(state)["products"][0]
    assert entry["id"] == "unranked"
    assert entry["score"] is None
    assert entry["reasons"] == []


def test_display_order_follows_displayed_products():
    first, second = make_product("first"), make_product("second")
    state = initial_state()
    state["displayed_products"] = [first, second]
    state["ranked_products"] = [
        RankedProduct(product=second, score=99.0),
        RankedProduct(product=first, score=1.0),
    ]

    assert [item["id"] for item in state_to_view(state)["products"]] == ["first", "second"]


def test_total_results_counts_all_ranked_products_not_the_page():
    products = [make_product(f"p{index}") for index in range(5)]
    state = initial_state()
    state["displayed_products"] = products[:2]
    state["ranked_products"] = [RankedProduct(product=p, score=1.0) for p in products]
    state["display_offset"] = 2

    view = state_to_view(state)
    assert len(view["products"]) == 2
    assert view["total_results"] == 5
    assert view["display_offset"] == 2


# --------------------------------------------------------------------------
# curated picks
# --------------------------------------------------------------------------
def test_best_pick_without_reasons_inherits_them_from_the_ranking():
    product = make_product("p1")
    state = initial_state()
    state["ranked_products"] = [
        RankedProduct(product=product, score=50.0, reasons=["Well rated"])
    ]
    state["best_picks"] = [
        BestPick(tier="overall", product=product, match_pct=90,
                 match_label="match", headline="Closest fit", reasons=[])
    ]

    pick = state_to_view(state)["best_picks"][0]
    assert pick["reasons"] == ["Well rated"]
    assert pick["tier"] == "overall"
    assert pick["match_pct"] == 90


def test_best_pick_keeps_its_own_reasons_when_present():
    product = make_product("p1")
    state = initial_state()
    state["ranked_products"] = [
        RankedProduct(product=product, score=50.0, reasons=["From ranking"])
    ]
    state["best_picks"] = [
        BestPick(tier="value", product=product, match_pct=80, match_label="match",
                 headline="Saves money", reasons=["Own reason"])
    ]

    assert state_to_view(state)["best_picks"][0]["reasons"] == ["Own reason"]


def test_best_pick_without_matching_ranking_still_renders():
    state = initial_state()
    state["ranked_products"] = []
    state["best_picks"] = [
        BestPick(tier="upgrade", product=make_product("orphan"), match_pct=70,
                 match_label="functional match", headline="Better reviews", reasons=[])
    ]

    pick = state_to_view(state)["best_picks"][0]
    assert pick["reasons"] == []
    assert pick["match_label"] == "functional match"


# --------------------------------------------------------------------------
# community feedback
# --------------------------------------------------------------------------
def test_community_feedback_is_serialised_per_product():
    state = initial_state()
    state["community_feedback"] = {
        "p1": CommunityFeedbackSummary(
            product_id="p1",
            available=True,
            summary="Reviewers like the cushioning.",
            sources=[
                CommunityFeedback(product_id="p1", title="Thread",
                                  url="https://forum.test/t/1", domain="forum.test")
            ],
        )
    }

    feedback = state_to_view(state)["community_feedback"]["p1"]
    assert feedback["available"] is True
    assert feedback["summary"] == "Reviewers like the cushioning."
    assert feedback["sources"][0]["domain"] == "forum.test"


def test_absent_community_feedback_is_an_empty_mapping():
    assert state_to_view(initial_state())["community_feedback"] == {}
