"""Event: document processed (OCR complete)."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentProcessed(DocumentEvent):
    ocr_engine: str = ""
    language: str | None = None
