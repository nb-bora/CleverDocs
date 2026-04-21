from app.domain.document.events.document_failed import DocumentFailed
from app.domain.document.events.document_indexed import DocumentIndexed
from app.domain.document.events.document_processed import DocumentProcessed
from app.domain.document.events.document_reindex_requested import DocumentReindexRequested
from app.domain.document.events.document_uploaded import DocumentUploaded
from app.domain.document.events.document_version_added import DocumentVersionAdded

__all__ = [
    "DocumentFailed",
    "DocumentIndexed",
    "DocumentProcessed",
    "DocumentReindexRequested",
    "DocumentUploaded",
    "DocumentVersionAdded",
]
"""Document domain events."""
