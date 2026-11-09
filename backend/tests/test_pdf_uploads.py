import asyncio
import logging
from collections.abc import Callable
from io import BytesIO
from traceback import format_exception
from typing import Any

import pytest
from conftest import (
    FakeGemini,
    StartApp,
    content_stream,
    create_dataset,
    dataset_id_of,
    pdf_bytes,
    pdf_file,
    pdf_writer,
)
from fastapi import Request
from fastapi.testclient import TestClient
from httpx2 import Response
from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import URL

from context_lens.dependencies import get_document_store
from context_lens.services import documents
from context_lens.services.documents import (
    Document,
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentError,
    read_upload,
)

LIMIT = 1_000_000
NOT_A_PDF = "The file must be a valid PDF."
ENCRYPTED = "The PDF must not be password-protected or encrypted."
NO_TEXT = "This PDF has no text that can be read. Scanned pages aren't supported."
REPORT = [
    ["Quarterly report", "Sales rose by 4%."],
    [],
    ["  Costs (mostly travel) fell.", "Back\\slash, café and žár"],
]
REPORT_TEXT = (
    "Quarterly report\nSales rose by 4%.\n"
    "  Costs (mostly travel) fell.\nBack\\slash, café and žár\n"
)
# Long and all alike, so that a file of them compresses to much less than its text.
LONG_LINE = "x" * 200


def lines_on_pages(*line_counts: int) -> list[list[str]]:
    return [
        [f"Page {page} line {line}" for line in range(1, count + 1)]
        for page, count in enumerate(line_counts, start=1)
    ]


def encrypted_pdf(user_password: str, **options: Any) -> bytes:
    writer = pdf_writer([["Private text"]])
    writer.encrypt(user_password, "owner password", **options)
    return pdf_bytes(writer)


def with_content(operators: bytes) -> bytes:
    writer = pdf_writer([["Replaced"]])
    writer.pages[0].replace_contents(content_stream(operators))
    return pdf_bytes(writer)


# pypdf fails on the stray brace, and its error quotes the text around it.
FAILING_PDF = with_content(b"BT /F1 12 Tf 72 720 Td (Private text) Tj } ET")
# The same brace in a property list, where pypdf logs its error, with the text around
# it, and goes on.
LOGGING_PDF = with_content(
    b"BT /F1 12 Tf 72 720 Td (Visible text) Tj "
    b"/Span << /ActualText (Private alt text) /X } BDC (Private shown text) Tj EMC ET"
)


def record_pages_read(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    # The number, from 0, of each page whose text is extracted.
    read: list[int] = []
    extract_text = PageObject.extract_text

    def recording(page: PageObject, *args: Any, **kwargs: Any) -> str:
        read.append(page.page_number)
        return extract_text(page, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", recording)
    return read


def extract_as(monkeypatch: pytest.MonkeyPatch, extract: Callable[[], str]) -> None:
    monkeypatch.setattr(PageObject, "extract_text", lambda page, **kwargs: extract())


def test_text_of_the_pages_is_read_in_their_order() -> None:
    upload = read_upload("report.pdf", pdf_file(REPORT), LIMIT)

    assert upload.filename == "report.pdf"
    assert upload.text == REPORT_TEXT
    assert upload.page_starts == (1, 3, 3)


@pytest.mark.parametrize(
    ("line_counts", "page_starts"),
    [
        pytest.param([4, 0, 3], (1, 5, 5), id="empty_page_between"),
        pytest.param([2], (1,), id="one_page"),
        pytest.param([1, 1, 1], (1, 2, 3), id="a_line_each"),
        pytest.param([0, 2], (1, 1), id="empty_first_page"),
        pytest.param([2, 3, 0], (1, 3, 6), id="empty_last_page"),
        pytest.param([1, 0, 0], (1, 2, 2), id="empty_last_pages"),
        pytest.param([0, 0, 2, 0], (1, 1, 1, 3), id="empty_pages_around"),
    ],
)
def test_each_page_starts_after_the_lines_of_the_pages_before(
    line_counts: list[int], page_starts: tuple[int, ...]
) -> None:
    upload = read_upload("report.pdf", pdf_file(lines_on_pages(*line_counts)), LIMIT)

    assert upload.page_starts == page_starts
    assert Document("1", "report.pdf", upload.text).line_count == sum(line_counts)


def test_lines_are_numbered_through_the_whole_document() -> None:
    pages = lines_on_pages(3, 0, 2, 4)

    upload = read_upload("report.pdf", pdf_file(pages), LIMIT)

    lines = Document("1", "report.pdf", upload.text).lines
    assert lines == [line for page in pages for line in page]
    for page, start in zip(pages, upload.page_starts, strict=True):
        assert lines[start - 1 : start - 1 + len(page)] == page


def test_line_breaks_nul_and_surrogates_are_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A surrogate pair in two pieces, as pypdf can leave one, and a lone surrogate.
    extract_as(monkeypatch, lambda: "one\r\ntwo\rthree\x00four😀 \ud800 end")

    upload = read_upload("report.pdf", pdf_file([["Replaced"]]), LIMIT)

    assert upload.text == "one\ntwo\nthreefour\U0001f600 � end\n"
    assert upload.page_starts == (1,)


def test_whitespace_lines_count_as_in_a_text_file() -> None:
    upload = read_upload("report.pdf", pdf_file([["  ", "Text"], ["\t"]]), LIMIT)

    assert upload.text == "  \nText\n\t\n"
    assert upload.page_starts == (1, 3)


def test_text_file_has_no_page_starts() -> None:
    upload = read_upload("notes.txt", b"one\ntwo\n", LIMIT)

    assert upload.page_starts is None


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"Quarterly report\n", id="text"),
        pytest.param(b"%PDF-1.7\n", id="header_only"),
        pytest.param(pdf_file(REPORT)[:600], id="cut_short"),
        pytest.param(FAILING_PDF, id="broken_page"),
    ],
)
def test_file_that_is_not_a_readable_pdf_is_refused(content: bytes) -> None:
    with pytest.raises(UnsupportedDocumentError) as error:
        read_upload("report.pdf", content, LIMIT)

    assert str(error.value) == NOT_A_PDF


def test_refusal_of_a_pdf_pypdf_fails_on_does_not_quote_it() -> None:
    # pypdf's own error does quote the text around where it failed.
    page = PdfReader(BytesIO(FAILING_PDF)).pages[0]
    with pytest.raises(PdfReadError, match="Private text"):
        page.extract_text()

    with pytest.raises(UnsupportedDocumentError) as refusal:
        read_upload("report.pdf", FAILING_PDF, LIMIT)

    message = "".join(format_exception(refusal.value))
    assert "Traceback" in message  # Proves the check is looking at something.
    assert "Private" not in message
    assert "PdfReadError" not in message


@pytest.mark.parametrize("error_type", [PdfReadError, ValueError, RecursionError])
def test_any_error_in_reading_is_a_refusal_without_the_error(
    monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    def fail() -> str:
        raise error_type("Private text")

    extract_as(monkeypatch, fail)

    with pytest.raises(UnsupportedDocumentError, match=NOT_A_PDF) as refusal:
        read_upload("report.pdf", pdf_file([["Visible"]]), LIMIT)

    message = "".join(format_exception(refusal.value))
    assert "Private" not in message
    assert error_type.__name__ not in message


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(encrypted_pdf("secret"), id="password"),
        pytest.param(encrypted_pdf(""), id="opens_without_a_password"),
        pytest.param(encrypted_pdf("secret", algorithm="AES-256"), id="aes"),
    ],
)
def test_encrypted_pdf_is_refused(content: bytes) -> None:
    with pytest.raises(UnsupportedDocumentError) as error:
        read_upload("report.pdf", content, LIMIT)

    assert str(error.value) == ENCRYPTED


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param([[]], id="one_empty_page"),
        pytest.param([[], [], []], id="empty_pages"),
        pytest.param([["   "], [" ", "\t"]], id="only_whitespace"),
    ],
)
def test_pdf_without_text_is_refused(pages: list[list[str]]) -> None:
    with pytest.raises(EmptyDocumentError) as error:
        read_upload("report.pdf", pdf_file(pages), LIMIT)

    assert str(error.value) == NO_TEXT


def test_text_at_the_limit_is_accepted() -> None:
    content = pdf_file([[LONG_LINE] * 10, [LONG_LINE] * 10])
    text_size = 20 * len(f"{LONG_LINE}\n")
    assert len(content) < text_size  # The file itself is within the limit.

    upload = read_upload("report.pdf", content, text_size)

    assert len(upload.text.encode()) == text_size


def test_text_over_the_limit_is_refused() -> None:
    content = pdf_file([[LONG_LINE] * 10, [LONG_LINE] * 10])
    text_size = 20 * len(f"{LONG_LINE}\n")
    assert len(content) < text_size - 1

    with pytest.raises(DocumentTooLargeError) as error:
        read_upload("report.pdf", content, text_size - 1)

    assert str(error.value) == (
        f"The text of the PDF must not be larger than {text_size - 1:,} bytes."
    )


def test_limit_counts_the_text_in_utf8() -> None:
    # Two bytes each in UTF-8, and one each as Windows-1252 in the file.
    content = pdf_file([["é" * 1_000]])
    assert len(content) < 2_000

    with pytest.raises(DocumentTooLargeError):
        read_upload("report.pdf", content, 2_000)
    assert read_upload("report.pdf", content, 2_001).text == "é" * 1_000 + "\n"


def test_text_over_the_limit_stops_the_reading_at_that_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = record_pages_read(monkeypatch)
    # Each page has 2,010 bytes of text, so the second is over the limit.
    content = pdf_file([[LONG_LINE] * 10] * 5)
    assert len(content) < 3_000

    with pytest.raises(DocumentTooLargeError):
        read_upload("report.pdf", content, 3_000)

    assert read == [0, 1]


def test_more_pages_than_the_limit_are_refused_before_any_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)
    read = record_pages_read(monkeypatch)

    with pytest.raises(DocumentTooLargeError) as error:
        read_upload("report.pdf", pdf_file(lines_on_pages(1, 1, 1)), LIMIT)

    assert str(error.value) == "The PDF must not have more than 2 pages."
    assert read == []


def test_pages_at_the_limit_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)

    upload = read_upload("report.pdf", pdf_file(lines_on_pages(1, 1)), LIMIT)

    assert upload.page_starts == (1, 2)


def test_pdf_over_the_real_page_limit_is_refused() -> None:
    content = pdf_file([["Text"]] + [[]] * 1_000)

    with pytest.raises(DocumentTooLargeError) as error:
        read_upload("report.pdf", content, LIMIT)

    assert str(error.value) == "The PDF must not have more than 1,000 pages."


def test_file_size_is_checked_before_the_pdf_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = record_pages_read(monkeypatch)
    content = pdf_file(REPORT)

    with pytest.raises(DocumentTooLargeError, match="The file must not be larger"):
        read_upload("report.pdf", content, len(content) - 1)

    assert read == []


def test_pypdf_would_log_text_from_the_logging_pdf(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Proves that LOGGING_PDF makes pypdf log its text when it's let through.
    caplog.set_level(logging.WARNING, logger="pypdf")

    PdfReader(BytesIO(LOGGING_PDF)).pages[0].extract_text()

    assert "Private shown text" in caplog.text


def test_reading_a_pdf_logs_nothing_at_all_from_pypdf(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    upload = read_upload("report.pdf", LOGGING_PDF, LIMIT)

    assert "Visible text" in upload.text
    assert caplog.records == []


def upload(
    client: TestClient,
    documents_url: str,
    content: bytes = pdf_file(REPORT),
    filename: str = "report.pdf",
) -> Response:
    return client.post(documents_url, files={"file": (filename, content)})


def stored_document(client: TestClient, document_id: str) -> Document:
    store = get_document_store(Request({"type": "http", "app": client.app}))
    # On the app's event loop, because the store's connections belong to it.
    document = client.portal.call(store.get, document_id)
    assert document is not None
    return document


@pytest.mark.parametrize("filename", ["report.pdf", "REPORT.PDF", "Report.Pdf"])
def test_uploaded_pdf_is_stored_with_its_page_starts(
    client: TestClient, documents_url: str, filename: str
) -> None:
    response = upload(client, documents_url, filename=filename)

    assert response.status_code == 201
    assert response.json()["filename"] == filename
    assert response.json()["line_count"] == 4
    document = stored_document(client, response.json()["id"])
    assert document.text == REPORT_TEXT
    assert document.page_starts == (1, 3, 3)


def test_uploaded_pdf_is_split_into_chunks_of_its_lines(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    fake_gemini.embedded.clear()

    upload(client, documents_url)

    [texts] = fake_gemini.embedded
    assert "Sales rose by 4%.\n  Costs (mostly travel) fell." in texts[0]


@pytest.mark.parametrize(
    ("content", "status", "detail"),
    [
        pytest.param(b"Quarterly report\n", 415, NOT_A_PDF, id="not_a_pdf"),
        pytest.param(FAILING_PDF, 415, NOT_A_PDF, id="broken_page"),
        pytest.param(encrypted_pdf("secret"), 415, ENCRYPTED, id="encrypted"),
        pytest.param(pdf_file([[], []]), 422, NO_TEXT, id="no_text"),
    ],
)
def test_refused_pdf_stores_nothing_and_costs_nothing(
    client: TestClient,
    documents_url: str,
    fake_gemini: FakeGemini,
    content: bytes,
    status: int,
    detail: str,
) -> None:
    fake_gemini.embedded.clear()

    response = upload(client, documents_url, content)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert client.get(documents_url).json() == []
    assert fake_gemini.embedded == []


def test_pdf_with_too_many_pages_is_refused(
    client: TestClient, documents_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)

    response = upload(client, documents_url, pdf_file(lines_on_pages(1, 1, 1)))

    assert response.status_code == 413
    assert response.json() == {"detail": "The PDF must not have more than 2 pages."}
    assert client.get(documents_url).json() == []


@pytest.mark.usefixtures("clean_database")
def test_limit_on_the_text_comes_from_the_settings(
    start_app: StartApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "3000")
    content = pdf_file([[LONG_LINE] * 10] * 2)
    assert len(content) <= 3_000

    with start_app() as client:
        documents_url = create_dataset(client)

        response = upload(client, documents_url, content)

        assert response.status_code == 413
        assert response.json() == {
            "detail": "The text of the PDF must not be larger than 3,000 bytes."
        }
        assert client.get(documents_url).json() == []


def event_loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def test_pdf_is_read_off_the_event_loop(
    client: TestClient, documents_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_the_loop: list[bool] = []
    open_pdf = documents.PdfReader
    extract_text = PageObject.extract_text

    def opening(*args: Any, **kwargs: Any) -> PdfReader:
        on_the_loop.append(event_loop_running())
        return open_pdf(*args, **kwargs)

    def extracting(page: PageObject, *args: Any, **kwargs: Any) -> str:
        on_the_loop.append(event_loop_running())
        return extract_text(page, *args, **kwargs)

    monkeypatch.setattr(documents, "PdfReader", opening)
    monkeypatch.setattr(PageObject, "extract_text", extracting)

    response = upload(client, documents_url)

    assert response.status_code == 201
    # Opened, then each of the three pages read, and none of it on the loop.
    assert on_the_loop == [False] * 4


@pytest.mark.parametrize(
    ("content", "status"),
    [
        pytest.param(LOGGING_PDF, 201, id="logged_by_pypdf"),
        pytest.param(FAILING_PDF, 415, id="failed_in_pypdf"),
    ],
)
def test_uploading_a_pdf_logs_nothing_from_its_text(
    client: TestClient,
    documents_url: str,
    caplog: pytest.LogCaptureFixture,
    content: bytes,
    status: int,
) -> None:
    caplog.set_level(logging.DEBUG)

    response = upload(client, documents_url, content)

    assert response.status_code == status
    assert "Private" not in caplog.text


def ask(client: TestClient, documents_url: str) -> None:
    dataset_id = dataset_id_of(documents_url)
    question = {"dataset_id": dataset_id, "question": "Which pets are there?"}
    assert client.post("/api/ask", json=question).status_code == 200


def test_prompt_shows_a_pdf_exactly_as_it_shows_a_text_file(
    client: TestClient, documents_url: str, fake_gemini: FakeGemini
) -> None:
    pages = [["The cat is orange.", "  It sleeps (a lot)."], [], ["The dog is brown."]]
    text_url = create_dataset(client, "Text")
    upload(client, documents_url, pdf_file(pages), "pets.pdf")
    lines = [line for page in pages for line in page]
    upload(client, text_url, "\n".join(lines).encode(), "pets.pdf.txt")

    ask(client, documents_url)
    ask(client, text_url)

    pdf_prompt, text_prompt = fake_gemini.prompts
    assert pdf_prompt == (
        '<excerpt file="pets.pdf" lines="1-3">\n'
        "1: The cat is orange.\n"
        "2:   It sleeps (a lot).\n"
        "3: The dog is brown.\n"
        "</excerpt>\n"
        "\n"
        "Question: Which pets are there?"
    )
    assert pdf_prompt == text_prompt.replace("pets.pdf.txt", "pets.pdf")


def test_pdf_documents_and_their_pages_survive_an_app_restart(
    clean_database: URL, start_app: StartApp
) -> None:
    with start_app() as before_restart:
        documents_url = create_dataset(before_restart)
        uploaded = upload(before_restart, documents_url).json()

    with start_app() as after_restart:
        document = stored_document(after_restart, uploaded["id"])

    assert document.text == REPORT_TEXT
    assert document.page_starts == (1, 3, 3)
