"""Graph nodes. Each is a small state transition; routing lives in routing.py.

The LLM does the reasoning (interpret the turn, choose the next question, screen
results); the deterministic tools do the maths and the I/O.
"""

from __future__ import annotations

from datetime import date

from shopping_agent.llm.semantics import apply_patch, interpret, next_question, screen
from shopping_agent.schemas import UserRequirements
from shopping_agent.tools.cart import prepare_cart
from shopping_agent.tools.context import new_session
from shopping_agent.tools.customer_response import build_customer_response
from shopping_agent.tools.customer_service import handle as cs_handle
from shopping_agent.tools.pickup import check_pickup_availability
from shopping_agent.tools.recommendation import rank_candidates
from shopping_agent.tools.search import search_products

from .state import AgentState


def understand(state: AgentState) -> dict:
    """LLM: classify the turn and patch the remembered requirements.

    This is the memory step — a refinement ("make it black") edits the existing
    request instead of starting over.
    """
    message = state.get("message", "")
    current = state.get("requirements")
    result = interpret(message, current, state.get("last_question", ""), llm=state.get("llm"))

    update: dict = {"intent": result.intent}
    if result.intent == "quit":
        return {**update, "finished": True, "awaiting_input": False,
                "reply": "Thanks for shopping with Muse! Nothing was ordered."}

    if result.intent == "new_search":
        # a different product: start a fresh request, but keep the conversation
        merged = apply_patch(None, result.patch)
        update["asked"] = []
        update["response"] = None
    else:
        merged = apply_patch(current, result.patch)

    if not merged.product_query and current is not None:
        merged.product_query = current.product_query
    update["requirements"] = merged
    if result.reply:
        update["reply"] = result.reply
    return update


def ask(state: AgentState) -> dict:
    """LLM: ask the single most useful missing detail for this category."""
    reqs: UserRequirements = state["requirements"]
    asked = list(state.get("asked", []))
    follow = next_question(reqs, asked, llm=state.get("llm"))
    if follow.ready_to_search or not follow.question:
        return {"awaiting_input": False}
    if follow.field:
        asked.append(follow.field)
    return {
        "reply": follow.question,
        "last_question": follow.question,
        "asked": asked,
        "awaiting_input": True,
    }


def search(state: AgentState) -> dict:
    """Search the marketplace, then LLM-screen for genuine matches."""
    reqs: UserRequirements = state["requirements"]
    try:
        found = search_products(reqs)
    except Exception as exc:
        return {"candidates": [], "error": f"search failed: {exc}"}
    kept = screen(found, reqs, llm=state.get("llm"))
    return {"candidates": kept, "error": None}


def recommend(state: AgentState) -> dict:
    """Rank, enrich (pickup / after-sales / cart), and assemble the cards."""
    reqs: UserRequirements = state["requirements"]
    candidates = state.get("candidates", [])
    session = new_session(state.get("session_id", "agent"),
                          requirements=reqs, llm=state.get("llm"))
    session.add_candidates(candidates)
    today = date.today()

    rec = rank_candidates(candidates, reqs, today=today)
    session.recommendation = rec

    if rec.status == "ok":
        for item in rec.items:
            product = session.candidates[item.product_id]
            if reqs.deadline is not None:
                session.pickups[product.id] = check_pickup_availability(
                    product, reqs.deadline, reqs.shipping_location, today=today
                )
            session.cs_results[product.id] = cs_handle(
                product, "return policy", llm=state.get("llm")
            )
            session.cart_results[product.id] = prepare_cart(product)

    response = build_customer_response(session, today=today)
    session.customer_response = response

    if response.cards:
        reply = (f"Here are my top {len(response.cards)} picks — see the cards below. "
                 "Tell me what to change, or ask for something else.")
    else:
        reply = (rec.reason or "I couldn't find a good match.") + \
                " Want to raise the budget or relax a requirement?"
    return {"response": response, "reply": reply, "awaiting_input": True,
            "last_question": ""}


def chitchat(state: AgentState) -> dict:
    """Nothing actionable this turn — keep the conversation open."""
    reply = state.get("reply") or "Tell me what you'd like to shop for."
    return {"reply": reply, "awaiting_input": True}
