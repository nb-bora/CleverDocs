"""add user username

Revision ID: 7c3f2a1f7a8e
Revises: 5a8c1b9b2c11
Create Date: 2026-04-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "7c3f2a1f7a8e"
down_revision = "5a8c1b9b2c11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {col["name"] for col in inspector.get_columns("users")}
    if "username" not in existing_cols:
        op.add_column("users", sa.Column("username", sa.String(length=39), nullable=True))

    existing_indexes = {idx.get("name") for idx in inspector.get_indexes("users")}
    ix_username = op.f("ix_users_username")
    if ix_username not in existing_indexes:
        op.create_index(ix_username, "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_column("users", "username")

