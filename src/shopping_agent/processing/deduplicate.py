from shopping_agent.schemas import Product


def deduplicate_products(products: list[Product]) -> list[Product]:
    """Keep the first occurrence of every provider-neutral product ID."""
    seen: set[str] = set()
    return [product for product in products if not (product.id in seen or seen.add(product.id))]
