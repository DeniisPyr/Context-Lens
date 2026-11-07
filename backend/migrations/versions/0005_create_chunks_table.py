"""create chunks table

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 15:12:40.318207

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Documents already stored get no chunks here, because making them needs Gemini.
    op.create_table(
        "chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        # A number rather than EMBEDDING_DIMENSIONS, so this revision stays what it
        # was if the code changes.
        sa.Column("embedding", Vector(768), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "position", name=op.f("pk_chunks")),
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.execute("DROP EXTENSION vector")
