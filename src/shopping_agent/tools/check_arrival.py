from datetime import date
from typing import Protocol

from shopping_agent.schemas import Product


class ArrivalCheckTool(Protocol):
    def arrives_by(self, product: Product, deadline: date) -> bool: ...
