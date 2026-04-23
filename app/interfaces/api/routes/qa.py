"""QA / RAG routes (grounded answers with citations + abstention)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from app.domain.identity.services.authorization_policy import AuthorizationPolicy, TenantContext as DomainTenantContext
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.membership_model import MembershipModel
from app.infrastructure.llm.openai_compat_client import OpenAICompatClient, OpenAICompatConfig
from app.infrastructure.search.semantic_search import SemanticSettings, semantic_search_top_chunks
from app.interfaces.api.deps import CurrentUser, Settings, TenantContext, get_current_user, get_db, get_settings, get_tenant_context
from app.interfaces.api.schemas.qa import QARequest, QAResponse, QASource

router = APIRouter(prefix="/v1/qa", tags=["qa"])
_authz = AuthorizationPolicy()


def _get_tenant(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    return tenant


def _candidate_doc_ids_lexical_sqlite(
    *,
    db: Session,
    org_id: str,
    user_id: str | None,
    query: str,
    limit: int,
) -> list[str]:
    rows = db.execute(
        sql_text(
            """
            SELECT
              document_search_fts.document_id,
              bm25(document_search_fts) AS bm25_score
            FROM document_search_fts
            JOIN documents d ON d.id = document_search_fts.document_id
            WHERE d.organization_id = :org_id
              AND (:user_id IS NULL OR d.uploaded_by_user_id = :user_id)
              AND d.status != 'deleted'
              AND d.status != 'archived'
              AND document_search_fts MATCH :q
            ORDER BY bm25_score ASC
            LIMIT :limit
            """
        ),
        {"q": query, "org_id": org_id, "user_id": user_id, "limit": int(limit)},
    ).all()
    return [str(doc_id) for (doc_id, _bm25) in rows]


@router.post("", response_model=QAResponse)
def answer_question(
    body: QARequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    tenant: Annotated[TenantContext, Depends(_get_tenant)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> QAResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    # Access rule: reuse "read/search" style policy via tenant context.
    if not _authz.can_read(
        DomainTenantContext(organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role)
    ):
        raise HTTPException(status_code=403, detail="READ_NOT_ALLOWED")

    mode = (body.mode or "org").strip().lower()
    restrict_to_user_id: str | None = None
    if mode == "mine":
        restrict_to_user_id = user.user_id
    elif not _authz.is_admin(
        DomainTenantContext(organization_id=tenant.organization_id, user_id=tenant.user_id, role=tenant.role)
    ):
        restrict_to_user_id = tenant.user_id

    # Candidate doc ids: lexical first (fast), then semantic only within candidates.
    candidates: list[str] = []
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        candidates = _candidate_doc_ids_lexical_sqlite(
            db=db,
            org_id=tenant.organization_id,
            user_id=restrict_to_user_id,
            query=question,
            limit=250,
        )
    else:
        # Postgres fallback: just limit by accessible documents and let semantic do the rest.
        stmt = select(DocumentModel.id).where(DocumentModel.organization_id == tenant.organization_id)
        stmt = stmt.where(DocumentModel.status != "deleted").where(DocumentModel.status != "archived")
        if restrict_to_user_id is not None:
            stmt = stmt.where(DocumentModel.uploaded_by_user_id == restrict_to_user_id)
        candidates = [str(x[0]) for x in db.execute(stmt.limit(500)).all()]

    # Semantic top chunks
    sources_hits = []
    if settings.semantic_enabled and candidates:
        try:
            sources_hits = semantic_search_top_chunks(
                db=db,
                organization_id=tenant.organization_id,
                query=question,
                settings=SemanticSettings(
                    model_name=settings.semantic_model_name,
                    chunk_chars=int(settings.semantic_chunk_chars),
                    chunk_overlap_chars=int(settings.semantic_chunk_overlap_chars),
                    max_chunks_per_doc=int(settings.semantic_max_chunks_per_doc),
                ),
                candidate_document_ids=candidates,
                limit_chunks=int(settings.rag_max_sources),
            )
        except Exception:
            sources_hits = []

    if not sources_hits:
        return QAResponse(
            question=question,
            answer="Je ne sais pas : je n’ai trouvé aucune source pertinente dans tes documents.",
            abstained=True,
            sources=[],
        )

    best = max(h.score for h in sources_hits)
    if float(best) < float(settings.rag_min_best_chunk_score):
        return QAResponse(
            question=question,
            answer="Je ne sais pas : les sources retrouvées ne sont pas assez fiables pour répondre.",
            abstained=True,
            sources=[],
        )

    # Resolve filenames
    doc_ids = list({h.document_id for h in sources_hits})
    docs = (
        db.execute(
            select(DocumentModel.id, DocumentModel.filename)
            .where(DocumentModel.organization_id == tenant.organization_id)
            .where(DocumentModel.id.in_(doc_ids))
        )
        .all()
    )
    filename_by_id = {str(did): str(fn) for (did, fn) in docs}

    sources: list[QASource] = [
        QASource(
            document_id=h.document_id,
            filename=filename_by_id.get(h.document_id, ""),
            chunk_index=h.chunk_index,
            score=float(h.score),
            excerpt=h.chunk_text,
        )
        for h in sources_hits
    ]

    # If LLM not enabled/configured, return grounded sources only.
    if not settings.rag_enabled or not settings.rag_api_key:
        return QAResponse(
            question=question,
            answer="Sources retrouvées. Active `rag_enabled=true` + configure `rag_api_key` pour obtenir une réponse générée et citée.",
            abstained=False,
            sources=sources,
        )

    system = (
        "Tu es un assistant QA. Règles strictes:\n"
        "- Réponds UNIQUEMENT avec les informations contenues dans les SOURCES.\n"
        "- Chaque affirmation factuelle doit être justifiée par au moins une citation.\n"
        "- Si les SOURCES ne suffisent pas, réponds que tu ne sais pas.\n"
        'Réponds au format JSON: {"answer": "...", "abstained": true|false, "citations": [{"document_id":"...","chunk_index":0}]}'
    )
    packed_sources = [
        {
            "document_id": s.document_id,
            "filename": s.filename,
            "chunk_index": s.chunk_index,
            "score": s.score,
            "excerpt": s.excerpt,
        }
        for s in sources
    ]
    user_msg = f"QUESTION:\n{question}\n\nSOURCES:\n{json.dumps(packed_sources, ensure_ascii=False)}"

    client = OpenAICompatClient(
        OpenAICompatConfig(
            base_url=settings.rag_api_base_url,
            api_key=settings.rag_api_key,
            model=settings.rag_model,
        )
    )
    try:
        raw = client.chat_completion_json(system=system, user=user_msg, max_tokens=int(settings.rag_answer_max_tokens))
        content = (((raw.get("choices") or [])[0] or {}).get("message") or {}).get("content")
        data = json.loads(content) if isinstance(content, str) else {}
        answer = str(data.get("answer") or "").strip()
        abstained = bool(data.get("abstained") is True)
        if not answer:
            raise ValueError("empty_answer")
        return QAResponse(question=question, answer=answer, abstained=abstained, sources=sources)
    except Exception:
        # Hard safety fallback: do not hallucinate.
        return QAResponse(
            question=question,
            answer="Je ne sais pas : échec de génération fiable. Voici les sources brutes.",
            abstained=True,
            sources=sources,
        )

