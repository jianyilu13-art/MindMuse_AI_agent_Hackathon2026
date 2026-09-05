"""customer_service tool -- post-selection assistant.

No external API: everything is derived from listing text already captured by
search. Three sub-capabilities, routed by the `request` intent:
  - summarize_policies : returns / warranty / shipping terms
  - draft_seller_question : a polite pre-sales question
  - arrival_checklist : what to check on delivery, by category
Never fabricate specific policy terms when the listing lacks them.

The LLM is reached through `llm.parsing.structured_output(llm, tag, prompt,
schema)`, so a FakeLLM drives this in tests with no network/cost.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from shopping_agent.llm.parsing import structured_output
from shopping_agent.schemas import CustomerServiceResult, PolicySummary, Product
from shopping_agent.tools._registry import tool

_POLICY_WORDS = ("return", "refund", "warranty", "guarantee", "shipping", "policy")
_QUESTION_WORDS = ("ask", "question", "seller", "does it", "is it", "can it", "?")
_CHECKLIST_WORDS = ("check", "arrival", "inspect", "receive", "unbox", "delivery")


def classify_intent(request: str) -> str:
    """Return one of: policy | question | checklist | other."""
    s = (request or "").lower()
    if any(w in s for w in _CHECKLIST_WORDS):
        return "checklist"
    if any(w in s for w in _POLICY_WORDS):
        return "policy"
    if any(w in s for w in _QUESTION_WORDS):
        return "question"
    return "other"


def summarize_policies(product: Product, llm: Any = None) -> PolicySummary:
    """Summarise return/warranty/shipping terms from listing text only.
    Missing text -> None fields, never invented terms."""
    has_text = any([product.return_policy_text, product.warranty_text])
    if not has_text:
        # Nothing to summarise; do NOT invent terms.
        return PolicySummary()
    if llm is None:
        # Deterministic fallback: pass the raw listing text straight through.
        return PolicySummary(
            returns=product.return_policy_text,
            warranty=product.warranty_text,
            shipping_terms=product.delivery_estimate,
        )
    prompt = (
        "Summarise the return, warranty and shipping terms from this listing. "
        "Use only what is stated; leave a field empty if not mentioned.\n"
        f"Returns: {product.return_policy_text}\n"
        f"Warranty: {product.warranty_text}\n"
        f"Shipping: {product.delivery_estimate}"
    )
    try:
        return structured_output(llm, "cs_policy", prompt, PolicySummary)
    except Exception:
        return PolicySummary(
            returns=product.return_policy_text,
            warranty=product.warranty_text,
            shipping_terms=product.delivery_estimate,
        )


class _Draft(BaseModel):
    text: str


def draft_seller_question(product: Product, user_question: str, llm: Any = None) -> str:
    """Draft a short, polite pre-sales question to the seller."""
    if llm is None:
        q = (user_question or "your question").strip().rstrip("?")
        return (
            f"Hi, I'm interested in \"{product.title}\". Could you tell me about "
            f"{q}? Thank you!"
        )
    prompt = (
        f"Write a short, polite question to a marketplace seller about the "
        f"product \"{product.title}\". The buyer wants to know: {user_question}"
    )
    try:
        return structured_output(llm, "cs_question", prompt, _Draft).text
    except Exception:
        q = (user_question or "your question").strip().rstrip("?")
        return (
            f"Hi, I'm interested in \"{product.title}\". Could you tell me about "
            f"{q}? Thank you!"
        )


_GENERIC_CHECKLIST = [
    "Confirm the item matches the listing title and model.",
    "Check for physical damage to the item and packaging.",
    "Verify all accessories and cables are included.",
    "Test that the item powers on / functions before the return window closes.",
    "Keep the receipt and packaging until you're sure you're keeping it.",
]


def arrival_checklist(product: Product, llm: Any = None) -> list[str]:
    """Category-aware 'what to check on arrival' list."""
    if llm is None:
        return list(_GENERIC_CHECKLIST)

    class _List(BaseModel):
        items: list[str]

    prompt = (
        f"List 4-6 concrete things a buyer should check when \"{product.title}\" "
        f"arrives, given these attributes: {product.attributes}."
    )
    try:
        out = structured_output(llm, "cs_checklist", prompt, _List).items
        return out or list(_GENERIC_CHECKLIST)
    except Exception:
        return list(_GENERIC_CHECKLIST)


def handle(product: Product, request: str, llm: Any = None) -> CustomerServiceResult:
    """Pure core: route the request to sub-capabilities and assemble a result.
    For an ambiguous ('other') intent, run policy + checklist as a helpful
    default."""
    intent = classify_intent(request)
    result = CustomerServiceResult(product_id=product.id, intent=intent)

    if intent in ("policy", "other"):
        result.policy = summarize_policies(product, llm=llm)
        if intent == "policy" and result.policy == PolicySummary():
            result.note = "The listing doesn't state its return/warranty terms."
    if intent == "question":
        result.drafted_question = draft_seller_question(product, request, llm=llm)
    if intent in ("checklist", "other"):
        result.checklist = arrival_checklist(product, llm=llm)

    return result


def _summarize_result(result: CustomerServiceResult) -> str:
    """Compact human-readable summary for the agent."""
    parts: list[str] = []
    if result.policy is not None:
        p = result.policy
        if any([p.returns, p.warranty, p.shipping_terms]):
            bits = [
                f"returns: {p.returns}" if p.returns else None,
                f"warranty: {p.warranty}" if p.warranty else None,
                f"shipping: {p.shipping_terms}" if p.shipping_terms else None,
            ]
            parts.append("Policy — " + "; ".join(b for b in bits if b))
    if result.drafted_question:
        parts.append(f"Drafted question: {result.drafted_question}")
    if result.checklist:
        parts.append("On arrival, check:\n- " + "\n- ".join(result.checklist))
    if result.note:
        parts.append(result.note)
    return "\n".join(parts) if parts else "Nothing to report for this request."


@tool
def customer_service(product_id: str, request: str) -> str:
    """Answer a post-selection question about a product: return/warranty
    policy, draft a question to the seller, or a delivery-check checklist.

    Reads the product from shared state, writes a CustomerServiceResult back,
    returns a compact summary for the agent.
    """
    from shopping_agent.tools.context import get_session

    session = get_session()
    product = session.get_product(product_id)
    result = handle(product, request, llm=session.llm)
    session.cs_results[product_id] = result
    return _summarize_result(result)
