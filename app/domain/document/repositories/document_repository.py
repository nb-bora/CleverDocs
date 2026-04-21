"""DocumentRepository port (interface)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.document.aggregates.document import Document


class DocumentRepository(ABC):
    @abstractmethod
    def get_by_id_for_org(self, *, document_id: str, organization_id: str) -> Document | None: ...

    @abstractmethod
    def save(self, doc: Document) -> None: ...
