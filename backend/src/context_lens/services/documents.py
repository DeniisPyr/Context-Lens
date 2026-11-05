from dataclasses import dataclass
from pathlib import PureWindowsPath
from uuid import uuid4

ALLOWED_EXTENSIONS = {".txt", ".md"}


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


@dataclass(frozen=True)
class Document:
    id: str
    filename: str
    text: str

    @property
    def lines(self) -> list[str]:
        return split_lines(self.text)

    @property
    def line_count(self) -> int:
        return len(self.lines)


class DocumentStore:
    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    def add(self, filename: str, text: str) -> Document:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        document = Document(id=str(uuid4()), filename=filename, text=normalized)
        self._documents[document.id] = document
        return document

    def get(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)

    def list_all(self) -> list[Document]:
        return list(self._documents.values())


def _clean_filename(filename: str | None) -> str:
    # PureWindowsPath splits on both / and \, so it handles paths from any client.
    path = PureWindowsPath(filename or "")
    # Names like "/" or "C:\" have no suffix, so this rejects them too.
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UnsupportedDocumentError("Only .txt and .md files are accepted.")
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


def add_upload(
    store: DocumentStore, filename: str | None, data: bytes, max_bytes: int
) -> Document:
    clean_name = _clean_filename(filename)
    if len(data) > max_bytes:
        raise DocumentTooLargeError(
            f"The file must not be larger than {max_bytes:,} bytes."
        )
    text = _decode_text(data)
    if not text.strip():
        raise EmptyDocumentError("The file must not be empty.")
    return store.add(clean_name, text)


def get_document(store: DocumentStore, document_id: str) -> Document:
    document = store.get(document_id)
    if document is None:
        raise DocumentNotFoundError("Document not found.")
    return document
