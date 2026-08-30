## State-driven shopping graph

Every turn enters through `interpret_user_input`. That LLM node converts the raw message into
an intent and a signal to update requirements. When an update is needed,
`extract_requirements` asks the LLM for both a structured requirement patch and a
task-specific completeness assessment. The router then selects one operation from the shared
state after every node; no graph edge encodes a fixed happy-path sequence.

`next_action` is deliberately pure: it does not read `last_user_message`, invoke a model, or
extract business facts. It evaluates lifecycle fields such as `input_status`,
`requirement_status`, `review_status`, `ranking_status`, `presentation_status`, and
`purchase_status`.

The compiled LangGraph has conditional edges from `START` and every operational node back to
the same router. Its path map includes `interpret_user_input`, `extract_requirements`,
`ask_clarification`, `search_products`, `fetch_reviews`, `rank_products`, `display_results`,
`add_to_cart`, `terminate`, and `end`.

Examples:

- A new request with incomplete requirements routes `interpret_user_input → extract_requirements → ask_clarification`.
- A budget change after results routes `interpret_user_input → extract_requirements → search_products`; reviews and ranking are reset only because the search inputs changed.
- A purchase request routes `interpret_user_input → add_to_cart`.
- A request for another page routes `interpret_user_input → display_results`.
