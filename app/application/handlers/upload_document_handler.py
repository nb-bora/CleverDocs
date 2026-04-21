"""Use case: upload document (write side).

This orchestrates:
- domain aggregate creation + event emission
- persistence
- enqueue OCR job
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.commands.upload_document import UploadDocument
from app.application.common.event_publisher import EventPublisher
from app.domain.document.aggregates.document import Document as DomainDocument
from app.infrastructure.db.orm.models.document_model import DocumentModel
from app.infrastructure.db.orm.models.job_model import JobModel


@dataclass(frozen=True)
class UploadDocumentResult:
    document_id: str


def handle_upload_document(*, cmd: UploadDocument, db: Session, publisher: EventPublisher | None = None) -> UploadDocumentResult:
    document_id = str(uuid.uuid4())

    agg = DomainDocument.upload(
        document_id=document_id,
        organization_id=cmd.organization_id,
        filename=cmd.filename,
        storage_key=cmd.storage_key,
    )

    doc = DocumentModel(
        id=agg.id,
        organization_id=agg.organization_id,
        filename=agg.filename,
        status=str(agg.status),
        storage_key=agg.storage_key,
        failed_reason=None,
    )
    db.add(doc)
    db.add(JobModel(type="OCR", status="queued", document_id=doc.id))
    db.commit()

    if publisher is not None:
        for ev in agg.pop_events():
            publisher.publish(ev)

    return UploadDocumentResult(document_id=doc.id)

"""Use case: upload document."""
