"""add documents page starts

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 16:18:13.452436

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and without a backfill: NULL means a text file, which every document
    # stored before this revision is.
    op.add_column(
        "documents", sa.Column("page_starts", sa.ARRAY(sa.Integer()), nullable=True)
    )


def downgrade() -> None:
    # The documents stay. A PDF's text keeps its lines, so its citations still work,
    # and only where its pages start is lost.
    op.drop_column("documents", "page_starts")
