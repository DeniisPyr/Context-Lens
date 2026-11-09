from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, get_args

from context_lens.clients.gemini import GeminiClient
from context_lens.evaluation.cases import Question
from context_lens.evaluation.dataset import DATASET_ID, ChunkIndex, DocumentsById
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    Excerpt,
    ask_about_excerpts,
    build_prompt,
    verify_answer,
)
from context_lens.services.documents import Document
from context_lens.services.search import (
    DatasetAnswer,
    FoundChunk,
    answer_from_dataset,
    excerpts_from_chunks,
)

MethodName = Literal["rag", "whole_document"]
METHODS: tuple[MethodName, ...] = get_args(MethodName)


class Method(Protocol):
    @property
    def name(self) -> MethodName: ...

    async def answer(
        self, question: Question, gemini: GeminiClient
    ) -> DatasetAnswer: ...


def document_excerpt(document: Document) -> Excerpt:
    # The whole document, so the lines Gemini is shown are the real ones.
    lines = dict(enumerate(document.lines, start=1))
    return Excerpt(document_id=document.id, filename=document.filename, lines=lines)


@dataclass(frozen=True)
class WholeDocuments:
    """How the app answered before search: with the documents whole in the prompt."""

    name: ClassVar[MethodName] = "whole_document"
    documents: dict[str, Document]

    def excerpts(self, question: Question) -> list[Excerpt]:
        # The question's own document first, then the others its evidence and its
        # cases are in.
        return [document_excerpt(self.documents[name]) for name in question.files]

    def prompt_characters(self, question: Question) -> int:
        prompt = build_prompt(question.question, self.excerpts(question))
        return len(SYSTEM_INSTRUCTION) + len(prompt)

    async def answer(self, question: Question, gemini: GeminiClient) -> DatasetAnswer:
        excerpts = self.excerpts(question)
        answer = await ask_about_excerpts(question.question, excerpts, gemini)
        return DatasetAnswer(answer=verify_answer(answer, excerpts), excerpts=excerpts)


@dataclass(frozen=True)
class DatasetSearch:
    """How the app answers now: from the chunks a search of the whole dataset finds."""

    name: ClassVar[MethodName] = "rag"
    chunks: ChunkIndex
    documents: DocumentsById
    chunks_per_question: int

    async def answer(self, question: Question, gemini: GeminiClient) -> DatasetAnswer:
        # The app's own function, so that what's measured is what the app does.
        return await answer_from_dataset(
            question.question,
            DATASET_ID,
            self.chunks,
            self.documents,
            gemini,
            self.chunks_per_question,
        )


def prompt_characters_at_most(
    question: Question, chunks: list[FoundChunk], limit: int
) -> int:
    # The prompt if the largest chunks were found, each as an excerpt of its own.
    # Chunks of a document that touch are merged into one excerpt, which only saves
    # characters, so no search can find chunks that make a longer prompt.
    excerpts = [
        excerpt for chunk in chunks for excerpt in excerpts_from_chunks([chunk])
    ]
    excerpts.sort(key=lambda excerpt: len(build_prompt("", [excerpt])), reverse=True)
    prompt = build_prompt(question.question, excerpts[:limit])
    return len(SYSTEM_INSTRUCTION) + len(prompt)
