from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from context_lens.db.models import DocumentRow
from context_lens.services.documents import Document, DocumentInfo


class DocumentRejectedError(Exception):
    """A constraint refused the document, so the schema and this code disagree."""


class DocumentStore:
    # Each method holds a connection only for its own short transaction. /api/ask waits
    # up to a minute for Gemini, and must not keep a connection busy all that time.
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine)

    async def add(self, filename: str, text: str) -> Document:
        document = Document(id=str(uuid4()), filename=filename, text=text)
        row = DocumentRow(
            id=UUID(document.id),
            filename=filename,
            text=text,
            line_count=document.line_count,
        )
        try:
            async with self._sessions.begin() as session:
                session.add(row)
        except IntegrityError as error:
            # hide_parameters doesn't cover this: Postgres itself quotes the failing row
            # in its message, and the traceback would carry that text into the logs.
            raise DocumentRejectedError(error.orig.diag.message_primary) from None
        return document

    async def get(self, document_id: str) -> Document | None:
        try:
            key = UUID(document_id)
        except ValueError:
            # Ids come straight from the API, and this one can't belong to a document.
            return None
        async with self._sessions.begin() as session:
            row = await session.get(DocumentRow, key)
            if row is None:
                return None
            return Document(id=str(row.id), filename=row.filename, text=row.text)

    async def list_all(self) -> list[DocumentInfo]:
        statement = select(
            DocumentRow.id, DocumentRow.filename, DocumentRow.line_count
        ).order_by(DocumentRow.created_at, DocumentRow.id)
        async with self._sessions.begin() as session:
            rows = await session.execute(statement)
            return [
                DocumentInfo(
                    id=str(row.id), filename=row.filename, line_count=row.line_count
                )
                for row in rows
            ]
