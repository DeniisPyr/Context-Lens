from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class Document:
    id: str
    filename: str
    text: str

    @property
    def lines(self) -> list[str]:
        if not self.text:
            return []
        # Not str.splitlines(): it also splits on form feeds and Unicode separators,
        # so its numbering would disagree with a text editor and break citations.
        return self.text.removesuffix("\n").split("\n")


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
