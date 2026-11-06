from dataclasses import dataclass

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)
from context_lens.services.chunking import TextChunk, split_into_chunks
from context_lens.services.embeddings import document_embedding_text


class IndexingError(Exception):
    """Gemini could not embed the chunks, and trying again is unlikely to help."""


class IndexingUnavailableError(IndexingError):
    """Gemini was unavailable while embedding the chunks, so trying again may work."""


@dataclass(frozen=True)
class EmbeddedChunk:
    start_line: int
    end_line: int
    text: str
    embedding: list[float]


def texts_to_embed(filename: str, chunks: list[TextChunk]) -> list[str]:
    return [document_embedding_text(filename, chunk.text) for chunk in chunks]


async def index_lines(
    gemini: GeminiClient, filename: str, lines: list[str]
) -> list[EmbeddedChunk]:
    chunks = split_into_chunks(lines)
    # Errors of their own, so that a failed upload can say the document wasn't saved
    # rather than that a question wasn't answered.
    try:
        embeddings = await gemini.embed(texts_to_embed(filename, chunks))
    except GeminiUnavailableError as exc:
        raise IndexingUnavailableError("Gemini is unavailable right now.") from exc
    except GeminiError as exc:
        raise IndexingError("Gemini could not embed the document.") from exc
    return [
        EmbeddedChunk(chunk.start_line, chunk.end_line, chunk.text, embedding)
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
