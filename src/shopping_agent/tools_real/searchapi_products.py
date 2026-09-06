"""SearchAPI.io adapters for public Google Shopping and Google web results."""

from __future__ import annotations

import json
import os
import re
from math import isfinite
from hashlib import sha1
import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from dotenv import load_dotenv
import requests

from shopping_agent.schemas import CommunityFeedback, CommunityFeedbackSummary, Product, ReviewSummary, UserRequirements

SEARCH_ENDPOINT = "https://www.searchapi.io/api/v1/search"
_PRICE = re.compile(r"(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)")
logger = logging.getLogger(__name__)


class TTLCache:
    """Small, process-local, thread-safe cache for public search responses."""
    def __init__(self, ttl_seconds: float = 300, max_items: int = 128) -> None:
        self.ttl_seconds, self.max_items = ttl_seconds, max_items
        self._values: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            value = self._values.get(key)
            if value is None or monotonic() - value[0] > self.ttl_seconds:
                self._values.pop(key, None)
                return None
            self._values.move_to_end(key)
            return value[1]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._values[key] = (monotonic(), value)
            self._values.move_to_end(key)
            while len(self._values) > self.max_items:
                self._values.popitem(last=False)


class SearchAPIError(RuntimeError):
    """Actionable failure returned by the public SearchAPI integration."""


def extract_price(value: Any) -> float | None:
    """Return a numeric price from SearchAPI's string or numeric price fields."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        price = float(value)
        return price if isfinite(price) and price >= 0 else None
    if not isinstance(value, str):
        return None
    match = _PRICE.search(value.replace("\u00a0", " "))
    if not match:
        return None
    price = float(match.group(1).replace(",", ""))
    return price if isfinite(price) and price >= 0 else None


def _first_present(item: dict[str, Any], *names: str) -> Any:
    """Return the first non-empty provider value without losing valid zeroes."""
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return None


def extract_currency(value: Any) -> str | None:
    """Infer a currency only when its code or unambiguous symbol is present."""
    if not isinstance(value, str):
        return None
    code = re.search(r"\b([A-Z]{3})\b", value)
    if code:
        return code.group(1)
    for symbol, currency in (("S$", "SGD"), ("US$", "USD"), ("A$", "AUD"), ("€", "EUR"), ("£", "GBP")):
        if symbol in value:
            return currency
    return None


class SearchAPIClient:
    def __init__(self, api_key: str | None = None, *, gl: str | None = None, hl: str | None = None,
                 timeout: float = 10.0, opener: Callable[..., Any] | None = None,
                 session: requests.Session | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("SEARCHAPI_API_KEY")
        self.gl, self.hl, self.timeout, self.opener = gl or os.getenv("SEARCHAPI_GL", "sg"), hl or os.getenv("SEARCHAPI_HL", "en"), timeout, opener
        self.session = session
        self._thread_local = threading.local()

    def _session_for_current_thread(self) -> requests.Session:
        if self.session is not None:
            return self.session
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def search(self, params: dict[str, str]) -> dict[str, Any]:
        if not self.api_key:
            raise SearchAPIError("SEARCHAPI_API_KEY is missing. Add it to .env before searching products.")
        request_params = {**params, "api_key": self.api_key, "gl": self.gl, "hl": self.hl}
        started = monotonic()
        try:
            if self.opener is not None:  # Test seam retained for deterministic HTTP tests.
                query = urlencode(request_params)
                request = Request(f"{SEARCH_ENDPOINT}?{query}", headers={"Accept": "application/json"})
                with self.opener(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            else:
                response = self._session_for_current_thread().get(SEARCH_ENDPOINT, params=request_params, headers={"Accept": "application/json"}, timeout=(3.0, self.timeout))
                response.raise_for_status()
                payload = response.json()
        except HTTPError as error:
            message = "SearchAPI rate limit reached. Please wait and retry." if error.code == 429 else f"SearchAPI request failed (HTTP {error.code}). Please retry later."
            raise SearchAPIError(message) from error
        except requests.Timeout as error:
            raise SearchAPIError("SearchAPI timed out. Please retry.") from error
        except requests.RequestException as error:
            status = getattr(error.response, "status_code", None)
            if status == 429:
                raise SearchAPIError("SearchAPI rate limit reached. Please wait and retry.") from error
            raise SearchAPIError("SearchAPI could not be reached. Check your connection and retry.") from error
        except (URLError, TimeoutError) as error:
            raise SearchAPIError("SearchAPI could not be reached. Check your connection and retry.") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SearchAPIError("SearchAPI returned an invalid response.") from error
        if not isinstance(payload, dict):
            raise SearchAPIError("SearchAPI returned an unexpected response format.")
        if payload.get("error"):
            raise SearchAPIError(f"SearchAPI error: {payload['error']}")
        logger.info("searchapi_request engine=%s elapsed_ms=%.1f", params.get("engine"), (monotonic() - started) * 1000)
        return payload


def build_shopping_query(requirements: UserRequirements) -> str:
    query = requirements.query or ""
    if requirements.size:
        query += " size " + requirements.size
    if requirements.attributes:
        query += " " + " ".join(f"{name} {value}" for name, value in requirements.attributes.items())
    if requirements.must_have:
        query += " " + " ".join(requirements.must_have)
    if requirements.preferred_brands:
        query += " " + " ".join(requirements.preferred_brands)
    # These are search preferences, not authenticated marketplace operations.
    if requirements.preferred_platforms:
        query += " " + " ".join(requirements.preferred_platforms)
    return query.strip()


def normalize_shopping_result(item: dict[str, Any], index: int = 0) -> Product | None:
    price_text = _first_present(item, "extracted_price", "price")
    price = extract_price(price_text)
    if price is None:
        return None
    title_value = _first_present(item, "title", "name")
    url_value = _first_present(item, "link", "product_link", "url")
    if not title_value or not url_value:
        return None
    title, url = str(title_value), str(url_value)
    if urlparse(url).scheme not in {"http", "https"}:
        return None
    seller = item.get("source") or item.get("seller") or item.get("merchant") or item.get("store")
    currency = str(_first_present(item, "currency", "price_currency") or extract_currency(item.get("price")) or _locale_currency())
    rating = item.get("rating") or item.get("reviews_rating")
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    count = item.get("reviews") or item.get("review_count") or item.get("rating_count") or 0
    try:
        count = int(str(count).replace(",", ""))
    except (TypeError, ValueError):
        count = 0
    identifier = str(item.get("product_id") or item.get("id") or sha1(f"{title}|{url}|{index}".encode()).hexdigest()[:16])
    sizes_value = _first_present(item, "sizes", "available_sizes", "size", "variants")
    if isinstance(sizes_value, (list, tuple, set)):
        sizes_value = ", ".join(str(size) for size in sizes_value)
    elif isinstance(sizes_value, dict):
        sizes_value = ", ".join(str(size) for size in sizes_value.keys())
    raw_attributes = {
        "delivery": item.get("delivery"),
        "condition": item.get("condition"),
        "brand": item.get("brand"),
        "sizes": sizes_value,
    }
    if rating is not None:
        rating = min(max(rating, 0), 5)
    stock_value = item.get("stock") if item.get("stock") is not None else item.get("stock_count")
    try:
        stock = int(stock_value) if stock_value is not None else None
    except (TypeError, ValueError):
        stock = None
    availability = str(item.get("availability") or "").lower()
    available = availability not in {"out of stock", "unavailable", "false"}
    return Product(id=identifier, title=title, price=price, currency=currency, platform=str(seller or urlparse(url).netloc), seller=str(seller) if seller else None,
                   url=url, rating=rating, review_count=max(count, 0), shipping_info=item.get("delivery") or item.get("shipping"),
                   image_url=_first_present(item, "thumbnail", "image", "image_url"), original_price=extract_price(_first_present(item, "old_price", "original_price")),
                   stock=stock, available=available, attributes={k: str(v) for k, v in raw_attributes.items() if v not in (None, "")}, raw_metadata=item)


def _locale_currency() -> str:
    """Use the configured SearchAPI locale only when the result omits currency."""
    return {"sg": "SGD", "us": "USD", "gb": "GBP", "au": "AUD", "ca": "CAD"}.get(
        os.getenv("SEARCHAPI_GL", "sg").lower(), "USD"
    )


class SearchAPIProductSearchTool:
    def __init__(self, client: SearchAPIClient | None = None, *, cache: TTLCache | None = None) -> None:
        self.client = client or SearchAPIClient()
        self.cache = cache or TTLCache()

    def search(self, requirements: UserRequirements) -> list[Product]:
        query = build_shopping_query(requirements)
        if not query:
            return []
        key = json.dumps({"query": query, "min_price": requirements.min_price, "max_price": requirements.max_price, "size": requirements.size,
                          "must_have": sorted(requirements.must_have), "brands": sorted(requirements.preferred_brands),
                          "platforms": sorted(requirements.preferred_platforms), "gl": getattr(self.client, "gl", ""), "hl": getattr(self.client, "hl", "")}, sort_keys=True)
        cached = self.cache.get(key)
        if cached is not None:
            logger.info("searchapi_product_cache hit=true")
            return [product.model_copy(deep=True) for product in cached]
        payload = self.client.search({"engine": "google_shopping", "q": query})
        results = payload.get("shopping_results") or payload.get("product_results") or []
        if not isinstance(results, list):
            raise SearchAPIError("SearchAPI shopping results were malformed.")
        limit = max(1, int(os.getenv("SEARCHAPI_MAX_PRODUCTS", "12")))
        products = [product for index, item in enumerate(results[:limit]) if isinstance(item, dict) and (product := normalize_shopping_result(item, index))]
        self.cache.put(key, products)
        return [product.model_copy(deep=True) for product in products]


class SearchAPIReviewTool:
    """Marketplace evidence already present in Shopping results; never fabricated."""
    def fetch(self, products: list[Product]) -> dict[str, ReviewSummary]:
        return {product.id: ReviewSummary(product_id=product.id, available=product.rating is not None,
                highlights=[f"Marketplace rating: {product.rating}/5 ({product.review_count} reviews)"] if product.rating is not None else []) for product in products}


class SearchAPICommunityFeedbackTool:
    def __init__(self, client: SearchAPIClient | None = None, *, cache: TTLCache | None = None, top_k: int | None = None) -> None:
        self.client = client or SearchAPIClient()
        self.cache = cache or TTLCache()
        self.top_k = top_k if top_k is not None else max(0, int(os.getenv("SEARCHAPI_FORUM_TOP_K", "1")))

    def fetch(self, products: list[Product]) -> dict[str, CommunityFeedbackSummary]:
        selected = products[:self.top_k]
        def fetch_one(product: Product) -> CommunityFeedbackSummary:
            key = f"{product.title.casefold()}|{product.url}"
            cached = self.cache.get(key)
            if cached is not None:
                return cached.model_copy(deep=True)
            payload = self.client.search({"engine": "google", "q": f"{product.title} Reddit reviews forum opinions user experience", "num": "5"})
            sources: list[CommunityFeedback] = []
            results = payload.get("organic_results", []) or []
            if not isinstance(results, list):
                raise SearchAPIError("SearchAPI community results were malformed.")
            for item in results:
                if not isinstance(item, dict) or not item.get("link"):
                    continue
                url = str(item["link"]); domain = urlparse(url).netloc.lower()
                sources.append(CommunityFeedback(product_id=product.id, title=str(item.get("title") or domain), snippet=str(item.get("snippet") or ""), url=url, domain=domain))
            sources.sort(key=lambda source: ("reddit.com" not in source.domain and "forum" not in source.domain, source.domain))
            summary = CommunityFeedbackSummary(product_id=product.id, available=bool(sources), sources=sources)
            self.cache.put(key, summary)
            return summary
        if not selected:
            return {}
        with ThreadPoolExecutor(max_workers=min(3, len(selected))) as executor:
            summaries = list(executor.map(fetch_one, selected))
        return {summary.product_id: summary for summary in summaries}
