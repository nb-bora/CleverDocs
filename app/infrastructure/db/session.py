"""DB engine/session factory (SQLAlchemy 2.x, sync).

MVP: sync sessions are simpler. We can switch to async later if needed.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        # Default to a local SQLite DB to avoid shipping credentials in code.
        "sqlite:///./cleverdocs.db",
    )


ENGINE = create_engine(get_database_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)


def ensure_sqlite_fts() -> None:
    """Ensure SQLite FTS5 table exists for accent-insensitive search + BM25 ranking.

    This keeps the MVP usable without OpenSearch while still having "real" search:
    - diacritics-insensitive (ingenieur == ingénieur)
    - BM25 ranking
    - snippet generation
    """

    url = str(ENGINE.url)
    if not url.startswith("sqlite"):
        return

    with ENGINE.begin() as conn:
        # If the FTS schema isn't tenant-aware yet, recreate it (SQLite limitation).
        cols = conn.execute(text("PRAGMA table_info(document_search_fts)")).fetchall()
        col_names = {c[1] for c in cols} if cols else set()
        if col_names and "organization_id" not in col_names:
            conn.execute(text("DROP TABLE document_search_fts"))
            col_names = set()

        if not col_names:
            # FTS table kept in sync manually (delete+insert) when content is processed.
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_search_fts
                    USING fts5(
                      organization_id UNINDEXED,
                      document_id UNINDEXED,
                      filename,
                      content,
                      tokenize = 'unicode61 remove_diacritics 2'
                    );
                    """
                )
            )

            # Best-effort backfill from existing rows.
            conn.execute(
                text(
                    """
                    INSERT INTO document_search_fts(organization_id, document_id, filename, content)
                    SELECT d.organization_id, d.id, d.filename, COALESCE(c.cleaned_text, '')
                    FROM documents d
                    JOIN document_contents c ON c.document_id = d.id
                    WHERE d.organization_id IS NOT NULL
                      AND c.cleaned_text IS NOT NULL
                      AND length(c.cleaned_text) > 0
                    """
                )
            )


def ensure_sqlite_jobs_schema() -> None:
    """Evolve SQLite schema for `jobs` table in MVP without Alembic.

    SQLite doesn't support all ALTER patterns, but adding a nullable column is fine.
    """
    url = str(ENGINE.url)
    if not url.startswith("sqlite"):
        return

    with ENGINE.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
        if not cols:
            return
        col_names = {c[1] for c in cols}  # pragma: no cover
        if "organization_id" not in col_names:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN organization_id VARCHAR(36)"))
        if "next_run_at" not in col_names:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN next_run_at DATETIME"))


def ensure_sqlite_tenant_schema() -> None:
    """Evolve SQLite schema for multi-tenant MVP without Alembic."""
    url = str(ENGINE.url)
    if not url.startswith("sqlite"):
        return

    with ENGINE.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        if not cols:
            return
        col_names = {c[1] for c in cols}
        if "organization_id" not in col_names:
            conn.execute(text("ALTER TABLE documents ADD COLUMN organization_id VARCHAR(36)"))
        if "uploaded_by_user_id" not in col_names:
            conn.execute(text("ALTER TABLE documents ADD COLUMN uploaded_by_user_id VARCHAR(36)"))


def ensure_sqlite_identity_schema() -> None:
    """Evolve SQLite schema for auth/identity without Alembic (dev-only MVP)."""
    url = str(ENGINE.url)
    if not url.startswith("sqlite"):
        return

    with ENGINE.begin() as conn:
        user_cols = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        if user_cols:
            user_col_names = {c[1] for c in user_cols}
            if "password_hash" not in user_col_names:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))

        # Refresh tokens table (new in auth phase)
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                  id VARCHAR(36) PRIMARY KEY,
                  user_id VARCHAR(36) NOT NULL,
                  token_hash VARCHAR(128) NOT NULL UNIQUE,
                  expires_at DATETIME NOT NULL,
                  revoked_at DATETIME,
                  created_at DATETIME,
                  updated_at DATETIME
                )
                """
            )
        )

