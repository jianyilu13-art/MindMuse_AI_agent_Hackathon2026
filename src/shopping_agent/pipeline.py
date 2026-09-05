"""pipeline -- end-to-end orchestration over the unified contract.

A lightweight reference orchestrator that runs the whole shopping flow on one
set of requirements:

    search (front half) -> recommend/rank -> pickup + service + cart (back half)
    -> customer-facing response

It deliberately stays framework-free so it runs anywhere with no LLM and no
network (offline search fixture). jianyi's LangGraph agent can replace this
orchestrator later using the same Session + tool contract — the tools and
schemas don't change.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from shopping_agent.schemas import CustomerResponse, UserRequirements
from shopping_agent.tools.cart import prepare_cart
from shopping_agent.tools.context import Session, new_session
from shopping_agent.tools.customer_response import build_customer_response
from shopping_agent.tools.customer_service import handle as cs_handle
from shopping_agent.tools.pickup import check_pickup_availability
from shopping_agent.tools.recommendation import rank_candidates
from shopping_agent.tools.search import search_products


def run_shopping(
    reqs: UserRequirements,
    *,
    session_id: str = "default",
    llm=None,
    today: Optional[date] = None,
    api_key: Optional[str] = None,
) -> CustomerResponse:
    """Run the full pipeline and return the customer-facing bundle.

    All intermediate results are written to the Session, so a caller (or a real
    agent) can inspect recommendation / pickups / cart afterwards."""
    today = today or date.today()
    session: Session = new_session(session_id, requirements=reqs, llm=llm)

    # 1. front half: search -> unified Products
    candidates = search_products(reqs, api_key=api_key)
    session.add_candidates(candidates)

    # 2. recommendation: rank + curated picks (top-N)
    rec = rank_candidates(
        candidates,
        reqs,
        review_summaries=session.review_summaries or None,
        pickup_infos=session.pickups or None,
        today=today,
    )
    session.recommendation = rec
    if rec.status != "ok":
        # nothing qualified -> still produce a response (empty cards + reason)
        resp = build_customer_response(session, today=today)
        resp.headline = rec.reason or "No products matched your requirements."
        session.customer_response = resp
        return resp

    # 3. back half, per recommended product:
    #    pickup (if a deadline was given), after-sales policy, checkout link
    recommended_ids = [item.product_id for item in rec.items]
    for pid in recommended_ids:
        product = session.candidates[pid]
        if reqs.deadline is not None:
            session.pickups[pid] = check_pickup_availability(
                product, reqs.deadline, reqs.shipping_location, today=today
            )
        session.cs_results[pid] = cs_handle(product, "return policy", llm=llm)
        session.cart_results[pid] = prepare_cart(product)

    # 4. final customer-facing assembly (owns the 🥇/💰/⭐ tiers)
    resp = build_customer_response(session, today=today)
    session.customer_response = resp
    return resp
