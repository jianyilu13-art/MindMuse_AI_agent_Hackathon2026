# Shopping Agent

A stateful shopping assistant built with LangGraph. It uses a reactive loop:
after each user message and tool result, the router examines the current state
and chooses the next concrete operation. The current implementation uses mock
search, review, and cart tools, so it can run before marketplace APIs are
integrated.

## Run locally

Use Python 3.10 or newer.

```bash
python3 -m pip install -e .
python3 -m shopping_agent.main
```

Enter a shopping request when prompted. Type `exit` or `quit` to leave. The
default graph uses mock services and does not require a Groq API key.

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
- `src/shopping_agent/llm/` — provider-specific LLM integrations; Groq is the current option.
- `src/shopping_agent/tools/` — external capabilities, currently mock search, review, and cart tools.
- `src/shopping_agent/processing/` — deterministic product processing, including hard-constraint filtering and ranking.
- `src/shopping_agent/schemas/` — typed data structures for requirements, products, and reviews.
- `src/shopping_agent/platforms/` — platform-specific marketplace implementations, to be added by adapters.
