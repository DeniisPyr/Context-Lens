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
