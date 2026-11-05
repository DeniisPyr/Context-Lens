from unittest.mock import ANY
from uuid import uuid4

import pytest
from conftest import (
    FakeGemini,
    StartApp,
    apply_migrations,
    as_setting,
    create_dataset,
    run_sql,
)
from fastapi import Request
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import URL as DatabaseURL

from context_lens.dependencies import get_document_store
from context_lens.main import create_app
from context_lens.schemas.documents import DocumentSummary
from context_lens.services.answering import Citation, ModelAnswer
from context_lens.services.documents import Document, DocumentInfo

URL = "/api/documents"
LIMIT = 1_000_000
BOM = b"\xef\xbb\xbf"


def upload(
    client: TestClient,
    documents_url: str,
    content: bytes = b"hello",
    filename: str = "notes.txt",
) -> Response:
    return client.post(documents_url, files={"file": (filename, content)})


def stored_document(client: TestClient, response: Response) -> Document:
    store = get_document_store(Request({"type": "http", "app": client.app}))
    # On the app's event loop, because the store's connections belong to it.
    document = client.portal.call(store.get, response.json()["id"])
    assert document is not None
    return document


def test_upload_returns_the_document_summary(
    client: TestClient, documents_url: str
) -> None:
    text = "Příliš žluťoučký\nkůň\n"

    response = upload(client, documents_url, text.encode(), "poznámky.txt")

    assert response.status_code == 201
    assert response.json() == {"id": ANY, "filename": "poznámky.txt", "line_count": 2}
    assert stored_document(client, response).text == text


@pytest.mark.parametrize("filename", ["notes.txt", "notes.md", "NOTES.TXT", "Notes.Md"])
def test_extensions_are_case_insensitive(
    client: TestClient, documents_url: str, filename: str
) -> None:
    response = upload(client, documents_url, filename=filename)

    assert response.status_code == 201
    assert response.json()["filename"] == filename


@pytest.mark.parametrize(
    ("filename", "content", "status", "detail"),
    [
        ("notes.pdf", b"hello", 415, "Only .txt and .md"),
        ("notes", b"hello", 415, "Only .txt and .md"),
        ("/", b"hello", 415, "Only .txt and .md"),
        ("C:\\", b"hello", 415, "Only .txt and .md"),
        ("notes.txt", b"caf\xe9", 415, "UTF-8"),
        ("notes.txt", b"a\x00b", 415, "NUL"),
        ("notes.txt", b"", 422, "empty"),
        ("notes.txt", b" \t\r\n", 422, "empty"),
        ("notes.txt", BOM, 422, "empty"),
    ],
)
def test_rejected_upload_stores_nothing(
    client: TestClient,
    documents_url: str,
    filename: str,
    content: bytes,
    status: int,
    detail: str,
) -> None:
    response = upload(client, documents_url, content, filename)

    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert client.get(documents_url).json() == []


def test_part_without_a_filename_is_a_validation_error(
    client: TestClient, documents_url: str
) -> None:
    # The HTTP client leaves out an empty filename, so the part is a plain form field.
    response = upload(client, documents_url, filename="")

    assert response.status_code == 422
    assert client.get(documents_url).json() == []


def test_nul_in_the_filename_is_rejected(
    client: TestClient, documents_url: str
) -> None:
    # The HTTP client would percent-encode the NUL, so this sends the exact bytes.
    body = (
        b'--x\r\nContent-Disposition: form-data; name="file"; filename="a\x00.txt"'
        b"\r\n\r\nhello\r\n--x--\r\n"
    )

    response = client.post(
        documents_url,
        content=body,
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 415
    assert "NUL" in response.json()["detail"]
    assert client.get(documents_url).json() == []


def test_file_at_the_size_limit_is_accepted(
    client: TestClient, documents_url: str
) -> None:
    response = upload(client, documents_url, b"x" * LIMIT)

    assert response.status_code == 201
    assert len(client.get(documents_url).json()) == 1


def test_file_over_the_size_limit_is_rejected(
    client: TestClient, documents_url: str
) -> None:
    # Not valid UTF-8 either: the size is checked first, before any decoding.
    response = upload(client, documents_url, b"\xff" * (LIMIT + 1))

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]
    assert client.get(documents_url).json() == []


def test_file_type_is_checked_before_the_size(
    client: TestClient, documents_url: str
) -> None:
    response = upload(client, documents_url, b"x" * (LIMIT + 1), "notes.pdf")

    assert response.status_code == 415


@pytest.mark.usefixtures("clean_database")
def test_upload_limit_comes_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")

    with TestClient(create_app()) as client:
        documents_url = create_dataset(client)

        response = upload(client, documents_url, b"x" * 11)

        assert response.status_code == 413
        assert response.json() == {
            "detail": "The file must not be larger than 10 bytes."
        }
        assert client.get(documents_url).json() == []


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("a\nb\n", ["a", "b"]),
        ("a\n\nb", ["a", "", "b"]),
        ("a\n\n", ["a", ""]),
        ("\n\na", ["", "", "a"]),
        ("a\r\nb\r\n", ["a", "b"]),
        ("a\rb", ["a", "b"]),
        ("a\x0cb\n", ["a\x0cb"]),
        ("a\u2028b", ["a\u2028b"]),
    ],
)
def test_lines_match_an_editor(
    client: TestClient, documents_url: str, text: str, lines: list[str]
) -> None:
    response = upload(client, documents_url, text.encode())

    assert response.status_code == 201
    assert response.json()["line_count"] == len(lines)
    assert stored_document(client, response).lines == lines


def test_document_without_text_has_no_lines() -> None:
    document = Document(id="1", filename="a.txt", text="")

    assert document.lines == []
    assert document.line_count == 0


# Every way of counting lines other than the one the citations use gets one of these
# wrong: blank lines, trailing newlines, and the characters str.splitlines() splits on.
TEXTS_WITH_THEIR_LINE_COUNTS = [
    pytest.param("a\n\n\nb\n", 4, id="blank_lines"),
    pytest.param("a\n\n\n", 3, id="trailing_newlines"),
    pytest.param("a\nb", 2, id="no_final_newline"),
    pytest.param("a\x0cb\n", 1, id="form_feed"),
    pytest.param("a\x0bb\n", 1, id="vertical_tab"),
    pytest.param("a\x1cb\x1dc\x1ed\n", 1, id="separators"),
    pytest.param("a\x85b\n", 1, id="next_line"),
    pytest.param("a\u2028b\u2029c\n", 1, id="unicode_separators"),
    pytest.param("Příliš žluťoučký\nkůň\n", 2, id="czech"),
]


@pytest.mark.parametrize(("text", "line_count"), TEXTS_WITH_THEIR_LINE_COUNTS)
def test_line_count_is_the_number_of_lines(text: str, line_count: int) -> None:
    document = Document(id="1", filename="a.txt", text=text)

    assert len(document.lines) == line_count
    assert document.line_count == line_count


@pytest.mark.parametrize(("text", "line_count"), TEXTS_WITH_THEIR_LINE_COUNTS)
def test_stored_line_count_matches_the_lines_of_the_stored_text(
    client: TestClient, documents_url: str, text: str, line_count: int
) -> None:
    uploaded = upload(client, documents_url, text.encode()).json()

    # The list reads the stored column, and the read counts the lines of the text.
    [listed] = client.get(documents_url).json()
    read = client.get(f"{URL}/{uploaded['id']}").json()

    assert uploaded["line_count"] == line_count
    assert listed["line_count"] == line_count
    assert read["line_count"] == line_count
    assert len(read["lines"]) == line_count


def test_summary_can_be_built_without_the_text() -> None:
    info = DocumentInfo(id="1", filename="a.txt", line_count=7)

    assert DocumentSummary.from_document(info).model_dump() == {
        "id": "1",
        "filename": "a.txt",
        "line_count": 7,
    }


def test_stored_text_has_no_bom_or_carriage_returns(
    client: TestClient, documents_url: str
) -> None:
    response = upload(client, documents_url, BOM + b"first\r\nsecond\rthird\n")

    document = stored_document(client, response)
    assert document.text == "first\nsecond\nthird\n"
    assert document.lines[0] == "first"


@pytest.mark.parametrize(
    ("filename", "base_name"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\docs\\a.txt", "a.txt"),
        ("C:a.txt", "a.txt"),
        ("..\\..\\secret.md", "secret.md"),
    ],
)
def test_only_the_base_name_of_the_filename_is_stored(
    client: TestClient, documents_url: str, filename: str, base_name: str
) -> None:
    response = upload(client, documents_url, filename=filename)

    assert response.status_code == 201
    assert response.json()["filename"] == base_name


def test_list_is_empty_without_uploads(client: TestClient, documents_url: str) -> None:
    response = client.get(documents_url)

    assert response.status_code == 200
    assert response.json() == []


def test_list_is_in_upload_order_without_the_text(
    client: TestClient, documents_url: str
) -> None:
    names = ["z.txt", "a.md", "m.txt"]
    uploads = [upload(client, documents_url, filename=name).json() for name in names]

    response = client.get(documents_url)

    assert response.status_code == 200
    assert response.json() == uploads
    assert [item["filename"] for item in response.json()] == names
    assert all("text" not in item for item in response.json())


def test_list_order_does_not_depend_on_where_the_rows_are_stored(
    client: TestClient, documents_url: str, clean_database: DatabaseURL
) -> None:
    uploads = [
        upload(client, documents_url, filename=f"{name}.txt").json() for name in "abc"
    ]

    # Rewrites the first row, so Postgres now finds it last when it scans the table.
    run_sql(
        clean_database,
        "UPDATE documents SET filename = filename WHERE filename = 'a.txt'",
    )

    assert client.get(documents_url).json() == uploads


def test_list_order_follows_the_upload_time(
    client: TestClient, documents_url: str, clean_database: DatabaseURL
) -> None:
    uploads = [
        upload(client, documents_url, filename=f"{name}.txt").json() for name in "abc"
    ]

    # The last row stays last on disk, so only the sort can move it to the front.
    run_sql(
        clean_database,
        "UPDATE documents SET created_at = created_at - interval '1 day' "
        "WHERE filename = 'c.txt'",
    )

    assert client.get(documents_url).json() == [uploads[2], uploads[0], uploads[1]]


def test_list_order_of_uploads_at_the_same_moment_is_by_id(
    client: TestClient, documents_url: str, clean_database: DatabaseURL
) -> None:
    names = [f"{name}.txt" for name in "abcde"]
    uploads = [upload(client, documents_url, filename=name).json() for name in names]

    run_sql(clean_database, "UPDATE documents SET created_at = '2026-01-01'")

    ids = [item["id"] for item in client.get(documents_url).json()]
    assert ids == sorted(item["id"] for item in uploads)


def test_list_and_upload_responses_have_no_lines(
    client: TestClient, documents_url: str
) -> None:
    uploaded = upload(client, documents_url, b"one\ntwo\n").json()

    assert "lines" not in uploaded
    assert all("lines" not in item for item in client.get(documents_url).json())


def test_read_returns_the_document_with_its_lines(
    client: TestClient, documents_url: str
) -> None:
    uploaded = upload(
        client, documents_url, "Příliš žluťoučký\nkůň\n".encode(), "poznámky.txt"
    ).json()

    response = client.get(f"{URL}/{uploaded['id']}")

    assert response.status_code == 200
    assert response.json() == {
        "id": uploaded["id"],
        "filename": "poznámky.txt",
        "line_count": 2,
        "lines": ["Příliš žluťoučký", "kůň"],
    }


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("a\n\nb\n", ["a", "", "b"]),
        ("\n\na", ["", "", "a"]),
        ("a\n\n", ["a", ""]),
        ("  two spaces\n\ttab\ntrailing  \n", ["  two spaces", "\ttab", "trailing  "]),
        ("a\r\nb\rc", ["a", "b", "c"]),
        ("a\x0cb\nc\u2028d", ["a\x0cb", "c\u2028d"]),
        ('<b>tučně</b> & "víc"', ['<b>tučně</b> & "víc"']),
    ],
)
def test_read_keeps_every_line_as_it_is_in_the_document(
    client: TestClient, documents_url: str, text: str, lines: list[str]
) -> None:
    uploaded = upload(client, documents_url, text.encode())

    body = client.get(f"{URL}/{uploaded.json()['id']}").json()

    assert body["lines"] == lines
    assert body["line_count"] == len(lines)
    assert body["lines"] == stored_document(client, uploaded).lines


@pytest.mark.parametrize(
    "document_id",
    [
        "unknown",
        "not-a-uuid",
        "123",
        "00000000-0000-0000-0000-00000000000g",
        "0" * 33,
        "%00",
        "%20",
        "é",
        str(uuid4()),
    ],
)
def test_read_of_an_unknown_id_is_a_404(
    client: TestClient, documents_url: str, document_id: str
) -> None:
    upload(client, documents_url)

    response = client.get(f"{URL}/{document_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


# A form feed and a Unicode line separator are where str.splitlines() would number
# differently, and a blank line is where a filter on empty lines would.
NUMBERING_TEXT = "První\n\nform\x0cfeed\nline\u2028separator\n  žluťoučký kůň\n"


def test_read_lines_are_the_lines_the_prompt_numbers(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    document_id = upload(client, documents_url, NUMBERING_TEXT.encode()).json()["id"]

    client.post("/api/ask", json={"document_id": document_id, "question": "Proč?"})
    lines = client.get(f"{URL}/{document_id}").json()["lines"]

    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(lines, start=1))
    assert len(lines) == 5
    assert f"<document>\n{numbered}\n</document>" in fake_gemini.prompts[0]


def test_a_citation_points_at_the_same_line_in_the_read_response(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="Kůň je žluťoučký.",
        citations=[Citation(start_line=5, end_line=5, quote="žluťoučký kůň")],
    )
    document_id = upload(client, documents_url, NUMBERING_TEXT.encode()).json()["id"]

    answer = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Jaký je kůň?"}
    ).json()
    lines = client.get(f"{URL}/{document_id}").json()["lines"]

    citation = answer["citations"][0]
    assert answer["status"] == "answered"
    assert citation["quote"] in lines[citation["start_line"] - 1]


@pytest.mark.parametrize(
    ("sent", "stored", "lines", "cited_line", "quote"),
    [
        pytest.param(
            "První\n\n\nposlední\n",
            "První\n\n\nposlední\n",
            ["První", "", "", "poslední"],
            4,
            "poslední",
            id="blank_lines",
        ),
        pytest.param(
            "a\nkůň\n\n\n",
            "a\nkůň\n\n\n",
            ["a", "kůň", "", ""],
            2,
            "kůň",
            id="trailing_newlines",
        ),
        pytest.param(
            "one\x0cstill one\ntwo\n",
            "one\x0cstill one\ntwo\n",
            ["one\x0cstill one", "two"],
            2,
            "two",
            id="form_feed",
        ),
        pytest.param(
            "a\u2028b\u2029c\x85d\nnext\n",
            "a\u2028b\u2029c\x85d\nnext\n",
            ["a\u2028b\u2029c\x85d", "next"],
            2,
            "next",
            id="unicode_line_separators",
        ),
        pytest.param(
            "Příliš žluťoučký\nkůň úpěl ďábelské ódy\n",
            "Příliš žluťoučký\nkůň úpěl ďábelské ódy\n",
            ["Příliš žluťoučký", "kůň úpěl ďábelské ódy"],
            2,
            "kůň úpěl ďábelské ódy",
            id="czech",
        ),
        pytest.param(
            "first\r\n\r\nthird\r\nfourth\rfifth\r\n",
            "first\n\nthird\nfourth\nfifth\n",
            ["first", "", "third", "fourth", "fifth"],
            5,
            "fifth",
            id="crlf_and_cr",
        ),
        pytest.param(
            "  indented\n\ttab\ntrailing  \n",
            "  indented\n\ttab\ntrailing  \n",
            ["  indented", "\ttab", "trailing  "],
            3,
            "trailing",
            id="spaces_and_tabs",
        ),
        pytest.param(
            "50% 'quoted' \"double\" \\ %(id)s :text $1 ;--\nnext\n",
            "50% 'quoted' \"double\" \\ %(id)s :text $1 ;--\nnext\n",
            ["50% 'quoted' \"double\" \\ %(id)s :text $1 ;--", "next"],
            1,
            "%(id)s :text $1",
            id="characters_sql_cares_about",
        ),
    ],
)
def test_text_comes_back_exact_so_citations_still_verify(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    sent: str,
    stored: str,
    lines: list[str],
    cited_line: int,
    quote: str,
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="An answer.",
        citations=[Citation(start_line=cited_line, end_line=cited_line, quote=quote)],
    )

    uploaded = upload(client, documents_url, sent.encode())
    read = client.get(f"{URL}/{uploaded.json()['id']}").json()
    answer = client.post(
        "/api/ask", json={"document_id": read["id"], "question": "Hi"}
    ).json()

    assert stored_document(client, uploaded).text == stored
    assert read["lines"] == lines
    assert answer["status"] == "answered"
    assert answer["citations"][0]["start_line"] == cited_line
    assert f"{cited_line}: {lines[cited_line - 1]}\n" in fake_gemini.prompts[0]


def test_document_survives_an_app_restart(
    clean_database: DatabaseURL,
    start_app: StartApp,
    fake_gemini: FakeGemini,
) -> None:
    with start_app() as before_restart:
        documents_url = create_dataset(before_restart)
        uploaded = upload(
            before_restart, documents_url, b"The cat is orange.\n", "cat.txt"
        ).json()

    with start_app() as after_restart:
        listed = after_restart.get(documents_url).json()
        read = after_restart.get(f"{URL}/{uploaded['id']}").json()
        answer = after_restart.post(
            "/api/ask",
            json={"document_id": uploaded["id"], "question": "Which colour?"},
        ).json()

    assert listed == [uploaded]
    assert read == {**uploaded, "lines": ["The cat is orange."]}
    assert answer["status"] == "answered"
    assert answer["citations"][0]["filename"] == "cat.txt"
    assert "1: The cat is orange." in fake_gemini.prompts[0]


def test_apps_on_different_databases_do_not_share_documents(
    clean_database: DatabaseURL,
    database: DatabaseURL,
    start_app: StartApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_migrations(database)
    monkeypatch.setenv("DATABASE_URL", as_setting(clean_database))

    with start_app() as first:
        monkeypatch.setenv("DATABASE_URL", as_setting(database))
        with start_app() as second:
            first_url = create_dataset(first)
            upload(first, first_url)

            assert len(first.get(first_url).json()) == 1
            assert second.get(first_url).status_code == 404
            assert second.get("/api/datasets").json() == []
