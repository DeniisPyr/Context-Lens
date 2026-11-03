from unittest.mock import ANY

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from httpx2 import Response

from context_lens.dependencies import get_document_store
from context_lens.documents import Document, DocumentStore
from context_lens.main import create_app

URL = "/api/documents"
LIMIT = 1_000_000
BOM = b"\xef\xbb\xbf"


def upload(
    client: TestClient, content: bytes = b"hello", filename: str = "notes.txt"
) -> Response:
    return client.post(URL, files={"file": (filename, content)})


def stored_document(client: TestClient, response: Response) -> Document:
    store = get_document_store(Request({"type": "http", "app": client.app}))
    document = store.get(response.json()["id"])
    assert document is not None
    return document


def test_upload_returns_the_document_summary(client: TestClient) -> None:
    text = "Příliš žluťoučký\nkůň\n"

    response = upload(client, text.encode(), "poznámky.txt")

    assert response.status_code == 201
    assert response.json() == {"id": ANY, "filename": "poznámky.txt", "line_count": 2}
    assert stored_document(client, response).text == text


@pytest.mark.parametrize("filename", ["notes.txt", "notes.md", "NOTES.TXT", "Notes.Md"])
def test_extensions_are_case_insensitive(client: TestClient, filename: str) -> None:
    response = upload(client, filename=filename)

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
    client: TestClient, filename: str, content: bytes, status: int, detail: str
) -> None:
    response = upload(client, content, filename)

    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert client.get(URL).json() == []


def test_part_without_a_filename_is_a_validation_error(client: TestClient) -> None:
    # The HTTP client leaves out an empty filename, so the part is a plain form field.
    response = upload(client, filename="")

    assert response.status_code == 422
    assert client.get(URL).json() == []


def test_nul_in_the_filename_is_rejected(client: TestClient) -> None:
    # The HTTP client would percent-encode the NUL, so this sends the exact bytes.
    body = (
        b'--x\r\nContent-Disposition: form-data; name="file"; filename="a\x00.txt"'
        b"\r\n\r\nhello\r\n--x--\r\n"
    )

    response = client.post(
        URL, content=body, headers={"Content-Type": "multipart/form-data; boundary=x"}
    )

    assert response.status_code == 415
    assert "NUL" in response.json()["detail"]
    assert client.get(URL).json() == []


def test_file_at_the_size_limit_is_accepted(client: TestClient) -> None:
    response = upload(client, b"x" * LIMIT)

    assert response.status_code == 201
    assert len(client.get(URL).json()) == 1


def test_file_over_the_size_limit_is_rejected(client: TestClient) -> None:
    # Not valid UTF-8 either: the size is checked first, before any decoding.
    response = upload(client, b"\xff" * (LIMIT + 1))

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]
    assert client.get(URL).json() == []


def test_upload_limit_comes_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")

    with TestClient(create_app()) as client:
        response = upload(client, b"x" * 11)

        assert response.status_code == 413
        assert response.json() == {
            "detail": "The file must not be larger than 10 bytes."
        }
        assert client.get(URL).json() == []


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
def test_lines_match_an_editor(client: TestClient, text: str, lines: list[str]) -> None:
    response = upload(client, text.encode())

    assert response.status_code == 201
    assert response.json()["line_count"] == len(lines)
    assert stored_document(client, response).lines == lines


def test_document_without_text_has_no_lines() -> None:
    assert Document(id="1", filename="a.txt", text="").lines == []


def test_stored_text_has_no_bom_or_carriage_returns(client: TestClient) -> None:
    response = upload(client, BOM + b"first\r\nsecond\rthird\n")

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
    client: TestClient, filename: str, base_name: str
) -> None:
    response = upload(client, filename=filename)

    assert response.status_code == 201
    assert response.json()["filename"] == base_name


def test_list_is_empty_without_uploads(client: TestClient) -> None:
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == []


def test_list_is_in_upload_order_without_the_text(client: TestClient) -> None:
    names = ["z.txt", "a.md", "z.txt"]
    uploads = [upload(client, filename=name).json() for name in names]

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == uploads
    assert [item["filename"] for item in response.json()] == names
    assert all("text" not in item for item in response.json())


def test_store_get_finds_known_ids_and_returns_none_for_unknown_ones() -> None:
    store = DocumentStore()
    document = store.add("notes.txt", "hello\n")

    assert store.get(document.id) is document
    assert store.get("unknown") is None


def test_two_apps_do_not_share_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with TestClient(create_app()) as first, TestClient(create_app()) as second:
        upload(first)

        assert len(first.get(URL).json()) == 1
        assert second.get(URL).json() == []
