"""QA / RAG schemas (grounded answers with citations)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QASource(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    score: float
    excerpt: str = Field(max_length=2000)


class QARequest(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    mode: str | None = Field(default="org")  # "org" | "mine"


class QAResponse(BaseModel):
    question: str
    answer: str
    abstained: bool = False
    sources: list[QASource]

