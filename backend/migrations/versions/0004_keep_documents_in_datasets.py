"""keep documents in datasets

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05 17:38:52.640271

"""

from collections.abc import Sequence
from os.path import splitext
from uuid import UUID

import sqlalchemy as sa
from alembic import context, op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _numbered(filename: str, number: int) -> str:
    stem, extension = splitext(filename)
    return f"{stem} ({number}){extension}"


def _new_names_for_duplicates(documents: Sequence[sa.Row]) -> list[tuple[UUID, str]]:
    # Every name in use counts as taken from the start, so a copy of notes.txt skips
    # notes (2).txt when a file is really called that, whichever came first.
    taken = {document.filename for document in documents}
    kept = set()
    new_names = []
    for document in documents:
        if document.filename not in kept:
            kept.add(document.filename)
            continue
        number = 2
        while _numbered(document.filename, number) in taken:
            number += 1
        new_name = _numbered(document.filename, number)
        taken.add(new_name)
        new_names.append((document.id, new_name))
    return new_names


def _rename_duplicates() -> None:
    connection = op.get_bind()
    # Oldest first, so the oldest copy keeps the name. Never reads the text: it's up to
    # 1 MB per document, and the renaming doesn't need it.
    documents = connection.execute(
        sa.text("SELECT id, filename FROM documents ORDER BY created_at, id")
    ).all()
    for document_id, new_name in _new_names_for_duplicates(documents):
        connection.execute(
            sa.text("UPDATE documents SET filename = :filename WHERE id = :id"),
            {"filename": new_name, "id": document_id},
        )


def upgrade() -> None:
    op.add_column("documents", sa.Column("dataset_id", sa.Uuid(), nullable=True))
    # Only when there are documents to move. The name can already be there, from 0003 or
    # an earlier downgrade, and then the documents join that dataset.
    op.execute(
        "INSERT INTO datasets (id, name) "
        "SELECT gen_random_uuid(), 'My documents' "
        "WHERE EXISTS (SELECT 1 FROM documents) "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        "UPDATE documents "
        "SET dataset_id = (SELECT id FROM datasets WHERE name = 'My documents')"
    )
    # A SQL script can't read rows to work out new names, so running one on a database
    # with duplicates stops at the unique constraint below, and nothing changes.
    if not context.is_offline_mode():
        _rename_duplicates()
    op.alter_column("documents", "dataset_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_documents_dataset_id_datasets"),
        "documents",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_documents_dataset_id_filename"),
        "documents",
        ["dataset_id", "filename"],
    )


def downgrade() -> None:
    # The documents stay. Renamed ones keep their new names, because nothing recorded the
    # old ones and they're still correct.
    op.drop_constraint(
        op.f("uq_documents_dataset_id_filename"), "documents", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_documents_dataset_id_datasets"), "documents", type_="foreignkey"
    )
    op.drop_column("documents", "dataset_id")
