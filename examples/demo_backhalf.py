"""Runnable demo of the back-half tools against fixture data.

    python examples/demo_backhalf.py

Loads sample candidates into a session, then runs the four tools the way the
agent would: recommend -> pickup -> customer_service -> cart. No network, no
API key (uses the deterministic no-LLM fallbacks).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from shopping_agent.schemas import Product, UserRequirements, Weights
from shopping_agent.tools import add_to_cart, check_pickup, customer_service, recommend_products
from shopping_agent.tools.context import get_session, new_session

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _call(tool, *args):
    return tool.func(*args) if hasattr(tool, "func") else tool(*args)


def main() -> None:
    candidates = [
        Product.model_validate(d)
        for d in json.loads((FIXTURES / "candidates.json").read_text())
    ]

    session = new_session(
        "demo",
        requirements=UserRequirements(
            product_query="wireless earbuds",
            budget=Decimal("150"),
            preferences=["USB-C", "ANC"],
            weights=Weights(price=0.4, speed=0.4, preference=0.2),
            max_results=3,
        ),
    )
    session.add_candidates(candidates)

    print("USER: best wireless earbuds under $150, USB-C, prefer ANC, need it soon\n")

    print("=== recommend_products ===")
    print(_call(recommend_products, "demo"), "\n")

    winner = get_session("demo").recommendation.items[0].product_id
    platform = winner.split(":")[0]

    print("=== check_pickup (top pick, in 3 days) ===")
    print(_call(check_pickup, winner, platform, "in 3 days"), "\n")

    print("=== customer_service (return policy) ===")
    print(_call(customer_service, winner, "what's the return policy?"), "\n")

    print("=== add_to_cart (top pick) ===")
    print(_call(add_to_cart, winner, platform))


if __name__ == "__main__":
    main()
