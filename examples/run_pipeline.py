"""End-to-end demo: one user request -> full pipeline -> customer response.

Runs offline (seeded search fixture, no LLM, no API key). Set SEARCHAPI_API_KEY
to hit real Google Shopping instead.

    PYTHONPATH=src python examples/run_pipeline.py
"""

from datetime import date, timedelta
from decimal import Decimal

from shopping_agent.schemas import UserRequirements, Weights
from shopping_agent.pipeline import run_shopping
from shopping_agent.tools.customer_response import render_customer_response


def main() -> None:
    reqs = UserRequirements(
        product_query="running shoes",
        category="running_shoes",
        budget=Decimal("150"),
        currency="SGD",
        deadline=date.today() + timedelta(days=4),
        preferences=["cushioned", "lightweight", "breathable"],
        must_have=["running"],
        preferred_brands=["Nike", "Adidas", "ASICS"],
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
        max_results=3,
    )

    resp = run_shopping(reqs)
    print("=" * 60)
    print("USER: running shoes, budget S$150, needs cushioned/lightweight")
    print("=" * 60)
    print(render_customer_response(resp))


if __name__ == "__main__":
    main()
