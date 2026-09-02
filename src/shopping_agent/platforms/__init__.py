"""Marketplace adapter registry used by :mod:`shopping_agent.tools_real`."""

from __future__ import annotations

from collections.abc import Callable

from .amazon import AmazonPlatform
from .base import ShoppingPlatform
from .ebay import EbayPlatform
from .lazada import LazadaPlatform
from .shopee import ShopeePlatform

PlatformFactory = Callable[[], ShoppingPlatform]

PLATFORMS: dict[str, PlatformFactory] = {
    "shopee": ShopeePlatform,
    "lazada": LazadaPlatform,
    "amazon": AmazonPlatform,
    "ebay": EbayPlatform,
}


def get_platform(name: str) -> ShoppingPlatform:
    """Create the adapter registered for a provider name."""
    normalized = name.strip().lower()
    try:
        return PLATFORMS[normalized]()
    except KeyError as error:
        supported = ", ".join(sorted(PLATFORMS))
        raise ValueError(f"Unsupported shopping platform {name!r}. Supported: {supported}.") from error


__all__ = [
    "AmazonPlatform", "EbayPlatform", "LazadaPlatform", "PLATFORMS", "PlatformFactory",
    "ShopeePlatform", "ShoppingPlatform", "get_platform",
]
