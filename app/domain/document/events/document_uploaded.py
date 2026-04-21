"""Event: document uploaded."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.document.events._base import DocumentEvent


@dataclass(frozen=True, slots=True)
class DocumentUploaded(DocumentEvent):
    filename: str = ""
    storage_key: str = ""
"""Event: document uploaded."""
