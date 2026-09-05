from __future__ import annotations

from pydantic import BaseModel, Field


class CommunityFeedback(BaseModel):
    """One public forum/community search result."""

    product_id: str
    title: str
    snippet: str = ""
    url: str
    domain: str


class CommunityFeedbackSummary(BaseModel):
    """Community evidence collected for one product."""

    product_id: str
    available: bool = False
    sources: list[CommunityFeedback] = Field(default_factory=list)
    summary: str | None = None