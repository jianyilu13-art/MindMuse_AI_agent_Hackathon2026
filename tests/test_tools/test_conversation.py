"""Conversational requirement gathering -> real pipeline."""

from __future__ import annotations

from decimal import Decimal

from shopping_agent.ui.conversation import ChatSession, handle_message, is_quit


def _last(session):
    return session.messages[-1]["content"]


def test_multi_turn_gathers_then_runs():
    s = ChatSession()
    handle_message(s, "running shoes")          # product (needs size)
    assert s.stage == "need_size"
    handle_message(s, "EU 42")
    assert s.stage == "need_budget"
    handle_message(s, "under 150")
    assert s.stage == "need_prefs"
    handle_message(s, "cushioned, lightweight")
    assert s.stage == "results"
    assert s.response is not None and s.response.cards
    assert s.budget == Decimal("150")
    assert "cushioned" in s.prefs and "lightweight" in s.prefs


def test_one_shot_message_skips_answered_slots():
    s = ChatSession()
    # everything in one message: product + size + budget + a known pref
    handle_message(s, "running shoes EU 42 under $150 cushioned")
    # size/budget/pref absorbed inline -> should go straight to results
    assert s.stage == "results"
    assert s.response is not None and s.response.cards
    assert s.size and s.size.upper().startswith("EU")
    assert s.budget == Decimal("150")
    assert "cushioned" in s.prefs


def test_skip_budget_and_prefs():
    s = ChatSession()
    handle_message(s, "headphones")             # no size category -> straight to budget
    assert s.stage == "need_budget"
    handle_message(s, "skip")
    assert s.stage == "need_prefs"
    handle_message(s, "none")
    assert s.stage == "results"
    assert s.budget is None and s.prefs == []


def test_quit():
    s = ChatSession()
    handle_message(s, "quit")
    assert s.done is True
    assert is_quit("exit") and not is_quit("running shoes")
