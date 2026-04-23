from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.infrastructure.db.orm.base import Base

# Ensure models are imported so metadata is populated.
from app.infrastructure.db.orm.models.document_content_model import DocumentContentModel  # noqa: F401
from app.infrastructure.db.orm.models.document_model import DocumentModel  # noqa: F401
from app.infrastructure.db.orm.models.document_version_model import DocumentVersionModel  # noqa: F401
from app.infrastructure.db.orm.models.job_model import JobModel  # noqa: F401
from app.infrastructure.db.orm.models.organization_model import OrganizationModel  # noqa: F401
from app.infrastructure.db.orm.models.user_model import UserModel  # noqa: F401
from app.infrastructure.db.orm.models.membership_model import MembershipModel  # noqa: F401
from app.infrastructure.db.orm.models.refresh_token_model import RefreshTokenModel  # noqa: F401
from app.infrastructure.db.orm.models.audit_log_model import AuditLogModel  # noqa: F401
from app.infrastructure.db.orm.models.invitation_model import InvitationModel  # noqa: F401
from app.infrastructure.db.orm.models.outbox_event_model import OutboxEventModel  # noqa: F401
from app.infrastructure.db.orm.models.permission_model import PermissionModel  # noqa: F401
from app.infrastructure.db.orm.models.role_model import RoleModel  # noqa: F401
from app.infrastructure.db.orm.models.role_permission_model import RolePermissionModel  # noqa: F401
from app.infrastructure.db.orm.models.document_embedding_model import DocumentEmbeddingModel  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # Alembic supports env var interpolation with %(DATABASE_URL)s, but we also
    # provide a fallback so `alembic` works in more contexts.
    return os.getenv("DATABASE_URL", "sqlite:///./cleverdocs.db")


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

