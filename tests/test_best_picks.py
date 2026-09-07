from __future__ import annotations

from shopping_agent.agent.nodes import ShoppingNodes
from shopping_agent.agent.state import initial_state
from shopping_agent.processing import apply_hard_constraints
from shopping_agent.schemas import Product, RankedProduct, UserRequirements


def product(product_id: str, price: float, rating: float, reviews: int, platform: str = "store") -> Product:
    return Product(
        id=product_id,
        title=product_id.title(),
        price=price,
        platform=platform,
        url=f"https://example.test/{product_id}",
        rating=rating,
        review_count=reviews,
    )


def ranked(item: Product, score: float) -> RankedProduct:
    return RankedProduct(product=item, score=score, reasons=["Rating evidence"])


def state_with_products(
    requirements: UserRequirements,
    ranked_products: list[RankedProduct],
    raw_products: list[Product],
):
    state = initial_state()
    state.update(
        requirements=requirements,
        ranked_products=ranked_products,
        raw_products=raw_products,
        ranking_status="completed",
        presentation_status="ready",
    )
    return state


def test_selects_three_distinct_tiers_from_qualified_products() -> None:
    overall = product("overall", 100, 4.5, 100)
    value = product("value", 80, 4.2, 100)
    upgrade = product("upgrade", 104, 4.8, 300)
    state = state_with_products(
        UserRequirements(query="shoes", max_price=105),
        [ranked(overall, 50), ranked(value, 45), ranked(upgrade, 44)],
        [overall, value, upgrade],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert [pick.tier for pick in picks] == ["overall", "value", "upgrade"]
    assert len({pick.product.id for pick in picks}) == 3
    assert picks[1].product.price < picks[0].product.price
    assert picks[2].product.id == "upgrade"
    assert picks[2].match_label == "functional match"
    assert all(0 <= pick.match_pct <= 100 for pick in picks)


def test_best_overall_follows_personalized_rank_over_price() -> None:
    overall = product("overall", 100, 4.8, 500)
    cheaper = product("cheaper", 95, 4.0, 80)
    state = state_with_products(
        UserRequirements(query="laptop", max_price=120),
        [ranked(overall, 70), ranked(cheaper, 55)],
        [overall, cheaper],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert picks[0].tier == "overall"
    assert picks[0].product.id == "overall"


def test_best_value_is_not_the_absolute_cheapest_product() -> None:
    overall = product("overall", 150, 4.8, 500)
    moderate = product("moderate", 100, 4.6, 400)
    cheapest = product("cheapest", 50, 2.8, 10)
    state = state_with_products(
        UserRequirements(query="laptop", max_price=160),
        [ranked(overall, 70), ranked(moderate, 60), ranked(cheapest, 20)],
        [overall, moderate, cheapest],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert next(pick for pick in picks if pick.tier == "value").product.id == "moderate"


def test_upgrade_requires_meaningful_quality_improvement_and_stays_in_budget() -> None:
    overall = product("overall", 100, 4.2, 100)
    upgrade = product("upgrade", 110, 4.5, 220)
    state = state_with_products(
        UserRequirements(query="laptop", max_price=115),
        [ranked(overall, 50), ranked(upgrade, 45)],
        [overall, upgrade],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]
    upgrade_pick = next(pick for pick in picks if pick.tier == "upgrade")

    assert upgrade_pick.product.id == "upgrade"
    assert upgrade_pick.product.price <= 115
    assert upgrade_pick.match_label == "functional match"


def test_no_valid_upgrade_is_not_invented() -> None:
    overall = product("overall", 100, 4.5, 100)
    slightly_better = product("slightly-better", 105, 4.55, 110)
    state = state_with_products(
        UserRequirements(query="snacks", max_price=110),
        [ranked(overall, 50), ranked(slightly_better, 49)],
        [overall, slightly_better],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert not any(pick.tier == "upgrade" for pick in picks)


def test_unknown_critical_attribute_has_lower_confidence_than_verified_match() -> None:
    unknown_size = product("unknown-size", 100, 4.8, 500)
    verified_size = product("verified-size", 100, 4.2, 100)
    verified_size.attributes["sizes"] = "42,43"
    state = state_with_products(
        UserRequirements(query="shoes", size="42"),
        [ranked(unknown_size, 70), ranked(verified_size, 55)],
        [unknown_size, verified_size],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert picks[0].product.id == "verified-size"
    assert picks[0].match_pct == 100


def test_selector_supports_non_shoe_categories() -> None:
    laptop = product("laptop", 900, 4.7, 300)
    laptop.attributes["storage_interface"] = "NVMe"
    state = state_with_products(
        UserRequirements(query="laptop", attributes={"storage_interface": "NVMe"}),
        [ranked(laptop, 60)],
        [laptop],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert picks[0].product.id == "laptop"


def test_hard_constraint_violator_cannot_reach_any_category() -> None:
    valid = product("valid", 90, 4.5, 200)
    valid.attributes["sizes"] = "42,43"
    over_budget = product("over-budget", 120, 5.0, 1000)
    over_budget.attributes["sizes"] = "42,43"
    requirements = UserRequirements(query="shoes", size="42", max_price=100)

    qualified = apply_hard_constraints([valid, over_budget], requirements)

    assert [item.id for item in qualified] == ["valid"]


def test_does_not_pad_when_only_overall_qualifies() -> None:
    overall = product("overall", 100, 4.5, 100)
    weak_upgrade = product("weak-upgrade", 110, 4.5, 110)
    state = state_with_products(
        UserRequirements(query="shoes", max_price=105),
        [ranked(overall, 50)],
        [overall, weak_upgrade],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert [pick.tier for pick in picks] == ["overall"]


def test_upgrade_respects_fifteen_percent_ceiling() -> None:
    overall = product("overall", 100, 4.5, 100)
    too_expensive = product("too-expensive", 121, 5.0, 500)
    state = state_with_products(
        UserRequirements(query="shoes", max_price=105),
        [ranked(overall, 50)],
        [overall, too_expensive],
    )

    picks = ShoppingNodes(None).select_best_picks(state)["best_picks"]

    assert [pick.tier for pick in picks] == ["overall"]


def test_empty_ranked_products_return_empty_best_picks() -> None:
    state = state_with_products(UserRequirements(query="shoes"), [], [])

    assert ShoppingNodes(None).select_best_picks(state) == {"best_picks": []}
