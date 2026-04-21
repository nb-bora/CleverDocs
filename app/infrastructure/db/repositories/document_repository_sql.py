"""SQL implementation of DocumentRepository (MVP)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_model import DocumentModel


@dataclass(frozen=True)
class DocumentRepositorySql:
    db: Session

    def get(self, document_id: str) -> DocumentModel | None:
        return self.db.get(DocumentModel, document_id)

    def get_by_id_for_org(self, *, document_id: str, organization_id: str) -> DocumentModel | None:
        return (
            self.db.execute(
                select(DocumentModel)
                .where(DocumentModel.id == document_id)
                .where(DocumentModel.organization_id == organization_id)
            )
            .scalars()
            .first()
        )

    def add(self, doc: DocumentModel) -> None:
        self.db.add(doc)
