"""Search schemas (DTOs)."""

from __future__ import annotations

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    document_id: str
    filename: str
    score: float
    preview: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
