# Shopping Agent

A stateful shopping assistant built with LangGraph. It uses a reactive loop:
after each user message and tool result, the router examines the current state
and chooses the next concrete operation. Groq handles intent and requirement
understanding when configured; the local search, review, and cart adapters are
deterministic demo integrations until marketplace APIs are connected.

## Run locally

Use Python 3.10 or newer.

```bash
python3 -m pip install -e ".[test]"
python3 -m shopping_agent.main
```

Create a `.env` file from `.env.example` and set `GROQ_API_KEY` to use Groq.
`GROQ_MODEL` is configurable; the default is `llama-3.3-70b-versatile`. If no
key is present, the app uses the small local fallback so the conversation and
UI can still be tested.

The CLI starts by asking what you want to buy. After you name a product, the
assistant recommends category-specific attributes and separates them into
required and optional fields. Type `exit` or `quit` to leave.

## Browser UI

Run the zero-dependency shopping/chatbot UI:

```bash
python3 -m shopping_agent.ui
```

Then open <http://127.0.0.1:8000>. The UI includes a chat composer, quick
shopping prompts, attribute guidance, product cards, add-to-cart buttons, a
new-chat action, and a collapsible view of the latest search-tool payload.

## Search tool contract

The agent owns the conversation and requirement merging. The search tool gets
one stable Pydantic input object:

```python
ShoppingToolInput(
    category="running_shoes",
    attributes={
        "gender": "women",
        "size": "EU39",
        "max_price": 150,
        "brand": "Nike",
        "color": "purple",
        "usage": "running",
    },
)
```

This is the only boundary a Framework marketplace adapter needs to implement:
`search(request: ShoppingToolInput) -> list[Product]`. The current mock
adapter uses the same contract, so replacing it does not change the agent
workflow.

## Architecture

```text
User
  -> main.py
  -> LangGraph
  -> routing
  -> node
  -> updated state
  -> routing / node / ...
  -> assistant response
  -> main.py
  -> User
```

The graph loops internally until it needs another user answer or has completed
the requested action. `main.py` retains the returned state and passes it back
on the next user turn.

## Project structure

- `src/shopping_agent/main.py` — outer user ↔ agent conversation loop.
- `src/shopping_agent/agent/graph.py` — builds and compiles the LangGraph workflow.
- `src/shopping_agent/agent/state.py` — shared `ShoppingState` observed by all nodes and routing.
- `src/shopping_agent/agent/routing.py` — reactive next-action decision based on the current state.
- `src/shopping_agent/agent/nodes.py` — individual state-transition operations, such as search or clarification.
- `src/shopping_agent/llm/` — Groq integration, JSON parsing, and the no-key fallback.
- `src/shopping_agent/tools/` — external capabilities and the fixed search-tool contract.
- `src/shopping_agent/ui/` — browser UI served by Python's standard library.
- `src/shopping_agent/processing/` — deterministic product processing, including hard-constraint filtering and ranking.
- `src/shopping_agent/schemas/` — typed data structures for requirements, products, and reviews.
- `src/shopping_agent/platforms/` — platform-specific marketplace implementations, to be added by adapters.
