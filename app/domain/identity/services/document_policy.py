"""Document policy rules for actions/transitions."""

from __future__ import annotations

from app.domain.document.aggregates.document import Document
from app.domain.document.value_objects.document_status import DocumentStatus


class DocumentPolicy:
    def can_reindex(self, doc: Document) -> bool:
        return doc.status in {DocumentStatus.processed, DocumentStatus.indexed, DocumentStatus.indexing_failed}
