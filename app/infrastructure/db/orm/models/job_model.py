"""ORM model: background jobs queue (DB-backed, MVP).

We use a DB-backed queue to keep the system simple and reliable without Redis/Celery.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.orm.base import Base


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # job types: OCR, INDEX (extend later)
    type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")

    # Multi-tenant scope (required for strict isolation).
    organization_id: Mapped[str] = mapped_column(String(36), index=True)

    document_id: Mapped[str] = mapped_column(String(36), index=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Next time the job can run (backoff / scheduling). If null => run immediately.
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def schedule_in(self, seconds: int) -> None:
        self.next_run_at = datetime.now(UTC) + timedelta(seconds=max(1, int(seconds)))

