"""Transparent ranking.

`rank_products` must stay explainable: the score is assembled from stated
shopper priorities and provider facts only, and every product carries the
reasons behind its position. These tests pin the ordering guarantees the UI
depends on, and the rule that review insight may add signal but never invents
a rating.
"""

from __future__ import annotations

from datetime import date

from shopping_agent.processing import rank_products
from shopping_agent.schemas import Product, ReviewSummary, UserRequirements


def make_product(
    product_id: str,
    *,
    price: float = 100.0,
    rating: float | None = 4.0,
    review_count: int = 0,
    platform: str = "mock-market",
    arrival_date: date | None = None,
) -> Product:
    return Product(
        id=product_id,
        title=f"Product {product_id}",
        price=price,
        platform=platform,
        url=f"https://example.test/{product_id}",
        rating=rating,
        review_count=review_count,
        arrival_date=arrival_date,
    )


def order(ranked) -> list[str]:
    return [item.product.id for item in ranked]


def score_of(ranked, product_id: str) -> float:
    return next(item.score for item in ranked if item.product.id == product_id)


# --------------------------------------------------------------------------
# ordering
# --------------------------------------------------------------------------
def test_results_are_sorted_by_descending_score():
    products = [
        make_product("low", rating=3.0),
        make_product("high", rating=5.0),
        make_product("middle", rating=4.0),
    ]
    ranked = rank_products(products, UserRequirements(), {})
    assert order(ranked) == ["high", "middle", "low"]
    assert [item.score for item in ranked] == sorted(
        (item.score for item in ranked), reverse=True
    )


def test_every_product_is_ranked_not_filtered():
    """Ranking never drops products — filtering is the hard-constraint step."""
    products = [make_product("a"), make_product("b"), make_product("c")]
    assert len(rank_products(products, UserRequirements(), {})) == 3


def test_empty_input_returns_empty_ranking():
    assert rank_products([], UserRequirements(), {}) == []


# --------------------------------------------------------------------------
# rating and review volume
# --------------------------------------------------------------------------
def test_higher_rating_outranks_lower_rating():
    products = [make_product("worse", rating=3.5), make_product("better", rating=4.8)]
    assert order(rank_products(products, UserRequirements(), {}))[0] == "better"


def test_review_volume_breaks_a_rating_tie():
    products = [
        make_product("few", rating=4.5, review_count=10),
        make_product("many", rating=4.5, review_count=900),
    ]
    assert order(rank_products(products, UserRequirements(), {}))[0] == "many"


def test_review_volume_contribution_is_capped():
    """Beyond the cap, extra reviews must not keep inflating the score."""
    products = [
        make_product("at-cap", rating=4.0, review_count=1000),
        make_product("way-over-cap", rating=4.0, review_count=50_000),
    ]
    ranked = rank_products(products, UserRequirements(), {})
    assert score_of(ranked, "at-cap") == score_of(ranked, "way-over-cap")


def test_missing_rating_is_reported_rather_than_assumed():
    products = [make_product("unrated", rating=None)]
    ranked = rank_products(products, UserRequirements(), {})
    assert "No marketplace rating" in ranked[0].reasons


def test_rated_product_reports_its_rating():
    ranked = rank_products([make_product("rated", rating=4.5)], UserRequirements(), {})
    assert any("4.5" in reason for reason in ranked[0].reasons)


# --------------------------------------------------------------------------
# price and stated priorities
# --------------------------------------------------------------------------
def test_cheaper_product_scores_higher_within_the_same_budget():
    products = [
        make_product("expensive", price=140.0, rating=4.0),
        make_product("cheap", price=40.0, rating=4.0),
    ]
    ranked = rank_products(products, UserRequirements(max_price=150), {})
    assert order(ranked)[0] == "cheap"


def test_price_priority_increases_the_advantage_of_a_cheaper_product():
    products = [
        make_product("expensive", price=140.0, rating=4.0),
        make_product("cheap", price=40.0, rating=4.0),
    ]
    baseline = rank_products(products, UserRequirements(max_price=150), {})
    prioritised = rank_products(
        products,
        UserRequirements(max_price=150, ranking_priorities=["price"]),
        {},
    )
    baseline_gap = score_of(baseline, "cheap") - score_of(baseline, "expensive")
    prioritised_gap = score_of(prioritised, "cheap") - score_of(prioritised, "expensive")
    assert prioritised_gap > baseline_gap


def test_rating_priority_rewards_the_better_rated_product():
    products = [make_product("top", rating=5.0), make_product("ok", rating=3.0)]
    baseline = rank_products(products, UserRequirements(), {})
    prioritised = rank_products(
        products, UserRequirements(ranking_priorities=["rating"]), {}
    )
    assert (score_of(prioritised, "top") - score_of(prioritised, "ok")) > (
        score_of(baseline, "top") - score_of(baseline, "ok")
    )


def test_priorities_are_matched_case_insensitively():
    products = [make_product("top", rating=5.0), make_product("ok", rating=3.0)]
    upper = rank_products(products, UserRequirements(ranking_priorities=["RATING"]), {})
    lower = rank_products(products, UserRequirements(ranking_priorities=["rating"]), {})
    assert score_of(upper, "top") == score_of(lower, "top")


def test_no_price_boost_without_a_stated_budget():
    """Without a budget there is no reference point, so price must not score."""
    products = [
        make_product("cheap", price=10.0, rating=4.0),
        make_product("pricey", price=900.0, rating=4.0),
    ]
    ranked = rank_products(products, UserRequirements(), {})
    assert score_of(ranked, "cheap") == score_of(ranked, "pricey")


# --------------------------------------------------------------------------
# preferred platform
# --------------------------------------------------------------------------
def test_preferred_platform_is_rewarded_and_explained():
    products = [
        make_product("preferred", platform="Shopee"),
        make_product("other", platform="Lazada"),
    ]
    ranked = rank_products(
        products, UserRequirements(preferred_platforms=["shopee"]), {}
    )
    assert order(ranked)[0] == "preferred"
    preferred = next(item for item in ranked if item.product.id == "preferred")
    assert any("preferred seller" in reason.lower() for reason in preferred.reasons)


def test_platform_preference_is_case_insensitive():
    products = [make_product("preferred", platform="SHOPEE")]
    ranked = rank_products(products, UserRequirements(preferred_platforms=["shopee"]), {})
    assert any("preferred seller" in reason.lower() for reason in ranked[0].reasons)


# --------------------------------------------------------------------------
# review insight
# --------------------------------------------------------------------------
def test_positive_review_summary_adds_score_and_highlights():
    products = [make_product("reviewed"), make_product("plain")]
    reviews = {
        "reviewed": ReviewSummary(
            product_id="reviewed",
            sentiment="positive",
            highlights=["Comfortable", "Durable", "Third highlight"],
        )
    }
    ranked = rank_products(products, UserRequirements(), reviews)
    assert score_of(ranked, "reviewed") > score_of(ranked, "plain")

    reviewed = next(item for item in ranked if item.product.id == "reviewed")
    assert "Comfortable" in reviewed.reasons
    assert "Third highlight" not in reviewed.reasons  # only the top highlights


def test_unavailable_review_summary_changes_nothing():
    products = [make_product("reviewed"), make_product("plain")]
    reviews = {
        "reviewed": ReviewSummary(
            product_id="reviewed",
            sentiment="positive",
            highlights=["Ignored"],
            available=False,
        )
    }
    ranked = rank_products(products, UserRequirements(), reviews)
    assert score_of(ranked, "reviewed") == score_of(ranked, "plain")
    reviewed = next(item for item in ranked if item.product.id == "reviewed")
    assert "Ignored" not in reviewed.reasons


def test_negative_sentiment_adds_no_score_bonus():
    products = [make_product("negative"), make_product("plain")]
    reviews = {
        "negative": ReviewSummary(product_id="negative", sentiment="negative")
    }
    ranked = rank_products(products, UserRequirements(), reviews)
    assert score_of(ranked, "negative") == score_of(ranked, "plain")


# --------------------------------------------------------------------------
# delivery priority
# --------------------------------------------------------------------------
def test_delivery_priority_favours_earlier_arrival():
    deadline = date(2026, 9, 20)
    products = [
        make_product("fast", arrival_date=date(2026, 9, 12)),
        make_product("slow", arrival_date=date(2026, 9, 19)),
    ]
    requirements = UserRequirements(
        arrival_by=deadline, ranking_priorities=["delivery"]
    )
    assert order(rank_products(products, requirements, {}))[0] == "fast"


# --------------------------------------------------------------------------
# output shape
# --------------------------------------------------------------------------
def test_scores_are_rounded_for_display():
    ranked = rank_products([make_product("p", rating=4.567, review_count=333)],
                           UserRequirements(), {})
    assert ranked[0].score == round(ranked[0].score, 2)


def test_every_ranked_product_carries_at_least_one_reason():
    products = [make_product("a"), make_product("b", rating=None)]
    ranked = rank_products(products, UserRequirements(), {})
    assert all(item.reasons for item in ranked)
