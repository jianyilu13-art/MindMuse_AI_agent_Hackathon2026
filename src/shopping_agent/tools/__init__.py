"""Back-half tools: recommendation, pickup, customer_service, cart.

(search / compare are the front-half, owned by another teammate.)
"""

from shopping_agent.tools.recommendation import recommend_products, rank_candidates
from shopping_agent.tools.pickup import check_pickup, check_pickup_availability
from shopping_agent.tools.customer_service import customer_service
from shopping_agent.tools.cart import add_to_cart, prepare_cart

# Tools to bind to the agent from this half.
BACKHALF_TOOLS = [recommend_products, check_pickup, customer_service, add_to_cart]

__all__ = [
    "recommend_products",
    "rank_candidates",
    "check_pickup",
    "check_pickup_availability",
    "customer_service",
    "add_to_cart",
    "prepare_cart",
    "BACKHALF_TOOLS",
]
