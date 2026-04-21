"""Event: indexed in search."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentIndexed(DocumentEvent):
    index_name: str = ""
