import pytest
from conftest import FakeGemini, direction, fake_embedding

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError
from context_lens.evaluation.dataset import (
    DATASET_ID,
    ChunkIndex,
    DocumentsById,
    index_documents,
    plan_index,
)
from context_lens.services.chunking import split_into_chunks
from context_lens.services.documents import Document
from context_lens.services.embeddings import EMBEDDING_DIMENSIONS
from context_lens.services.indexing import (
    IndexingError,
    IndexingUnavailableError,
    texts_to_embed,
)
from context_lens.services.search import FoundChunk

pytestmark = pytest.mark.anyio

QUESTION = direction(0)
# Two paragraphs too long for one chunk together, so each is a chunk of its own.
LEAVE = Document(
    id="leave.md",
    filename="leave.md",
    text=(
        "".join(
            f"Annual leave rule {n}: book it in the portal first.\n" for n in range(12)
        )
        + "\n"
        + "".join(
            f"Sick leave rule {n}: tell your manager by nine.\n" for n in range(12)
        )
    ),
)
NOTES = Document(id="notes.txt", filename="notes.txt", text="The cat is orange.\n")


def found(filename: str, line: int) -> FoundChunk:
    return FoundChunk(
        document_id=filename,
        filename=filename,
        position=line - 1,
        start_line=line,
        end_line=line,
        text=f"Line {line} of {filename}.",
    )


def index_of(*documents: tuple[str, list[list[float]]]) -> ChunkIndex:
    # One chunk of one line for each embedding, so line n is the chunk at position n - 1.
    return ChunkIndex(
        [
            (found(filename, line), embedding)
            for filename, embeddings in documents
            for line, embedding in enumerate(embeddings, start=1)
        ]
    )


def scaled(vector: list[float], factor: float) -> list[float]:
    return [value * factor for value in vector]


async def test_search_finds_the_nearest_chunks_first() -> None:
    index = index_of(
        ("a.txt", [direction(40), direction(10)]),
        ("b.md", [direction(30), direction(20)]),
    )

    chunks = await index.search(DATASET_ID, QUESTION, 8)

    assert chunks == [
        found("a.txt", 2),
        found("b.md", 2),
        found("b.md", 1),
        found("a.txt", 1),
    ]


async def test_nearness_is_the_angle_not_the_length_or_the_dot_product() -> None:
    # The short one points nearly the question's way. Euclidean distance and the dot
    # product would both put the long one first.
    index = index_of(("a.txt", [direction(20), scaled(direction(5), 0.1)]))

    chunks = await index.search(DATASET_ID, scaled(QUESTION, 3), 8)

    assert chunks == [found("a.txt", 2), found("a.txt", 1)]


async def test_opposite_chunk_comes_last_and_one_of_zeros_after_it() -> None:
    zeros = [0.0] * EMBEDDING_DIMENSIONS
    index = index_of(("a.txt", [zeros, direction(180), direction(90)]))

    chunks = await index.search(DATASET_ID, QUESTION, 8)

    assert chunks == [found("a.txt", 3), found("a.txt", 2), found("a.txt", 1)]


async def test_equally_near_chunks_come_in_document_order() -> None:
    index = index_of(
        ("b.md", [direction(10), direction(10)]), ("a.txt", [direction(10)])
    )

    chunks = await index.search(DATASET_ID, QUESTION, 8)

    assert chunks == [found("a.txt", 1), found("b.md", 1), found("b.md", 2)]


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
async def test_search_finds_at_most_the_limit(limit: int) -> None:
    angles = [30, 20, 10, 40]
    index = index_of(("a.txt", [direction(angle) for angle in angles]))
    nearest_first = [found("a.txt", line) for line in (3, 2, 1, 4)]

    chunks = await index.search(DATASET_ID, QUESTION, limit)

    assert chunks == nearest_first[:limit]


async def test_the_one_dataset_can_always_be_searched() -> None:
    index = index_of(("a.txt", [direction(10)]))

    await index.check_can_search(DATASET_ID)


async def test_documents_are_looked_up_by_id_each_once() -> None:
    documents = DocumentsById([LEAVE, NOTES])

    found_documents = await documents.get_many(
        ["notes.txt", "missing.md", "leave.md", "notes.txt"]
    )

    assert found_documents == [NOTES, LEAVE]


async def test_documents_are_indexed_with_the_apps_chunks_and_embeddings(
    fake_gemini: FakeGemini,
) -> None:
    index = await index_documents([LEAVE, NOTES], fake_gemini)

    leave_chunks = split_into_chunks(LEAVE.lines)
    assert len(leave_chunks) == 2
    assert fake_gemini.embedded == [
        texts_to_embed("leave.md", leave_chunks),
        texts_to_embed("notes.txt", split_into_chunks(NOTES.lines)),
    ]
    assert len(index) == 3
    # Each chunk's own embedding finds it first.
    [sick_text] = fake_gemini.embedded[0][1:]
    [first] = await index.search(DATASET_ID, fake_embedding(sick_text), 1)
    assert first == FoundChunk(
        document_id="leave.md",
        filename="leave.md",
        position=1,
        start_line=leave_chunks[1].start_line,
        end_line=leave_chunks[1].end_line,
        text=leave_chunks[1].text,
    )


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        pytest.param(
            GeminiUnavailableError("Busy."), IndexingUnavailableError, id="busy"
        ),
        pytest.param(GeminiError("Rejected."), IndexingError, id="rejected"),
    ],
)
async def test_gemini_failing_to_embed_is_an_indexing_error(
    fake_gemini: FakeGemini, error: GeminiError, raised: type[IndexingError]
) -> None:
    fake_gemini.embed_error = error

    with pytest.raises(raised):
        await index_documents([LEAVE, NOTES], fake_gemini)


async def test_plan_has_the_chunks_and_characters_indexing_embeds(
    fake_gemini: FakeGemini,
) -> None:
    plan = plan_index([LEAVE, NOTES])

    index = await index_documents([LEAVE, NOTES], fake_gemini)

    embedded = [text for texts in fake_gemini.embedded for text in texts]
    assert plan.characters_to_embed == sum(map(len, embedded))
    everything = await index.search(DATASET_ID, QUESTION, len(index))
    assert sorted(plan.chunks, key=str) == sorted(everything, key=str)
