"""Query: get document (read side)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel
from app.infrastructure.db.orm.models.document_model import DocumentModel


@dataclass(frozen=True, slots=True)
class GetDocument:
    organization_id: str
    document_id: str


def query_get_document(*, q: GetDocument, db: Session) -> dict:
    doc = (
        db.query(DocumentModel)
        .filter(DocumentModel.id == q.document_id)
        .filter(DocumentModel.organization_id == q.organization_id)
        .first()
    )
    if doc is None:
        raise KeyError("Document not found")
    content = db.get(DocumentContentModel, doc.id)
    preview = (content.cleaned_text or "")[:500] if content and content.cleaned_text else None
    return {
        "id": doc.id,
        "organization_id": doc.organization_id,
        "filename": doc.filename,
        "status": doc.status,
        "failed_reason": doc.failed_reason,
        "text_preview": preview,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
