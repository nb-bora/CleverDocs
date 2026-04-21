"""DB engine/session factory (SQLAlchemy 2.x, sync).

MVP: sync sessions are simpler. We can switch to async later if needed.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        # Default to a local SQLite DB to avoid shipping credentials in code.
        "sqlite:///./cleverdocs.db",
    )


ENGINE = create_engine(get_database_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)

