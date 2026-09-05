"""Realistic in-memory product source used only by integration tests."""

from datetime import date

from shopping_agent.schemas import Product, ShoppingToolInput


class MockRunningShoeSearch:
    def search(self, request: ShoppingToolInput) -> list[Product]:
        if not request.query or "shoe" not in request.query.lower():
            return []
        return [
            Product(id="nike-pegasus-41", title="Nike Pegasus 41", price=95, platform="mock-store", url="https://mock.test/nike-pegasus-41", arrival_date=date(2026, 9, 2), rating=4.6, review_count=830, attributes={"brand": "Nike", "category": "running shoes", "sizes": "41,42,43", "cushioning": "responsive"}),
            Product(id="asics-gel-cumulus-26", title="ASICS Gel-Cumulus 26", price=75, platform="mock-store", url="https://mock.test/asics-gel-cumulus-26", arrival_date=date(2026, 9, 3), rating=4.7, review_count=620, attributes={"brand": "ASICS", "category": "running shoes", "sizes": "40,41,42,43", "cushioning": "soft"}),
            Product(id="new-balance-1080v13", title="New Balance Fresh Foam 1080v13", price=110, platform="mock-store", url="https://mock.test/new-balance-1080v13", arrival_date=date(2026, 9, 1), rating=4.8, review_count=510, attributes={"brand": "New Balance", "category": "running shoes", "sizes": "41,42,44", "cushioning": "plush"}),
            Product(id="adidas-ultraboost-light", title="Adidas Ultraboost Light", price=120, platform="mock-store", url="https://mock.test/adidas-ultraboost-light", arrival_date=date(2026, 9, 4), rating=4.5, review_count=710, attributes={"brand": "Adidas", "category": "running shoes", "sizes": "40,42,43", "cushioning": "energy return"}),
        ]
