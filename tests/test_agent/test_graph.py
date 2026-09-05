"""LangGraph agent: memory, incremental refinement, LLM-driven turns."""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopping_agent.agent import initial_state, run_turn
from shopping_agent.llm.parsing import FakeLLM
from shopping_agent.llm.semantics import (
    FollowUp,
    RequirementPatch,
    TurnInterpretation,
    apply_patch,
    screen,
)
from shopping_agent.schemas import Product, UserRequirements
from shopping_agent.tools.context import clear_all


@pytest.fixture(autouse=True)
def _clean():
    clear_all()
    yield
    clear_all()


# ---------------------------------------------------------------- rule mode
def test_offline_conversation_reaches_results():
    s = initial_state("t", llm=None)
    s = run_turn(s, "running shoes under 150")
    assert s["requirements"].product_query == "running shoes"
    assert s["requirements"].budget == Decimal("150")
    s = run_turn(s, "cushioned lightweight")
    assert s["response"] is not None and s["response"].cards


def test_refinement_keeps_memory():
    """The bug this fixes: changing one detail must not lose the rest."""
    s = initial_state("t", llm=None)
    s = run_turn(s, "running shoes under 150")
    s = run_turn(s, "cushioned lightweight")
    s = run_turn(s, "actually make it black")

    r = s["requirements"]
    assert s["intent"] == "refine"
    assert r.product_query == "running shoes"          # remembered
    assert r.budget == Decimal("150")                  # remembered
    assert "cushioned" in r.preferences                # remembered
    assert r.attributes.get("color") == "black"        # newly applied
    assert s["response"].cards                         # re-searched


def test_quit_ends_conversation():
    s = initial_state("t", llm=None)
    s = run_turn(s, "quit")
    assert s["finished"] is True


# ---------------------------------------------------------------- LLM mode
def test_llm_drives_interpretation_and_questions():
    llm = FakeLLM({
        "interpret": TurnInterpretation(
            intent="new_search",
            patch=RequirementPatch(product_query="gaming laptop", budget=2000),
            reply="Looking for a gaming laptop.",
        ),
        # category-aware question — the rule engine would have asked for budget
        "next_question": FollowUp(field="ram", question="How much RAM do you need?"),
    })
    s = initial_state("t", llm=llm)
    s = run_turn(s, "I want a gaming laptop around 2000")

    assert s["requirements"].product_query == "gaming laptop"
    assert s["reply"] == "How much RAM do you need?"
    assert "ram" in s["asked"]
    assert [tag for tag, _ in llm.calls] == ["interpret", "next_question"]


def test_llm_failure_falls_back_to_rules():
    llm = FakeLLM({})  # every tag raises -> deterministic path
    s = initial_state("t", llm=llm)
    s = run_turn(s, "running shoes under 150")
    assert s["requirements"].product_query == "running shoes"
    assert s["requirements"].budget == Decimal("150")


# ---------------------------------------------------------------- patching
def test_apply_patch_merges_without_clobbering():
    base = UserRequirements(
        product_query="running shoes", budget=Decimal("150"),
        preferences=["cushioned"], attributes={"color": "white"},
    )
    merged = apply_patch(base, RequirementPatch(
        preferences=["lightweight"], attributes={"color": "black"}
    ))
    assert merged.product_query == "running shoes"
    assert merged.budget == Decimal("150")
    assert merged.preferences == ["cushioned", "lightweight"]   # extended
    assert merged.attributes["color"] == "black"                # overwritten


def test_apply_patch_can_clear_a_field():
    base = UserRequirements(product_query="shoes", budget=Decimal("100"))
    merged = apply_patch(base, RequirementPatch(cleared_fields=["budget"]))
    assert merged.budget is None


# ---------------------------------------------------------------- screening
def _p(pid, title, price=100):
    return Product(id=pid, platform="x", title=title, url="https://e/" + pid,
                   price=Decimal(str(price)))


def test_rule_screen_enforces_brand_and_attributes():
    products = [
        _p("1", "Nike Pegasus running shoes, black"),
        _p("2", "Adidas Duramo running shoes, black"),   # wrong brand
        _p("3", "Nike Pegasus running shoes, white"),    # wrong colour
    ]
    reqs = UserRequirements(product_query="running shoes",
                            preferred_brands=["Nike"], attributes={"color": "black"})
    kept = screen(products, reqs, llm=None)
    assert [p.id for p in kept] == ["1"]


def test_screen_never_empties_the_list():
    products = [_p("1", "Totally unrelated kettle")]
    reqs = UserRequirements(product_query="running shoes", preferred_brands=["Nike"])
    assert screen(products, reqs, llm=None) == products
