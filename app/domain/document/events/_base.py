"""Document domain event base types."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.common.events import DomainEvent


@dataclass(frozen=True, slots=True)
class DocumentEvent(DomainEvent):
    document_id: str = ""
    organization_id: str = ""
