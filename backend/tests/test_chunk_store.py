import math
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from conftest import MAX_DOCUMENTS, NO_CHUNKS
from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import AsyncEngine

from context_lens.db.chunk_store import ChunkStore
from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.datasets import DatasetNotFoundError
from context_lens.services.documents import Document
from context_lens.services.embeddings import EMBEDDING_DIMENSIONS
from context_lens.services.indexing import EmbeddedChunk
from context_lens.services.search import FoundChunk
from context_lens.settings import DatabaseSettings

pytestmark = pytest.mark.anyio

LIMIT = 8


def direction(degrees: float) -> list[float]:
    # Embeddings at an angle to direction(0): the smaller the angle, the nearer.
    radians = math.radians(degrees)
    rest = [0.0] * (EMBEDDING_DIMENSIONS - 2)
    return [math.cos(radians), math.sin(radians), *rest]


QUESTION = direction(0)


@pytest.fixture
async def engine(clean_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(DatabaseSettings())
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> ChunkStore:
    return ChunkStore(engine)


@pytest.fixture
def documents(engine: AsyncEngine) -> DocumentStore:
    return DocumentStore(engine)


@pytest.fixture
def datasets(engine: AsyncEngine) -> DatasetStore:
    return DatasetStore(engine)


@pytest.fixture
async def dataset_id(datasets: DatasetStore) -> str:
    return (await datasets.add("Reports")).id


async def add_document(
    documents: DocumentStore, dataset_id: str, filename: str, *angles: float
) -> Document:
    # One chunk of one line for each angle, so line n is the chunk at position n - 1.
    lines = [f"Line {number} of {filename}." for number in range(1, len(angles) + 1)]
    chunks = [
        EmbeddedChunk(number, number, line, direction(angle))
        for number, (line, angle) in enumerate(zip(lines, angles), start=1)
    ]
    text = "".join(f"{line}\n" for line in lines)
    return await documents.add(dataset_id, filename, text, chunks, MAX_DOCUMENTS)


def found(document: Document, line: int) -> FoundChunk:
    return FoundChunk(
        document_id=document.id,
        filename=document.filename,
        position=line - 1,
        start_line=line,
        end_line=line,
        text=f"Line {line} of {document.filename}.",
    )


async def test_search_finds_the_nearest_chunks_first(
    store: ChunkStore, documents: DocumentStore, dataset_id: str
) -> None:
    first = await add_document(documents, dataset_id, "a.txt", 40, 10)
    second = await add_document(documents, dataset_id, "b.md", 30, 20)

    chunks = await store.search(dataset_id, QUESTION, LIMIT)

    assert chunks == [
        found(first, 2),
        found(second, 2),
        found(second, 1),
        found(first, 1),
    ]


async def test_search_returns_a_chunks_whole_line_range_and_text(
    store: ChunkStore, documents: DocumentStore, dataset_id: str
) -> None:
    text = "Příliš žluťoučký\nkůň\n\núpěl ďábelské ódy\n"
    chunks = [
        EmbeddedChunk(1, 2, "Příliš žluťoučký\nkůň", direction(5)),
        EmbeddedChunk(4, 4, "úpěl ďábelské ódy", direction(80)),
    ]
    document = await documents.add(dataset_id, "kůň.md", text, chunks, MAX_DOCUMENTS)

    [nearest, *_] = await store.search(dataset_id, QUESTION, LIMIT)

    assert nearest == FoundChunk(
        document_id=document.id,
        filename="kůň.md",
        position=0,
        start_line=1,
        end_line=2,
        text="Příliš žluťoučký\nkůň",
    )


async def test_equally_near_chunks_come_in_document_order(
    store: ChunkStore, documents: DocumentStore, dataset_id: str
) -> None:
    document = await add_document(documents, dataset_id, "a.txt", 10, 10, 10)

    chunks = await store.search(dataset_id, QUESTION, LIMIT)

    assert chunks == [found(document, 1), found(document, 2), found(document, 3)]


@pytest.mark.parametrize("limit", [1, 2, 3])
async def test_search_finds_at_most_the_limit(
    store: ChunkStore, documents: DocumentStore, dataset_id: str, limit: int
) -> None:
    document = await add_document(documents, dataset_id, "a.txt", 30, 20, 10, 40)
    nearest_first = [found(document, line) for line in (3, 2, 1, 4)]

    chunks = await store.search(dataset_id, QUESTION, limit)

    assert chunks == nearest_first[:limit]


async def test_search_finds_only_that_datasets_chunks(
    store: ChunkStore,
    documents: DocumentStore,
    datasets: DatasetStore,
    dataset_id: str,
) -> None:
    other_dataset = await datasets.add("Other")
    await add_document(documents, other_dataset.id, "a.txt", 0, 1)
    document = await add_document(documents, dataset_id, "a.txt", 50)

    chunks = await store.search(dataset_id, QUESTION, LIMIT)

    assert chunks == [found(document, 1)]


async def test_search_of_an_empty_dataset_finds_nothing(
    store: ChunkStore, dataset_id: str
) -> None:
    assert await store.search(dataset_id, QUESTION, LIMIT) == []


async def test_search_finds_nothing_in_documents_stored_without_chunks(
    store: ChunkStore, documents: DocumentStore, dataset_id: str
) -> None:
    await documents.add(dataset_id, "old.txt", "Stored early.\n", NO_CHUNKS, 1)

    assert await store.search(dataset_id, QUESTION, LIMIT) == []


async def test_search_finds_no_chunks_of_a_deleted_document(
    store: ChunkStore, documents: DocumentStore, dataset_id: str
) -> None:
    kept = await add_document(documents, dataset_id, "kept.txt", 30)
    deleted = await add_document(documents, dataset_id, "gone.txt", 10)

    await documents.delete(deleted.id)

    assert await store.search(dataset_id, QUESTION, LIMIT) == [found(kept, 1)]


@pytest.mark.parametrize(
    "unknown_id",
    ["not-a-uuid", "", "\x00", "00000000-0000-0000-0000-000000000000"],
    ids=["not_a_uuid", "empty", "nul", "unknown_uuid"],
)
async def test_search_refuses_an_unknown_dataset(
    store: ChunkStore, unknown_id: str
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.search(unknown_id, QUESTION, LIMIT)


async def test_search_refuses_a_deleted_dataset(
    store: ChunkStore,
    documents: DocumentStore,
    datasets: DatasetStore,
    dataset_id: str,
) -> None:
    await add_document(documents, dataset_id, "a.txt", 10)
    await datasets.delete(dataset_id)

    with pytest.raises(DatasetNotFoundError):
        await store.search(dataset_id, QUESTION, LIMIT)


async def test_search_of_a_bad_id_does_not_need_a_connection(
    store: ChunkStore, engine: AsyncEngine
) -> None:
    with pytest.raises(DatasetNotFoundError):
        await store.search("not-a-uuid", QUESTION, LIMIT)

    assert engine.pool.checkedin() == 0


async def test_search_gives_its_connection_back(
    store: ChunkStore, documents: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    await add_document(documents, dataset_id, "a.txt", 10)

    await store.search(dataset_id, QUESTION, LIMIT)
    assert engine.pool.checkedout() == 0

    with pytest.raises(DatasetNotFoundError):
        await store.search(str(uuid4()), QUESTION, LIMIT)
    assert engine.pool.checkedout() == 0

    assert engine.pool.checkedin() == 1


async def test_search_does_not_read_the_documents_texts(
    store: ChunkStore, documents: DocumentStore, engine: AsyncEngine, dataset_id: str
) -> None:
    await add_document(documents, dataset_id, "a.txt", 10)
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    await store.search(dataset_id, QUESTION, LIMIT)

    [select] = [statement for statement in statements if "FROM chunks" in statement]
    assert "documents.filename" in select
    assert "documents.text" not in select
