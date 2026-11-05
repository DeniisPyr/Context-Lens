import asyncio
from collections.abc import AsyncIterator
from traceback import format_exception
from uuid import UUID, uuid4

import pytest
from conftest import apply_migrations, run_sql, wait_for_a_blocked_query
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentRejectedError, DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.datasets import DatasetNotFoundError
from context_lens.services.documents import (
    Document,
    DocumentInfo,
    DocumentNotFoundError,
    DuplicateDocumentError,
)
from context_lens.settings import DatabaseSettings

pytestmark = pytest.mark.anyio

PRIVATE_NAME = "private-name.txt"
PRIVATE_LINES = ["private first line", "private second line"]
PRIVATE_TEXT = "\n".join(PRIVATE_LINES)


@pytest.fixture
async def engine(clean_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(DatabaseSettings())
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> DocumentStore:
    return DocumentStore(engine)


@pytest.fixture
async def dataset_id(engine: AsyncEngine) -> str:
    return (await DatasetStore(engine).add("Reports")).id


@pytest.fixture
async def broken_engine(database: URL) -> AsyncIterator[AsyncEngine]:
    # For tests that change the schema, on a database of their own.
    apply_migrations(database)
    engine = create_database_engine(DatabaseSettings())
    yield engine
    await engine.dispose()


@pytest.fixture
def broken_store(broken_engine: AsyncEngine) -> DocumentStore:
    return DocumentStore(broken_engine)


@pytest.fixture
async def broken_dataset_id(broken_engine: AsyncEngine) -> str:
    return (await DatasetStore(broken_engine).add("Reports")).id


async def test_get_finds_known_ids_and_returns_none_for_unknown_ones(
    store: DocumentStore, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "notes.txt", "hello\n")

    assert await store.get(document.id) == document
    assert await store.get("00000000-0000-0000-0000-000000000000") is None
    assert await store.get("unknown") is None


async def test_list_in_dataset_returns_the_documents_without_their_text(
    store: DocumentStore, dataset_id: str
) -> None:
    first = await store.add(dataset_id, "a.txt", "one\n")
    second = await store.add(dataset_id, "b.txt", "one\ntwo\n")

    assert await store.list_in_dataset(dataset_id) == [
        DocumentInfo(id=first.id, filename="a.txt", line_count=1),
        DocumentInfo(id=second.id, filename="b.txt", line_count=2),
    ]


async def test_list_in_dataset_holds_only_that_datasets_documents(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    other = await DatasetStore(engine).add("Other")
    mine = await store.add(dataset_id, "a.txt", "mine\n")
    theirs = await store.add(other.id, "a.txt", "theirs\n")

    [listed_mine] = await store.list_in_dataset(dataset_id)
    [listed_theirs] = await store.list_in_dataset(other.id)

    assert listed_mine.id == mine.id
    assert listed_theirs.id == theirs.id


async def test_list_in_dataset_of_an_empty_dataset_is_empty(
    store: DocumentStore, dataset_id: str
) -> None:
    assert await store.list_in_dataset(dataset_id) == []


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_list_in_dataset_refuses_an_unknown_dataset(
    store: DocumentStore, unknown: str
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.list_in_dataset(unknown)


async def test_list_in_dataset_does_not_select_the_text(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    await store.add(dataset_id, "a.txt", "one\n")
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.list_in_dataset(dataset_id)

    [select] = [s for s in statements if "FROM documents" in s]
    assert "documents.line_count" in select
    assert "documents.text" not in select


async def test_get_does_not_need_a_connection_for_a_bad_id(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    assert await store.get("not-a-uuid") is None

    assert engine.pool.checkedin() == 0


async def test_bad_dataset_id_does_not_need_a_connection(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.add("not-a-uuid", "a.txt", "one\n")
    with pytest.raises(DatasetNotFoundError):
        await store.list_in_dataset("not-a-uuid")

    assert engine.pool.checkedin() == 0


async def test_every_method_gives_its_connection_back(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n")
    assert engine.pool.checkedout() == 0

    await store.get(document.id)
    assert engine.pool.checkedout() == 0

    await store.get("00000000-0000-0000-0000-000000000000")
    assert engine.pool.checkedout() == 0

    await store.list_in_dataset(dataset_id)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DuplicateDocumentError):
        await store.add(dataset_id, "a.txt", "one\n")
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.add(str(uuid4()), "a.txt", "one\n")
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.list_in_dataset(str(uuid4()))
    assert engine.pool.checkedout() == 0

    await store.delete(document.id)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DocumentNotFoundError):
        await store.delete(document.id)
    assert engine.pool.checkedout() == 0

    assert engine.pool.checkedin() == 1


def assert_no_text(error: BaseException) -> None:
    message = "".join(format_exception(error))
    assert "Traceback" in message  # Proves the check is looking at something.
    for private in PRIVATE_LINES:
        assert private not in message
    # Postgres's own error isn't chained on, so nothing it quotes can reach the logs.
    assert "IntegrityError" not in message


def assert_no_private_content(error: BaseException) -> None:
    assert_no_text(error)
    assert PRIVATE_NAME not in "".join(format_exception(error))


@pytest.mark.parametrize(
    "constraint",
    [
        "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)",
        "ALTER TABLE documents ADD COLUMN added_later text NOT NULL",
    ],
    ids=["check", "not_null"],
)
async def test_refused_write_keeps_the_text_out_of_the_error(
    broken_store: DocumentStore,
    broken_dataset_id: str,
    database: URL,
    constraint: str,
) -> None:
    # Postgres quotes the failing row in these messages, which hide_parameters can't
    # hide.
    run_sql(database, constraint)

    with pytest.raises(DocumentRejectedError, match="violates") as error:
        await broken_store.add(broken_dataset_id, PRIVATE_NAME, PRIVATE_TEXT)

    assert_no_private_content(error.value)


async def test_failed_write_keeps_the_text_out_of_the_error(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    run_sql(database, "DROP TABLE documents")

    with pytest.raises(ProgrammingError, match="documents") as error:
        await broken_store.add(broken_dataset_id, PRIVATE_NAME, PRIVATE_TEXT)

    assert_no_private_content(error.value)


async def test_refused_write_stores_nothing(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    run_sql(database, "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)")

    with pytest.raises(DocumentRejectedError):
        await broken_store.add(broken_dataset_id, "notes.txt", PRIVATE_TEXT)

    assert await broken_store.list_in_dataset(broken_dataset_id) == []


async def test_unknown_dataset_is_refused_by_the_foreign_key_without_the_text(
    store: DocumentStore,
) -> None:
    with pytest.raises(DatasetNotFoundError) as error:
        await store.add(str(uuid4()), PRIVATE_NAME, PRIVATE_TEXT)

    assert str(error.value) == "Dataset not found."
    assert_no_private_content(error.value)


async def test_filename_taken_in_the_dataset_is_refused_without_the_text(
    store: DocumentStore, dataset_id: str
) -> None:
    first = await store.add(dataset_id, PRIVATE_NAME, "first version\n")

    with pytest.raises(DuplicateDocumentError) as error:
        await store.add(dataset_id, PRIVATE_NAME, PRIVATE_TEXT)

    # The message names the file, which the person uploading it just sent.
    assert str(error.value) == f"{PRIVATE_NAME} is already in this dataset."
    assert_no_text(error.value)
    assert await store.get(first.id) == first
    assert [d.id for d in await store.list_in_dataset(dataset_id)] == [first.id]


INSERT = text(
    "INSERT INTO documents (id, dataset_id, filename, text, line_count) "
    "VALUES (gen_random_uuid(), :dataset_id, 'notes.txt', 'rival', 1)"
)


async def test_add_waits_for_a_rival_transaction_and_then_loses_to_it(
    store: DocumentStore, clean_database: URL, dataset_id: str
) -> None:
    # The rival's row isn't visible to anyone until it commits, so no SELECT made before
    # the insert could find it. Only the constraint can stop this one.
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(INSERT, {"dataset_id": dataset_id})
        add = asyncio.create_task(store.add(dataset_id, "notes.txt", PRIVATE_TEXT))
        await wait_for_a_blocked_query(clean_database)
        assert not add.done()

        rival.commit()

    with pytest.raises(DuplicateDocumentError) as error:
        await add
    assert_no_text(error.value)
    assert len(await store.list_in_dataset(dataset_id)) == 1


async def test_add_goes_through_when_the_rival_transaction_rolls_back(
    store: DocumentStore, clean_database: URL, dataset_id: str
) -> None:
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(INSERT, {"dataset_id": dataset_id})
        add = asyncio.create_task(store.add(dataset_id, "notes.txt", PRIVATE_TEXT))
        await wait_for_a_blocked_query(clean_database)

        rival.rollback()

    document = await add
    assert [d.id for d in await store.list_in_dataset(dataset_id)] == [document.id]


async def test_exactly_one_of_two_concurrent_adds_wins(
    store: DocumentStore, dataset_id: str
) -> None:
    results = await asyncio.gather(
        store.add(dataset_id, "notes.txt", "one\n"),
        store.add(dataset_id, "notes.txt", "two\n"),
        return_exceptions=True,
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DuplicateDocumentError]
    assert len(await store.list_in_dataset(dataset_id)) == 1


async def test_store_does_not_change_the_text(
    store: DocumentStore, dataset_id: str
) -> None:
    text_with_oddities = "a\r\n\x0cb č\n\n"

    document = await store.add(dataset_id, "notes.txt", text_with_oddities)

    assert document == Document(
        id=document.id, filename="notes.txt", text=text_with_oddities
    )
    assert await store.get(document.id) == document


async def test_delete_removes_only_that_document(
    store: DocumentStore, dataset_id: str
) -> None:
    kept = await store.add(dataset_id, "kept.txt", "kept\n")
    deleted = await store.add(dataset_id, "gone.txt", "gone\n")

    await store.delete(deleted.id)

    assert await store.get(deleted.id) is None
    assert await store.get(kept.id) == kept


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_delete_refuses_an_unknown_document(
    store: DocumentStore, dataset_id: str, unknown: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n")

    with pytest.raises(DocumentNotFoundError) as error:
        await store.delete(unknown)

    assert str(error.value) == "Document not found."
    assert await store.get(document.id) == document


async def test_delete_refuses_a_document_it_has_already_deleted(
    store: DocumentStore, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n")
    await store.delete(document.id)

    with pytest.raises(DocumentNotFoundError):
        await store.delete(document.id)


async def test_exactly_one_of_two_concurrent_deletes_wins(
    store: DocumentStore, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n")

    results = await asyncio.gather(
        store.delete(document.id), store.delete(document.id), return_exceptions=True
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DocumentNotFoundError]
    assert await store.get(document.id) is None


async def test_delete_waits_for_a_rival_delete_and_then_finds_nothing(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    # A SELECT made before deleting would still find the row the rival is deleting, so
    # only the delete's own result can tell that it was already gone.
    document = await store.add(dataset_id, "a.txt", "one\n")
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(
            text("DELETE FROM documents WHERE id = :id"), {"id": UUID(document.id)}
        )
        deletion = asyncio.create_task(store.delete(document.id))
        await wait_for_a_blocked_query(clean_database)

        rival.commit()

    with pytest.raises(DocumentNotFoundError):
        await deletion


async def test_delete_does_not_read_the_text(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", PRIVATE_TEXT)
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.delete(document.id)

    [statement] = [s for s in statements if "documents" in s]
    assert statement.startswith("DELETE FROM documents")
    assert "documents.text" not in statement


async def test_delete_of_a_bad_id_does_not_need_a_connection(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    with pytest.raises(DocumentNotFoundError):
        await store.delete("not-a-uuid")

    assert engine.pool.checkedin() == 0
