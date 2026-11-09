from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from context_lens.services.answering import (
    AnswerStatus,
    Citation,
    Clarification,
    Excerpt,
    sources_by_name,
)
from context_lens.services.search import DatasetAnswer


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Gemini's own text, sent back as the app returned it, so it may be longer than a
    # user's question.
    question: str = Field(min_length=1, max_length=4000)
    reply: str = Field(min_length=1, max_length=2000)


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dataset_id: str
    question: str = Field(min_length=1, max_length=2000)
    # When the app answered this question with a clarifying question, the user's reply.
    clarification: ClarificationRequest | None = None

    def to_clarification(self) -> Clarification | None:
        if self.clarification is None:
            return None
        return Clarification(
            question=self.clarification.question, reply=self.clarification.reply
        )


class CitationResponse(BaseModel):
    document_id: str
    filename: str
    start_line: int
    end_line: int
    # The pages of a PDF that hold start_line and end_line. None for a text file.
    start_page: int | None
    end_page: int | None
    quote: str

    @classmethod
    def from_citation(
        cls, citation: Citation, source: Excerpt, result: DatasetAnswer
    ) -> Self:
        return cls(
            document_id=source.document_id,
            filename=source.filename,
            start_line=citation.start_line,
            end_line=citation.end_line,
            start_page=result.page_of(source.document_id, citation.start_line),
            end_page=result.page_of(source.document_id, citation.end_line),
            quote=citation.quote,
        )


class AskResponse(BaseModel):
    status: AnswerStatus
    answer: str
    citations: list[CitationResponse]

    @classmethod
    def from_answer(cls, result: DatasetAnswer) -> Self:
        # Verification let through only citations of files that Gemini was shown.
        sources = sources_by_name(result.excerpts)
        return cls(
            status=result.answer.status,
            answer=result.answer.answer,
            citations=[
                CitationResponse.from_citation(citation, sources[citation.file], result)
                for citation in result.answer.citations
            ],
        )
