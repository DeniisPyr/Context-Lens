from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from context_lens.db.ids import parse_id
from context_lens.db.models import ChunkRow, DatasetRow, DocumentRow
from context_lens.services.datasets import DatasetNotFoundError
from context_lens.services.search import FoundChunk


class ChunkStore:
    # As in DocumentStore, each method holds a connection only for its own transaction.
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine)

    async def search(
        self, dataset_id: str, embedding: list[float], limit: int
    ) -> list[FoundChunk]:
        key = parse_id(dataset_id)
        if key is None:
            raise DatasetNotFoundError
        # No index: every chunk of the dataset is compared, so the nearest are always
        # found, which an approximate index doesn't promise. Ties go by place in the
        # documents, so that the same search always finds the same chunks.
        statement = (
            select(
                ChunkRow.document_id,
                DocumentRow.filename,
                ChunkRow.position,
                ChunkRow.start_line,
                ChunkRow.end_line,
                ChunkRow.text,
            )
            .join(DocumentRow, DocumentRow.id == ChunkRow.document_id)
            .where(DocumentRow.dataset_id == key)
            .order_by(
                ChunkRow.embedding.cosine_distance(embedding),
                ChunkRow.document_id,
                ChunkRow.position,
            )
            .limit(limit)
        )
        async with self._sessions.begin() as session:
            # An empty dataset and a missing one both have no chunks to find.
            if await session.get(DatasetRow, key) is None:
                raise DatasetNotFoundError
            rows = await session.execute(statement)
            return [
                FoundChunk(
                    document_id=str(row.document_id),
                    filename=row.filename,
                    position=row.position,
                    start_line=row.start_line,
                    end_line=row.end_line,
                    text=row.text,
                )
                for row in rows
            ]
