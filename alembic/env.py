from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# IMPORTANT: for now, we don't import ORM models metadata.
# When SQLAlchemy models are implemented, set:
# from app.infrastructure.db.orm.base import Base
# target_metadata = Base.metadata
target_metadata = None


def get_url() -> str:
    # Alembic supports env var interpolation with %(DATABASE_URL)s, but we also
    # provide a fallback so `alembic` works in more contexts.
    return os.getenv("DATABASE_URL", "postgresql+psycopg://cleverdocs:cleverdocs@localhost:5432/cleverdocs")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

