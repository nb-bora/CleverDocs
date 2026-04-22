"""add user avatar

Revision ID: 8b4fd42dd99b
Revises: c05068be1ebd
Create Date: 2026-04-22 11:52:04.945170

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b4fd42dd99b'
down_revision = 'c05068be1ebd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_storage_key", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_storage_key")

