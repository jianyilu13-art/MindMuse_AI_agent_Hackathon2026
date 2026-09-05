"""Shared test fixtures. Loads the JSON fixtures into pydantic objects."""

import json
from pathlib import Path

import pytest

from shopping_agent.schemas import Product

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _force_offline_search(monkeypatch):
    """Tests must be deterministic and network-free: force the seeded search
    fixture even when a real SEARCHAPI_API_KEY is present in .env/env.
    (searchapi_key() treats an empty string as 'no key'.)"""
    monkeypatch.setenv("SEARCHAPI_API_KEY", "")
    yield


@pytest.fixture
def candidates() -> list[Product]:
    data = json.loads((FIXTURES / "candidates.json").read_text())
    return [Product.model_validate(d) for d in data]


@pytest.fixture
def local_inventory() -> dict:
    return json.loads((FIXTURES / "local_inventory.json").read_text())
