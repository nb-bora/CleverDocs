"""Audit logger (writes to audit_logs)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.audit_log_model import AuditLogModel


@dataclass(frozen=True, slots=True)
class AuditEvent:
    organization_id: str
    actor_user_id: str | None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    detail: dict[str, Any] | None = None


class AuditLogger:
    def __init__(self, db: Session) -> None:
        self._db = db

    def log(self, ev: AuditEvent) -> None:
        payload = None
        if ev.detail is not None:
            payload = json.dumps(ev.detail, ensure_ascii=False, separators=(",", ":"))
        self._db.add(
            AuditLogModel(
                organization_id=ev.organization_id,
                actor_user_id=ev.actor_user_id,
                action=ev.action,
                target_type=ev.target_type,
                target_id=ev.target_id,
                detail=payload,
            )
        )
