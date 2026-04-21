"""SQLite FTS helpers (MVP).

We keep these in infrastructure/db so both API and workers can reuse without importing API routes.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def upsert_sqlite_fts(
    *, db: Session, organization_id: str, document_id: str, filename: str, content: str
) -> None:
    if db.bind is None or db.bind.dialect.name != "sqlite":
        return
    db.execute(text("DELETE FROM document_search_fts WHERE document_id = :id"), {"id": document_id})
    db.execute(
        text(
            "INSERT INTO document_search_fts(organization_id, document_id, filename, content) "
            "VALUES (:org, :id, :fn, :ct)"
        ),
        {"org": organization_id, "id": document_id, "fn": filename, "ct": content},
    )

