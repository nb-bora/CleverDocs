"""ORM model: semantic embeddings for document chunks (vector search)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.orm.base import Base


class DocumentEmbeddingModel(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)

    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)

    # JSON string (list[float]) to stay portable across SQLite/Postgres.
    embedding_json: Mapped[str] = mapped_column(Text)

    model_name: Mapped[str] = mapped_column(String(255), default="unknown")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_embedding_doc_chunk"),
    )

