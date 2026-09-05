"""Deterministic enforcement of shopper hard constraints."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from shopping_agent.schemas import Product, UserRequirements


def apply_hard_constraints(
    products: list[Product],
    requirements: UserRequirements,
) -> list[Product]:
    """Return only products that satisfy explicit shopper constraints."""

    qualified: list[Product] = []

    for product in products:
        if not _matches_price(product, requirements):
            continue

        if not _matches_arrival_date(product, requirements):
            continue

        if not _matches_brand(product, requirements):
            continue

        if not _matches_legacy_size(product, requirements):
            continue

        if not _matches_dynamic_attributes(product, requirements):
            continue

        if not _matches_must_have(product, requirements):
            continue

        qualified.append(product)

    return qualified


def _matches_price(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Reject products over the shopper's maximum price."""

    if requirements.max_price is None:
        return True

    return product.price <= requirements.max_price


def _matches_arrival_date(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Reject products that arrive after the shopper's deadline."""

    if requirements.arrival_by is None:
        return True

    if product.arrival_date is None:
        return False

    return product.arrival_date <= requirements.arrival_by


def _matches_brand(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Match the shopper's preferred brands."""

    requested_brands = list(requirements.preferred_brands)
    attribute_brand = requirements.attributes.get("brand")

    if attribute_brand not in (None, "", [], {}):
        requested_brands = (
            list(attribute_brand)
            if isinstance(attribute_brand, (list, tuple, set))
            else [str(attribute_brand)]
        )

    if not requested_brands:
        return True

    product_brand = str(
        product.attributes.get("brand", "")
    ).strip().lower()

    preferred_brands = {
        str(brand).strip().lower()
        for brand in requested_brands
    }

    return product_brand in preferred_brands


def _matches_legacy_size(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Preserve compatibility with the existing size field."""

    if requirements.size is None:
        return True

    product_sizes = product.attributes.get("sizes")

    if product_sizes is None:
        return False

    return _attribute_matches(
        requested_value=requirements.size,
        product_value=product_sizes,
    )


def _matches_dynamic_attributes(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Match every explicitly provided category-specific attribute."""

    for attribute_name, requested_value in requirements.attributes.items():
        if attribute_name in {
            "size",
            "max_price",
            "arrival_by",
            "brand",
            "sizes",
        }:
            continue

        product_value = product.attributes.get(attribute_name)

        if product_value is None:
            return False

        if not _attribute_matches(
            requested_value=requested_value,
            product_value=product_value,
        ):
            return False

    return True


def _matches_must_have(
    product: Product,
    requirements: UserRequirements,
) -> bool:
    """Match free-form required features against product text."""

    if not requirements.must_have:
        return True

    product_text = _product_text(product)

    return all(
        feature.strip().lower() in product_text
        for feature in requirements.must_have
    )


def _attribute_matches(
    requested_value: Any,
    product_value: Any,
) -> bool:
    """Compare scalar and collection-shaped product attributes."""

    if requested_value is None:
        return True

    if isinstance(requested_value, (list, tuple, set)):
        requested_values = list(requested_value)
    else:
        requested_values = [requested_value]

    if isinstance(product_value, (list, tuple, set)):
        product_values = list(product_value)
    else:
        product_values = [product_value]

    normalized_product_values = [
        _normalize_value(value)
        for value in product_values
    ]

    for requested_item in requested_values:
        normalized_requested = _normalize_value(requested_item)

        if normalized_requested in normalized_product_values:
            continue

        if any(
            normalized_requested in product_item
            or product_item in normalized_requested
            for product_item in normalized_product_values
        ):
            continue

        return False

    return True


def _normalize_value(value: Any) -> str:
    """Normalize values for case-insensitive matching."""

    return str(value).strip().lower().replace("_", " ")


def _product_text(product: Product) -> str:
    """Create searchable text from product title and attributes."""

    values: Iterable[Any] = product.attributes.values()

    attribute_text = " ".join(
        str(value)
        for value in values
    )

    return f"{product.title} {attribute_text}".lower()
