"""Event: new document version added."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentVersionAdded(DocumentEvent):
    version_id: str = ""
