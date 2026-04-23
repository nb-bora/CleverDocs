"""Invitation provisioning + decline tracking.

Adds:
- declined_at
- invited_user_id
- provisioned_user_id
- provisioned_user_was_created
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "3d0c2a9b4f1a"
down_revision = ("7c3f2a1f7a8e", "8b4fd42dd99b")
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invitations") as b:
        b.add_column(sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("invited_user_id", sa.String(length=36), nullable=True))
        b.add_column(sa.Column("provisioned_user_id", sa.String(length=36), nullable=True))
        b.add_column(sa.Column("provisioned_user_was_created", sa.Boolean(), nullable=False, server_default=sa.text("false")))

        b.create_index("ix_invitations_invited_user_id", ["invited_user_id"])
        b.create_index("ix_invitations_provisioned_user_id", ["provisioned_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("invitations") as b:
        b.drop_index("ix_invitations_provisioned_user_id")
        b.drop_index("ix_invitations_invited_user_id")

        b.drop_column("provisioned_user_was_created")
        b.drop_column("provisioned_user_id")
        b.drop_column("invited_user_id")
        b.drop_column("declined_at")

