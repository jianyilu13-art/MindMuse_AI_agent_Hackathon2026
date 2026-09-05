"""Deterministic enforcement of shopper hard constraints."""

from shopping_agent.schemas import Product, UserRequirements


def apply_hard_constraints(products: list[Product], requirements: UserRequirements) -> list[Product]:
    qualified: list[Product] = []
    for product in products:
        if not product.available or (product.stock is not None and product.stock <= 0):
            continue
        if requirements.min_price is not None and product.price < requirements.min_price:
            continue
        if requirements.max_price is not None and product.price > requirements.max_price:
            continue
        if requirements.arrival_by is not None and (
            product.arrival_date is None or product.arrival_date > requirements.arrival_by
        ):
            continue
        product_text = f"{product.title} {product.description} {' '.join(str(value) for value in product.attributes.values())}".lower()
        if requirements.size is not None:
            available_sizes = {size.strip() for size in str(product.attributes.get("sizes", "")).split(",")}
            if requirements.size not in available_sizes:
                continue
        if any(feature.lower() not in product_text for feature in requirements.must_have):
            continue
        qualified.append(product)
    return qualified
