"""Shared test fixtures. Loads the JSON fixtures into pydantic objects."""

import json
from pathlib import Path

import pytest

from shopping_agent.schemas import Product

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def candidates() -> list[Product]:
    data = json.loads((FIXTURES / "candidates.json").read_text())
    return [Product.model_validate(d) for d in data]


@pytest.fixture
def local_inventory() -> dict:
    return json.loads((FIXTURES / "local_inventory.json").read_text())
