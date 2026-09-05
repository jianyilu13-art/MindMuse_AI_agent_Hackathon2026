"""Fictional, local product catalogue used in mock shopping mode.

Nothing in this module contacts a marketplace.  The compact source rows expand
to 36 stable records (six categories, six products each) at import time.
"""

from __future__ import annotations

from datetime import date, timedelta

from shopping_agent.schemas import Product


# category, name, brand, price, rating, stock, colours, sizes, keywords
_ROWS = [
    ("electronics", "Nimbus Air Laptop 14", "Northstar", 899, 4.7, 12, "silver", "14-inch", "laptop lightweight 16GB fast"),
    ("electronics", "Atlas Work Laptop 15", "Vertex", 1099, 4.8, 7, "black", "15-inch", "laptop creator 32GB"),
    ("electronics", "Cedar Student Laptop", "Pine", 649, 4.3, 18, "blue", "14-inch", "laptop student budget"),
    ("electronics", "Echo Quiet Headphones", "Sonora", 179, 4.8, 24, "black", "one size", "headphones wireless noise cancelling"),
    ("electronics", "Pulse Everyday Headphones", "Sonora", 79, 4.4, 32, "white", "one size", "headphones wireless lightweight"),
    ("electronics", "Orbit Studio Headphones", "Aural", 229, 4.9, 0, "black", "one size", "headphones studio noise cancelling"),
    ("clothing", "Willow Linen Shirt", "Morrow", 48, 4.5, 20, "white", "S,M,L,XL", "shirt linen breathable summer"),
    ("clothing", "Harbor Everyday Hoodie", "Morrow", 62, 4.6, 15, "navy", "S,M,L,XL", "hoodie cotton casual"),
    ("clothing", "Juniper Tailored Blazer", "Aster", 148, 4.7, 6, "black", "S,M,L", "blazer formal work"),
    ("clothing", "Solstice Running Tee", "Stride", 35, 4.4, 28, "coral", "S,M,L,XL", "tee running moisture wicking"),
    ("clothing", "Meadow Knit Cardigan", "Aster", 74, 4.2, 9, "cream", "S,M,L", "cardigan knit soft"),
    ("clothing", "Nightfall Rain Jacket", "Harbor", 115, 4.8, 0, "black", "S,M,L,XL", "jacket waterproof rain"),
    ("shoes", "Metro Black Running Shoe", "Stride", 89, 4.7, 21, "black", "39,40,41,42,43,44", "shoes running black cushioned"),
    ("shoes", "Canyon Trail Runner", "Trailwise", 129, 4.8, 8, "black", "40,41,42,43,44", "shoes trail running grip"),
    ("shoes", "Cloudwalk Everyday Sneaker", "Cloudwalk", 69, 4.3, 35, "white", "38,39,40,41,42", "shoes sneaker casual"),
    ("shoes", "Velvet Evening Flat", "Luma", 55, 4.1, 14, "black", "36,37,38,39,40", "shoes black flat dress"),
    ("shoes", "Forge Leather Boot", "Canyon", 165, 4.6, 5, "brown", "40,41,42,43,44", "shoes boot leather"),
    ("shoes", "Breeze Slide Sandal", "Coast", 39, 4.0, 0, "black", "37,38,39,40,41", "shoes sandal summer"),
    ("beauty", "Dewdrop Hydration Set", "Lunara", 42, 4.7, 26, "clear", "one size", "beauty skincare hydration gift"),
    ("beauty", "Velvet Tint Lip Duo", "Lunara", 28, 4.5, 31, "rose", "one size", "beauty lipstick gift"),
    ("beauty", "Serein Night Serum", "Serein", 86, 4.8, 10, "amber", "one size", "beauty serum skincare"),
    ("beauty", "Morning Glow SPF", "Sunwell", 24, 4.4, 44, "beige", "one size", "beauty sunscreen skincare"),
    ("beauty", "Atelier Fragrance Mini", "Atelier", 49, 4.6, 0, "gold", "one size", "beauty perfume gift"),
    ("beauty", "Silk Makeup Brush Set", "Lunara", 58, 4.3, 11, "pink", "one size", "beauty makeup gift brushes"),
    ("home", "Hearth Pour-Over Kit", "Hearth", 45, 4.8, 19, "glass", "one size", "home coffee gift kitchen"),
    ("home", "Halo Desk Lamp", "Northstar", 68, 4.6, 16, "white", "one size", "home lamp desk led"),
    ("home", "Cove Cotton Throw", "Cove", 72, 4.7, 13, "sage", "one size", "home blanket gift soft"),
    ("home", "Tidy Modular Basket", "Cove", 32, 4.2, 37, "natural", "one size", "home storage basket"),
    ("home", "Oakline Chef Knife", "Oakline", 119, 4.9, 4, "steel", "one size", "home kitchen knife gift"),
    ("home", "Ember Aroma Diffuser", "Ember", 54, 4.5, 0, "stone", "one size", "home diffuser gift"),
    ("accessories", "Comet Crossbody Bag", "Luma", 76, 4.7, 17, "black", "one size", "accessories bag gift leather"),
    ("accessories", "Sundial Polarized Sunglasses", "Coast", 59, 4.4, 22, "black", "one size", "accessories sunglasses gift"),
    ("accessories", "Moss Wool Scarf", "Morrow", 38, 4.6, 25, "green", "one size", "accessories scarf gift wool"),
    ("accessories", "Arc Minimal Watch", "Vertex", 145, 4.8, 6, "silver", "one size", "accessories watch gift"),
    ("accessories", "Crescent Travel Wallet", "Luma", 44, 4.3, 29, "tan", "one size", "accessories wallet gift travel"),
    ("accessories", "Orbit Carry-on Organizer", "Cove", 26, 4.1, 0, "navy", "one size", "accessories travel organizer gift"),
]


def products() -> list[Product]:
    """Return fresh Pydantic models so cart/search callers cannot mutate the catalogue."""
    result: list[Product] = []
    for index, (category, name, brand, price, rating, stock, colour, sizes, tags) in enumerate(_ROWS, 1):
        original = round(price * (1.18 if index % 4 == 0 else 1), 2)
        discount = f"{round((1 - price / original) * 100)}% off" if original > price else None
        arrival = date(2026, 9, 6) + timedelta(days=index % 5)
        result.append(Product(
            id=f"mock-{category}-{index:02d}", title=name, description=f"Fictional {name.lower()} for mock shopping demonstrations.",
            price=float(price), original_price=original if original > price else None, currency="USD", platform="mock-market",
            url=f"https://example.test/mock-products/{index}", arrival_date=arrival, rating=rating, review_count=80 + index * 37,
            stock=stock, available=stock > 0, image_url=f"https://placehold.co/640x480?text={index}", seller="Mock Market Store",
            shipping_info="Express: 1–2 business days" if index % 3 == 0 else "Standard: 3–5 business days", promotion=discount,
            attributes={"category": category, "brand": brand, "color": colour, "sizes": sizes, "tags": tags},
        ))
    return result
