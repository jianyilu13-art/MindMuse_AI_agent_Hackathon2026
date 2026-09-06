"""Deterministic enforcement of shopper hard constraints."""

from shopping_agent.schemas import Product, UserRequirements


def _attribute_matches(name: str, value: str, product_text: str) -> bool:
    """Match stated attribute values against normalized provider text."""
    normalized_name = name.casefold().replace("_", " ")
    normalized_value = value.casefold().strip()
    if not normalized_value:
        return True
    if normalized_name in {"gender", "sex"}:
        if normalized_value in {"female", "woman", "women", "womens"}:
            return any(term in product_text for term in ("female", "woman", "women", "womens"))
        if normalized_value in {"male", "man", "men", "mens"}:
            return any(term in product_text for term in ("male", "man", "men", "mens"))
    return normalized_value in product_text


def _attribute_match_state(product: Product, name: str, value: str, product_text: str) -> str:
    """Return match, mismatch, or unknown without treating missing data as mismatch."""
    if _attribute_matches(name, value, product_text):
        return "match"
    normalized_name = name.casefold().replace("_", " ")
    has_named_field = any(
        key.casefold().replace("_", " ") == normalized_name
        for key in product.attributes
    )
    return "mismatch" if has_named_field else "unknown"


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
            sizes_text = str(product.attributes.get("sizes", "")).strip()
            available_sizes = {size.strip() for size in sizes_text.split(",") if size.strip()}
            # A shopping aggregator often omits variants/sizes. Missing size
            # metadata means "unverified", not "does not match".
            if available_sizes and requirements.size not in available_sizes:
                continue
        if any(
            _attribute_match_state(product, name, value, product_text) == "mismatch"
            for name, value in requirements.attributes.items()
        ):
            continue
        if any(feature.lower() not in product_text for feature in requirements.must_have):
            continue
        qualified.append(product)
    return qualified
