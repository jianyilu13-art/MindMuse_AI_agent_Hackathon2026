from shopping_agent.schemas import Product


def normalize_products(products: list[Product]) -> list[Product]:
    """Extension point for marketplace adapters; mocks already use this format."""
    return products
