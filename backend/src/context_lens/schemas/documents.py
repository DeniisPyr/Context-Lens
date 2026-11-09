from typing import Self

from pydantic import BaseModel

from context_lens.services.documents import Document, DocumentInfo


class DocumentSummary(BaseModel):
    id: str
    filename: str
    line_count: int
    # None for a text file, which has no pages.
    page_count: int | None

    @classmethod
    def from_document(cls, document: Document | DocumentInfo) -> Self:
        return cls(
            id=document.id,
            filename=document.filename,
            line_count=document.line_count,
            page_count=document.page_count,
        )


class DocumentDetail(DocumentSummary):
    lines: list[str]
    # The line each page of a PDF starts on, as Document has them. None for a text file.
    page_starts: list[int] | None

    @classmethod
    def from_document(cls, document: Document) -> Self:
        # Document.lines splits the text on every read, so read it once.
        lines = document.lines
        page_starts = document.page_starts
        return cls(
            id=document.id,
            filename=document.filename,
            line_count=len(lines),
            page_count=document.page_count,
            lines=lines,
            page_starts=None if page_starts is None else list(page_starts),
        )
