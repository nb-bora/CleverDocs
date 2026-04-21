"""Search routes (MVP).

Phase 4: minimal full-text search using the SQL database (LIKE).
Later phases will use OpenSearch/Elasticsearch read-model.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.interfaces.api.deps import Settings, get_db, get_settings
from app.interfaces.api.schemas.search import SearchResponse, SearchResultItem


router = APIRouter(prefix="/v1/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_documents(
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query")

    # Prefer OpenSearch if reachable; fallback to SQL LIKE.
    try:
        engine = SearchEngineImpl(
            SearchEngineSettings(
                opensearch_url=settings.opensearch_url,
                index_prefix=settings.opensearch_index_prefix,
            )
        )
        if engine.ping():
            resp = engine.search(q=query, organization_id=None, size=25)
            hits = resp.get("hits", {}).get("hits", [])
            results: list[SearchResultItem] = []
            for h in hits:
                src = h.get("_source", {}) or {}
                score = float(h.get("_score") or 0.0)
                filename = src.get("filename") or ""
                doc_id = src.get("document_id") or h.get("_id") or ""
                hl = (h.get("highlight", {}) or {}).get("content")
                preview = None
                if isinstance(hl, list) and hl:
                    preview = hl[0]
                results.append(
                    SearchResultItem(
                        document_id=doc_id,
                        filename=filename,
                        score=score,
                        preview=preview,
                    )
                )
            return SearchResponse(query=query, results=results)
    except Exception:
        # Fall back to SQL search below.
        pass

    # Simple scoring: documents that contain the query earlier get a higher score.
    like = f"%{query}%"

    stmt = (
        select(DocumentModel, DocumentContentModel)
        .join(DocumentContentModel, DocumentContentModel.document_id == DocumentModel.id)
        .where(DocumentContentModel.cleaned_text.ilike(like))
        .limit(25)
    )

    results: list[SearchResultItem] = []
    for doc, content in db.execute(stmt).all():
        text = content.cleaned_text or ""
        pos = text.lower().find(query.lower())
        score = 1.0 if pos < 0 else max(0.1, 1.0 - min(pos, 1000) / 1000.0)
        preview = text[max(0, pos - 80) : pos + 160] if pos >= 0 else text[:240]
        results.append(
            SearchResultItem(
                document_id=doc.id,
                filename=doc.filename,
                score=score,
                preview=preview or None,
            )
        )

    # Sort by score desc
    results.sort(key=lambda r: r.score, reverse=True)
    return SearchResponse(query=query, results=results)
