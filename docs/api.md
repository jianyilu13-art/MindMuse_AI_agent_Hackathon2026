# Search tool API

The agent sends the Framework marketplace search tool one typed request:

```python
from shopping_agent.schemas import ShoppingToolInput

request = ShoppingToolInput(
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

The adapter boundary is:

```python
def search(request: ShoppingToolInput) -> list[Product]:
    ...
```

The search tool is responsible for understanding product data. The main agent
is responsible for conversation, requirement merging, missing-field questions,
and deciding when this tool should be called.
