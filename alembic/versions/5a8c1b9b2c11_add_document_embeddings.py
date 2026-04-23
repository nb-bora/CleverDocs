"""add document_embeddings

Revision ID: 5a8c1b9b2c11
Revises: eaca94e53f97
Create Date: 2026-04-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "5a8c1b9b2c11"
down_revision = "eaca94e53f97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "document_embeddings" not in existing_tables:
        op.create_table(
            "document_embeddings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("organization_id", sa.String(length=36), nullable=False),
            sa.Column("document_id", sa.String(length=36), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("chunk_text", sa.Text(), nullable=False),
            sa.Column("embedding_json", sa.Text(), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_embedding_doc_chunk"),
        )

    existing_indexes = {idx.get("name") for idx in inspector.get_indexes("document_embeddings")}
    ix_doc = op.f("ix_document_embeddings_document_id")
    ix_org = op.f("ix_document_embeddings_organization_id")

    if ix_doc not in existing_indexes:
        op.create_index(ix_doc, "document_embeddings", ["document_id"], unique=False)
    if ix_org not in existing_indexes:
        op.create_index(ix_org, "document_embeddings", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_embeddings_organization_id"), table_name="document_embeddings")
    op.drop_index(op.f("ix_document_embeddings_document_id"), table_name="document_embeddings")
    op.drop_table("document_embeddings")

