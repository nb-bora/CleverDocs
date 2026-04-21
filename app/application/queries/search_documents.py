"""Query: search documents (read side)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.interfaces.api.deps import Settings


@dataclass(frozen=True, slots=True)
class SearchDocuments:
    organization_id: str
    query: str
    size: int = 25


def query_search_documents(*, q: SearchDocuments, db: Session, settings: Settings) -> dict:
    engine = SearchEngineImpl(
        SearchEngineSettings(opensearch_url=settings.opensearch_url, index_prefix=settings.opensearch_index_prefix)
    )
    if engine.ping():
        return engine.search(q=q.query, organization_id=q.organization_id, size=q.size)
    # Fallback: let API route use SQLite FTS; here we keep minimal.
    return {"hits": {"hits": []}}
