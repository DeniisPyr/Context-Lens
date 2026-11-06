import asyncio
from collections.abc import AsyncIterator
from traceback import format_exception

import pytest
from conftest import apply_migrations, run_sql, wait_for_a_blocked_query
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from context_lens.db.dataset_store import DatasetRejectedError, DatasetStore
from context_lens.db.document_store import DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.datasets import (
    Dataset,
    DatasetNameTakenError,
    DatasetNotFoundError,
)
from context_lens.settings import DatabaseSettings

pytestmark = pytest.mark.anyio

PRIVATE_NAME = "private dataset name"
INSERT = text(
    "INSERT INTO datasets (id, name) VALUES (gen_random_uuid(), :name) RETURNING id"
)


@pytest.fixture
async def engine(clean_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(DatabaseSettings())
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> DatasetStore:
    return DatasetStore(engine)


@pytest.fixture
async def broken_store(database: URL) -> AsyncIterator[DatasetStore]:
    # For tests that change the schema, on a database of their own.
    apply_migrations(database)
    engine = create_database_engine(DatabaseSettings())
    yield DatasetStore(engine)
    await engine.dispose()


def assert_no_private_content(error: BaseException) -> None:
    message = "".join(format_exception(error))
    assert "Traceback" in message  # Proves the check is looking at something.
    assert PRIVATE_NAME not in message


async def test_add_returns_what_the_list_finds(store: DatasetStore) -> None:
    first = await store.add("a")
    second = await store.add("b")

    assert first == Dataset(id=first.id, name="a")
    assert await store.list_all() == [first, second]


async def test_second_add_with_a_name_is_refused_by_the_constraint(
    store: DatasetStore,
) -> None:
    first = await store.add(PRIVATE_NAME)

    with pytest.raises(DatasetNameTakenError) as error:
        await store.add(PRIVATE_NAME)

    assert str(error.value) == "A dataset with this name already exists."
    assert_no_private_content(error.value)
    assert await store.list_all() == [first]


async def test_add_waits_for_a_rival_transaction_and_then_loses_to_it(
    store: DatasetStore, clean_database: URL
) -> None:
    # The rival's row isn't visible to anyone until it commits, so no SELECT made before
    # the insert could find it. Only the constraint can stop this one.
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(INSERT, {"name": "Reports"})
        add = asyncio.create_task(store.add("Reports"))
        await wait_for_a_blocked_query(clean_database)
        assert not add.done()

        rival.commit()

    with pytest.raises(DatasetNameTakenError):
        await add
    assert [dataset.name for dataset in await store.list_all()] == ["Reports"]


async def test_add_goes_through_when_the_rival_transaction_rolls_back(
    store: DatasetStore, clean_database: URL
) -> None:
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(INSERT, {"name": "Reports"})
        add = asyncio.create_task(store.add("Reports"))
        await wait_for_a_blocked_query(clean_database)

        rival.rollback()

    dataset = await add
    assert await store.list_all() == [dataset]


async def test_exactly_one_of_two_concurrent_adds_wins(store: DatasetStore) -> None:
    results = await asyncio.gather(
        store.add("Reports"), store.add("Reports"), return_exceptions=True
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DatasetNameTakenError]
    assert len(await store.list_all()) == 1


@pytest.mark.parametrize(
    "constraint",
    [
        "ALTER TABLE datasets ADD CONSTRAINT refuse_all CHECK (false)",
        "ALTER TABLE datasets ADD COLUMN added_later text NOT NULL",
    ],
    ids=["check", "not_null"],
)
async def test_any_other_refusal_keeps_the_name_out_of_the_error(
    broken_store: DatasetStore, database: URL, constraint: str
) -> None:
    # Postgres quotes the failing row in these messages, which hide_parameters can't hide.
    run_sql(database, constraint)

    with pytest.raises(DatasetRejectedError, match="violates") as error:
        await broken_store.add(PRIVATE_NAME)

    assert_no_private_content(error.value)
    assert await broken_store.list_all() == []


async def test_every_method_gives_its_connection_back(
    store: DatasetStore, engine: AsyncEngine
) -> None:
    await store.add("a")
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNameTakenError):
        await store.add("a")
    assert engine.pool.checkedout() == 0

    await store.list_all()
    assert engine.pool.checkedout() == 0

    dataset = await store.add("b")
    await store.delete(dataset.id)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.delete(dataset.id)
    assert engine.pool.checkedout() == 0


async def test_delete_removes_only_that_dataset(store: DatasetStore) -> None:
    kept = await store.add("Kept")
    deleted = await store.add("Deleted")

    await store.delete(deleted.id)

    assert await store.list_all() == [kept]


async def test_delete_takes_the_datasets_documents_with_it_and_no_others(
    store: DatasetStore, engine: AsyncEngine
) -> None:
    documents = DocumentStore(engine)
    kept, deleted = await store.add("Kept"), await store.add("Deleted")
    theirs = await documents.add(kept.id, "a.txt", "theirs\n")
    mine = [
        await documents.add(deleted.id, name, "mine\n") for name in ["a.txt", "b.txt"]
    ]

    await store.delete(deleted.id)

    assert [await documents.get(document.id) for document in mine] == [None, None]
    assert await documents.get(theirs.id) == theirs


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_delete_refuses_an_unknown_dataset(
    store: DatasetStore, unknown: str
) -> None:
    dataset = await store.add("Reports")

    with pytest.raises(DatasetNotFoundError) as error:
        await store.delete(unknown)

    assert str(error.value) == "Dataset not found."
    assert await store.list_all() == [dataset]


async def test_delete_refuses_a_dataset_it_has_already_deleted(
    store: DatasetStore,
) -> None:
    dataset = await store.add("Reports")
    await store.delete(dataset.id)

    with pytest.raises(DatasetNotFoundError):
        await store.delete(dataset.id)


async def test_exactly_one_of_two_concurrent_deletes_wins(store: DatasetStore) -> None:
    dataset = await store.add("Reports")

    results = await asyncio.gather(
        store.delete(dataset.id), store.delete(dataset.id), return_exceptions=True
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DatasetNotFoundError]
    assert await store.list_all() == []


async def test_delete_leaves_the_documents_to_postgres(
    store: DatasetStore, engine: AsyncEngine
) -> None:
    # The cascade deletes them without the app reading a single row, text included.
    dataset = await store.add("Reports")
    await DocumentStore(engine).add(dataset.id, "a.txt", "one\n")
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.delete(dataset.id)

    [statement] = [s for s in statements if "datasets" in s or "documents" in s]
    assert statement.startswith("DELETE FROM datasets")


async def test_delete_of_a_bad_id_does_not_need_a_connection(
    store: DatasetStore, engine: AsyncEngine
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.delete("not-a-uuid")

    assert engine.pool.checkedin() == 0
