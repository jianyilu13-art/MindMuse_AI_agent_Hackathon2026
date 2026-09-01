"""Prompt definitions for shopping-agent semantic operations."""

INPUT_INTERPRETATION_PROMPT = """Interpret the shopper's latest message in context.

Return JSON only:
{{
  "intent": one of [
    "search",
    "change_requirements",
    "more_results",
    "purchase",
    "finish",
    "clarify"
  ],
  "selected_product_id": string|null,
  "should_extract_requirements": boolean
}}

Set should_extract_requirements to true when the message provides or changes
shopping requirements. Do not extract detailed attribute values in this step.

Latest shopper message:
{message}

Current requirements:
{current_requirements}

Known products:
{products}
"""


REQUIREMENT_EXTRACTION_PROMPT = """Extract shopping requirements from the shopper message.

The product category may be arbitrary. Identify the category and propose the
most important attributes for that category. Do not use a fixed category list.

Return JSON only:
{{
  "requirements": {{
    "query": string|null,
    "category": string|null,
    "attributes": {{
      "attribute_name": "attribute_value"
    }},
    "max_price": number|null,
    "arrival_by": "YYYY-MM-DD"|null,
    "must_have": [string],
    "preferred_brands": [string],
    "preferred_platforms": [string],
    "no_preference_fields": [string]
  }},
  "assessment": {{
    "sufficient_for_search": boolean,
    "missing_required_information": [string],
    "optional_preferences": [string],
    "suggested_attributes": [
      {{
        "name": string,
        "attribute_type": one of [
          "string",
          "number",
          "boolean",
          "date",
          "string_list",
          "number_list"
        ],
        "required": boolean,
        "reason": string
      }}
    ],
    "clarification_context": string|null
  }}
}}

Rules:

1. Infer the product category from the shopper's request.
2. Propose attributes that are genuinely important for that category.
3. Mark an attribute as required only when searching without it would be
   unreliable or unusable.
4. Do not require every possible feature.
5. Use attributes for category-specific values such as size, taste, material,
   usage, dietary restrictions, storage, or compatibility.
6. Use max_price for the maximum acceptable price.
7. Use arrival_by for the latest acceptable delivery date.
8. Do not invent prices, dates, sizes, preferences, or product facts.
9. Preserve existing requirements unless the shopper explicitly changes them.
10. Record "any is fine" or "I do not care" in no_preference_fields.
11. Return missing_required_information using attribute names only.
12. The value of sufficient_for_search must be false when a required attribute
    is missing.

Shopper message:
{message}

Current requirements:
{current_requirements}
"""


CLARIFICATION_PROMPT = """Write one concise shopping clarification question.

Return JSON only:
{{
  "clarification_question": string
}}

Ask only about the missing required attributes. Use the attribute names and
their reasons to make the question natural and useful. Do not ask again about
information already present. Do not invent product facts.

Product category:
{category}

Current requirements:
{requirements}

Suggested attributes:
{suggested_attributes}

Missing required attributes:
{missing_required_information}

Optional preferences:
{optional_preferences}

Context:
{clarification_context}
"""


REVIEW_ANALYSIS_PROMPT = """Summarize the supplied product reviews for a shopper.

Return JSON only:
{{
  "sentiment": "positive"|"mixed"|"negative"|"unknown",
  "highlights": [string],
  "concerns": [string]
}}

Do not claim facts that are absent from the reviews.

Reviews:
{reviews}
"""


PRODUCT_RANKING_PROMPT = """Describe shopper-relevant trade-offs among the
already-qualified products.

Do not remove products or decide hard constraints. Price, attributes, and
delivery eligibility have already been handled by Python.

Requirements:
{requirements}

Products:
{products}
"""