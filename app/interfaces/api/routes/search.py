"""Search routes (MVP).

Phase 4: minimal full-text search using the SQL database (LIKE).
Later phases will use OpenSearch/Elasticsearch read-model.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext
from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.search.semantic_search import (
    SemanticSettings,
    rrf_fuse,
    semantic_search_chunks,
 )
from app.infrastructure.search.search_engine_impl import SearchEngineImpl, SearchEngineSettings
from app.interfaces.api.deps import CurrentUser, Settings, TenantContext, get_current_user, get_db, get_settings, get_tenant_context
from app.interfaces.api.schemas.search import SearchResponse, SearchResultItem
from app.infrastructure.audit.audit_logger import AuditEvent, AuditLogger


router = APIRouter(prefix="/v1/search", tags=["search"])

_authz = AuthorizationPolicy()

_STOP_WORDS = {
    "et",
    "ou",
    "de",
    "des",
    "du",
    "la",
    "le",
    "les",
    "un",
    "une",
    "au",
    "aux",
    "en",
    "dans",
    "pour",
    "sur",
    "avec",
    "sans",
    "par",
}


def _fts_query_from_user_text(user_q: str) -> str:
    q = (user_q or "").strip()
    if not q:
        return ""
    cleaned = re.sub(r"[^\w\u00C0-\u017F]+", " ", q, flags=re.UNICODE)
    parts = [p for p in cleaned.split() if p]
    tokens: list[str] = []
    for p in parts:
        low = p.lower()
        if low in _STOP_WORDS:
            continue
        if len(p) < 2:
            continue
        tokens.append(f'"{p}"')
    return " OR ".join(tokens)


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
    if not _authz.is_admin(
        DomainTenantContext(
            organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role
        )
    ):
        restrict_to_user_id = tenant.user_id

    include_archived = False
    AuditLogger(db).log(
        AuditEvent(
            organization_id=tenant.organization_id,
            actor_user_id=tenant.user_id,
            action="SEARCH_QUERY",
            target_type=None,
            target_id=None,
            detail={"q": query, "include_archived": include_archived},
        )
    )
    db.commit()

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
        # Build the accessible doc set once so semantic search respects permissions.
        docs_stmt = (
            select(DocumentModel.id, DocumentModel.filename)
            .where(DocumentModel.organization_id == tenant.organization_id)
            .where(DocumentModel.status != "deleted")
        )
        if restrict_to_user_id is not None:
            docs_stmt = docs_stmt.where(DocumentModel.uploaded_by_user_id == restrict_to_user_id)
        if not include_archived:
            docs_stmt = docs_stmt.where(DocumentModel.status != "archived")
        accessible = db.execute(docs_stmt).all()
        accessible_ids = [str(did) for did, _ in accessible]
        filename_by_id = {str(did): str(fn) for did, fn in accessible}

        semantic_hits: dict[str, tuple[float, str | None]] = {}
        if settings.semantic_enabled and accessible_ids:
            try:
                sem = semantic_search_chunks(
                    db=db,
                    organization_id=tenant.organization_id,
                    query=query,
                    settings=SemanticSettings(
                        model_name=settings.semantic_model_name,
                        chunk_chars=int(settings.semantic_chunk_chars),
                        chunk_overlap_chars=int(settings.semantic_chunk_overlap_chars),
                        max_chunks_per_doc=int(settings.semantic_max_chunks_per_doc),
                    ),
                    candidate_document_ids=accessible_ids,
                    limit_docs=25,
                )
                semantic_hits = {doc_id: (float(sc), prev) for (doc_id, sc, prev) in sem}
            except Exception:
                semantic_hits = {}

        fts_q = _fts_query_from_user_text(query)
        rows = db.execute(
            sql_text(
                """
                SELECT
                  document_search_fts.document_id,
                  d.filename,
                  bm25(document_search_fts) AS bm25_score,
                  snippet(document_search_fts, 2, '[', ']', '…', 12) AS snip
                FROM document_search_fts
                JOIN documents d ON d.id = document_search_fts.document_id
                WHERE d.organization_id = :org_id
                  AND (:user_id IS NULL OR d.uploaded_by_user_id = :user_id)
                  AND d.status != 'deleted'
                  AND (:include_archived = 1 OR d.status != 'archived')
                  AND document_search_fts MATCH :q
                ORDER BY bm25_score ASC
                LIMIT 25
                """
            ),
            {
                "q": fts_q or query,
                "org_id": tenant.organization_id,
                "user_id": restrict_to_user_id,
                "include_archived": (1 if include_archived else 0),
            },
        ).all()

        lexical_ranked: list[str] = [str(doc_id) for (doc_id, _, _, _) in rows]
        semantic_ranked: list[str] = list(semantic_hits.keys())

        # If FTS returns nothing (or query had tricky punctuation), fall back to LIKE even on SQLite.
        if not lexical_ranked and not semantic_ranked:
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
                results.append(
                    SearchResultItem(
                        document_id=doc.id,
                        filename=doc.filename,
                        score=0.5,
                        preview=(doc_text[:240] or None),
                    )
                )
            results.sort(key=lambda r: r.score, reverse=True)
            return SearchResponse(query=query, results=results)

        merged_ids = rrf_fuse(ranked_lists=[semantic_ranked, lexical_ranked], limit=25)

        lexical_by_id: dict[str, tuple[float, str | None]] = {}
        for doc_id, _filename, bm25_score, snip in rows:
            # Convert BM25 (lower is better) to a higher-is-better score in (0,1].
            lexical_by_id[str(doc_id)] = (1.0 / (1.0 + float(bm25_score or 0.0)), str(snip) if snip else None)

        results: list[SearchResultItem] = []
        for doc_id in merged_ids:
            fn = filename_by_id.get(doc_id) or (doc_id if doc_id else "")
            if doc_id in semantic_hits:
                sc, prev = semantic_hits[doc_id]
                # Similarity in [-1,1]; clamp to [0,1] for UI consistency.
                score = max(0.0, min(1.0, (sc + 1.0) / 2.0))
                results.append(SearchResultItem(document_id=doc_id, filename=fn, score=score, preview=prev))
            elif doc_id in lexical_by_id:
                sc, prev = lexical_by_id[doc_id]
                results.append(SearchResultItem(document_id=doc_id, filename=fn, score=float(sc), preview=prev))
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
    user: Annotated[CurrentUser, Depends(get_current_user)],
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
                  document_search_fts.document_id,
                  d.filename,
                  bm25(document_search_fts) AS bm25_score,
                  snippet(document_search_fts, 2, '[', ']', '…', 12) AS snip
                FROM document_search_fts
                JOIN documents d ON d.id = document_search_fts.document_id
                JOIN memberships m ON m.organization_id = d.organization_id
                WHERE m.user_id = :user_id
                  AND m.status = 'active'
                  AND d.uploaded_by_user_id = :user_id
                  AND d.status != 'deleted'
                  AND d.status != 'archived'
                  AND document_search_fts MATCH :q
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
