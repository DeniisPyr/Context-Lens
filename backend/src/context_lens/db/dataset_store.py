from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from context_lens.db.ids import parse_id
from context_lens.db.models import DatasetRow
from context_lens.services.datasets import (
    Dataset,
    DatasetNameTakenError,
    DatasetNotFoundError,
)

NAME_CONSTRAINT = "uq_datasets_name"


class DatasetRejectedError(Exception):
    """A constraint refused the dataset, so the schema and this code disagree."""


class DatasetStore:
    # As in DocumentStore, each method holds a connection only for its own transaction.
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine)

    async def add(self, name: str) -> Dataset:
        dataset = Dataset(id=str(uuid4()), name=name)
        row = DatasetRow(id=UUID(dataset.id), name=name)
        try:
            async with self._sessions.begin() as session:
                session.add(row)
        except IntegrityError as error:
            # The constraint decides rather than a SELECT beforehand, so that two requests
            # racing for one name can't both succeed. As in DocumentStore.add, the original
            # error stays out of the chain because Postgres quotes the failing row in it.
            diagnostics = error.orig.diag
            if diagnostics.constraint_name == NAME_CONSTRAINT:
                raise DatasetNameTakenError from None
            raise DatasetRejectedError(diagnostics.message_primary) from None
        return dataset

    async def list_all(self) -> list[Dataset]:
        statement = select(DatasetRow.id, DatasetRow.name).order_by(
            DatasetRow.created_at, DatasetRow.id
        )
        async with self._sessions.begin() as session:
            rows = await session.execute(statement)
            return [Dataset(id=str(row.id), name=row.name) for row in rows]

    async def delete(self, dataset_id: str) -> None:
        key = parse_id(dataset_id)
        if key is None:
            raise DatasetNotFoundError
        # As in DocumentStore.delete, RETURNING tells a deleted row from a missing one.
        statement = (
            delete(DatasetRow).where(DatasetRow.id == key).returning(DatasetRow.id)
        )
        async with self._sessions.begin() as session:
            # Postgres deletes the dataset's documents in the same transaction, through
            # ON DELETE CASCADE on their foreign key, so none can be left behind.
            deleted = (await session.execute(statement)).scalar_one_or_none()
        if deleted is None:
            raise DatasetNotFoundError
