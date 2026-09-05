"""customer_response -- the back half's final, customer-facing assembly.

The teammate's half returns a set of recommended products (+ optional ranking
reasons). This layer turns them into what the shopper actually sees:

    basic info  ·  why it's recommended  ·  how to get it (pickup/delivery)
    ·  after-sales (returns/warranty)  ·  a checkout link

It also owns the curated highlight tiers (🥇 Best Overall / 💰 Best Value /
⭐ Best Upgrade), computed from the recommended products + the user's stated
priorities.

Everything is derived from what's already in the Session and from listing text —
no network, no order is ever placed. The LLM (if present) only polishes text.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from shopping_agent.schemas import (
    CartStatus,
    CustomerResponse,
    PickTier,
    PickupInfo,
    PickupMethod,
    Product,
    ProductCard,
    UserRequirements,
)
from shopping_agent.tools._registry import tool
from shopping_agent.tools.cart import prepare_cart
from shopping_agent.tools.customer_service import summarize_policies
from shopping_agent.tools.pickup import check_pickup_availability, parse_delivery_days
from shopping_agent.tools.recommendation import curate_picks


# --------------------------------------------------------------------------
# per-card narrative pieces
# --------------------------------------------------------------------------
def _availability_line(
    product: Product,
    session,
    reqs: Optional[UserRequirements],
    today: date,
) -> Optional[str]:
    """How the shopper can get it. Prefers a pickup result already in the
    session; otherwise derives one from the deadline, else the listing ETA."""
    info: Optional[PickupInfo] = session.pickups.get(product.id)
    if info is None and reqs is not None and reqs.deadline is not None:
        try:
            info = check_pickup_availability(
                product, reqs.deadline, reqs.shipping_location, today=today
            )
        except Exception:
            info = None

    if info is not None:
        when = info.available_by.isoformat() if info.available_by else "an unknown date"
        if info.method == PickupMethod.STORE_PICKUP:
            return f"In-store pickup by {when}" + (f" at {info.location}" if info.location else "")
        if info.method == PickupMethod.LOCKER:
            return f"Locker collection by {when}"
        if info.method == PickupMethod.UNAVAILABLE:
            return f"Won't arrive in time — earliest {when}"
        return f"Ships, arriving around {when}"

    days = parse_delivery_days(product.delivery_estimate)
    if days is not None:
        return f"Ships in about {days} day{'s' if days != 1 else ''}"
    return None


def _after_sales_line(product: Product, llm=None) -> Optional[str]:
    """Return / warranty in one line, from listing text only (never invented)."""
    policy = summarize_policies(product, llm=llm)
    bits = []
    if policy.returns:
        bits.append(f"Returns: {policy.returns}")
    if policy.warranty:
        bits.append(f"Warranty: {policy.warranty}")
    return " · ".join(bits) if bits else None


def _checkout(product: Product, session) -> tuple[str, str]:
    """(url, note). Reuses a prepared cart if present, else prepares one now."""
    result = session.cart_results.get(product.id) or prepare_cart(product)
    if result.status == CartStatus.PREPARED and "cart/add" in result.checkout_url:
        note = "Click to add it straight to your Amazon cart, then check out yourself."
    elif result.status == CartStatus.PREPARED:
        note = "Click to open the product page and add it to your cart there."
    else:
        note = "Click to open the product page to buy it yourself."
    return result.checkout_url, note


def _reason_map(session) -> dict[str, str]:
    """Ranking reasons keyed by product id, if the recommender supplied them."""
    rec = session.recommendation
    if rec is None:
        return {}
    return {item.product_id: item.explanation for item in rec.items if item.explanation}


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------
def build_customer_response(
    session,
    *,
    today: Optional[date] = None,
    max_cards: int = 3,
) -> CustomerResponse:
    """Pure core: turn the recommended products + gathered results into a
    customer-facing bundle. No I/O beyond the session; safe to unit-test."""
    from datetime import date as _date

    today = today or _date.today()
    reqs = session.requirements
    products = list(session.candidates.values())
    if not products:
        return CustomerResponse(
            headline="No products to show yet.",
            cards=[],
            footer="",
        )

    reasons = _reason_map(session)

    # Curated tiers live here, in the feedback layer, computed from the
    # recommended products + the user's priorities.
    picks = []
    if reqs is not None:
        picks = curate_picks(
            products,
            reqs,
            session.review_summaries or None,
            session.pickups or None,
            today=today,
        )

    by_id = {p.id: p for p in products}
    pick_by_id = {pick.product_id: pick for pick in picks}

    # Order: curated picks first (in tier order), then any remaining products.
    ordered_ids = [pick.product_id for pick in picks]
    for p in products:
        if p.id not in ordered_ids:
            ordered_ids.append(p.id)
    ordered_ids = ordered_ids[:max_cards]

    cards: list[ProductCard] = []
    for pid in ordered_ids:
        product = by_id[pid]
        pick = pick_by_id.get(pid)
        url, note = _checkout(product, session)
        # reason: prefer the recommender's explanation, else the tier headline
        reason = reasons.get(pid) or (pick.headline if pick else "")
        cards.append(
            ProductCard(
                product_id=product.id,
                title=product.title,
                platform=product.platform,
                price=f"{product.currency} {product.total_price()}",
                rating=product.rating,
                url=product.url,
                image_url=product.image_url,
                tier=pick.tier if pick else None,
                match_pct=pick.match_pct if pick else None,
                match_label=pick.match_label if pick else "match",
                reason=reason,
                availability=_availability_line(product, session, reqs, today),
                after_sales=_after_sales_line(product, llm=session.llm),
                checkout_url=url,
                checkout_note=note,
            )
        )

    headline = "Here are your top picks:" if cards else "No matching products."
    footer = "Nothing has been ordered — you complete checkout yourself."
    return CustomerResponse(headline=headline, cards=cards, footer=footer)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
_TIER_LABEL = {
    PickTier.BEST_OVERALL: "🥇 BEST OVERALL",
    PickTier.BEST_VALUE: "💰 BEST VALUE",
    PickTier.BEST_UPGRADE: "⭐ BEST UPGRADE",
}


def render_customer_response(resp: CustomerResponse) -> str:
    """Human-readable rendering of the bundle (the card view)."""
    if not resp.cards:
        return resp.headline

    blocks: list[str] = []
    for card in resp.cards:
        head = _TIER_LABEL.get(card.tier) if card.tier else None
        lines: list[str] = []
        if head:
            lines.append(head)
        rating = f"  ·  {card.rating}★" if card.rating is not None else ""
        lines.append(f"{card.title} — {card.price}{rating}  ·  {card.platform}")
        if card.image_url:
            lines.append(f"🖼 {card.image_url}")
        if card.match_pct is not None:
            lines.append(f"{card.match_pct}% {card.match_label}")
        if card.reason:
            lines.append(card.reason)
        if card.availability:
            lines.append(f"🚚 {card.availability}")
        if card.after_sales:
            lines.append(f"📋 {card.after_sales}")
        if card.checkout_url:
            lines.append(f"🔗 {card.checkout_url}\n   {card.checkout_note}")
        blocks.append("\n".join(lines))

    parts = []
    if resp.headline:
        parts.append(resp.headline)
    parts.append("\n\n".join(blocks))
    if resp.footer:
        parts.append(resp.footer)
    return "\n\n".join(parts)


@tool
def present_to_customer(session_id: str = "") -> str:
    """Assemble the final customer-facing reply for the recommended products:
    basic info, why each is recommended, how to get it, after-sales, and a
    checkout link. Reads everything from shared state; places no order."""
    from shopping_agent.tools.context import get_session

    session = get_session(session_id or None)
    resp = build_customer_response(session)
    session.customer_response = resp
    return render_customer_response(resp)
