"""customer_service core tests, driven by FakeLLM (no network/cost) and by the
deterministic no-llm fallback path."""

from shopping_agent.llm.parsing import FakeLLM
from shopping_agent.schemas import PolicySummary
from shopping_agent.tools.customer_service import (
    arrival_checklist,
    classify_intent,
    draft_seller_question,
    handle,
    summarize_policies,
)


def test_classify_intent():
    assert classify_intent("what's the return policy?") == "policy"
    assert classify_intent("can you ask the seller if it's waterproof?") == "question"
    assert classify_intent("what should I check when it arrives?") == "checklist"
    assert classify_intent("tell me about this") == "other"


def test_summarize_policies_no_llm_passthrough(candidates):
    amazon = next(c for c in candidates if c.platform == "amazon")
    summary = summarize_policies(amazon, llm=None)
    assert "30 days" in summary.returns
    assert "1-year" in summary.warranty


def test_summarize_policies_never_invents_when_missing(candidates):
    ebay = next(c for c in candidates if c.platform == "ebay")  # no policy text
    summary = summarize_policies(ebay, llm=None)
    assert summary == PolicySummary()  # all None, nothing invented


def test_summarize_policies_with_fake_llm(candidates):
    amazon = next(c for c in candidates if c.platform == "amazon")
    fake = FakeLLM(
        responses={
            "cs_policy": PolicySummary(
                returns="30-day free returns", warranty="1 year", shipping_terms="1-2 days"
            )
        }
    )
    summary = summarize_policies(amazon, llm=fake)
    assert summary.returns == "30-day free returns"
    assert fake.calls and fake.calls[0][0] == "cs_policy"


def test_draft_seller_question_no_llm(candidates):
    shopee = next(c for c in candidates if c.platform == "shopee")
    q = draft_seller_question(shopee, "battery life", llm=None)
    assert "battery life" in q
    assert shopee.title in q


def test_arrival_checklist_no_llm(candidates):
    shopee = next(c for c in candidates if c.platform == "shopee")
    items = arrival_checklist(shopee, llm=None)
    assert len(items) >= 4


def test_handle_other_intent_runs_policy_and_checklist(candidates):
    amazon = next(c for c in candidates if c.platform == "amazon")
    res = handle(amazon, "tell me about this product", llm=None)
    assert res.intent == "other"
    assert res.policy is not None
    assert res.checklist
