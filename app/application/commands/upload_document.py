"""Command: UploadDocument."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UploadDocument:
    organization_id: str
    filename: str
    storage_key: str
    actor_user_id: str | None = None
