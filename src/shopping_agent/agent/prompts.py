"""Prompts only. Nodes and graph construction must not embed prompt text."""

INPUT_INTERPRETATION_PROMPT = """Interpret the shopper's latest message in context.
Return JSON only: {{"intent": one of "search", "change_requirements", "more_results",
"purchase", "compare", "finish", "clarify", "selected_product_id": string|null,
"selected_product_ids": [string],
"should_extract_requirements": boolean}}. Set should_extract_requirements when the
message supplies or changes shopping requirements. Do not extract field values here.

Message: {message}
Current requirements: {current_requirements}
Known products: {products}
Recent conversation:
{conversation_context}

Interpret the message in the conversation context. Every message must be classified,
including short replies such as "yes", "no", "any", "no preference", or "keep current".
If the shopper confirms the current requirements and wants to proceed, return intent="search"
and should_extract_requirements=false. If the shopper wants to relax, replace, or add a
requirement, return intent="change_requirements" and should_extract_requirements=true.
If the shopper supplies an answer to a clarification question, return
should_extract_requirements=true so the answer is merged into the current requirements.
For a new product request with no current requirements, return
should_extract_requirements=true so the product category can be assessed before searching.
Any message that states or changes a price, budget, minimum, maximum, size, interface,
capacity, delivery date, platform, or product feature must set should_extract_requirements=true
and intent="change_requirements", even if the message is short or follows a no-results response.
Do not infer a value that the shopper did not state.
"""

REQUIREMENT_EXTRACTION_PROMPT = """Extract shopping requirements from the shopper message and
assess whether this particular request is ready for a useful search. Return JSON only:
{{"requirements":{{"query":string|null,"size":string|null,"min_price":number|null,"max_price":number|null,"arrival_by":YYYY-MM-DD|null,
"attributes":{{string:string}},
"must_have":[string],"preferred_brands":[string],"preferred_platforms":[string],
"ranking_priorities":[string],"no_preference_fields":[string]}},"assessment":{{"sufficient_for_search":boolean,
"missing_required_information":[string],"optional_preferences":[string],
"clarification_context":string|null}},"relaxed_fields":[string],"clarification_question":string|null}}.

First identify the product category and the minimum facts needed for a useful search.
Ask for category-specific required details before searching. Examples: shoe size for shoes,
storage interface and capacity for an SSD (for example NVMe or SATA), dimensions for furniture,
and compatibility for electronics. Put stated category-specific values in attributes.
Put missing required details in missing_required_information and set sufficient_for_search=false.
Put useful but optional preferences, such as brand or colour, in optional_preferences instead of
blocking the search. Only record ranking priorities explicitly stated by the shopper (for example price,
rating, reviews, or delivery speed). If none are stated, leave ranking_priorities empty. Record an explicit "I don't care" or
"any is fine", "no preference", "doesn't matter", or "I don't know" in no_preference_fields.
Treat those phrases as an explicit lack of preference, not as a value to invent. For a required
field, treat an explicit "any" or "no preference" as an answered field with no constraint.
For example, for a shoe-size question, "any size" means the shopper accepts any size: clear
the size value, remove size from missing_required_information, and do not ask for it again.
Preserve known values unless the shopper changes them.
Do not invent prices, dates, sizes, or preferences. When asked to generate a clarification,
use the supplied assessment and ask only for missing required information.
If the shopper changes to a different product category, start a fresh requirement set for
that category and do not copy category-specific values such as shoe size, storage capacity,
or furniture dimensions from the current requirements. Only keep such a value if the shopper
states it again in the latest message. If the shopper says any/no preference for a field,
clear the previous value for that field.

Shopper message: {message}
Current requirements: {current_requirements}
"""

CLARIFICATION_PROMPT = """Write one concise shopping clarification question. Return JSON only:
{{"clarification_question": string}}. Ask only about the genuinely required missing information;
do not ask about optional preferences or imply that a brand is required. Tell the shopper exactly
what format to reply with and give a short example. For example: "What shoe size and budget do
you need? Reply: size 42, under $100. If brand does not matter, reply: any brand." If a missing
field is optional, explicitly say the shopper can reply "any", "no preference", or "doesn't matter".
Never invent a value on the shopper's behalf.

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
