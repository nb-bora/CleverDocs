"""Query: document status timeline.

MVP: keep it minimal (documents table doesn't store transition history yet).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_model import DocumentModel


@dataclass(frozen=True, slots=True)
class GetDocumentStatusTimeline:
    organization_id: str
    document_id: str


def query_get_document_status_timeline(*, q: GetDocumentStatusTimeline, db: Session) -> dict:
    doc = (
        db.query(DocumentModel)
        .filter(DocumentModel.id == q.document_id)
        .filter(DocumentModel.organization_id == q.organization_id)
        .first()
    )
    if doc is None:
        raise KeyError("Document not found")
    return {
        "document_id": doc.id,
        "organization_id": doc.organization_id,
        "current_status": doc.status,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
        "events": [],
    }
