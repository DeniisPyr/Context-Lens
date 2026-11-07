import pytest
from conftest import (
    FakeGemini,
    create_dataset,
    dataset_id_of,
    fake_embedding,
    run_sql,
    stored_chunks,
)
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import URL, create_engine, text
from sqlalchemy.pool import NullPool

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError
from context_lens.services.chunking import TextChunk, split_into_chunks
from context_lens.services.documents import split_lines
from context_lens.services.embeddings import query_embedding_text
from context_lens.services.indexing import (
    EmbeddedChunk,
    IndexingError,
    IndexingUnavailableError,
    index_lines,
)

PARAGRAPHS = [
    "# Cestovní náhrady",
    "",
    *[f"Řádek {number}: {'x' * 90}" for number in range(12)],
    "",
    *[f"Line {number}: {'y' * 90}" for number in range(12)],
    "",
    "The last line.",
]
DOCUMENT = "\n".join(PARAGRAPHS) + "\n"
PRIVATE_TEXT = "private document text"
UNAVAILABLE = {
    "detail": (
        "Gemini is unavailable right now, so the document wasn't saved. "
        "Please try again."
    )
}
NOT_INDEXED = {"detail": "Gemini could not index this document, so it wasn't saved."}


def upload(
    client: TestClient,
    documents_url: str,
    content: bytes = DOCUMENT.encode(),
    filename: str = "notes.txt",
) -> Response:
    return client.post(documents_url, files={"file": (filename, content)})


def rows_in(url: URL, table: str) -> int:
    with create_engine(url, poolclass=NullPool).connect() as connection:
        return connection.scalar(text(f"SELECT count(*) FROM {table}"))


def embedding_texts(filename: str, chunks: list[TextChunk]) -> list[str]:
    return [f"title: {filename} | text: {chunk.text}" for chunk in chunks]


def test_upload_stores_each_chunk_with_its_lines_and_embedding(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    clean_database: URL,
) -> None:
    expected = split_into_chunks(PARAGRAPHS)
    assert len(expected) > 1  # Proves the document is long enough to split.

    response = upload(client, documents_url, filename="náhrady.md")

    assert response.status_code == 201
    texts = embedding_texts("náhrady.md", expected)
    assert fake_gemini.embedded == [texts]
    assert stored_chunks(clean_database, response.json()["id"]) == [
        EmbeddedChunk(
            chunk.start_line, chunk.end_line, chunk.text, fake_embedding(sent)
        )
        for chunk, sent in zip(expected, texts, strict=True)
    ]


def test_chunk_lines_point_at_the_lines_the_read_returns(
    client: TestClient, documents_url: str, clean_database: URL
) -> None:
    document_id = upload(client, documents_url).json()["id"]

    lines = client.get(f"/api/documents/{document_id}").json()["lines"]

    for chunk in stored_chunks(clean_database, document_id):
        assert chunk.text == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])


@pytest.mark.parametrize(
    ("sent", "title"),
    [
        pytest.param("poznámky.txt", "poznámky.txt", id="czech"),
        pytest.param("C:\\docs\\notes.txt", "notes.txt", id="windows_path"),
    ],
)
def test_title_is_the_stored_filename(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    sent: str,
    title: str,
) -> None:
    upload(client, documents_url, b"Hello\n", sent)

    assert fake_gemini.embedded == [[f"title: {title} | text: Hello"]]


def test_duplicate_filename_is_refused_without_calling_gemini(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    upload(client, documents_url)
    fake_gemini.embedded.clear()

    response = upload(client, documents_url, b"another version\n")

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this dataset."}
    assert fake_gemini.embedded == []


@pytest.mark.parametrize(
    "dataset_id",
    ["not-a-uuid", "00000000-0000-0000-0000-000000000000"],
    ids=["bad_id", "unknown_id"],
)
def test_unknown_dataset_is_refused_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, dataset_id: str
) -> None:
    response = upload(client, f"/api/datasets/{dataset_id}/documents")

    assert response.status_code == 404
    assert fake_gemini.embedded == []


def test_deleted_dataset_is_refused_without_calling_gemini(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    client.delete(documents_url.removesuffix("/documents"))

    response = upload(client, documents_url)

    assert response.status_code == 404
    assert fake_gemini.embedded == []


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        pytest.param("notes.pdf", b"hello", 415, id="wrong_type"),
        pytest.param("notes.txt", b"caf\xe9", 415, id="not_utf8"),
        pytest.param("notes.txt", b" \n", 422, id="empty"),
        pytest.param("notes.txt", b"x" * 1_000_001, 413, id="too_large"),
    ],
)
def test_rejected_file_is_refused_without_calling_gemini(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    filename: str,
    content: bytes,
    status: int,
) -> None:
    response = upload(client, documents_url, content, filename)

    assert response.status_code == status
    assert fake_gemini.embedded == []


@pytest.mark.parametrize(
    ("error", "status", "body"),
    [
        pytest.param(GeminiUnavailableError("Busy."), 503, UNAVAILABLE, id="busy"),
        pytest.param(GeminiError("Rejected."), 502, NOT_INDEXED, id="rejected"),
    ],
)
def test_gemini_failure_stores_nothing_and_says_so(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    clean_database: URL,
    error: GeminiError,
    status: int,
    body: dict,
) -> None:
    fake_gemini.embed_error = error

    response = upload(client, documents_url)

    assert response.status_code == status
    assert response.json() == body
    assert client.get(documents_url).json() == []
    assert rows_in(clean_database, "documents") == 0
    assert rows_in(clean_database, "chunks") == 0


def test_upload_works_once_gemini_is_back(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    fake_gemini.embed_error = GeminiUnavailableError("Busy.")
    upload(client, documents_url)
    fake_gemini.embed_error = None

    response = upload(client, documents_url)

    assert response.status_code == 201
    assert len(client.get(documents_url).json()) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            GeminiUnavailableError("Busy."),
            "Gemini is unavailable, so a document wasn't saved.",
            id="busy",
        ),
        pytest.param(
            GeminiError("Rejected."),
            "Gemini could not index a document.",
            id="rejected",
        ),
    ],
)
def test_gemini_failure_is_logged_with_its_cause_and_without_the_text(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    caplog: pytest.LogCaptureFixture,
    error: GeminiError,
    message: str,
) -> None:
    fake_gemini.embed_error = error

    upload(client, documents_url, PRIVATE_TEXT.encode())

    [record] = [r for r in caplog.records if r.getMessage() == message]
    assert record.exc_info is not None
    assert record.exc_info[1].__cause__ is error
    assert PRIVATE_TEXT not in caplog.text


def test_no_database_connection_is_held_while_gemini_embeds(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    pool = client.app.state.engine.pool
    during_the_call = []
    fake_gemini.during_embed = lambda texts: during_the_call.append(
        (pool.checkedout(), pool.checkedin())
    )

    response = upload(client, documents_url)

    assert response.status_code == 201
    # None in use, and the one the check used is back in the pool.
    assert during_the_call == [(0, 1)]


def test_upload_that_loses_a_race_for_its_filename_stores_no_chunks(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    clean_database: URL,
) -> None:
    # Another upload of the name arrives while Gemini embeds this one, after the check.
    dataset_id = documents_url.split("/")[3]
    fake_gemini.during_embed = lambda texts: run_sql(
        clean_database,
        "INSERT INTO documents (id, dataset_id, filename, text, line_count) "
        f"VALUES (gen_random_uuid(), '{dataset_id}', 'notes.txt', 'rival', 1)",
    )

    response = upload(client, documents_url)

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this dataset."}
    assert rows_in(clean_database, "documents") == 1
    assert rows_in(clean_database, "chunks") == 0


def test_upload_into_a_dataset_deleted_meanwhile_stores_nothing(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    clean_database: URL,
) -> None:
    fake_gemini.during_embed = lambda texts: run_sql(
        clean_database, "DELETE FROM datasets"
    )

    response = upload(client, documents_url)

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}
    assert rows_in(clean_database, "chunks") == 0


def test_deleting_a_document_or_dataset_deletes_the_chunks(
    client: TestClient, clean_database: URL
) -> None:
    reports_url = create_dataset(client, "Reports")
    invoices_url = create_dataset(client, "Invoices")
    report = upload(client, reports_url, filename="report.txt").json()
    upload(client, reports_url, filename="other.txt")
    invoice = upload(client, invoices_url, b"Invoice\n", "invoice.txt").json()

    per_document = len(split_into_chunks(PARAGRAPHS))

    client.delete(f"/api/documents/{report['id']}")
    assert stored_chunks(clean_database, report["id"]) == []
    assert rows_in(clean_database, "chunks") == per_document + 1

    client.delete(reports_url.removesuffix("/documents"))
    assert rows_in(clean_database, "chunks") == 1
    assert len(stored_chunks(clean_database, invoice["id"])) == 1


def test_asking_embeds_only_the_question_and_sends_the_chunks_found(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    upload(client, documents_url)
    dataset_id = dataset_id_of(documents_url)
    fake_gemini.embedded.clear()

    client.post("/api/ask", json={"dataset_id": dataset_id, "question": "Hi"})

    # The document has fewer chunks than a question finds, so all of them are sent.
    chunks = split_into_chunks(PARAGRAPHS)
    assert len(chunks) < 8
    for chunk in chunks:
        numbered = "\n".join(
            f"{number}: {line}"
            for number, line in enumerate(chunk.text.split("\n"), chunk.start_line)
        )
        assert f"\n{numbered}\n" in fake_gemini.prompts[0]
    assert fake_gemini.embedded == [[query_embedding_text("Hi")]]


@pytest.mark.anyio
async def test_index_lines_embeds_each_chunk_with_its_title(
    fake_gemini: FakeGemini,
) -> None:
    lines = split_lines(DOCUMENT)

    chunks = await index_lines(fake_gemini, "notes.txt", lines)

    expected = split_into_chunks(lines)
    texts = embedding_texts("notes.txt", expected)
    assert fake_gemini.embedded == [texts]
    assert chunks == [
        EmbeddedChunk(
            chunk.start_line, chunk.end_line, chunk.text, fake_embedding(sent)
        )
        for chunk, sent in zip(expected, texts, strict=True)
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "raised"),
    [
        pytest.param(
            GeminiUnavailableError("Busy."), IndexingUnavailableError, id="busy"
        ),
        pytest.param(GeminiError("Rejected."), IndexingError, id="rejected"),
    ],
)
async def test_index_lines_says_why_gemini_failed(
    fake_gemini: FakeGemini, error: GeminiError, raised: type[IndexingError]
) -> None:
    fake_gemini.embed_error = error

    with pytest.raises(raised) as caught:
        await index_lines(fake_gemini, "notes.txt", ["Hello"])

    assert type(caught.value) is raised
    assert caught.value.__cause__ is error
