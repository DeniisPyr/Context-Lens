from collections.abc import AsyncIterator
from traceback import format_exception

import pytest
from conftest import apply_migrations, run_sql
from sqlalchemy import URL, event
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from context_lens.db.document_store import DocumentRejectedError, DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.documents import Document, DocumentInfo
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
async def broken_store(database: URL) -> AsyncIterator[DocumentStore]:
    # For tests that change the schema, on a database of their own.
    apply_migrations(database)
    engine = create_database_engine(DatabaseSettings())
    yield DocumentStore(engine)
    await engine.dispose()


async def test_get_finds_known_ids_and_returns_none_for_unknown_ones(
    store: DocumentStore,
) -> None:
    document = await store.add("notes.txt", "hello\n")

    assert await store.get(document.id) == document
    assert await store.get("00000000-0000-0000-0000-000000000000") is None
    assert await store.get("unknown") is None


async def test_list_all_returns_the_documents_without_their_text(
    store: DocumentStore,
) -> None:
    first = await store.add("a.txt", "one\n")
    second = await store.add("b.txt", "one\ntwo\n")

    assert await store.list_all() == [
        DocumentInfo(id=first.id, filename="a.txt", line_count=1),
        DocumentInfo(id=second.id, filename="b.txt", line_count=2),
    ]


async def test_list_all_does_not_select_the_text(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    await store.add("a.txt", "one\n")
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.list_all()

    [select] = [s for s in statements if "FROM documents" in s]
    assert "documents.line_count" in select
    assert "documents.text" not in select


async def test_get_does_not_need_a_connection_for_a_bad_id(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    assert await store.get("not-a-uuid") is None

    assert engine.pool.checkedin() == 0


async def test_every_method_gives_its_connection_back(
    store: DocumentStore, engine: AsyncEngine
) -> None:
    document = await store.add("a.txt", "one\n")
    assert engine.pool.checkedout() == 0

    await store.get(document.id)
    assert engine.pool.checkedout() == 0

    await store.get("00000000-0000-0000-0000-000000000000")
    assert engine.pool.checkedout() == 0

    await store.list_all()
    assert engine.pool.checkedout() == 0

    assert engine.pool.checkedin() == 1


def assert_no_private_content(error: BaseException) -> None:
    message = "".join(format_exception(error))
    assert "Traceback" in message  # Proves the check is looking at something.
    for private in (PRIVATE_NAME, *PRIVATE_LINES):
        assert private not in message


@pytest.mark.parametrize(
    "constraint",
    [
        "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)",
        "ALTER TABLE documents ADD COLUMN added_later text NOT NULL",
    ],
    ids=["check", "not_null"],
)
async def test_refused_write_keeps_the_text_out_of_the_error(
    broken_store: DocumentStore, database: URL, constraint: str
) -> None:
    # Postgres quotes the failing row in these messages, which hide_parameters can't
    # hide.
    run_sql(database, constraint)

    with pytest.raises(DocumentRejectedError, match="violates") as error:
        await broken_store.add(PRIVATE_NAME, PRIVATE_TEXT)

    assert_no_private_content(error.value)


async def test_failed_write_keeps_the_text_out_of_the_error(
    broken_store: DocumentStore, database: URL
) -> None:
    run_sql(database, "DROP TABLE documents")

    with pytest.raises(ProgrammingError, match="documents") as error:
        await broken_store.add(PRIVATE_NAME, PRIVATE_TEXT)

    assert_no_private_content(error.value)


async def test_refused_write_stores_nothing(
    broken_store: DocumentStore, database: URL
) -> None:
    run_sql(database, "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)")

    with pytest.raises(DocumentRejectedError):
        await broken_store.add("notes.txt", PRIVATE_TEXT)

    assert await broken_store.list_all() == []


async def test_store_does_not_change_the_text(store: DocumentStore) -> None:
    text = "a\r\n\x0cb č\n\n"

    document = await store.add("notes.txt", text)

    assert document == Document(id=document.id, filename="notes.txt", text=text)
    assert await store.get(document.id) == document
