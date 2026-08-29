"""Prompts only. Nodes and graph construction must not embed prompt text."""

REQUIREMENT_EXTRACTION_PROMPT = """Extract shopping requirements from the shopper message.
Return JSON only with: query (string or null), max_price (number or null),
arrival_by (YYYY-MM-DD or null), must_have (string list), preferred_brands
(string list), preferred_platforms (string list). Do not infer a price or
arrival deadline that was not stated.

Shopper message: {message}
Current requirements: {current_requirements}
"""

INTENT_PROMPT = """Classify the shopper's latest message in the context of the current
shopping state. Return JSON only with intent, where intent is one of search,
change_requirements, more_results, purchase, finish, or clarify; and optional
selected_product_id. A request to alter budget, item, delivery, or features is
change_requirements. Do not decide whether products meet price or date limits.

Message: {message}
Known products: {products}
"""

REVIEW_ANALYSIS_PROMPT = """Summarize these reviews for a shopper. Return JSON only with
sentiment, highlights, and concerns. Do not claim facts absent from reviews.

Reviews: {reviews}
"""

PRODUCT_RANKING_PROMPT = """Describe shopper-relevant trade-offs among the supplied
already-qualified products. Do not remove products or decide hard constraints;
price and delivery eligibility have already been handled by Python.

Requirements: {requirements}
Products: {products}
"""
