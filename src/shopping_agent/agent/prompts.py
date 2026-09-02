"""Prompts only. Nodes and graph construction must not embed prompt text."""

INPUT_INTERPRETATION_PROMPT = """Interpret the shopper's latest message in context.
Return JSON only: {{"intent": one of "search", "change_requirements", "more_results",
"purchase", "finish", "clarify", "selected_product_id": string|null,
"should_extract_requirements": boolean}}. Set should_extract_requirements when the
message supplies or changes shopping requirements. Do not extract field values here.

Message: {message}
Current requirements: {current_requirements}
Known products: {products}
"""

REQUIREMENT_EXTRACTION_PROMPT = """Extract shopping requirements from the shopper message and
assess whether this particular request is ready for a useful search. Return JSON only:
{{"requirements":{{"query":string|null,"size":string|null,"max_price":number|null,"arrival_by":YYYY-MM-DD|null,
"must_have":[string],"preferred_brands":[string],"preferred_platforms":[string],
"ranking_priorities":[string],"no_preference_fields":[string]}},"assessment":{{"sufficient_for_search":boolean,
"missing_required_information":[string],"optional_preferences":[string],
"clarification_context":string|null}},"clarification_question":string|null}}.

Only record ranking priorities explicitly stated by the shopper (for example price, rating,
reviews, or delivery speed). If none are stated, leave ranking_priorities empty. Only treat
information as required when necessary for a useful search. Brand, colour, and
every possible feature are not automatically required. Record an explicit "I don't care" or
"any is fine" in no_preference_fields. Preserve known values unless the shopper changes them.
Do not invent prices, dates, sizes, or preferences. When asked to generate a clarification,
use the supplied assessment and ask only for missing required information.

Shopper message: {message}
Current requirements: {current_requirements}
"""

CLARIFICATION_PROMPT = """Write one concise shopping clarification question. Return JSON only:
{{"clarification_question": string}}. Ask only about the genuinely required missing information;
do not ask about optional preferences or imply that a brand is required.

Requirements: {requirements}
Missing required information: {missing_required_information}
Optional preferences: {optional_preferences}
Context: {clarification_context}
"""

SHOPPING_AGENT_SYSTEM_PROMPT = """You are a careful shopping assistant. Never invent
product facts, prices, availability, delivery dates, or reviews. Ask a concise clarification
when a critical requirement is genuinely missing."""

REVIEW_ANALYSIS_PROMPT = """Summarize these reviews for a shopper. Return JSON only with
sentiment, highlights, and concerns. Do not claim facts absent from reviews.

Reviews: {reviews}
"""

RANKING_PROMPT = """Describe shopper-relevant trade-offs among the supplied
already-qualified products. Do not remove products or decide hard constraints;
price and delivery eligibility have already been handled by Python.

Requirements: {requirements}
Products: {products}
"""

# Backward-compatible name used by any existing callers.
PRODUCT_RANKING_PROMPT = RANKING_PROMPT
