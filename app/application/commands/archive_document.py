"""Command: ArchiveDocument."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArchiveDocument:
    organization_id: str
    document_id: str
    actor_user_id: str | None = None
