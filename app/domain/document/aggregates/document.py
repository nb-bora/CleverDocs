"""Document aggregate root: lifecycle + invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.common.exceptions import InvariantViolation, InvalidTransition
from app.domain.common.events import DomainEvent
from app.domain.document.events import (
    DocumentFailed,
    DocumentIndexed,
    DocumentProcessed,
    DocumentReindexRequested,
    DocumentUploaded,
)
from app.domain.document.value_objects.document_status import DocumentStatus
from app.domain.document.value_objects.file_type import FileType


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Document:
    """Aggregate root for document lifecycle."""

    id: str
    organization_id: str
    filename: str
    storage_key: str

    status: DocumentStatus = DocumentStatus.uploaded
    file_type: FileType = FileType.other

    failed_reason: str | None = None

    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    @property
    def events(self) -> list[DomainEvent]:
        return list(self._events)

    def pop_events(self) -> list[DomainEvent]:
        ev, self._events = self._events, []
        return ev

    @staticmethod
    def upload(*, document_id: str, organization_id: str, filename: str, storage_key: str) -> "Document":
        if not organization_id:
            raise InvariantViolation("organization_id is required")
        if not filename:
            raise InvariantViolation("filename is required")
        if not storage_key:
            raise InvariantViolation("storage_key is required")

        doc = Document(
            id=document_id,
            organization_id=organization_id,
            filename=filename,
            storage_key=storage_key,
            status=DocumentStatus.uploaded,
            file_type=FileType.from_filename(filename),
        )
        doc._emit(
            DocumentUploaded(
                document_id=document_id,
                organization_id=organization_id,
                filename=filename,
                storage_key=storage_key,
            )
        )
        return doc

    def mark_processing(self) -> None:
        if self.status not in (DocumentStatus.uploaded, DocumentStatus.failed, DocumentStatus.indexing_failed):
            raise InvalidTransition(f"Cannot transition {self.status} -> processing")
        self.status = DocumentStatus.processing
        self.failed_reason = None
        self._touch()

    def mark_processed(self, *, ocr_engine: str, language: str | None) -> None:
        if self.status != DocumentStatus.processing:
            raise InvalidTransition(f"Cannot transition {self.status} -> processed")
        self.status = DocumentStatus.processed
        self.failed_reason = None
        self._touch()
        self._emit(
            DocumentProcessed(
                document_id=self.id,
                organization_id=self.organization_id,
                ocr_engine=ocr_engine,
                language=language,
            )
        )

    def request_reindex(self, *, requested_by_user_id: str | None = None) -> None:
        if self.status not in (
            DocumentStatus.processed,
            DocumentStatus.indexed,
            DocumentStatus.indexing_failed,
        ):
            raise InvalidTransition(f"Cannot request reindex from status {self.status}")
        self.status = DocumentStatus.indexing_pending
        self._touch()
        self._emit(
            DocumentReindexRequested(
                document_id=self.id,
                organization_id=self.organization_id,
                requested_by_user_id=requested_by_user_id,
            )
        )

    def mark_indexed(self, *, index_name: str) -> None:
        if self.status not in (DocumentStatus.processed, DocumentStatus.indexing_pending):
            raise InvalidTransition(f"Cannot transition {self.status} -> indexed")
        self.status = DocumentStatus.indexed
        self.failed_reason = None
        self._touch()
        self._emit(DocumentIndexed(document_id=self.id, organization_id=self.organization_id, index_name=index_name))

    def fail(self, *, reason: str, stage: str) -> None:
        if not reason:
            raise InvariantViolation("reason is required")
        self.status = DocumentStatus.failed if stage == "ocr" else DocumentStatus.indexing_failed
        self.failed_reason = reason
        self._touch()
        self._emit(DocumentFailed(document_id=self.id, organization_id=self.organization_id, reason=reason, stage=stage))

    def _touch(self) -> None:
        self.updated_at = _now()

    def _emit(self, event: DomainEvent) -> None:
        self._events.append(event)
