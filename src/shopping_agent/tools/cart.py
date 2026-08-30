"""cart tool -- order handoff.

Third-party carts are not writable, so this prepares a checkout deep link
instead of placing an order. Amazon's /gp/aws/cart/add.html?ASIN=... add-to-cart
URL is a real, login-free capability; other platforms get a product-link
handoff. NEVER claim an order was placed.
"""

from __future__ import annotations

from decimal import Decimal

from shopping_agent.schemas import CartLine, CartResult, CartStatus, Product
from shopping_agent.tools._registry import tool

# platforms where we can only hand off the product page (no add-to-cart link)
_HANDOFF_ONLY = {"ebay", "lazada", "shopee"}


def _amazon_asin(product: Product) -> str | None:
    """Pull the ASIN from an amazon id ('amazon:B0ABC123') or attributes."""
    if product.attributes.get("asin"):
        return str(product.attributes["asin"])
    if ":" in product.id:
        return product.id.split(":", 1)[1]
    return None


def build_checkout_url(product: Product, quantity: int = 1) -> str:
    """Construct a platform-specific add-to-cart / product deep link.
    Unknown / handoff-only platform -> the product's own URL."""
    platform = (product.platform or "").lower()
    if platform == "amazon":
        asin = _amazon_asin(product)
        if asin:
            # Real login-free add-to-cart endpoint.
            return (
                "https://www.amazon.sg/gp/aws/cart/add.html?"
                f"ASIN.1={asin}&Quantity.1={quantity}"
            )
    return product.url


def prepare_cart(product: Product, quantity: int = 1) -> CartResult:
    """Pure core: build link, line items, subtotal. status='prepared' or
    'unsupported'. Never 'ordered'."""
    if quantity < 1:
        quantity = 1
    platform = (product.platform or "").lower()
    url = build_checkout_url(product, quantity)

    unit = product.total_price()
    subtotal = (unit * quantity) if unit is not None else None
    line = CartLine(
        product_id=product.id,
        title=product.title,
        quantity=quantity,
        unit_price=unit,
    )

    if platform == "amazon" and "cart/add" in url:
        status = CartStatus.PREPARED
        instructions = (
            "Open this link to review the item in your Amazon cart and complete "
            "checkout yourself. Nothing has been ordered."
        )
    elif platform in _HANDOFF_ONLY:
        status = CartStatus.PREPARED
        instructions = (
            f"Open this {product.platform} product page to add it to your cart "
            "and check out yourself. Nothing has been ordered."
        )
    else:
        status = CartStatus.UNSUPPORTED
        instructions = (
            "Automated cart handoff isn't supported for this platform; open the "
            "product page to buy it yourself. Nothing has been ordered."
        )

    return CartResult(
        status=status,
        platform=product.platform,
        checkout_url=url,
        lines=[line],
        subtotal=subtotal,
        currency=product.currency,
        next_step_instructions=instructions,
    )


@tool
def add_to_cart(product_id: str, platform: str) -> str:
    """Prepare a checkout handoff for a chosen product: a deep link the user
    opens to review and pay. Does not place an order.

    Reads the product from shared state, writes a CartResult back, returns a
    compact summary for the agent.
    """
    from shopping_agent.tools.context import get_session

    session = get_session()
    product = session.get_product(product_id)
    result = prepare_cart(product)
    session.cart_results[product_id] = result

    if result.subtotal is not None:
        price = f" ({result.currency} {result.subtotal})"
    else:
        price = ""
    return (
        f"Checkout link ready for {product.title}{price}: {result.checkout_url}\n"
        f"{result.next_step_instructions}"
    )
