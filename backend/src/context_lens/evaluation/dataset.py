import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

from context_lens.clients.gemini import GeminiClient
from context_lens.services.chunking import TextChunk, split_into_chunks
from context_lens.services.documents import Document
from context_lens.services.indexing import EmbeddedChunk, index_lines, texts_to_embed
from context_lens.services.search import FoundChunk

# The evaluation's documents make one dataset, so this is the only id there is.
DATASET_ID = "evaluation"


class IndexInfo(TypedDict):
    chunks: int
    embedded_characters: int
    seconds: float


@dataclass(frozen=True)
class IndexPlan:
    chunks: list[FoundChunk]
    characters_to_embed: int


@dataclass(frozen=True)
class _Entry:
    chunk: FoundChunk
    embedding: list[float]
    norm: float


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _cosine_distance(entry: _Entry, embedding: list[float], norm: float) -> float:
    if entry.norm == 0 or norm == 0:
        # pgvector's distance to a vector of zeros is NaN, which Postgres sorts after
        # every number.
        return math.inf
    dot = sum(a * b for a, b in zip(entry.embedding, embedding, strict=True))
    return 1 - dot / (entry.norm * norm)


class ChunkIndex:
    """Every chunk of the set's documents, in memory instead of in Postgres."""

    def __init__(self, chunks: list[tuple[FoundChunk, list[float]]]) -> None:
        self._entries = [
            _Entry(chunk, embedding, _norm(embedding)) for chunk, embedding in chunks
        ]

    def __len__(self) -> int:
        return len(self._entries)

    async def check_can_search(self, dataset_id: str) -> None:
        # There's only the one dataset, and nothing deletes it, so there's nothing to
        # refuse.
        return None

    async def search(
        self, dataset_id: str, embedding: list[float], limit: int
    ) -> list[FoundChunk]:
        # As ChunkStore searches: every chunk is compared, the nearest by cosine
        # distance come first, and ties go by place in the documents.
        norm = _norm(embedding)
        ranked = sorted(
            self._entries,
            key=lambda entry: (
                _cosine_distance(entry, embedding, norm),
                entry.chunk.document_id,
                entry.chunk.position,
            ),
        )
        return [entry.chunk for entry in ranked[:limit]]


class DocumentsById:
    """The set's documents, in memory instead of in Postgres."""

    def __init__(self, documents: Iterable[Document]) -> None:
        self._documents = {document.id: document for document in documents}

    async def get_many(self, document_ids: list[str]) -> list[Document]:
        # As DocumentStore gives them: each document found once, and no others.
        return [
            self._documents[document_id]
            for document_id in dict.fromkeys(document_ids)
            if document_id in self._documents
        ]


def _found(
    document: Document, position: int, chunk: TextChunk | EmbeddedChunk
) -> FoundChunk:
    return FoundChunk(
        document_id=document.id,
        filename=document.filename,
        position=position,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        text=chunk.text,
    )


async def index_documents(
    documents: Iterable[Document], gemini: GeminiClient
) -> ChunkIndex:
    # With the app's own indexing, so the chunks and their embeddings are the ones an
    # upload of each document would store.
    chunks = []
    for document in documents:
        embedded = await index_lines(gemini, document.filename, document.lines)
        chunks += [
            (_found(document, position, chunk), chunk.embedding)
            for position, chunk in enumerate(embedded)
        ]
    return ChunkIndex(chunks)


def plan_index(documents: Iterable[Document]) -> IndexPlan:
    # What index_documents would make and embed, split and labelled as index_lines
    # does it, but without Gemini.
    chunks = []
    characters = 0
    for document in documents:
        split = split_into_chunks(document.lines)
        characters += sum(map(len, texts_to_embed(document.filename, split)))
        chunks += [
            _found(document, position, chunk) for position, chunk in enumerate(split)
        ]
    return IndexPlan(chunks, characters)
