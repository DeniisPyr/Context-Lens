from dataclasses import dataclass
from typing import Protocol

from context_lens.clients.gemini import GeminiClient
from context_lens.services.answering import (
    Excerpt,
    ModelAnswer,
    ask_about_excerpts,
    not_found_answer,
    sources_by_name,
    verify_answer,
)
from context_lens.services.documents import Document
from context_lens.services.embeddings import query_embedding_text


@dataclass(frozen=True)
class FoundChunk:
    document_id: str
    filename: str
    # Where the chunk comes in its document, counted from 0.
    position: int
    # Numbered from 1 and inclusive, like the lines of a citation.
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class DatasetAnswer:
    answer: ModelAnswer
    # What Gemini was shown, so that each citation's file leads back to its document.
    excerpts: list[Excerpt]


class ChunkSearch(Protocol):
    """What these functions need from the store in db/, which they don't import."""

    async def check_can_search(self, dataset_id: str) -> None: ...

    async def search(
        self, dataset_id: str, embedding: list[float], limit: int
    ) -> list[FoundChunk]: ...


class DocumentLookup(Protocol):
    """What these functions need from the store in db/, which they don't import."""

    async def get_many(self, document_ids: list[str]) -> list[Document]: ...


def _lines(chunks: list[FoundChunk]) -> dict[int, str]:
    # A line too long for one chunk is stored as several, each holding a piece of it,
    # so the pieces found of one line are joined with a space, in their order. That's
    # only for Gemini to read: quotes are checked against the real line.
    pieces: dict[int, list[str]] = {}
    for chunk in sorted(chunks, key=lambda chunk: chunk.position):
        numbers = range(chunk.start_line, chunk.end_line + 1)
        for number, line in zip(numbers, chunk.text.split("\n"), strict=True):
            pieces.setdefault(number, []).append(line)
    return {number: " ".join(pieces[number]) for number in sorted(pieces)}


def _runs(lines: dict[int, str]) -> list[dict[int, str]]:
    # Lines whose numbers follow on make one run, so chunks that touch are merged.
    runs: list[dict[int, str]] = []
    for number, line in lines.items():
        if runs and number - 1 in runs[-1]:
            runs[-1][number] = line
        else:
            runs.append({number: line})
    return runs


def excerpts_from_chunks(chunks: list[FoundChunk]) -> list[Excerpt]:
    # The chunks come nearest first, so a document comes before another when its
    # nearest chunk does. Its excerpts follow in line order, so that the context reads
    # as the document does.
    by_document: dict[str, list[FoundChunk]] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.document_id, []).append(chunk)
    return [
        Excerpt(document_id=document_id, filename=found[0].filename, lines=run)
        for document_id, found in by_document.items()
        for run in _runs(_lines(found))
    ]


def with_real_lines(
    excerpts: list[Excerpt], documents: list[Document]
) -> list[Excerpt]:
    # The lines Gemini was shown, but as their documents hold them. A document that
    # isn't there, such as one deleted meanwhile, leaves its excerpts out.
    lines_by_id = {document.id: document.lines for document in documents}
    return [
        Excerpt(
            document_id=excerpt.document_id,
            filename=excerpt.filename,
            lines={number: lines[number - 1] for number in excerpt.lines},
        )
        for excerpt in excerpts
        if (lines := lines_by_id.get(excerpt.document_id)) is not None
    ]


async def _excerpts_to_check(
    answer: ModelAnswer, excerpts: list[Excerpt], documents: DocumentLookup
) -> list[Excerpt]:
    if answer.status != "answered":
        # Verification gives the fixed not_found answer without looking at any.
        return []
    sources = sources_by_name(excerpts)
    # Each cited document once. A file Gemini wasn't shown fails verification anyway.
    document_ids = dict.fromkeys(
        sources[citation.file].document_id
        for citation in answer.citations
        if citation.file in sources
    )
    # After Gemini, in the store's own transaction, so that no connection waits for it.
    return with_real_lines(excerpts, await documents.get_many([*document_ids]))


async def answer_from_dataset(
    question: str,
    dataset_id: str,
    chunks: ChunkSearch,
    documents: DocumentLookup,
    gemini: GeminiClient,
    limit: int,
) -> DatasetAnswer:
    # Before Gemini, so that a question the store is going to refuse costs nothing.
    await chunks.check_can_search(dataset_id)
    # Between the store's transactions, so that no connection waits for Gemini.
    [embedding] = await gemini.embed([query_embedding_text(question)])
    found = await chunks.search(dataset_id, embedding, limit)
    if not found:
        # Nothing to answer from, such as in an empty dataset, so Gemini isn't asked.
        return DatasetAnswer(answer=not_found_answer(), excerpts=[])
    excerpts = excerpts_from_chunks(found)
    answer = await ask_about_excerpts(question, excerpts, gemini)
    checked = await _excerpts_to_check(answer, excerpts, documents)
    return DatasetAnswer(answer=verify_answer(answer, checked), excerpts=excerpts)
