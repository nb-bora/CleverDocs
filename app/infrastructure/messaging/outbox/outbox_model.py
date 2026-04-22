"""Outbox event persistence helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.outbox_event_model import OutboxEventModel


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_type: str
    payload: dict[str, Any]
    organization_id: str | None = None


def enqueue_outbox_event(*, db: Session, ev: OutboxEvent) -> None:
    db.add(
        OutboxEventModel(
            organization_id=ev.organization_id,
            event_type=ev.event_type,
            payload_json=json.dumps(ev.payload, ensure_ascii=False, separators=(",", ":")),
            status="pending",
            attempts=0,
            last_error=None,
        )
    )
