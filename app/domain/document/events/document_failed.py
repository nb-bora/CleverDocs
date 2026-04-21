"""Event: document failed during processing/indexing."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentFailed(DocumentEvent):
    reason: str = ""
    stage: str = ""  # ocr|index|other
"""Event: document processing failed."""
