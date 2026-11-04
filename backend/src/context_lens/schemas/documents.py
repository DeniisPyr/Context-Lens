from typing import Self

from pydantic import BaseModel

from context_lens.services.documents import Document


class DocumentSummary(BaseModel):
    id: str
    filename: str
    line_count: int

    @classmethod
    def from_document(cls, document: Document) -> Self:
        return cls(
            id=document.id, filename=document.filename, line_count=len(document.lines)
        )


class DocumentDetail(DocumentSummary):
    lines: list[str]

    @classmethod
    def from_document(cls, document: Document) -> Self:
        # Document.lines splits the text on every read, so read it once.
        lines = document.lines
        return cls(
            id=document.id,
            filename=document.filename,
            line_count=len(lines),
            lines=lines,
        )
