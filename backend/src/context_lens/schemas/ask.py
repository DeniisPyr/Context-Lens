from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from context_lens.services.answering import AnswerStatus, sources_by_name
from context_lens.services.search import DatasetAnswer


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dataset_id: str
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
    def from_answer(cls, result: DatasetAnswer) -> Self:
        # Verification let through only citations of files that Gemini was shown.
        sources = sources_by_name(result.excerpts)
        return cls(
            status=result.answer.status,
            answer=result.answer.answer,
            citations=[
                CitationResponse(
                    document_id=sources[citation.file].document_id,
                    filename=sources[citation.file].filename,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    quote=citation.quote,
                )
                for citation in result.answer.citations
            ],
        )
