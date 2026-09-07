"""Hard-constraint filtering.

`apply_hard_constraints` is the deterministic gate between search results and
ranking, and it encodes two subtle rules that are easy to regress:

  * missing provider data means "unverified", never "does not match" — an
    aggregator often omits sizes and attributes, and dropping those products
    would silently empty the results;
  * a stated attribute only rejects a product when the provider actually
    published that field with a conflicting value.
"""

from __future__ import annotations

from datetime import date

import pytest

from shopping_agent.processing import apply_hard_constraints
from shopping_agent.schemas import Product, UserRequirements


def make_product(
    product_id: str = "p1",
    *,
    title: str = "Running Shoe",
    price: float = 100.0,
    description: str = "",
    attributes: dict[str, str] | None = None,
    arrival_date: date | None = None,
    available: bool = True,
    stock: int | None = None,
) -> Product:
    return Product(
        id=product_id,
        title=title,
        price=price,
        platform="mock-market",
        url=f"https://example.test/{product_id}",
        description=description,
        attributes=attributes or {},
        arrival_date=arrival_date,
        available=available,
        stock=stock,
    )


def ids(products: list[Product]) -> list[str]:
    return [product.id for product in products]


# --------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------
def test_unavailable_products_are_rejected():
    products = [
        make_product("in-stock"),
        make_product("unavailable", available=False),
    ]
    assert ids(apply_hard_constraints(products, UserRequirements())) == ["in-stock"]


def test_zero_stock_is_rejected_but_unknown_stock_is_kept():
    products = [
        make_product("unknown-stock", stock=None),
        make_product("has-stock", stock=3),
        make_product("sold-out", stock=0),
    ]
    kept = ids(apply_hard_constraints(products, UserRequirements()))
    assert kept == ["unknown-stock", "has-stock"]


# --------------------------------------------------------------------------
# price
# --------------------------------------------------------------------------
def test_price_bounds_are_inclusive():
    products = [
        make_product("below", price=49.0),
        make_product("at-min", price=50.0),
        make_product("at-max", price=150.0),
        make_product("above", price=151.0),
    ]
    requirements = UserRequirements(min_price=50, max_price=150)
    assert ids(apply_hard_constraints(products, requirements)) == ["at-min", "at-max"]


# --------------------------------------------------------------------------
# arrival date
# --------------------------------------------------------------------------
def test_arrival_deadline_rejects_late_and_undated_products():
    deadline = date(2026, 9, 10)
    products = [
        make_product("early", arrival_date=date(2026, 9, 8)),
        make_product("on-time", arrival_date=deadline),
        make_product("late", arrival_date=date(2026, 9, 11)),
        make_product("undated", arrival_date=None),
    ]
    requirements = UserRequirements(arrival_by=deadline)
    assert ids(apply_hard_constraints(products, requirements)) == ["early", "on-time"]


def test_arrival_date_ignored_when_no_deadline_is_set():
    products = [make_product("undated", arrival_date=None)]
    assert ids(apply_hard_constraints(products, UserRequirements())) == ["undated"]


# --------------------------------------------------------------------------
# size: missing metadata must not be treated as a mismatch
# --------------------------------------------------------------------------
def test_size_filter_matches_declared_sizes():
    products = [
        make_product("has-size", attributes={"sizes": "9, 10, 11"}),
        make_product("wrong-size", attributes={"sizes": "7, 8"}),
    ]
    requirements = UserRequirements(size="10")
    assert ids(apply_hard_constraints(products, requirements)) == ["has-size"]


def test_product_without_size_metadata_is_kept_as_unverified():
    """An aggregator that omits variants must not lose the product."""
    products = [make_product("no-size-data", attributes={})]
    requirements = UserRequirements(size="10")
    assert ids(apply_hard_constraints(products, requirements)) == ["no-size-data"]


def test_size_values_are_compared_after_trimming_whitespace():
    products = [make_product("spaced", attributes={"sizes": " 9 , 10 , 11 "})]
    assert ids(apply_hard_constraints(products, UserRequirements(size="10"))) == ["spaced"]


# --------------------------------------------------------------------------
# attributes: mismatch vs unknown
# --------------------------------------------------------------------------
def test_attribute_mismatch_rejects_only_when_the_field_exists():
    products = [
        make_product("declared-blue", attributes={"color": "blue"}),
        make_product("declared-red", attributes={"color": "red"}),
        make_product("undeclared", attributes={}),
    ]
    requirements = UserRequirements(attributes={"color": "red"})
    kept = ids(apply_hard_constraints(products, requirements))

    assert "declared-red" in kept          # matches
    assert "declared-blue" not in kept     # published a conflicting value
    assert "undeclared" in kept            # unknown, not a mismatch


def test_attribute_matches_against_title_and_description():
    products = [
        make_product("in-title", title="Red Running Shoe"),
        make_product("in-description", description="Comes in red"),
    ]
    requirements = UserRequirements(attributes={"color": "red"})
    assert ids(apply_hard_constraints(products, requirements)) == ["in-title", "in-description"]


def test_empty_attribute_value_is_not_a_constraint():
    products = [make_product("anything", attributes={"color": "green"})]
    requirements = UserRequirements(attributes={"color": ""})
    assert ids(apply_hard_constraints(products, requirements)) == ["anything"]


@pytest.mark.parametrize("stated", ["female", "woman", "women", "womens"])
def test_gender_synonyms_match_womens_listings(stated: str):
    products = [make_product("womens", title="Women's Running Shoe")]
    requirements = UserRequirements(attributes={"gender": stated})
    assert ids(apply_hard_constraints(products, requirements)) == ["womens"]


@pytest.mark.parametrize("stated", ["male", "man", "men", "mens"])
def test_gender_synonyms_match_mens_listings(stated: str):
    products = [make_product("mens", title="Men's Running Shoe")]
    requirements = UserRequirements(attributes={"gender": stated})
    assert ids(apply_hard_constraints(products, requirements)) == ["mens"]


def test_attribute_name_underscores_are_normalized():
    products = [make_product("declared", attributes={"shoe type": "trail"})]
    requirements = UserRequirements(attributes={"shoe_type": "trail"})
    assert ids(apply_hard_constraints(products, requirements)) == ["declared"]


# --------------------------------------------------------------------------
# must-have features
# --------------------------------------------------------------------------
def test_must_have_features_must_all_appear():
    products = [
        make_product("both", title="Cushioned lightweight runner"),
        make_product("one", title="Cushioned runner"),
    ]
    requirements = UserRequirements(must_have=["cushioned", "lightweight"])
    assert ids(apply_hard_constraints(products, requirements)) == ["both"]


def test_must_have_matching_is_case_insensitive():
    products = [make_product("upper", title="CUSHIONED Runner")]
    requirements = UserRequirements(must_have=["Cushioned"])
    assert ids(apply_hard_constraints(products, requirements)) == ["upper"]


# --------------------------------------------------------------------------
# whole-set behaviour
# --------------------------------------------------------------------------
def test_no_requirements_keeps_every_available_product():
    products = [make_product("a"), make_product("b")]
    assert ids(apply_hard_constraints(products, UserRequirements())) == ["a", "b"]


def test_input_order_is_preserved():
    products = [make_product("first", price=10), make_product("second", price=5)]
    assert ids(apply_hard_constraints(products, UserRequirements())) == ["first", "second"]


def test_empty_input_returns_empty_list():
    assert apply_hard_constraints([], UserRequirements(max_price=100)) == []
