"""SQL implementation of OrganizationRepository (MVP)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.organization_model import OrganizationModel


@dataclass(frozen=True)
class OrganizationRepositorySql:
    db: Session

    def get(self, organization_id: str) -> OrganizationModel | None:
        return self.db.get(OrganizationModel, organization_id)

    def add(self, org: OrganizationModel) -> None:
        self.db.add(org)
