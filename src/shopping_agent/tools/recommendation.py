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
    PickupInfo,
    Product,
    RankedItem,
    Recommendation,
    ReviewSummary,
    ScoreBreakdown,
    UserRequirements,
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


def rank_candidates(
    candidates: list[Product],
    reqs: UserRequirements,
    review_summaries: Optional[dict[str, ReviewSummary]] = None,
    pickup_infos: Optional[dict[str, PickupInfo]] = None,
    *,
    today: Optional[date] = None,
) -> Recommendation:
    """Pure core: score, filter, rank. No LLM, no I/O -> unit-testable."""
    from datetime import date as _date

    today = today or _date.today()
    review_summaries = review_summaries or {}
    pickup_infos = pickup_infos or {}
    weights = reqs.weights.normalized()

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

    # 2. axis inputs
    prices = [float(p.total_price()) for p in survivors]
    speeds = [_delivery_days(p, pickup_infos.get(p.id), today) for p in survivors]
    prefs = [
        preference_score(
            p.attributes,
            reqs.preferences,
            review_summaries[p.id].aspect_sentiment if p.id in review_summaries else {},
        )
        for p in survivors
    ]

    # 3. normalise within the surviving set
    price_scores = minmax_normalize(prices, higher_is_better=False)
    speed_scores = minmax_normalize(speeds, higher_is_better=False)
    # preference_score is already 0-1; keep as-is (don't re-normalise a 0-1 signal)

    # 4. weighted total + breakdown
    scored: list[tuple[Product, ScoreBreakdown]] = []
    for p, ps, ss, pf, raw_price, raw_speed in zip(
        survivors, price_scores, speed_scores, prefs, prices, speeds
    ):
        total = weights.price * ps + weights.speed * ss + weights.preference * pf
        breakdown = ScoreBreakdown(
            price_score=ps,
            speed_score=ss,
            preference_score=pf,
            weighted_total=total,
            raw={"total_price": raw_price, "delivery_days": raw_speed},
        )
        scored.append((p, breakdown))

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

    return Recommendation(status="ok", items=items, reason=None)


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
    lines: list[str] = []
    for item in rec.items:
        p = candidates_by_id.get(item.product_id)
        title = p.title if p else item.product_id
        price = f"{p.currency} {p.total_price()}" if p else "?"
        lines.append(
            f"{item.rank}. {title} — {price} ({p.platform if p else '?'})\n"
            f"   {item.explanation}"
        )
    return "Top picks:\n" + "\n".join(lines)


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
