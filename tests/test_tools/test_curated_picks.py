"""Curated best-overall / value / upgrade selection."""

from __future__ import annotations

from decimal import Decimal

from shopping_agent.schemas import PickTier, Product, UserRequirements, Weights
from shopping_agent.tools.recommendation import curate_picks, rank_candidates


def _p(pid, price, rating, attrs, ship="0", delivery="Ships in 2 days", reviews=100):
    return Product(
        id=pid,
        platform=pid.split(":")[0],
        title=pid,
        url=f"https://example.test/{pid}",
        price=Decimal(str(price)),
        shipping_cost=Decimal(str(ship)),
        rating=rating,
        review_count=reviews,
        delivery_estimate=delivery,
        attributes=attrs,
    )


def _reqs(budget="120"):
    return UserRequirements(
        product_query="running shoes",
        budget=Decimal(budget),
        preferences=["cushioned", "lightweight"],
        # preference-led: a better-fitting product can win despite costing more,
        # which is what makes a distinct 'best value' tier meaningful.
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
    )


def test_three_distinct_tiers():
    candidates = [
        _p("nike:PEG", 110, 4.4, {"features": "cushioned lightweight"}),   # best overall-ish
        _p("adidas:DUR", 80, 4.1, {"features": "lightweight"}),            # cheaper -> value
        _p("asics:GEL", 135, 4.8, {"features": "cushioned lightweight"}),  # over budget, better -> upgrade
    ]
    picks = curate_picks(candidates, _reqs(budget="120"))
    tiers = [p.tier for p in picks]

    assert PickTier.BEST_OVERALL in tiers
    assert PickTier.BEST_VALUE in tiers
    assert PickTier.BEST_UPGRADE in tiers

    by_tier = {p.tier: p for p in picks}
    # value is genuinely cheaper than overall
    assert by_tier[PickTier.BEST_VALUE].product_id == "adidas:DUR"
    # upgrade is the over-budget, higher-rated option, labelled 'functional match'
    up = by_tier[PickTier.BEST_UPGRADE]
    assert up.product_id == "asics:GEL"
    assert up.match_label == "functional match"
    assert "over budget" in up.headline.lower()
    # every tier points at a different product
    assert len({p.product_id for p in picks}) == 3


def test_no_padding_when_only_one_option():
    # single in-budget candidate, nothing cheaper, nothing better over budget
    picks = curate_picks([_p("nike:PEG", 110, 4.4, {"features": "cushioned"})], _reqs())
    assert [p.tier for p in picks] == [PickTier.BEST_OVERALL]


def test_upgrade_respects_slack_ceiling():
    # a far-over-budget shoe (budget 120, +15% -> ceiling 138) must be excluded
    candidates = [
        _p("nike:PEG", 110, 4.4, {"features": "cushioned lightweight"}),
        _p("lux:MAX", 300, 5.0, {"features": "cushioned lightweight"}),  # too expensive
    ]
    picks = curate_picks(candidates, _reqs(budget="120"))
    assert all(p.tier != PickTier.BEST_UPGRADE for p in picks)


def test_rank_candidates_attaches_picks():
    candidates = [
        _p("nike:PEG", 110, 4.4, {"features": "cushioned lightweight"}),
        _p("adidas:DUR", 80, 4.1, {"features": "lightweight"}),
    ]
    rec = rank_candidates(candidates, _reqs())
    assert rec.status == "ok"
    assert rec.picks  # picks attached by default
    assert rec.picks[0].tier == PickTier.BEST_OVERALL
    # match_pct is a clean 0-100 int
    assert all(0 <= p.match_pct <= 100 for p in rec.picks)
