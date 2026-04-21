"""Use case: request reindex (write side)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.commands.request_reindex import RequestReindex
from app.application.common.event_publisher import EventPublisher
from app.domain.document.aggregates.document import Document as DomainDocument
from app.domain.document.value_objects.document_status import DocumentStatus
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.job_model import JobModel


@dataclass(frozen=True)
class RequestReindexResult:
    document_id: str
    status: str


def handle_request_reindex(
    *, cmd: RequestReindex, db: Session, publisher: EventPublisher | None = None
) -> RequestReindexResult:
    doc = (
        db.query(DocumentModel)
        .filter(DocumentModel.id == cmd.document_id)
        .filter(DocumentModel.organization_id == cmd.organization_id)
        .first()
    )
    if doc is None:
        raise KeyError("Document not found")

    agg = DomainDocument(
        id=doc.id,
        organization_id=doc.organization_id or "",
        filename=doc.filename,
        storage_key=doc.storage_key,
        status=DocumentStatus(doc.status),
        failed_reason=doc.failed_reason,
    )
    agg.request_reindex(requested_by_user_id=cmd.actor_user_id)

    doc.status = str(agg.status)
    doc.failed_reason = None
    db.add(doc)
    db.add(JobModel(type="INDEX", status="queued", document_id=doc.id))
    db.commit()

    if publisher is not None:
        for ev in agg.pop_events():
            publisher.publish(ev)

    return RequestReindexResult(document_id=doc.id, status=doc.status)

"""Use case: request reindex."""
