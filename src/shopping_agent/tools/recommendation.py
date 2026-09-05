"""recommendation tool -- rank candidates into an explainable shortlist.

Design: deterministic weighted scoring (price / speed / preference), with the
LLM used only to polish the natural-language explanation. See scoring core in
`shopping_agent.processing.scoring`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from shopping_agent.processing.scoring import minmax_normalize, preference_score
from shopping_agent.schemas import (
    CuratedPick,
    PickTier,
    PickupInfo,
    Product,
    RankedItem,
    Recommendation,
    ReviewSummary,
    ScoreBreakdown,
    UserRequirements,
    Weights,
)
from shopping_agent.tools._registry import tool
from shopping_agent.tools.pickup import parse_delivery_days


def _delivery_days(product: Product, pickup: Optional[PickupInfo], today: date) -> float:
    """Best available 'days until I have it', for the speed axis. Prefers a
    concrete pickup date, falls back to listing text, then a large penalty."""
    if pickup is not None and pickup.available_by is not None:
        return max((pickup.available_by - today).days, 0)
    days = parse_delivery_days(product.delivery_estimate)
    if days is not None:
        return float(days)
    return 60.0  # unknown timing -> treated as slow


def _passes_objective(
    product: Product,
    reqs: UserRequirements,
    pickup: Optional[PickupInfo],
) -> bool:
    """Deterministic hard filter: budget and deadline / pickup requirement."""
    if reqs.budget is not None and product.total_price() > reqs.budget:
        return False
    if reqs.deadline is not None:
        if pickup is not None:
            if not pickup.meets_deadline(reqs.deadline):
                return False
        else:
            days = parse_delivery_days(product.delivery_estimate)
            if days is not None:
                from datetime import date as _date, timedelta

                if _date.today() + timedelta(days=days) > reqs.deadline:
                    return False
    if reqs.pickup_required:
        from shopping_agent.schemas import PickupMethod

        if pickup is None or pickup.method in (
            PickupMethod.UNAVAILABLE,
            PickupMethod.SHIP,
        ):
            return False
    return True


def _template_explanation(
    product: Product, breakdown: ScoreBreakdown, all_products: list[Product]
) -> str:
    """Deterministic reason string from the score breakdown."""
    bits: list[str] = []
    cheapest = min(all_products, key=lambda p: p.total_price())
    if product.id == cheapest.id:
        bits.append(f"cheapest at {product.currency} {product.total_price()}")
    elif breakdown.price_score >= 0.66:
        bits.append(f"good price ({product.currency} {product.total_price()})")
    if breakdown.speed_score >= 0.66:
        bits.append("fast availability")
    if breakdown.preference_score >= 0.66:
        bits.append("matches your preferences well")
    if product.rating is not None and product.rating >= 4.3:
        bits.append(f"well rated ({product.rating}★)")
    if not bits:
        bits.append("balanced option across price, speed and fit")
    return " · ".join(bits)


def _score_products(
    products: list[Product],
    reqs: UserRequirements,
    review_summaries: dict[str, ReviewSummary],
    pickup_infos: dict[str, PickupInfo],
    today: date,
) -> list[tuple[Product, ScoreBreakdown]]:
    """Score a set of products on the price / speed / preference axes,
    normalised *within this set*. No filtering — caller decides membership.
    Shared by `rank_candidates` (survivors) and `curate_picks` (which mixes in
    over-budget upgrade candidates)."""
    weights = reqs.weights.normalized()
    prices = [float(p.total_price()) for p in products]
    speeds = [_delivery_days(p, pickup_infos.get(p.id), today) for p in products]
    prefs = [
        preference_score(
            p.attributes,
            reqs.preferences,
            review_summaries[p.id].aspect_sentiment if p.id in review_summaries else {},
        )
        for p in products
    ]
    price_scores = minmax_normalize(prices, higher_is_better=False)
    speed_scores = minmax_normalize(speeds, higher_is_better=False)
    # preference_score is already 0-1; keep as-is (don't re-normalise a 0-1 signal)

    scored: list[tuple[Product, ScoreBreakdown]] = []
    for p, ps, ss, pf, raw_price, raw_speed in zip(
        products, price_scores, speed_scores, prefs, prices, speeds
    ):
        total = weights.price * ps + weights.speed * ss + weights.preference * pf
        scored.append(
            (
                p,
                ScoreBreakdown(
                    price_score=ps,
                    speed_score=ss,
                    preference_score=pf,
                    weighted_total=total,
                    raw={"total_price": raw_price, "delivery_days": raw_speed},
                ),
            )
        )
    return scored


def rank_candidates(
    candidates: list[Product],
    reqs: UserRequirements,
    review_summaries: Optional[dict[str, ReviewSummary]] = None,
    pickup_infos: Optional[dict[str, PickupInfo]] = None,
    *,
    today: Optional[date] = None,
    with_picks: bool = True,
) -> Recommendation:
    """Pure core: score, filter, rank. No LLM, no I/O -> unit-testable.
    When `with_picks`, also attach curated best-overall/value/upgrade highlights."""
    from datetime import date as _date

    today = today or _date.today()
    review_summaries = review_summaries or {}
    pickup_infos = pickup_infos or {}

    # 1. objective hard filter
    survivors = [
        p
        for p in candidates
        if _passes_objective(p, reqs, pickup_infos.get(p.id))
    ]
    if not survivors:
        reason = "No products fit the budget/deadline/pickup constraints."
        if candidates:
            cheapest = min(candidates, key=lambda p: p.total_price())
            reason += (
                f" Cheapest available is {cheapest.currency} "
                f"{cheapest.total_price()} ({cheapest.title})."
            )
        return Recommendation(status="empty", items=[], reason=reason)

    # 2-4. score survivors on all axes, normalised within the surviving set
    scored = _score_products(survivors, reqs, review_summaries, pickup_infos, today)

    # 5. sort desc, take top N, attach explanation
    scored.sort(key=lambda t: t[1].weighted_total, reverse=True)
    items: list[RankedItem] = []
    for rank, (p, breakdown) in enumerate(scored[: reqs.max_results], start=1):
        items.append(
            RankedItem(
                product_id=p.id,
                rank=rank,
                scores=breakdown,
                explanation=_template_explanation(p, breakdown, survivors),
            )
        )

    rec = Recommendation(status="ok", items=items, reason=None)
    if with_picks:
        rec.picks = curate_picks(
            candidates,
            reqs,
            review_summaries,
            pickup_infos,
            today=today,
            scored_survivors=scored,
        )
    return rec


# --------------------------------------------------------------------------
# curated picks: best overall / value / upgrade
# --------------------------------------------------------------------------
def _functional_match(breakdown: ScoreBreakdown, weights: Weights) -> float:
    """Fit ignoring price (speed + preference only), renormalised to 0-1.
    Used for the upgrade tier, which is allowed to exceed budget."""
    denom = weights.speed + weights.preference
    if denom <= 0:
        return breakdown.preference_score
    return (
        weights.speed * breakdown.speed_score
        + weights.preference * breakdown.preference_score
    ) / denom


def _pct(x: float) -> int:
    """Clamp a 0-1 score to an integer percentage."""
    return max(0, min(100, round(x * 100)))


def _better_quality(candidate: Product, base: Product) -> bool:
    """Is `candidate` a clear quality step up from `base`? Rating first, with
    review_count as a light tie-breaker. Conservative: needs a real margin."""
    cr, br = candidate.rating or 0.0, base.rating or 0.0
    if cr - br >= 0.2:
        return True
    if abs(cr - br) < 1e-9 and (candidate.review_count or 0) > (base.review_count or 0) * 1.5:
        return True
    return False


def curate_picks(
    candidates: list[Product],
    reqs: UserRequirements,
    review_summaries: Optional[dict[str, ReviewSummary]] = None,
    pickup_infos: Optional[dict[str, PickupInfo]] = None,
    *,
    today: Optional[date] = None,
    upgrade_slack: float = 0.15,
    scored_survivors: Optional[list[tuple[Product, ScoreBreakdown]]] = None,
) -> list[CuratedPick]:
    """Select up to three highlight products:

      - best_overall : highest weighted total among in-budget survivors
      - best_value   : best score-per-dollar that is *cheaper* than overall
      - best_upgrade : a pricier / up-to-`upgrade_slack`-over-budget product with
                       clearly better quality, scored on fit only (price excluded)

    Each tier is emitted only if a *distinct* product genuinely qualifies — no
    padding to reach three. Returns [] when there is nothing to rank.
    """
    from datetime import date as _date

    today = today or _date.today()
    review_summaries = review_summaries or {}
    pickup_infos = pickup_infos or {}
    weights = reqs.weights.normalized()

    if scored_survivors is None:
        survivors = [
            p for p in candidates if _passes_objective(p, reqs, pickup_infos.get(p.id))
        ]
        if not survivors:
            return []
        scored_survivors = _score_products(
            survivors, reqs, review_summaries, pickup_infos, today
        )
        scored_survivors.sort(key=lambda t: t[1].weighted_total, reverse=True)
    if not scored_survivors:
        return []

    by_breakdown = {p.id: b for p, b in scored_survivors}
    picks: list[CuratedPick] = []
    used: set[str] = set()

    # 1. best overall
    top_p, top_b = scored_survivors[0]
    picks.append(
        CuratedPick(
            tier=PickTier.BEST_OVERALL,
            product_id=top_p.id,
            match_pct=_pct(top_b.weighted_total),
            headline="Closest fit to everything you asked for.",
        )
    )
    used.add(top_p.id)
    top_price = top_p.total_price()

    # 2. best value — cheaper than overall, best weighted score per dollar
    value_pool = [
        (p, b)
        for p, b in scored_survivors
        if p.id not in used and p.total_price() < top_price
    ]
    if value_pool:
        best_p, best_b = max(
            value_pool,
            key=lambda t: t[1].weighted_total / max(float(t[0].total_price()), 1.0),
        )
        saving = top_price - best_p.total_price()
        headline = f"Saves {best_p.currency} {saving} versus the top pick"
        if best_b.preference_score < top_b.preference_score - 0.05:
            headline += ", trading off some of your preferences"
        headline += "."
        picks.append(
            CuratedPick(
                tier=PickTier.BEST_VALUE,
                product_id=best_p.id,
                match_pct=_pct(best_b.weighted_total),
                headline=headline,
            )
        )
        used.add(best_p.id)

    # 3. best upgrade — pricier, may exceed budget by up to `upgrade_slack`,
    #    but a clear quality step up; scored on fit only (price excluded).
    ceiling: Optional[Decimal] = None
    if reqs.budget is not None:
        ceiling = reqs.budget * (Decimal(1) + Decimal(str(upgrade_slack)))
    upgrade_pool = [
        p
        for p in candidates
        if p.id not in used
        and p.total_price() > top_price
        and (ceiling is None or p.total_price() <= ceiling)
        and _better_quality(p, top_p)
    ]
    if upgrade_pool:
        # score upgrades alongside survivors so the axes are comparable
        survivor_products = [p for p, _ in scored_survivors]
        union = survivor_products + [p for p in upgrade_pool if p.id not in by_breakdown]
        union_scores = {
            p.id: b
            for p, b in _score_products(
                union, reqs, review_summaries, pickup_infos, today
            )
        }
        best_up = max(
            upgrade_pool,
            key=lambda p: _functional_match(union_scores[p.id], weights),
        )
        up_b = union_scores[best_up.id]
        headline = "Pricier, but noticeably better reviews and quality"
        if reqs.budget is not None and best_up.total_price() > reqs.budget:
            over = best_up.total_price() - reqs.budget
            headline = (
                f"{best_up.currency} {over} over budget, but noticeably better "
                "reviews and quality"
            )
        picks.append(
            CuratedPick(
                tier=PickTier.BEST_UPGRADE,
                product_id=best_up.id,
                match_pct=_pct(_functional_match(up_b, weights)),
                match_label="functional match",
                headline=headline + ".",
            )
        )

    return picks


_TIER_LABEL = {
    PickTier.BEST_OVERALL: "🥇 BEST OVERALL",
    PickTier.BEST_VALUE: "💰 BEST VALUE",
    PickTier.BEST_UPGRADE: "⭐ BEST UPGRADE",
}


def format_picks(picks: list[CuratedPick], by_id: dict[str, Product]) -> str:
    """Render curated picks as the highlight block shown above the full list."""
    blocks: list[str] = []
    for pick in picks:
        p = by_id.get(pick.product_id)
        title = p.title if p else pick.product_id
        price = f"{p.currency} {p.total_price()}" if p else "?"
        blocks.append(
            f"{_TIER_LABEL[pick.tier]}\n"
            f"{title} — {price}\n"
            f"{pick.match_pct}% {pick.match_label}\n"
            f"{pick.headline}"
        )
    return "\n\n".join(blocks)


def explain(
    recommendation: Recommendation,
    candidates: list[Product],
    llm=None,
) -> Recommendation:
    """Optional: replace template explanations with an LLM-polished version for
    the top items. Falls back to the template (unchanged) on any failure or when
    no llm is supplied."""
    if llm is None:
        return recommendation
    by_id = {p.id: p for p in candidates}
    from shopping_agent.llm.parsing import structured_output
    from pydantic import BaseModel

    class _Phrase(BaseModel):
        text: str

    for item in recommendation.items:
        product = by_id.get(item.product_id)
        if product is None:
            continue
        try:
            prompt = (
                f"Rewrite this shortlist reason as one friendly sentence.\n"
                f"Product: {product.title}\nReason: {item.explanation}"
            )
            item.explanation = structured_output(
                llm, "recommend_explain", prompt, _Phrase
            ).text
        except Exception:
            pass  # keep the template explanation
    return recommendation


def _summarize_recommendation(rec: Recommendation, candidates_by_id: dict) -> str:
    """Compact human-readable shortlist for the agent."""
    if rec.status == "empty":
        return f"No matches. {rec.reason or ''}".strip()
    sections: list[str] = []
    if rec.picks:
        sections.append(format_picks(rec.picks, candidates_by_id))
    lines: list[str] = []
    for item in rec.items:
        p = candidates_by_id.get(item.product_id)
        title = p.title if p else item.product_id
        price = f"{p.currency} {p.total_price()}" if p else "?"
        lines.append(
            f"{item.rank}. {title} — {price} ({p.platform if p else '?'})\n"
            f"   {item.explanation}"
        )
    sections.append("Full ranking:\n" + "\n".join(lines))
    return "\n\n".join(sections)


@tool
def recommend_products(session_id: str = "") -> str:
    """Rank the current candidate products by the user's stated priorities and
    return the top few with a short reason for each.

    Reads candidates + requirements from shared state (keyed by session_id);
    does NOT take the full candidate list as an argument. Returns a compact
    human-readable summary for the agent; the structured Recommendation is
    written back to state.
    """
    from shopping_agent.tools.context import get_session

    session = get_session(session_id or None)
    if session.requirements is None:
        return "Cannot recommend yet: no user requirements in session."
    candidates = list(session.candidates.values())
    if not candidates:
        return "Cannot recommend yet: no candidate products in session."

    rec = rank_candidates(
        candidates,
        session.requirements,
        review_summaries=session.review_summaries or None,
        pickup_infos=session.pickups or None,
    )
    if session.llm is not None:
        rec = explain(rec, candidates, llm=session.llm)
    session.recommendation = rec
    return _summarize_recommendation(rec, session.candidates)
