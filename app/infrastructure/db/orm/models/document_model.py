"""ORM model: document (write model source-of-truth)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.orm.base import Base


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Multi-tenant: added early so we don't refactor later.
    # For now it's optional until Organization/Membership are implemented.
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    # Ownership: used for per-user access rules within/ across organizations.
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), index=True, default="uploaded")

    storage_key: Mapped[str] = mapped_column(String(512), unique=True)

    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

