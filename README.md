# MindMuse — Agentic AI Shopping Assistant

> A stateful, explainable shopping agent that turns an open-ended request into a structured product decision.

[Project Presentation](https://canva.link/d064g566q14ni1j) · [Architecture Notes](docs/architecture.md) · [State Model](docs/state.md)

MindMuse is the project name; **Muse** is the shopper-facing assistant. Muse does more than generate a one-off answer: it maintains shopping context, identifies missing information, chooses the next operation, searches live product data, applies hard constraints, ranks qualified products, and supports follow-up actions such as comparison, pagination, and product selection.

The project combines **LangGraph**, **Groq-hosted language models**, **SearchAPI**, and deterministic Python decision logic. A browser interface and a command-line interface are both included.

## Motivation

Online shopping creates a decision problem, not just a search problem.

A shopper may begin with an incomplete request such as “I need running shoes” while the details that determine a useful result—size, budget, compatibility, delivery deadline, or a must-have feature—remain unstated. Traditional search engines return large result sets, and conventional chatbots may recommend products without consistently enforcing constraints or preserving context across follow-up turns.

MindMuse is designed around four needs:

1. **Reduce choice overload.** Convert a broad request into a small set of decision-ready recommendations.
2. **Ask only useful questions.** Distinguish required information from optional preferences according to the product category.
3. **Make recommendations auditable.** Keep factual filtering and ranking in transparent Python logic instead of asking an LLM to invent or silently enforce product facts.
4. **Support a complete decision journey.** Preserve state across clarification, search, comparison, requirement changes, pagination, and purchase handoff.

## Solution

Muse treats shopping as a stateful, tool-using workflow:

- A Groq-hosted LLM classifies each user turn and converts natural language into typed shopping requirements.
- A LangGraph controller inspects the shared state after every operation and decides what should happen next.
- SearchAPI supplies live Google Shopping results and optional public community/forum sources.
- Deterministic processing removes duplicates, enforces hard constraints, and calculates a transparent ranking.
- A recommendation layer can surface **Best Overall**, **Best Value**, and **Best Upgrade** options when each tier has a justified candidate.
- The interface keeps the shopper in control and hands any real purchase off to the original marketplace page.

This hybrid approach uses the LLM where semantic understanding is valuable and ordinary code where consistency, traceability, and safety matter most.

## Key Highlights

### A genuinely agentic control loop

The workflow is not a fixed prompt chain. The router re-evaluates the complete structured state after every node. Depending on what it observes, it can clarify, search, enrich evidence, rank, show another page, compare products, handle a changed requirement, open a selected product, or terminate.

### Category-aware requirement discovery

Muse identifies the minimum information needed for the current category. Shoe size may be required for footwear, while interface and capacity may matter for an SSD. Optional preferences such as colour or brand do not block search unless the request makes them essential. Explicit answers such as “any brand” or “no preference” are recorded so the agent does not ask the same question again.

### LLM understanding with deterministic guardrails

The LLM interprets intent, extracts a requirement patch, and writes concise clarification questions. It does **not** decide whether a product violates a known price, stock, arrival, size, attribute, or must-have constraint. Those checks are performed by testable Python functions.

### Explainable, decision-oriented recommendations

Products are ranked using observable signals such as rating, review count, budget headroom, preferred platform, delivery priority, and available review evidence. Muse then creates distinct recommendation tiers when the result set contains a justified candidate for each:

- **Best Overall** — strongest fit across requirements, preferences, quality, and budget.
- **Best Value** — a lower-cost option that preserves a strong combination of match and quality.
- **Best Upgrade** — a more expensive option only when it provides a meaningful quality or evidence improvement and stays within a controlled ceiling.

The system never pads the list with a fabricated upgrade when no meaningful upgrade exists.

### Evidence-aware product discovery

The real-data mode normalizes Google Shopping results into provider-neutral product objects. Marketplace rating evidence feeds the ranking, while the Web UI can fetch public community and forum sources asynchronously so optional enrichment does not delay the core recommendation flow.

### Stateful follow-up interaction

Requirements, prior turns, ranked products, displayed products, and lifecycle statuses are retained in `ShoppingState`. This lets Muse understand follow-ups such as:

- “Make the budget $120.”
- “Show me more.”
- “Compare the first and third options.”
- “I want the second one.”
- “Any brand is fine.”

Positional references are resolved against the products the shopper actually saw, rather than the provider’s hidden raw ordering.

### Pluggable commerce boundaries

Search, review retrieval, cart/action handling, and language semantics are injected services. Mock implementations support repeatable development and tests, while provider-neutral schemas isolate the graph from external API response formats.

## Workflow

```mermaid
flowchart TD
    U[User message] --> I[Interpret intent]
    I -->|new or changed requirements| E[Extract and merge requirements]
    E --> C{Ready for a useful search?}
    C -->|No| Q[Ask a focused clarification]
    Q --> W[Wait for user]
    C -->|Yes| S[Search products]
    S --> D[Normalize and deduplicate]
    D --> F[Apply hard constraints]
    F --> R{Qualified results?}
    R -->|No| N[Show closest results and suggest relaxation]
    N --> W
    R -->|Yes| V[Collect rating/review evidence]
    V --> K[Deterministic ranking]
    K --> B[Select Overall / Value / Upgrade picks]
    B --> P[Display curated results]
    P --> W
    W -->|more results| P
    W -->|compare| X[Compare displayed products]
    W -->|change requirements| E
    W -->|select product| A[Open product / mock cart action]
    W -->|finish| T[Terminate]
```

Every turn starts with `interpret_user_input`. After each node, the pure `next_action` router selects exactly one next operation from lifecycle fields such as `requirement_status`, `search_required`, `review_status`, `ranking_status`, `presentation_status`, and `purchase_status`.

### Core graph nodes

| Node | Responsibility |
| --- | --- |
| `interpret_user_input` | Classify the latest turn and resolve search, change, more, compare, purchase, or finish intent. |
| `extract_requirements` | Convert the message into a typed requirement patch and assess search readiness. |
| `ask_clarification` | Ask only for missing required information or suggest relaxing an unsuccessful search. |
| `search_products` | Call the configured product source, deduplicate results, and enforce hard constraints. |
| `fetch_reviews` | Attach available marketplace rating/review evidence without fabricating missing evidence. |
| `rank_products` | Score qualified products with deterministic, inspectable logic. |
| `select_best_picks` | Produce a Best Overall pick plus justified Value and Upgrade recommendations. |
| `display_results` | Present a page of ranked results and wait for the next user decision. |
| `compare_products` | Compare products from the currently displayed result set. |
| `add_to_cart` | Use a mock cart in mock mode or return the real product link in SearchAPI mode. |
| `terminate` | Close the shopping session. |

## Architecture

```mermaid
flowchart LR
    UI[Web UI / CLI] --> SESSION[Conversation session]
    SESSION --> GRAPH[LangGraph controller]
    GRAPH --> SEM[Semantic boundary]
    GRAPH --> TOOLS[Tool boundary]
    GRAPH --> PROC[Deterministic processing]
    SEM --> GROQ[Groq API]
    TOOLS --> SEARCH[SearchAPI / mocks]
    TOOLS --> ADAPTERS[Marketplace adapter contracts]
    PROC --> SCHEMAS[Provider-neutral Pydantic schemas]
    SEARCH --> SCHEMAS
    ADAPTERS --> SCHEMAS
```

| Layer | Purpose |
| --- | --- |
| `agent/` | Shared state, graph construction, routing, prompts, and state-transition nodes. |
| `llm/` | Groq access and the natural-language-to-structured-state boundary. |
| `processing/` | Deduplication, hard-constraint filtering, and transparent scoring. |
| `schemas/` | Typed contracts for requirements, products, reviews, community evidence, and best picks. |
| `tools/` | Stable tool protocols and local mock implementations. |
| `tools_real/` | SearchAPI integration and real-operation orchestration. |
| `platforms/` | Provider adapter interface and marketplace-specific integration templates. |
| `ui/` | In-memory Web sessions, JSON endpoints, and the zero-framework browser interface. |

## Getting Started

### Prerequisites

- Python **3.10 or newer**
- A [Groq](https://console.groq.com/keys) API key and a model available to your Groq account
- A [SearchAPI](https://www.searchapi.io/) API key for live product search
- [`uv`](https://docs.astral.sh/uv/) is recommended; standard `pip` is also supported

### 1. Install the project

From the repository root:

```bash
uv sync
```

Alternatively, with `pip`:

```bash
python -m venv .venv
python -m pip install -e ".[test]"
```

Activate the virtual environment before using the `pip` commands below. On PowerShell run `.venv\Scripts\Activate.ps1`; on macOS or Linux run `source .venv/bin/activate`.

### 2. Configure environment variables

Copy the example file:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

Set at least the following values for live search:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=your_available_groq_model
SEARCHAPI_API_KEY=your_searchapi_api_key
SHOPPING_TOOL_MODE=searchapi
```

Do not commit `.env` or any API key.

### 3. Run the Web application

```bash
uv run python -m shopping_agent.ui
```

Or, if the package was installed with `pip`:

```bash
python -m shopping_agent.ui
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The Web UI provides:

- multi-turn chat;
- a live view of extracted and missing requirements;
- curated recommendation cards and ranking reasons;
- Overall, Value, and Upgrade decision tabs;
- public community-source availability;
- paginated results and safe links to seller pages;
- isolated in-memory browser sessions and a **New chat** action.

Press `Ctrl+C` in the terminal to stop the server.

### 4. Run the command-line agent

```bash
uv run python -m shopping_agent.main
```

Or with the active `pip` environment:

```bash
python -m shopping_agent.main
```

Type `exit` or `quit` to end the conversation.

## Run with Local Mock Commerce Tools

Mock mode keeps real LLM-based intent and requirement understanding, but replaces product search, review retrieval, and cart behavior with local deterministic data. A Groq key and model are still required for an interactive session; a SearchAPI key is not.

Set this in `.env`:

```dotenv
SHOPPING_TOOL_MODE=mock
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=your_available_groq_model
```

Then start either interface using the same commands above.

## Example Conversation

```text
You: I need running shoes.
Muse: What shoe size do you need? You can also share a budget, or say any budget.

You: EU 42, under $100, any brand.
Muse: [searches, filters, ranks, and presents the strongest matches]

You: Compare the first and third options.
Muse: [compares the currently displayed products]

You: Show me more.
Muse: [shows the next result page without repeating the search]

You: Increase my budget to $120.
Muse: [updates the requirement state and runs a new search]

You: I want the second one.
Muse: [opens the seller link in live mode or uses the mock cart in mock mode]
```

Exact wording varies because intent parsing and clarification generation use the configured LLM.

## Configuration Reference

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | Interactive runtime | — | Authenticates LLM requests. |
| `GROQ_MODEL` | Interactive runtime | — | Groq model ID available to the account. |
| `SHOPPING_TOOL_MODE` | No | `searchapi` | `searchapi`/`real` for live aggregated search, or `mock` for local commerce data. |
| `SEARCHAPI_API_KEY` | Live search | — | Authenticates SearchAPI requests. |
| `SEARCHAPI_GL` | No | `sg` | Search country/region code and fallback currency context. |
| `SEARCHAPI_HL` | No | `en` | Search result language. |
| `SEARCHAPI_MAX_PRODUCTS` | No | `12` | Maximum number of shopping results normalized per search. |
| `SEARCHAPI_FORUM_TOP_K` | No | `1` | Number of top products enriched with forum/community searches. Set `0` to disable. |

## Ranking and Safety Principles

### Hard constraints are enforced before ranking

A product is excluded when available data proves that it violates a stated constraint:

- unavailable or explicitly out of stock;
- below a minimum or above a maximum price;
- later than a required arrival date;
- incompatible with a verified size or named attribute;
- missing a stated must-have term.

Aggregated commerce data is sometimes incomplete. Unknown stock or size metadata is treated as **unverified**, not automatically as a mismatch. The recommendation layer reduces confidence for unverified critical attributes instead of presenting them as confirmed matches.

### LLM output cannot invent product facts

Prompts explicitly prohibit invented prices, availability, delivery dates, review claims, or preferences. Product eligibility and score calculations operate only on normalized provider data and explicit user requirements.

### Purchase remains user-controlled

In SearchAPI mode, selecting a product returns its marketplace or seller URL. Checkout occurs outside MindMuse. The project does not place a real order, store payment details, or perform an autonomous checkout.

## Web API

The included browser application exposes a small local JSON API:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Serve the Web interface. |
| `GET` | `/api/state` | Return the current session view model. |
| `POST` | `/api/chat` | Process `{"message": "..."}` through the shopping graph. |
| `POST` | `/api/reset` | Reset the current conversation. |

Sessions are identified by a same-site cookie and stored only in process memory. This API is intended for local demonstration and prototyping, not production deployment as-is.

## Testing

The test suite replaces the LLM and external commerce services with deterministic adapters, so it requires no API keys and no network access.

```bash
uv run pytest
```

Or:

```bash
python -m pytest
```

Coverage includes:

- clarification before search;
- requirement updates and no-result recovery;
- the full search → evidence → ranking → display flow;
- pagination without redundant searches;
- product comparison and cart/action routing;
- hard-constraint and unknown-metadata behavior;
- SearchAPI normalization, caching, locale, and community-source parsing;
- Best Overall, Best Value, and Best Upgrade selection rules;
- provider registry and dependency-injection boundaries.

## Project Structure

```text
.
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── state.md
├── src/shopping_agent/
│   ├── agent/          # LangGraph, router, nodes, prompts, shared state
│   ├── llm/            # Groq client and structured semantic parsing
│   ├── platforms/      # Marketplace contracts and adapter templates
│   ├── processing/     # Deduplication, filtering, and ranking
│   ├── schemas/        # Provider-neutral Pydantic models
│   ├── tool_mock/      # Local fictional catalogue support
│   ├── tools/          # Tool protocols and stable mocks
│   ├── tools_real/     # SearchAPI and real-operation orchestration
│   ├── ui/             # Browser application and view-model mapping
│   └── main.py         # CLI conversation loop
├── tests/              # Unit and end-to-end graph tests
├── .env.example
├── pyproject.toml
└── uv.lock
```

## Extending MindMuse

### Add a marketplace integration

Implement `ShoppingPlatform` in `src/shopping_agent/platforms/`, map the provider response into the shared `Product` and `Review` schemas, and register the adapter in `platforms.PLATFORMS`. Provider payloads and credentials should remain inside the adapter layer; the agent graph should not require platform-specific conditionals.

The Amazon, eBay, Lazada, and Shopee classes currently define integration templates and intentionally raise `NotImplementedError`. The default live application uses SearchAPI aggregation instead.

### Add a graph capability

1. Add the required observable field or lifecycle status to `ShoppingState`.
2. Implement one focused state-transition method in `ShoppingNodes`.
3. Register the node in `build_shopping_graph`.
4. Add a pure routing condition in `next_action`.
5. Cover the transition with a deterministic test adapter.

This keeps routing visible and prevents business decisions from being hidden inside prompts.

## Current Limitations

- Browser sessions are in memory and disappear when the local server restarts.
- Live product coverage depends on SearchAPI and the underlying Google Shopping result fields.
- SearchAPI mode uses marketplace rating metadata as review evidence; it does not fetch full review bodies from every seller.
- Community enrichment exposes public search sources and snippets, not a verified consensus score.
- Direct Amazon, eBay, Lazada, and Shopee API adapters are scaffolds for future implementation.
- Real checkout, authentication with seller accounts, and payment handling are deliberately out of scope.

## Roadmap

- Persistent sessions and user preference profiles
- Production-ready marketplace adapters
- Richer review retrieval, provenance, and contradiction analysis
- Evaluation datasets for requirement extraction and ranking quality
- Observability for node latency, tool failures, and recommendation outcomes
- Deployment packaging, authentication, and rate limiting for the Web API

---

**MindMuse** aims to make shopping feel less like browsing an endless catalogue and more like working through a decision with a careful, transparent assistant.
