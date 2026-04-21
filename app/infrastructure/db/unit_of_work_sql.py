"""SQL UnitOfWork implementation (MVP).

Goal: centralize transaction/session boundaries and expose repositories.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.document_repository_sql import DocumentRepositorySql
from app.infrastructure.db.repositories.organization_repository_sql import OrganizationRepositorySql
from app.infrastructure.db.repositories.user_repository_sql import UserRepositorySql


@dataclass
class UnitOfWorkSql:
    """Minimal Unit of Work for sync SQLAlchemy sessions."""

    db: Session

    def __post_init__(self) -> None:
        self.documents = DocumentRepositorySql(self.db)
        self.organizations = OrganizationRepositorySql(self.db)
        self.users = UserRepositorySql(self.db)

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
