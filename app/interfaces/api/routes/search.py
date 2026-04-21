"""Search routes (MVP).

Phase 4: minimal full-text search using the SQL database (LIKE).
Later phases will use OpenSearch/Elasticsearch read-model.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.interfaces.api.deps import Settings, TenantContext, UserContext, get_db, get_settings, get_tenant_context, get_user_context
from app.interfaces.api.schemas.search import SearchResponse, SearchResultItem


router = APIRouter(prefix="/v1/search", tags=["search"])

_ADMIN_ROLES = {"owner", "admin"}


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


@router.get("", response_model=SearchResponse)
def search_documents(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query")

    restrict_to_user_id: str | None = None
    if (tenant.role or "") not in _ADMIN_ROLES:
        if not tenant.user_id:
            raise HTTPException(status_code=400, detail="Missing X-User-Id header")
        restrict_to_user_id = tenant.user_id

    include_archived = False

    # Prefer OpenSearch if reachable; fallback to SQL/FTS below.
    try:
        engine = SearchEngineImpl(
            SearchEngineSettings(
                opensearch_url=settings.opensearch_url,
                index_prefix=settings.opensearch_index_prefix,
            )
        )
        if engine.ping():
            resp = engine.search(
                q=query,
                organization_id=tenant.organization_id,
                uploaded_by_user_id=restrict_to_user_id,
                include_archived=include_archived,
                size=25,
            )
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
        # Fall back to SQL search below (OpenSearch is optional in MVP).
        ...

    # SQLite fallback: use FTS5 (diacritics-insensitive + BM25).
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        rows = db.execute(
            sql_text(
                """
                SELECT
                  f.document_id,
                  f.filename,
                  bm25(f) AS bm25_score,
                  snippet(f, 2, '[', ']', '…', 12) AS snip
                FROM document_search_fts f
                JOIN documents d ON d.id = f.document_id
                WHERE f.organization_id = :org_id
                  AND (:user_id IS NULL OR d.uploaded_by_user_id = :user_id)
                  AND d.status != 'deleted'
                  AND (:include_archived = 1 OR d.status != 'archived')
                  AND f MATCH :q
                ORDER BY bm25_score ASC
                LIMIT 25
                """
            ),
            {
                "q": query,
                "org_id": tenant.organization_id,
                "user_id": restrict_to_user_id,
                "include_archived": (1 if include_archived else 0),
            },
        ).all()

        results: list[SearchResultItem] = []
        for doc_id, filename, bm25_score, snip in rows:
            # Convert BM25 (lower is better) to a higher-is-better score in (0,1].
            score = 1.0 / (1.0 + float(bm25_score or 0.0))
            results.append(
                SearchResultItem(
                    document_id=str(doc_id),
                    filename=str(filename),
                    score=score,
                    preview=str(snip) if snip else None,
                )
            )
        return SearchResponse(query=query, results=results)

    # Non-SQLite fallback: basic LIKE.
    like = f"%{query}%"

    stmt = (
        select(DocumentModel, DocumentContentModel)
        .join(DocumentContentModel, DocumentContentModel.document_id == DocumentModel.id)
        .where(DocumentModel.organization_id == tenant.organization_id)
        .where(DocumentModel.status != "deleted")
        .where(DocumentContentModel.cleaned_text.ilike(like))
        .limit(25)
    )
    if restrict_to_user_id is not None:
        stmt = stmt.where(DocumentModel.uploaded_by_user_id == restrict_to_user_id)
    if not include_archived:
        stmt = stmt.where(DocumentModel.status != "archived")

    results: list[SearchResultItem] = []
    for doc, content in db.execute(stmt).all():
        doc_text = content.cleaned_text or ""
        pos = doc_text.lower().find(query.lower())
        score = 1.0 if pos < 0 else max(0.1, 1.0 - min(pos, 1000) / 1000.0)
        preview = doc_text[max(0, pos - 80) : pos + 160] if pos >= 0 else doc_text[:240]
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


@router.get("/mine", response_model=SearchResponse)
def search_my_documents_across_orgs(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> SearchResponse:
    """Recherche "mes documents" sur toutes mes organisations.

    Règle: on retourne uniquement les documents uploadés par l'utilisateur, toutes orgs confondues
    auxquelles il est membre (membership active).
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query")

    org_ids = [
        row[0]
        for row in db.execute(
            select(MembershipModel.organization_id)
            .where(MembershipModel.user_id == user.user_id)
            .where(MembershipModel.status == "active")
        ).all()
    ]
    if not org_ids:
        return SearchResponse(query=query, results=[])

    # Prefer OpenSearch if reachable; fallback to SQLite FTS or LIKE.
    try:
        engine = SearchEngineImpl(
            SearchEngineSettings(
                opensearch_url=settings.opensearch_url,
                index_prefix=settings.opensearch_index_prefix,
            )
        )
        if engine.ping():
            # OpenSearch doesn't support a "terms" filter when we use the existing engine.search API
            # (single org). For MVP, just search org-by-org and merge.
            merged: list[SearchResultItem] = []
            for org_id in org_ids:
                resp = engine.search(
                    q=query,
                    organization_id=org_id,
                    uploaded_by_user_id=user.user_id,
                    include_archived=False,
                    size=25,
                )
                hits = resp.get("hits", {}).get("hits", [])
                for h in hits:
                    src = h.get("_source", {}) or {}
                    score = float(h.get("_score") or 0.0)
                    filename = src.get("filename") or ""
                    doc_id = src.get("document_id") or h.get("_id") or ""
                    hl = (h.get("highlight", {}) or {}).get("content")
                    preview = None
                    if isinstance(hl, list) and hl:
                        preview = hl[0]
                    merged.append(
                        SearchResultItem(
                            document_id=doc_id,
                            filename=filename,
                            score=score,
                            preview=preview,
                        )
                    )
            merged.sort(key=lambda r: r.score, reverse=True)
            return SearchResponse(query=query, results=merged[:25])
    except Exception:
        ...

    if db.bind is not None and db.bind.dialect.name == "sqlite":
        rows = db.execute(
            sql_text(
                """
                SELECT
                  f.document_id,
                  f.filename,
                  bm25(f) AS bm25_score,
                  snippet(f, 2, '[', ']', '…', 12) AS snip
                FROM document_search_fts f
                JOIN documents d ON d.id = f.document_id
                JOIN memberships m ON m.organization_id = f.organization_id
                WHERE m.user_id = :user_id
                  AND m.status = 'active'
                  AND d.uploaded_by_user_id = :user_id
                  AND d.status != 'deleted'
                  AND d.status != 'archived'
                  AND f MATCH :q
                ORDER BY bm25_score ASC
                LIMIT 25
                """
            ),
            {"q": query, "user_id": user.user_id},
        ).all()
        results: list[SearchResultItem] = []
        for doc_id, filename, bm25_score, snip in rows:
            score = 1.0 / (1.0 + float(bm25_score or 0.0))
            results.append(
                SearchResultItem(
                    document_id=str(doc_id),
                    filename=str(filename),
                    score=score,
                    preview=str(snip) if snip else None,
                )
            )
        return SearchResponse(query=query, results=results)

    like = f"%{query}%"
    stmt = (
        select(DocumentModel, DocumentContentModel)
        .join(DocumentContentModel, DocumentContentModel.document_id == DocumentModel.id)
        .join(MembershipModel, MembershipModel.organization_id == DocumentModel.organization_id)
        .where(MembershipModel.user_id == user.user_id)
        .where(MembershipModel.status == "active")
        .where(DocumentModel.uploaded_by_user_id == user.user_id)
        .where(DocumentModel.status != "deleted")
        .where(DocumentModel.status != "archived")
        .where(DocumentContentModel.cleaned_text.ilike(like))
        .limit(25)
    )
    results: list[SearchResultItem] = []
    for doc, content in db.execute(stmt).all():
        doc_text = content.cleaned_text or ""
        pos = doc_text.lower().find(query.lower())
        score = 1.0 if pos < 0 else max(0.1, 1.0 - min(pos, 1000) / 1000.0)
        preview = doc_text[max(0, pos - 80) : pos + 160] if pos >= 0 else doc_text[:240]
        results.append(
            SearchResultItem(
                document_id=doc.id,
                filename=doc.filename,
                score=score,
                preview=preview or None,
            )
        )
    results.sort(key=lambda r: r.score, reverse=True)
    return SearchResponse(query=query, results=results)
