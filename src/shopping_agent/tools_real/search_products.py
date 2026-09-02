"""Cross-platform real product search orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from shopping_agent.platforms import PLATFORMS, ShoppingPlatform, get_platform
from shopping_agent.schemas import Product, UserRequirements

logger = logging.getLogger(__name__)
PlatformResolver = Callable[[str], ShoppingPlatform]


def search_products(
    query: str,
    *,
    platform_names: Iterable[str] | None = None,
    platform_resolver: PlatformResolver = get_platform,
) -> list[Product]:
    """Search each requested adapter, skipping only unimplemented integrations."""
    names = list(platform_names) if platform_names is not None else list(PLATFORMS)
    products: list[Product] = []
    for name in names:
        platform = platform_resolver(name)
        try:
            products.extend(platform.search_products(query))
        except NotImplementedError:
            logger.info("Skipping unimplemented %s search integration.", name)
    return products


class RealProductSearchTool:
    """Graph-compatible adapter around the real multi-platform search function."""

    def __init__(self, platform_resolver: PlatformResolver = get_platform) -> None:
        self.platform_resolver = platform_resolver

    def search(self, requirements: UserRequirements) -> list[Product]:
        if not requirements.query:
            return []
        names = requirements.preferred_platforms or None
        return search_products(
            requirements.query,
            platform_names=names,
            platform_resolver=self.platform_resolver,
        )
