from uuid import UUID, uuid4

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from context_lens.db.ids import parse_id
from context_lens.db.models import ChunkRow, DatasetRow, DocumentRow
from context_lens.services.datasets import DatasetFullError, DatasetNotFoundError
from context_lens.services.documents import (
    Document,
    DocumentInfo,
    DocumentNotFoundError,
    DuplicateDocumentError,
)
from context_lens.services.indexing import EmbeddedChunk

FILENAME_CONSTRAINT = "uq_documents_dataset_id_filename"
DATASET_CONSTRAINT = "fk_documents_dataset_id_datasets"


class DocumentRejectedError(Exception):
    """A constraint refused the document, so the schema and this code disagree."""


def _chunk_rows(document_id: UUID, chunks: list[EmbeddedChunk]) -> list[ChunkRow]:
    return [
        ChunkRow(
            document_id=document_id,
            position=position,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            text=chunk.text,
            embedding=chunk.embedding,
        )
        for position, chunk in enumerate(chunks)
    ]


def _count_documents(dataset_key: UUID) -> Select[int]:
    return (
        select(func.count())
        .select_from(DocumentRow)
        .where(DocumentRow.dataset_id == dataset_key)
    )


class DocumentStore:
    # Each method holds a connection only for its own short transaction. /api/ask waits
    # up to a minute for Gemini, and must not keep a connection busy all that time.
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine)

    async def check_can_add(
        self, dataset_id: str, filename: str, max_documents: int
    ) -> None:
        key = parse_id(dataset_id)
        if key is None:
            raise DatasetNotFoundError
        same_name = select(DocumentRow.id).where(
            DocumentRow.dataset_id == key, DocumentRow.filename == filename
        )
        # Only tells an upload early that add would refuse it. Another upload can still
        # get there first, and then add's constraints decide.
        async with self._sessions.begin() as session:
            if await session.get(DatasetRow, key) is None:
                raise DatasetNotFoundError
            if await session.scalar(_count_documents(key)) >= max_documents:
                raise DatasetFullError(max_documents)
            if await session.scalar(same_name.exists().select()):
                raise DuplicateDocumentError(filename)

    async def add(
        self,
        dataset_id: str,
        filename: str,
        text: str,
        chunks: list[EmbeddedChunk],
        max_documents: int,
    ) -> Document:
        key = parse_id(dataset_id)
        if key is None:
            raise DatasetNotFoundError
        document = Document(id=str(uuid4()), filename=filename, text=text)
        row = DocumentRow(
            id=UUID(document.id),
            dataset_id=key,
            filename=filename,
            text=text,
            line_count=document.line_count,
        )
        try:
            # One transaction, so a document is never stored without its chunks.
            async with self._sessions.begin() as session:
                # Locked until the transaction ends, so uploads into one dataset take
                # turns here, and two can't both see room for one more document.
                dataset = select(DatasetRow.id).where(DatasetRow.id == key)
                if await session.scalar(dataset.with_for_update()) is None:
                    raise DatasetNotFoundError
                if await session.scalar(_count_documents(key)) >= max_documents:
                    raise DatasetFullError(max_documents)
                session.add(row)
                # The models have no relationship, so SQLAlchemy can't tell that the
                # document must be inserted before its chunks.
                await session.flush()
                session.add_all(_chunk_rows(row.id, chunks))
        except IntegrityError as error:
            # The constraints decide rather than a SELECT beforehand, so a race can't get
            # past them. hide_parameters doesn't cover this: Postgres itself quotes the
            # failing row in its message, and the traceback would carry that text into
            # the logs.
            diagnostics = error.orig.diag
            if diagnostics.constraint_name == FILENAME_CONSTRAINT:
                raise DuplicateDocumentError(filename) from None
            if diagnostics.constraint_name == DATASET_CONSTRAINT:
                raise DatasetNotFoundError from None
            raise DocumentRejectedError(diagnostics.message_primary) from None
        return document

    async def get(self, document_id: str) -> Document | None:
        key = parse_id(document_id)
        if key is None:
            return None
        async with self._sessions.begin() as session:
            row = await session.get(DocumentRow, key)
            if row is None:
                return None
            return Document(id=str(row.id), filename=row.filename, text=row.text)

    async def delete(self, document_id: str) -> None:
        key = parse_id(document_id)
        if key is None:
            raise DocumentNotFoundError
        # RETURNING tells a deleted row from a missing one in the same statement, so a
        # SELECT beforehand isn't needed, and two requests racing can't both succeed.
        statement = (
            delete(DocumentRow).where(DocumentRow.id == key).returning(DocumentRow.id)
        )
        async with self._sessions.begin() as session:
            deleted = (await session.execute(statement)).scalar_one_or_none()
        if deleted is None:
            raise DocumentNotFoundError

    async def list_in_dataset(self, dataset_id: str) -> list[DocumentInfo]:
        key = parse_id(dataset_id)
        if key is None:
            raise DatasetNotFoundError
        statement = (
            select(DocumentRow.id, DocumentRow.filename, DocumentRow.line_count)
            .where(DocumentRow.dataset_id == key)
            .order_by(DocumentRow.created_at, DocumentRow.id)
        )
        async with self._sessions.begin() as session:
            # An empty dataset and a missing one both have no rows to list.
            if await session.get(DatasetRow, key) is None:
                raise DatasetNotFoundError
            rows = await session.execute(statement)
            return [
                DocumentInfo(
                    id=str(row.id), filename=row.filename, line_count=row.line_count
                )
                for row in rows
            ]
