"""Deterministic enforcement of shopper hard constraints."""

from shopping_agent.schemas import Product, UserRequirements


def apply_hard_constraints(products: list[Product], requirements: UserRequirements) -> list[Product]:
    qualified: list[Product] = []
    for product in products:
        if requirements.max_price is not None and product.price > requirements.max_price:
            continue
        if requirements.arrival_by is not None and (
            product.arrival_date is None or product.arrival_date > requirements.arrival_by
        ):
            continue
        product_text = f"{product.title} {' '.join(product.attributes.values())}".lower()
        if requirements.preferred_brands and product.attributes.get("brand", "").lower() not in {
            brand.lower() for brand in requirements.preferred_brands
        }:
            continue
        if requirements.size is not None:
            available_sizes = {size.strip() for size in product.attributes.get("sizes", "").split(",")}
            if requirements.size not in available_sizes:
                continue
        if any(feature.lower() not in product_text for feature in requirements.must_have):
            continue
        qualified.append(product)
    return qualified
