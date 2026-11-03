from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from context_lens.services.answering import AnswerStatus, ModelAnswer
from context_lens.services.documents import Document


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str
    question: str = Field(min_length=1, max_length=2000)


class CitationResponse(BaseModel):
    document_id: str
    filename: str
    start_line: int
    end_line: int
    quote: str


class AskResponse(BaseModel):
    status: AnswerStatus
    answer: str
    citations: list[CitationResponse]

    @classmethod
    def from_answer(cls, answer: ModelAnswer, document: Document) -> Self:
        return cls(
            status=answer.status,
            answer=answer.answer,
            citations=[
                CitationResponse(
                    document_id=document.id,
                    filename=document.filename,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    quote=citation.quote,
                )
                for citation in answer.citations
            ],
        )
