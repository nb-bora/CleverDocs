"""Command: AddDocumentVersion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AddDocumentVersion:
    organization_id: str
    document_id: str
    filename: str
    storage_key: str
    actor_user_id: str | None = None
