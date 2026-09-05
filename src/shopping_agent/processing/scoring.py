"""Transparent ranking; semantic review insights can only influence reasons."""

from shopping_agent.schemas import Product, RankedProduct, ReviewSummary, UserRequirements


def rank_products(
    products: list[Product],
    requirements: UserRequirements,
    reviews: dict[str, ReviewSummary],
) -> list[RankedProduct]:
    ranked: list[RankedProduct] = []
    priorities = {priority.lower() for priority in requirements.ranking_priorities}
    for product in products:
        score = (product.rating or 0) * 10 + min(product.review_count, 1000) / 100
        reasons = [f"Rating: {product.rating}/5" if product.rating else "No marketplace rating"]
        if requirements.max_price:
            score += max(0, (requirements.max_price - product.price) / requirements.max_price) * 10
        if "price" in priorities and requirements.max_price:
            score += max(0, (requirements.max_price - product.price) / requirements.max_price) * 10
        if "rating" in priorities:
            score += (product.rating or 0) * 5
        if "reviews" in priorities:
            score += min(product.review_count, 1000) / 100
        preferred_platforms = {platform.lower() for platform in requirements.preferred_platforms}
        if product.platform.lower() in preferred_platforms:
            score += 5
            reasons.append("Matches your preferred seller/platform")
        if ("delivery" in priorities or "arrival" in priorities) and product.arrival_date and requirements.arrival_by:
            score += max((requirements.arrival_by - product.arrival_date).days, 0)
        summary = reviews.get(product.id)
        if summary and summary.available:
            reasons.extend(summary.highlights[:2])
            score += 2 if summary.sentiment == "positive" else 0
        ranked.append(RankedProduct(product=product, score=round(score, 2), reasons=reasons))
    return sorted(ranked, key=lambda item: item.score, reverse=True)
