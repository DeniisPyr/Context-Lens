from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import FakeGemini, fake_embedding, run_sql, stored_chunks
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError
from context_lens.db.models import ChunkRow
from context_lens.index_documents import main
from context_lens.services.chunking import split_into_chunks
from context_lens.services.documents import split_lines
from context_lens.services.indexing import EmbeddedChunk
from context_lens.settings import Settings

PRIVATE_TEXT = "private document text"
LONG_TEXT = "".join(
    f"Paragraph {number}: {'slovo ' * 60}\n\n" for number in range(8)
).rstrip()
START = datetime(2026, 1, 1, tzinfo=UTC)


class Connections:
    def __init__(self, gemini: FakeGemini) -> None:
        self.gemini = gemini
        self.settings: list[Settings] = []

    def __call__(self, settings: Settings) -> FakeGemini:
        self.settings.append(settings)
        return self.gemini


@pytest.fixture
def connections(fake_gemini: FakeGemini) -> Connections:
    return Connections(fake_gemini)


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def insert_old_documents(url: URL, texts: dict[str, str]) -> list[str]:
    # As they were stored before uploads made chunks, a minute apart in this order.
    dataset_id = uuid4()
    ids = [uuid4() for _ in texts]
    rows = [
        {
            "id": document_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "text": document_text,
            "line_count": len(split_lines(document_text)),
            "created_at": START + timedelta(minutes=position),
        }
        for position, (document_id, (filename, document_text)) in enumerate(
            zip(ids, texts.items(), strict=True)
        )
    ]
    with create_engine(url, poolclass=NullPool).begin() as connection:
        connection.execute(
            text("INSERT INTO datasets (id, name) VALUES (:id, :name)"),
            {"id": dataset_id, "name": f"Dataset {dataset_id}"},
        )
        connection.execute(
            text(
                "INSERT INTO documents "
                "(id, dataset_id, filename, text, line_count, created_at) "
                "VALUES (:id, :dataset_id, :filename, :text, :line_count, :created_at)"
            ),
            rows,
        )
    return [str(document_id) for document_id in ids]


def add_chunk(url: URL, document_id: str, chunk_text: str) -> None:
    with Session(create_engine(url, poolclass=NullPool)) as session:
        session.add(
            ChunkRow(
                document_id=UUID(document_id),
                position=0,
                start_line=1,
                end_line=1,
                text=chunk_text,
                embedding=fake_embedding(chunk_text),
            )
        )
        session.commit()


def expected_chunks(filename: str, document_text: str) -> list[EmbeddedChunk]:
    return [
        EmbeddedChunk(
            chunk.start_line,
            chunk.end_line,
            chunk.text,
            fake_embedding(f"title: {filename} | text: {chunk.text}"),
        )
        for chunk in split_into_chunks(split_lines(document_text))
    ]


def when_embedding(
    filename: str, action: Callable[[], None]
) -> Callable[[list[str]], None]:
    # Runs the action while Gemini embeds that document's chunks.
    def during_embed(texts: list[str]) -> None:
        if texts[0].startswith(f"title: {filename} |"):
            action()

    return during_embed


def fail(error: Exception) -> Callable[[], None]:
    def raise_it() -> None:
        raise error

    return raise_it


def delete_document(url: URL, document_id: str) -> Callable[[], None]:
    return lambda: run_sql(url, f"DELETE FROM documents WHERE id = '{document_id}'")


@pytest.mark.usefixtures("api_key")
def test_indexes_only_the_documents_without_chunks_oldest_first(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
) -> None:
    [first, indexed, last] = insert_old_documents(
        clean_database,
        {"first.md": LONG_TEXT, "indexed.txt": "Done", "last.txt": "Short.\n"},
    )
    add_chunk(clean_database, indexed, "Done")

    exit_code = main([], connections)

    assert exit_code == 0
    assert stored_chunks(clean_database, first) == expected_chunks(
        "first.md", LONG_TEXT
    )
    assert stored_chunks(clean_database, last) == expected_chunks(
        "last.txt", "Short.\n"
    )
    assert [chunk.text for chunk in stored_chunks(clean_database, indexed)] == ["Done"]
    assert [texts[0].split(" |")[0] for texts in fake_gemini.embedded] == [
        "title: first.md",
        "title: last.txt",
    ]
    chunk_count = len(expected_chunks("first.md", LONG_TEXT))
    assert chunk_count > 1
    assert capsys.readouterr().err.splitlines() == [
        f"[1/2] {first} 'first.md': {chunk_count} chunks",
        f"[2/2] {last} 'last.txt': 1 chunk",
    ]
    assert fake_gemini.closed


@pytest.mark.usefixtures("api_key")
def test_second_run_finds_nothing_to_do(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insert_old_documents(clean_database, {"a.txt": "a", "b.txt": "b"})
    main([], connections)
    capsys.readouterr()
    fake_gemini.embedded.clear()

    exit_code = main([], connections)

    assert exit_code == 0
    assert fake_gemini.embedded == []
    assert len(connections.settings) == 1
    assert capsys.readouterr().err == "No documents need indexing.\n"


def test_dry_run_counts_what_it_would_embed_without_gemini_or_a_key(
    clean_database: URL,
    connections: Connections,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    [first, _] = insert_old_documents(
        clean_database, {"first.md": LONG_TEXT, "last.txt": "Short.\n"}
    )
    texts = [
        f"title: {filename} | text: {chunk.text}"
        for filename, document_text in [
            ("first.md", LONG_TEXT),
            ("last.txt", "Short.\n"),
        ]
        for chunk in split_into_chunks(split_lines(document_text))
    ]
    characters = sum(map(len, texts))

    exit_code = main(["--dry-run"], connections)

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "Documents without chunks: 2",
        f"Chunks to embed: {len(texts)}",
        f"Characters to embed: {characters:,}",
        f"Tokens at 4 characters a token: {round(characters / 4):,}",
    ]
    assert connections.settings == []
    assert stored_chunks(clean_database, first) == []


@pytest.mark.parametrize(
    ("error", "reported"),
    [
        pytest.param(
            GeminiUnavailableError("Busy."), "IndexingUnavailableError", id="busy"
        ),
        pytest.param(GeminiError("Rejected."), "IndexingError", id="rejected"),
    ],
)
@pytest.mark.usefixtures("api_key")
def test_gemini_failure_leaves_the_other_documents_indexed_and_exits_1(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
    error: GeminiError,
    reported: str,
) -> None:
    [first, failing, last] = insert_old_documents(
        clean_database, {"a.txt": "a", "b.txt": "b", "c.txt": "c"}
    )
    fake_gemini.during_embed = when_embedding("b.txt", fail(error))

    exit_code = main([], connections)

    assert exit_code == 1
    assert stored_chunks(clean_database, first) == expected_chunks("a.txt", "a")
    assert stored_chunks(clean_database, failing) == []
    assert stored_chunks(clean_database, last) == expected_chunks("c.txt", "c")
    lines = capsys.readouterr().err.splitlines()
    assert lines[1] == f"[2/3] {failing} 'b.txt': Gemini error: {reported}"
    assert lines[3] == (
        "1 of 3 documents weren't indexed because of Gemini errors. "
        "Run this again to retry them."
    )
    assert fake_gemini.closed


@pytest.mark.usefixtures("api_key")
def test_next_run_retries_a_document_gemini_failed_on(
    clean_database: URL, connections: Connections, fake_gemini: FakeGemini
) -> None:
    [document_id] = insert_old_documents(clean_database, {"a.txt": "a"})
    fake_gemini.embed_error = GeminiUnavailableError("Busy.")
    assert main([], connections) == 1
    fake_gemini.embed_error = None

    exit_code = main([], connections)

    assert exit_code == 0
    assert stored_chunks(clean_database, document_id) == expected_chunks("a.txt", "a")


@pytest.mark.usefixtures("api_key")
def test_document_deleted_while_gemini_embeds_it_is_skipped(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
) -> None:
    [deleted, kept] = insert_old_documents(clean_database, {"a.txt": "a", "b.txt": "b"})
    fake_gemini.during_embed = when_embedding(
        "a.txt", delete_document(clean_database, deleted)
    )

    exit_code = main([], connections)

    assert exit_code == 0
    assert stored_chunks(clean_database, deleted) == []
    assert stored_chunks(clean_database, kept) == expected_chunks("b.txt", "b")
    assert capsys.readouterr().err.splitlines()[0] == (
        f"[1/2] {deleted} 'a.txt': skipped, the document was deleted meanwhile"
    )


@pytest.mark.usefixtures("api_key")
def test_document_deleted_before_its_turn_is_skipped(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
) -> None:
    [_, deleted] = insert_old_documents(clean_database, {"a.txt": "a", "b.txt": "b"})
    fake_gemini.during_embed = when_embedding(
        "a.txt", delete_document(clean_database, deleted)
    )

    exit_code = main([], connections)

    assert exit_code == 0
    assert len(fake_gemini.embedded) == 1
    assert capsys.readouterr().err.splitlines()[1] == (
        f"[2/2] {deleted}: skipped, the document was deleted meanwhile"
    )


@pytest.mark.usefixtures("api_key")
def test_document_indexed_meanwhile_by_another_run_is_skipped(
    clean_database: URL,
    connections: Connections,
    fake_gemini: FakeGemini,
    capsys: pytest.CaptureFixture[str],
) -> None:
    [document_id] = insert_old_documents(clean_database, {"a.txt": "a"})
    fake_gemini.during_embed = when_embedding(
        "a.txt", lambda: add_chunk(clean_database, document_id, "theirs")
    )

    exit_code = main([], connections)

    assert exit_code == 0
    assert [c.text for c in stored_chunks(clean_database, document_id)] == ["theirs"]
    assert capsys.readouterr().err == (
        f"[1/1] {document_id} 'a.txt': skipped, another run indexed it meanwhile\n"
    )


@pytest.mark.usefixtures("api_key")
def test_output_never_holds_the_text_and_takes_a_line_for_each_document(
    clean_database: URL,
    connections: Connections,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insert_old_documents(
        clean_database, {"a.txt": PRIVATE_TEXT, "two\nlines.txt": PRIVATE_TEXT}
    )

    main(["--dry-run"], connections)
    main([], connections)

    output = capsys.readouterr()
    assert PRIVATE_TEXT not in output.out + output.err
    assert len(output.err.splitlines()) == 2
    assert "'two\\nlines.txt'" in output.err


@pytest.mark.usefixtures("api_key")
def test_gemini_is_closed_when_indexing_fails_with_a_bug(
    clean_database: URL, connections: Connections, fake_gemini: FakeGemini
) -> None:
    insert_old_documents(clean_database, {"a.txt": "a"})
    fake_gemini.during_embed = when_embedding("a.txt", fail(RuntimeError("bug")))

    with pytest.raises(RuntimeError, match="bug"):
        main([], connections)

    assert fake_gemini.closed


def test_missing_key_is_an_error_that_shows_no_settings_values(
    monkeypatch: pytest.MonkeyPatch,
    connections: Connections,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    exit_code = main([], connections)

    assert exit_code == 2
    output = capsys.readouterr()
    assert output.err.startswith(
        "Invalid settings: gemini_api_key. Set GEMINI_API_KEY in backend/.env"
    )
    # conftest's DATABASE_URL has this password.
    assert "hunter2" not in output.err + output.out
    assert connections.settings == []


@pytest.mark.usefixtures("api_key")
def test_unknown_setting_is_named_without_its_value(
    tmp_path: Path, connections: Connections, capsys: pytest.CaptureFixture[str]
) -> None:
    # conftest made tmp_path the working directory, where Settings reads .env.
    (tmp_path / ".env").write_text(
        "DATABSE_URL=postgresql+psycopg://someone:hunter3@db.example/other\n"
    )

    exit_code = main([], connections)

    assert exit_code == 2
    output = capsys.readouterr()
    assert output.err.startswith("Invalid settings: databse_url. ")
    assert "hunter3" not in output.err + output.out


@pytest.mark.parametrize(
    "argv",
    [pytest.param(["--unknown"], id="unknown_option"), pytest.param(["x"], id="file")],
)
def test_bad_options_are_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith(
        "usage: python -m context_lens.index_documents"
    )
