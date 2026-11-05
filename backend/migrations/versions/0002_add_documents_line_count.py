"""add documents line count

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 14:42:31.119794

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No backfill or server default: no released code has ever written to this table,
    # so it's empty in every real database.
    op.add_column("documents", sa.Column("line_count", sa.Integer(), nullable=False))


def downgrade() -> None:
    op.drop_column("documents", "line_count")
