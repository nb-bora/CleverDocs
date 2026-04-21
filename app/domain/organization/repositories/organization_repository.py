"""OrganizationRepository port (interface)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.organization.entities.organization import Organization


class OrganizationRepository(ABC):
    @abstractmethod
    def get_by_id(self, organization_id: str) -> Organization | None: ...
