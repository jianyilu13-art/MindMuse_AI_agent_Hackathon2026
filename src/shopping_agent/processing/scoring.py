"""Scoring math for the recommendation tool. Pure functions, no LLM, no I/O.

Kept separate from the tool so it can be unit-tested in isolation (golden test:
fixed candidates + fixed weights -> expected ranked order).
"""

from __future__ import annotations

from typing import Any


def minmax_normalize(values: list[float], *, higher_is_better: bool) -> list[float]:
    """Map values to [0, 1] within the set.

    When ``higher_is_better`` is False (e.g. price, delivery days), the smallest
    input gets the highest score.

    Degenerate cases (empty, single element, all equal) -> 0.5 for every
    element, so no axis dominates by accident.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    span = hi - lo
    scores = [(v - lo) / span for v in values]  # 0 at lo, 1 at hi
    if not higher_is_better:
        scores = [1.0 - s for s in scores]
    return scores


def preference_score(
    product_attributes: dict[str, Any],
    prefs: list[str],
    aspect_sentiment: dict[str, float],
) -> float:
    """0-1 match between the user's stated preferences and the product's
    attributes + review aspect sentiment.

    For each preference term we look for evidence in two places:
      - the product's attribute values/keys (keyword overlap) -> +1
      - review aspect sentiment for that term -> maps [-1, 1] to [0, 1]
    The term's contribution is the max of whatever evidence we found. With no
    preferences at all we return a neutral 0.5.
    """
    if not prefs:
        return 0.5

    # Flatten attributes into a lowercase searchable blob.
    attr_blob = " ".join(
        f"{k} {v}" for k, v in product_attributes.items()
    ).lower()
    sentiment = {k.lower(): v for k, v in (aspect_sentiment or {}).items()}

    per_term: list[float] = []
    for pref in prefs:
        term = pref.strip().lower()
        if not term:
            continue
        evidence = 0.0
        # attribute keyword match
        if term in attr_blob:
            evidence = max(evidence, 1.0)
        # review aspect sentiment (match on whole word or token overlap)
        for aspect, s in sentiment.items():
            if term in aspect or aspect in term:
                evidence = max(evidence, (s + 1.0) / 2.0)
        per_term.append(evidence)

    if not per_term:
        return 0.5
    return sum(per_term) / len(per_term)
