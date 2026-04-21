"""Event: reindex requested."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentReindexRequested(DocumentEvent):
    requested_by_user_id: str | None = None
