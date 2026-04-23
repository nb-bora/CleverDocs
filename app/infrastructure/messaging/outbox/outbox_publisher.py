"""Publish outbox events to bus (MVP)."""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.infrastructure.db.orm.models.outbox_event_model import OutboxEventModel
from app.infrastructure.messaging.event_bus import EventBus, PublishedEvent


def publish_one(*, db: Session, bus: EventBus | None, ev: OutboxEventModel) -> None:
    if bus is None:
        return
    bus.publish(
        PublishedEvent(
            event_type=ev.event_type,
            payload={},  # payload is already stored; bus is no-op MVP
            organization_id=ev.organization_id,
        )
    )


def get_pending_events(db: Session, *, limit: int = 100) -> list[OutboxEventModel]:
    stmt = (
        select(OutboxEventModel)
        .where(OutboxEventModel.status == "pending")
        .order_by(OutboxEventModel.created_at.asc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
