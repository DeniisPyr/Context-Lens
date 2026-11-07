import asyncio
from collections.abc import AsyncIterator
from traceback import format_exception
from uuid import UUID, uuid4

import pytest
from conftest import (
    MAX_DOCUMENTS,
    NO_CHUNKS,
    apply_migrations,
    fake_embedding,
    run_sql,
    stored_chunks,
    wait_for_a_blocked_query,
)
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentRejectedError, DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.datasets import DatasetFullError, DatasetNotFoundError
from context_lens.services.documents import (
    Document,
    DocumentInfo,
    DocumentNotFoundError,
    DuplicateDocumentError,
)
from context_lens.services.indexing import AlreadyIndexedError, EmbeddedChunk
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
    document = await store.add(
        dataset_id, "notes.txt", "hello\n", NO_CHUNKS, MAX_DOCUMENTS
    )

    assert await store.get(document.id) == document
    assert await store.get("00000000-0000-0000-0000-000000000000") is None
    assert await store.get("unknown") is None


async def test_get_many_finds_only_the_documents_asked_for(
    store: DocumentStore, dataset_id: str
) -> None:
    first = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.add(dataset_id, "b.txt", "two\n", NO_CHUNKS, MAX_DOCUMENTS)
    third = await store.add(dataset_id, "c.txt", "three\n", NO_CHUNKS, MAX_DOCUMENTS)

    found = await store.get_many([third.id, first.id])

    assert sorted(found, key=lambda document: document.filename) == [first, third]


async def test_get_many_leaves_out_unknown_bad_and_deleted_ids(
    store: DocumentStore, dataset_id: str
) -> None:
    kept = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    deleted = await store.add(dataset_id, "b.txt", "two\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.delete(deleted.id)

    found = await store.get_many(
        [kept.id, deleted.id, str(uuid4()), "not-a-uuid", "", "\x00"]
    )

    assert found == [kept]


async def test_get_many_of_no_good_ids_does_not_need_a_connection(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    assert await store.get_many([]) == []
    assert await store.get_many(["not-a-uuid", ""]) == []

    assert engine.pool.checkedin() == 0


async def test_list_in_dataset_returns_the_documents_without_their_text(
    store: DocumentStore, dataset_id: str
) -> None:
    first = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    second = await store.add(
        dataset_id, "b.txt", "one\ntwo\n", NO_CHUNKS, MAX_DOCUMENTS
    )

    assert await store.list_in_dataset(dataset_id) == [
        DocumentInfo(id=first.id, filename="a.txt", line_count=1),
        DocumentInfo(id=second.id, filename="b.txt", line_count=2),
    ]


async def test_list_in_dataset_holds_only_that_datasets_documents(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    other = await DatasetStore(engine).add("Other")
    mine = await store.add(dataset_id, "a.txt", "mine\n", NO_CHUNKS, MAX_DOCUMENTS)
    theirs = await store.add(other.id, "a.txt", "theirs\n", NO_CHUNKS, MAX_DOCUMENTS)

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
    await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
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
        await store.check_can_add("not-a-uuid", "a.txt", MAX_DOCUMENTS)
    with pytest.raises(DatasetNotFoundError):
        await store.add("not-a-uuid", "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    with pytest.raises(DatasetNotFoundError):
        await store.list_in_dataset("not-a-uuid")

    assert engine.pool.checkedin() == 0


async def test_every_method_gives_its_connection_back(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    assert engine.pool.checkedout() == 0

    await store.check_can_add(dataset_id, "b.txt", MAX_DOCUMENTS)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DuplicateDocumentError):
        await store.check_can_add(dataset_id, "a.txt", MAX_DOCUMENTS)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.check_can_add(str(uuid4()), "a.txt", MAX_DOCUMENTS)
    assert engine.pool.checkedout() == 0

    await store.get(document.id)
    assert engine.pool.checkedout() == 0

    await store.get("00000000-0000-0000-0000-000000000000")
    assert engine.pool.checkedout() == 0

    await store.get_many([document.id, str(uuid4())])
    assert engine.pool.checkedout() == 0

    await store.list_in_dataset(dataset_id)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DuplicateDocumentError):
        await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.add(str(uuid4()), "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
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
        await broken_store.add(
            broken_dataset_id, PRIVATE_NAME, PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
        )

    assert_no_private_content(error.value)


async def test_failed_write_keeps_the_text_out_of_the_error(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    run_sql(database, "DROP TABLE documents CASCADE")

    with pytest.raises(ProgrammingError, match="documents") as error:
        await broken_store.add(
            broken_dataset_id, PRIVATE_NAME, PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
        )

    assert_no_private_content(error.value)


async def test_refused_write_stores_nothing(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    run_sql(database, "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)")

    with pytest.raises(DocumentRejectedError):
        await broken_store.add(
            broken_dataset_id, "notes.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
        )

    assert await broken_store.list_in_dataset(broken_dataset_id) == []


async def test_unknown_dataset_is_refused_by_the_foreign_key_without_the_text(
    store: DocumentStore,
) -> None:
    with pytest.raises(DatasetNotFoundError) as error:
        await store.add(
            str(uuid4()), PRIVATE_NAME, PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
        )

    assert str(error.value) == "Dataset not found."
    assert_no_private_content(error.value)


async def test_filename_taken_in_the_dataset_is_refused_without_the_text(
    store: DocumentStore, dataset_id: str
) -> None:
    first = await store.add(
        dataset_id, PRIVATE_NAME, "first version\n", NO_CHUNKS, MAX_DOCUMENTS
    )

    with pytest.raises(DuplicateDocumentError) as error:
        await store.add(
            dataset_id, PRIVATE_NAME, PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
        )

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
        add = asyncio.create_task(
            store.add(dataset_id, "notes.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS)
        )
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
        add = asyncio.create_task(
            store.add(dataset_id, "notes.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS)
        )
        await wait_for_a_blocked_query(clean_database)

        rival.rollback()

    document = await add
    assert [d.id for d in await store.list_in_dataset(dataset_id)] == [document.id]


async def test_exactly_one_of_two_concurrent_adds_wins(
    store: DocumentStore, dataset_id: str
) -> None:
    results = await asyncio.gather(
        store.add(dataset_id, "notes.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS),
        store.add(dataset_id, "notes.txt", "two\n", NO_CHUNKS, MAX_DOCUMENTS),
        return_exceptions=True,
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DuplicateDocumentError]
    assert len(await store.list_in_dataset(dataset_id)) == 1


async def test_store_does_not_change_the_text(
    store: DocumentStore, dataset_id: str
) -> None:
    text_with_oddities = "a\r\n\x0cb č\n\n"

    document = await store.add(
        dataset_id, "notes.txt", text_with_oddities, NO_CHUNKS, MAX_DOCUMENTS
    )

    assert document == Document(
        id=document.id, filename="notes.txt", text=text_with_oddities
    )
    assert await store.get(document.id) == document


async def test_delete_removes_only_that_document(
    store: DocumentStore, dataset_id: str
) -> None:
    kept = await store.add(dataset_id, "kept.txt", "kept\n", NO_CHUNKS, MAX_DOCUMENTS)
    deleted = await store.add(
        dataset_id, "gone.txt", "gone\n", NO_CHUNKS, MAX_DOCUMENTS
    )

    await store.delete(deleted.id)

    assert await store.get(deleted.id) is None
    assert await store.get(kept.id) == kept


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_delete_refuses_an_unknown_document(
    store: DocumentStore, dataset_id: str, unknown: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)

    with pytest.raises(DocumentNotFoundError) as error:
        await store.delete(unknown)

    assert str(error.value) == "Document not found."
    assert await store.get(document.id) == document


async def test_delete_refuses_a_document_it_has_already_deleted(
    store: DocumentStore, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.delete(document.id)

    with pytest.raises(DocumentNotFoundError):
        await store.delete(document.id)


async def test_exactly_one_of_two_concurrent_deletes_wins(
    store: DocumentStore, dataset_id: str
) -> None:
    document = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)

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
    document = await store.add(dataset_id, "a.txt", "one\n", NO_CHUNKS, MAX_DOCUMENTS)
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
    document = await store.add(
        dataset_id, "a.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
    )
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


def chunks_of(*texts: str) -> list[EmbeddedChunk]:
    # One line each: the store keeps whatever lines it's given.
    return [
        EmbeddedChunk(number, number, text, fake_embedding(text))
        for number, text in enumerate(texts, start=1)
    ]


def positions_of(url: URL, document_id: str) -> list[int]:
    query = text(
        "SELECT position FROM chunks WHERE document_id = :id ORDER BY position"
    )
    with create_engine(url, poolclass=NullPool).connect() as connection:
        return list(connection.scalars(query, {"id": UUID(document_id)}))


async def test_add_stores_the_chunks_with_the_document_in_their_order(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    chunks = [
        EmbeddedChunk(1, 2, "Příliš žluťoučký\nkůň", fake_embedding("first")),
        EmbeddedChunk(4, 4, "úpěl ďábelské ódy", fake_embedding("second")),
    ]

    document = await store.add(
        dataset_id,
        "a.txt",
        "Příliš žluťoučký\nkůň\n\núpěl ďábelské ódy\n",
        chunks,
        MAX_DOCUMENTS,
    )

    assert stored_chunks(clean_database, document.id) == chunks
    assert positions_of(clean_database, document.id) == [0, 1]


async def test_chunks_of_each_document_are_their_own(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    first = await store.add(dataset_id, "a.txt", "a\n", chunks_of("a"), MAX_DOCUMENTS)
    second = await store.add(
        dataset_id, "b.txt", "b\nc\n", chunks_of("b", "c"), MAX_DOCUMENTS
    )

    assert stored_chunks(clean_database, first.id) == chunks_of("a")
    assert stored_chunks(clean_database, second.id) == chunks_of("b", "c")
    assert positions_of(clean_database, second.id) == [0, 1]


async def test_refused_chunk_stores_neither_it_nor_the_document(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    run_sql(database, "ALTER TABLE chunks ADD CONSTRAINT refuse_all CHECK (false)")

    with pytest.raises(DocumentRejectedError, match="chunks") as error:
        await broken_store.add(
            broken_dataset_id,
            PRIVATE_NAME,
            PRIVATE_TEXT,
            chunks_of(*PRIVATE_LINES),
            MAX_DOCUMENTS,
        )

    # Postgres quotes the failing row, the chunk's text and embedding, in its message.
    assert_no_private_content(error.value)
    assert await broken_store.list_in_dataset(broken_dataset_id) == []
    with create_engine(database, poolclass=NullPool).connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM chunks")) == 0


async def test_deleting_a_document_deletes_its_chunks(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    kept = await store.add(dataset_id, "kept.txt", "a\n", chunks_of("a"), MAX_DOCUMENTS)
    deleted = await store.add(
        dataset_id, "gone.txt", "b\n", chunks_of("b"), MAX_DOCUMENTS
    )

    await store.delete(deleted.id)

    assert stored_chunks(clean_database, deleted.id) == []
    assert stored_chunks(clean_database, kept.id) == chunks_of("a")


async def test_check_can_add_lets_a_new_filename_through(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    other = await DatasetStore(engine).add("Other")
    await store.add(other.id, "a.txt", "theirs\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.add(dataset_id, "b.txt", "mine\n", NO_CHUNKS, MAX_DOCUMENTS)

    await store.check_can_add(dataset_id, "a.txt", MAX_DOCUMENTS)
    await store.check_can_add(dataset_id, "B.txt", MAX_DOCUMENTS)


async def test_check_can_add_refuses_a_filename_taken_in_the_dataset(
    store: DocumentStore, dataset_id: str
) -> None:
    await store.add(dataset_id, PRIVATE_NAME, PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS)

    with pytest.raises(DuplicateDocumentError) as error:
        await store.check_can_add(dataset_id, PRIVATE_NAME, MAX_DOCUMENTS)

    assert str(error.value) == f"{PRIVATE_NAME} is already in this dataset."
    assert_no_text(error.value)


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_check_can_add_refuses_an_unknown_dataset(
    store: DocumentStore, unknown: str
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.check_can_add(unknown, "a.txt", MAX_DOCUMENTS)


async def test_check_can_add_refuses_a_deleted_dataset(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    await DatasetStore(engine).delete(dataset_id)

    with pytest.raises(DatasetNotFoundError):
        await store.check_can_add(dataset_id, "a.txt", MAX_DOCUMENTS)


async def test_check_can_add_does_not_read_the_text_or_write(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    await store.add(dataset_id, "a.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS)
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.check_can_add(dataset_id, "b.txt", MAX_DOCUMENTS)

    reads = [s for s in statements if "FROM documents" in s]
    assert reads  # Proves the listener saw them.
    assert not [read for read in reads if "documents.text" in read]
    assert all(s.startswith("SELECT") for s in statements)


async def add_documents(store: DocumentStore, dataset_id: str, count: int) -> list[str]:
    documents = [
        await store.add(dataset_id, f"{number}.txt", "a\n", NO_CHUNKS, MAX_DOCUMENTS)
        for number in range(count)
    ]
    return [document.id for document in documents]


async def test_add_refuses_a_document_past_the_limit(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    await add_documents(store, dataset_id, 2)

    with pytest.raises(DatasetFullError) as error:
        await store.add(dataset_id, "c.txt", "c\n", chunks_of("c"), 2)

    assert (
        str(error.value)
        == "This dataset already has 2 documents, the most it can hold."
    )
    assert len(await store.list_in_dataset(dataset_id)) == 2
    with create_engine(clean_database, poolclass=NullPool).connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM chunks")) == 0


async def test_add_accepts_the_last_document_that_fits(
    store: DocumentStore, dataset_id: str
) -> None:
    await add_documents(store, dataset_id, 2)

    await store.add(dataset_id, "c.txt", "c\n", NO_CHUNKS, 3)

    assert len(await store.list_in_dataset(dataset_id)) == 3


async def test_check_can_add_refuses_a_full_dataset(
    store: DocumentStore, dataset_id: str
) -> None:
    await add_documents(store, dataset_id, 2)

    await store.check_can_add(dataset_id, "c.txt", 3)
    with pytest.raises(DatasetFullError, match="already has 2 documents"):
        await store.check_can_add(dataset_id, "c.txt", 2)


async def test_full_dataset_is_refused_before_the_filename_is_compared(
    store: DocumentStore, dataset_id: str
) -> None:
    # As in add, where the count comes before the constraint on filenames.
    await add_documents(store, dataset_id, 1)

    with pytest.raises(DatasetFullError):
        await store.check_can_add(dataset_id, "0.txt", 1)
    with pytest.raises(DatasetFullError):
        await store.add(dataset_id, "0.txt", "a\n", NO_CHUNKS, 1)


async def test_limit_counts_only_the_documents_of_that_dataset(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    other = await DatasetStore(engine).add("Other")
    await add_documents(store, other.id, 2)

    await store.check_can_add(dataset_id, "a.txt", 2)
    await store.add(dataset_id, "a.txt", "a\n", NO_CHUNKS, 2)


async def test_deleting_a_document_makes_room_for_another(
    store: DocumentStore, dataset_id: str
) -> None:
    [first, _] = await add_documents(store, dataset_id, 2)

    await store.delete(first)

    await store.check_can_add(dataset_id, "c.txt", 2)
    await store.add(dataset_id, "c.txt", "c\n", NO_CHUNKS, 2)


LOCK_DATASET = text("SELECT id FROM datasets WHERE id = :dataset_id FOR UPDATE")


async def test_add_waits_for_a_rival_upload_into_the_dataset_and_then_finds_it_full(
    store: DocumentStore, clean_database: URL, dataset_id: str
) -> None:
    # The rival's document isn't visible until it commits, so without the lock a count
    # would still find room for this one too.
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(LOCK_DATASET, {"dataset_id": dataset_id})
        rival.execute(INSERT, {"dataset_id": dataset_id})
        add = asyncio.create_task(
            store.add(dataset_id, "mine.txt", "mine\n", chunks_of("mine"), 1)
        )
        await wait_for_a_blocked_query(clean_database)
        assert not add.done()

        rival.commit()

    with pytest.raises(DatasetFullError):
        await add
    assert [d.filename for d in await store.list_in_dataset(dataset_id)] == [
        "notes.txt"
    ]


async def test_add_goes_through_when_the_rival_upload_rolls_back(
    store: DocumentStore, clean_database: URL, dataset_id: str
) -> None:
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(LOCK_DATASET, {"dataset_id": dataset_id})
        rival.execute(INSERT, {"dataset_id": dataset_id})
        add = asyncio.create_task(
            store.add(dataset_id, "mine.txt", "mine\n", NO_CHUNKS, 1)
        )
        await wait_for_a_blocked_query(clean_database)

        rival.rollback()

    document = await add
    assert [d.id for d in await store.list_in_dataset(dataset_id)] == [document.id]


@pytest.mark.parametrize("racing", [2, 8])
async def test_concurrent_adds_into_a_dataset_with_room_for_one_store_exactly_one(
    store: DocumentStore, dataset_id: str, racing: int
) -> None:
    await add_documents(store, dataset_id, 2)

    results = await asyncio.gather(
        *(
            store.add(dataset_id, f"new {number}.txt", "a\n", chunks_of("a"), 3)
            for number in range(racing)
        ),
        return_exceptions=True,
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert [type(error) for error in errors] == [DatasetFullError] * (racing - 1)
    assert len(await store.list_in_dataset(dataset_id)) == 3


async def test_ids_without_chunks_are_the_documents_without_any_oldest_first(
    store: DocumentStore, engine: AsyncEngine, dataset_id: str, clean_database: URL
) -> None:
    other = await DatasetStore(engine).add("Other")
    newer = await store.add(dataset_id, "newer.txt", "a\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.add(dataset_id, "indexed.txt", "b\n", chunks_of("b"), MAX_DOCUMENTS)
    older = await store.add(other.id, "older.txt", "c\n", NO_CHUNKS, MAX_DOCUMENTS)
    run_sql(
        clean_database,
        "UPDATE documents SET created_at = created_at - interval '1 day' "
        f"WHERE id = '{older.id}'",
    )

    assert await store.ids_without_chunks() == [older.id, newer.id]


async def test_ids_without_chunks_of_an_empty_database_are_none(
    store: DocumentStore,
) -> None:
    assert await store.ids_without_chunks() == []


async def test_add_chunks_gives_a_document_its_chunks(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    document = await store.add(dataset_id, "a.txt", "a\nb\n", NO_CHUNKS, MAX_DOCUMENTS)

    await store.add_chunks(document.id, chunks_of("a", "b"))

    assert stored_chunks(clean_database, document.id) == chunks_of("a", "b")
    assert positions_of(clean_database, document.id) == [0, 1]
    assert await store.ids_without_chunks() == []


@pytest.mark.parametrize(
    "unknown", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_add_chunks_refuses_an_unknown_document_without_the_text(
    store: DocumentStore, unknown: str
) -> None:
    with pytest.raises(DocumentNotFoundError) as error:
        await store.add_chunks(unknown, chunks_of(*PRIVATE_LINES))

    assert_no_private_content(error.value)


async def test_add_chunks_refuses_a_deleted_document(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    document = await store.add(dataset_id, "a.txt", "a\n", NO_CHUNKS, MAX_DOCUMENTS)
    await store.delete(document.id)

    with pytest.raises(DocumentNotFoundError):
        await store.add_chunks(document.id, chunks_of("a"))

    assert stored_chunks(clean_database, document.id) == []


async def test_add_chunks_refuses_a_document_that_has_chunks_already(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    document = await store.add(
        dataset_id, "a.txt", "a\n", chunks_of("first"), MAX_DOCUMENTS
    )

    with pytest.raises(AlreadyIndexedError) as error:
        await store.add_chunks(document.id, chunks_of(*PRIVATE_LINES))

    assert_no_text(error.value)
    assert stored_chunks(clean_database, document.id) == chunks_of("first")


async def test_add_chunks_waits_for_a_rival_run_and_then_loses_to_it(
    store: DocumentStore, dataset_id: str, clean_database: URL
) -> None:
    document = await store.add(dataset_id, "a.txt", "a\n", NO_CHUNKS, MAX_DOCUMENTS)
    engine = create_engine(clean_database, poolclass=NullPool)
    with engine.connect() as rival:
        rival.execute(
            text("INSERT INTO chunks VALUES (:id, 0, 1, 1, 'rival', :embedding)"),
            {"id": UUID(document.id), "embedding": str(fake_embedding("rival"))},
        )
        add = asyncio.create_task(store.add_chunks(document.id, chunks_of("mine")))
        await wait_for_a_blocked_query(clean_database)
        assert not add.done()

        rival.commit()

    with pytest.raises(AlreadyIndexedError):
        await add
    assert [chunk.text for chunk in stored_chunks(clean_database, document.id)] == [
        "rival"
    ]


async def test_refused_chunks_keep_the_text_out_of_the_error(
    broken_store: DocumentStore, broken_dataset_id: str, database: URL
) -> None:
    document = await broken_store.add(
        broken_dataset_id, "a.txt", PRIVATE_TEXT, NO_CHUNKS, MAX_DOCUMENTS
    )
    run_sql(database, "ALTER TABLE chunks ADD CONSTRAINT refuse_all CHECK (false)")

    with pytest.raises(DocumentRejectedError, match="violates") as error:
        await broken_store.add_chunks(document.id, chunks_of(*PRIVATE_LINES))

    assert_no_private_content(error.value)
