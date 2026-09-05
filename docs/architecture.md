# Architecture

```text
Browser UI / CLI
        |
        v
  LangGraph controller
        |
        +--> Groq semantic adapter
        |      - intent interpretation
        |      - category and attribute proposals
        |      - required/optional clarification wording
        |
        +--> ShoppingToolInput
        |      - category
        |      - normalized attributes
        |
        +--> search / reviews / cart adapters
```

Groq is selected when `GROQ_API_KEY` is available. The local semantic fallback
keeps the demo runnable without credentials; it is not used when Groq is
configured. Search, review, and cart are still local mock adapters until the
marketplace implementations are supplied.
