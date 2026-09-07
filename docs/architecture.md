## State-driven shopping graph

## Team ownership and integration boundaries

- `tools/` contains stable mock implementations for local development and tests.
- `tools_real/` coordinates real operations but contains no provider-specific HTTP code.
- `platforms/` contains one adapter per marketplace and is the only place provider API code belongs.
- `agent/` orchestrates the state-driven shopping workflow.
- `llm/` owns Groq access and semantic tasks such as requirement extraction.
- `schemas/` contains the provider-neutral contracts shared by all layers.

`SHOPPING_TOOL_MODE=mock` is the default. Set `SHOPPING_TOOL_MODE=real` only when using
implemented marketplace adapters. This preserves fully offline tests and local development.

Each marketplace teammate should implement their adapter by inheriting `ShoppingPlatform`,
reading credentials and endpoints from environment variables, calling the provider API, and
mapping responses into `Product` and `Review`. Raw provider response objects must not leave the
adapter, credentials must never be hard-coded, and no agent-graph change should be needed.

```python
class ExamplePlatform(ShoppingPlatform):
    def search_products(self, query: str) -> list[Product]:
        response = self._client.search(query=query)
        return [Product(id=item["id"], title=item["name"], price=item["price"],
                        platform="example", url=item["url"]) for item in response]
```

The real tools obtain the appropriate adapter through `platforms.get_platform()`; adding a
provider means registering its adapter once in `platforms.PLATFORMS`, not adding platform
conditionals throughout the application.

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
