# Back-half tools — interface contract

Owner: **tools (recommendation / pickup / customer_service / cart)**.
Consumers: the agent (tool calls) and the front-half tools (search / compare),
which produce the `Product` candidates.

> Status: scaffold. All `@tool` entrypoints and core functions exist with typed
> signatures and raise `NotImplementedError`. Behaviour is pinned by
> `tests/test_tools/test_spec.py` (xfail until implemented).

## Data shapes (`shopping_agent.schemas`)

- `Product` — a candidate. Front-half fills identity/price/signals/listing-text;
  back-half only reads it. **Field names to confirm with search/compare owner.**
- `UserRequirements` + `Weights` — produced by the agent from the user's request.
- `ReviewSummary` — condensed reviews, read by recommendation for preference score.
- Outputs: `Recommendation`, `PickupInfo`, `CustomerServiceResult`, `CartResult`.

## State convention (confirm with agent owners)

Tools do **not** take the full candidate list as an argument (too big for the
LLM to pass). They take a `session_id` / ids and read/write candidates +
requirements + tool outputs on shared LangGraph state. Adapter layer TBD with
the agent team — the pure core functions below are state-free and testable now.

## Tool entrypoints

| Tool | `@tool` signature | Core function (pure) | Output |
|------|-------------------|----------------------|--------|
| recommendation | `recommend_products(session_id)` | `rank_candidates(candidates, reqs, review_summaries?, pickup_infos?)` | `Recommendation` |
| pickup | `check_pickup(product_id, platform, date)` | `check_pickup_availability(product, target_date, location, *, today?)` | `PickupInfo` |
| customer_service | `customer_service(product_id, request)` | `summarize_policies` / `draft_seller_question` / `arrival_checklist` | `CustomerServiceResult` |
| cart | `add_to_cart(product_id, platform)` | `prepare_cart(product, quantity)` | `CartResult` |

## Contracts that matter

- **recommendation** — deterministic weighted scoring; LLM only polishes text.
  `status="empty"` + `reason` tells the agent to ask the user to relax
  constraints. Never returns items over budget or past deadline.
- **pickup** — no real store-pickup API. `store_pickup` path is a seeded fixture
  (`tests/fixtures/local_inventory.json`), stated honestly. `ship`/`locker`
  paths derive from real listing delivery text. Always degrades to `ship`.
- **customer_service** — listing-text only, no external API. Never invents
  policy terms when the listing lacks them.
- **cart** — prepares a checkout deep link; **never claims an order was placed**.
  Amazon add-to-cart URL is real; other platforms hand off the product URL.

## Open questions (resolve this week)

1. `Product` field names + currency handling — with search/compare owner.
2. State read/write adapter shape — with agent owners.
3. Who owns `llm/model.py` (provider switch, Groq⇄Bedrock) — with agent owners.
4. Demo product category (default: wireless earbuds) — team.
