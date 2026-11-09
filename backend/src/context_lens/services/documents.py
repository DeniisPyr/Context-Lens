import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import PureWindowsPath
from typing import Protocol

from pypdf import PdfReader

from context_lens.clients.gemini import GeminiClient
from context_lens.services.indexing import EmbeddedChunk, index_lines

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
# A constant rather than a setting, because it bounds what this code does wherever it
# runs. pypdf does some work for every page, even one without text, and the limit on
# the text doesn't bound that: a 1 MB file can hold tens of thousands of empty pages.
# An ordinary page holds 2 to 3 kB of text, so a PDF within that limit has about 500
# pages at most, and only one with very little text a page, such as slides, has more
# than this.
MAX_PDF_PAGES = 1_000

# pypdf logs the problems it works around in a broken PDF, and some of its messages
# quote the file, such as the text around something it couldn't parse. Document text
# must never reach the logs, so nothing pypdf logs gets through. Its loggers are one
# per module, and they all take their level from this one.
logging.getLogger("pypdf").setLevel(logging.CRITICAL + 1)


class InvalidDocumentError(Exception):
    """The uploaded file cannot be stored as a document."""


class UnsupportedDocumentError(InvalidDocumentError):
    """The file has the wrong type, or its name or content is not plain text."""


class DocumentTooLargeError(InvalidDocumentError):
    """The file is over the upload size limit."""


class EmptyDocumentError(InvalidDocumentError):
    """The file has no text in it."""


class DocumentNotFoundError(Exception):
    """No stored document has the requested id."""

    def __init__(self) -> None:
        super().__init__("Document not found.")


class DuplicateDocumentError(Exception):
    """The dataset already holds a document with this filename."""

    def __init__(self, filename: str) -> None:
        super().__init__(f"{filename} is already in this dataset.")


def split_lines(text: str) -> list[str]:
    if not text:
        return []
    # Not str.splitlines(): it also splits on form feeds and Unicode separators,
    # so its numbering would disagree with a text editor and break citations.
    return text.removesuffix("\n").split("\n")


@dataclass(frozen=True)
class DocumentInfo:
    """A document without its text, for listing many without reading them all."""

    id: str
    filename: str
    line_count: int
    page_count: int | None


@dataclass(frozen=True)
class Document:
    id: str
    filename: str
    text: str
    # For a PDF, the line each page starts on, numbered from 1 like the lines. A page
    # without text starts on the same line as the page after it, or on the line after
    # the last when no page with text comes after it. None for a text file.
    page_starts: tuple[int, ...] | None = None

    @property
    def lines(self) -> list[str]:
        return split_lines(self.text)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def page_count(self) -> int | None:
        return None if self.page_starts is None else len(self.page_starts)


@dataclass(frozen=True)
class Upload:
    """An uploaded file, read into the text its document stores."""

    filename: str
    text: str
    page_starts: tuple[int, ...] | None = None


class DocumentStorage(Protocol):
    """What these functions need from the store in db/, which they don't import."""

    async def check_can_add(
        self, dataset_id: str, filename: str, max_documents: int
    ) -> None: ...

    async def add(
        self,
        dataset_id: str,
        filename: str,
        text: str,
        chunks: list[EmbeddedChunk],
        max_documents: int,
        *,
        page_starts: tuple[int, ...] | None = None,
    ) -> Document: ...

    async def get(self, document_id: str) -> Document | None: ...


def _clean_filename(filename: str | None) -> str:
    # PureWindowsPath splits on both / and \, so it handles paths from any client.
    path = PureWindowsPath(filename or "")
    # Names like "/" or "C:\" have no suffix, so this rejects them too.
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UnsupportedDocumentError("Only .txt, .md and .pdf files are accepted.")
    if "\x00" in path.name:
        raise UnsupportedDocumentError("The filename must not contain NUL characters.")
    return path.name


def _decode_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("The file must be valid UTF-8 text.") from exc
    if "\x00" in text:
        raise UnsupportedDocumentError("The file must not contain NUL characters.")
    return text


def _normalize_line_breaks(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


@contextmanager
def _pdf_errors() -> Iterator[None]:
    # pypdf raises all kinds of errors on a broken file, not only its own, so any error
    # is caught. Their messages can quote the file, so each becomes the same refusal,
    # without the error chained on, and nothing it quotes can reach the logs.
    try:
        yield
    except Exception:  # noqa: BLE001
        raise UnsupportedDocumentError("The file must be a valid PDF.") from None


def _page_lines(text: str) -> list[str]:
    # pypdf keeps the surrogates a font maps characters to, and UTF-8 can't hold one on
    # its own: a pair is joined into its character, and any other is replaced.
    text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
    # Postgres can't store NUL in text. A text file with one is refused, but in a PDF
    # it comes from a font that pypdf can't map, so it's left out instead.
    return split_lines(_normalize_line_breaks(text.replace("\x00", "")))


def _read_pdf(data: bytes, max_bytes: int) -> tuple[str, tuple[int, ...]]:
    with _pdf_errors():
        reader = PdfReader(BytesIO(data))
        encrypted = reader.is_encrypted
    # Even one that opens without a password, as many do: encryption is how the
    # author of a PDF restricts copying its text.
    if encrypted:
        raise UnsupportedDocumentError(
            "The PDF must not be password-protected or encrypted."
        )
    with _pdf_errors():
        page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise DocumentTooLargeError(
            f"The PDF must not have more than {MAX_PDF_PAGES:,} pages."
        )
    lines: list[str] = []
    page_starts: list[int] = []
    size = 0
    for number in range(page_count):
        with _pdf_errors():
            page_text = reader.pages[number].extract_text()
        page_lines = _page_lines(page_text)
        # The text file's limit, on the text as it's stored, so that embedding an upload
        # costs no more however well a PDF compresses. Checked page by page, so that a
        # PDF over it isn't read to the end.
        size += sum(len(line.encode()) + 1 for line in page_lines)
        if size > max_bytes:
            raise DocumentTooLargeError(
                f"The text of the PDF must not be larger than {max_bytes:,} bytes."
            )
        page_starts.append(len(lines) + 1)
        lines += page_lines
    if not any(line.strip() for line in lines):
        raise EmptyDocumentError(
            "This PDF has no text that can be read. Scanned pages aren't supported."
        )
    # A line break after every line, the last too, so that a last line that's empty
    # is still a line when the text is split again.
    return "".join(f"{line}\n" for line in lines), tuple(page_starts)


def read_upload(filename: str | None, data: bytes, max_bytes: int) -> Upload:
    clean_name = _clean_filename(filename)
    if len(data) > max_bytes:
        raise DocumentTooLargeError(
            f"The file must not be larger than {max_bytes:,} bytes."
        )
    if clean_name.lower().endswith(".pdf"):
        text, page_starts = _read_pdf(data, max_bytes)
        return Upload(clean_name, text, page_starts)
    text = _decode_text(data)
    if not text.strip():
        raise EmptyDocumentError("The file must not be empty.")
    return Upload(clean_name, _normalize_line_breaks(text))


async def add_upload(
    store: DocumentStorage,
    gemini: GeminiClient,
    dataset_id: str,
    filename: str | None,
    data: bytes,
    *,
    max_bytes: int,
    max_documents: int,
) -> Document:
    # In a worker thread, so that the event loop goes on serving other requests while
    # a PDF is read: pypdf is pure Python, and a big PDF can take it a second or more.
    # Our limits on the file, its pages and its text, and pypdf's own on the work for
    # each page, bound how long.
    upload = await asyncio.to_thread(read_upload, filename, data, max_bytes)
    # Before Gemini, so that an upload the store is going to refuse costs nothing.
    await store.check_can_add(dataset_id, upload.filename, max_documents)
    # Between the store's transactions, so that no connection waits for Gemini.
    chunks = await index_lines(gemini, upload.filename, split_lines(upload.text))
    return await store.add(
        dataset_id,
        upload.filename,
        upload.text,
        chunks,
        max_documents,
        page_starts=upload.page_starts,
    )


async def get_document(store: DocumentStorage, document_id: str) -> Document:
    document = await store.get(document_id)
    if document is None:
        raise DocumentNotFoundError
    return document
