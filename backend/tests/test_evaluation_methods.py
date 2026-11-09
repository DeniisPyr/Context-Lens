from itertools import combinations

import pytest
from conftest import FakeGemini

from context_lens.evaluation import methods
from context_lens.evaluation.cases import Question
from context_lens.evaluation.dataset import (
    DATASET_ID,
    DocumentsById,
    index_documents,
    plan_index,
)
from context_lens.evaluation.methods import (
    DatasetSearch,
    WholeDocuments,
    document_excerpt,
    prompt_characters_at_most,
)
from context_lens.services import search
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    Citation,
    Excerpt,
    ModelAnswer,
    build_prompt,
)
from context_lens.services.documents import Document
from context_lens.services.search import DatasetAnswer, excerpts_from_chunks

pytestmark = pytest.mark.anyio

HANDBOOK = Document(
    id="handbook.md",
    filename="handbook.md",
    text="# Handbook\nEmployees can work from home 3 days a week.\n",
)
RULES = Document(id="rules.md", filename="rules.md", text="# Rules\nDress well.\n")
POLICY = Document(id="policy.md", filename="policy.md", text="Lock your screen.\n")
DOCUMENTS = {document.id: document for document in (HANDBOOK, RULES, POLICY)}
NOTES = Document(id="notes.txt", filename="notes.txt", text="The cat is orange.\n")
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


def make_question(**changes: object) -> Question:
    fields = {
        "id": "remote-days",
        "document": "handbook.md",
        "category": "fact",
        "question": "How many days?",
        "facts": [["3 days"]],
        "evidence": [[2, 2]],
    }
    return Question.model_validate(fields | changes)


def test_document_excerpt_holds_every_line_numbered_from_one() -> None:
    document = Document(id="doc-1", filename="notes.txt", text="One.\n\nThree.\n")

    assert document_excerpt(document) == Excerpt(
        document_id="doc-1", filename="notes.txt", lines={1: "One.", 2: "", 3: "Three."}
    )


def test_whole_documents_show_only_the_questions_own_document() -> None:
    method = WholeDocuments(DOCUMENTS)

    assert method.excerpts(make_question()) == [document_excerpt(HANDBOOK)]


def test_whole_documents_show_its_document_then_those_its_evidence_is_in() -> None:
    question = make_question(
        category="cross_document",
        facts=[["3 days"], ["Dress well"]],
        evidence=[["policy.md", 1, 1], ["rules.md", 2, 2], [2, 2]],
    )
    method = WholeDocuments(DOCUMENTS)

    excerpts = method.excerpts(question)

    assert excerpts == [document_excerpt(d) for d in (HANDBOOK, POLICY, RULES)]
    assert method.prompt_characters(question) == len(SYSTEM_INSTRUCTION) + len(
        build_prompt(question.question, excerpts)
    )


def test_whole_documents_show_the_files_a_clarify_questions_cases_are_in_too() -> None:
    question = make_question(
        category="clarify",
        reply="In Brno.",
        cases=[["policy.md", 1, 1], [2, 2], ["rules.md", 2, 2]],
    )
    method = WholeDocuments(DOCUMENTS)

    excerpts = method.excerpts(question)

    assert excerpts == [document_excerpt(d) for d in (HANDBOOK, POLICY, RULES)]


async def test_whole_documents_answer_from_the_excerpts_they_show(
    fake_gemini: FakeGemini,
) -> None:
    method = WholeDocuments({"notes.txt": NOTES})
    question = make_question(
        document="notes.txt", facts=[["orange"]], evidence=[[1, 1]]
    )

    result = await method.answer(question, fake_gemini)

    assert result == DatasetAnswer(
        answer=fake_gemini.answer, excerpts=[document_excerpt(NOTES)]
    )
    assert fake_gemini.prompts == [
        build_prompt(question.question, [document_excerpt(NOTES)])
    ]


async def test_whole_documents_verify_the_answer(fake_gemini: FakeGemini) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="Purple.",
        citations=[
            Citation(file="notes.txt", start_line=1, end_line=1, quote="purple")
        ],
    )
    method = WholeDocuments({"notes.txt": NOTES})

    result = await method.answer(make_question(document="notes.txt"), fake_gemini)

    assert result.answer.status == "not_found"


def test_rag_answers_with_the_apps_own_function() -> None:
    assert methods.answer_from_dataset is search.answer_from_dataset


async def test_rag_asks_the_app_with_the_index_and_the_limit(
    monkeypatch: pytest.MonkeyPatch, fake_gemini: FakeGemini
) -> None:
    calls = []

    async def spy(*args: object) -> DatasetAnswer:
        calls.append(args)
        return await search.answer_from_dataset(*args)

    monkeypatch.setattr(methods, "answer_from_dataset", spy)
    index = await index_documents([NOTES, LEAVE], fake_gemini)
    documents = DocumentsById([NOTES, LEAVE])
    method = DatasetSearch(index, documents, 3)
    question = make_question(question="What colour is the cat?")

    result = await method.answer(question, fake_gemini)

    assert calls == [(question.question, DATASET_ID, index, documents, fake_gemini, 3)]
    assert result.answer == fake_gemini.answer
    assert len(result.excerpts) == 3


def test_prompt_of_a_one_chunk_document_is_its_whole_document_prompt() -> None:
    plan = plan_index([HANDBOOK])
    question = make_question()

    assert prompt_characters_at_most(question, plan.chunks, 8) == (
        WholeDocuments(DOCUMENTS).prompt_characters(question)
    )


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
def test_the_longest_prompt_a_search_can_make_is_the_bound(limit: int) -> None:
    chunks = plan_index([LEAVE, HANDBOOK, RULES]).chunks
    question = make_question()

    bound = prompt_characters_at_most(question, chunks, limit)

    sizes = [
        len(SYSTEM_INSTRUCTION)
        + len(build_prompt(question.question, excerpts_from_chunks(list(found))))
        for found in combinations(chunks, min(limit, len(chunks)))
    ]
    # No two of these chunks touch, so none are merged and the largest reach it.
    assert max(sizes) == bound


def test_chunks_that_touch_make_a_prompt_shorter_than_the_bound() -> None:
    # Without blank lines, each chunk starts on the line after the last one ends.
    text = "".join(f"Line {n} of a long list with no gaps.\n" for n in range(60))
    chunks = plan_index([Document(id="list.md", filename="list.md", text=text)]).chunks
    question = make_question()

    bound = prompt_characters_at_most(question, chunks, 2)

    sizes = [
        len(SYSTEM_INSTRUCTION)
        + len(build_prompt(question.question, excerpts_from_chunks(list(found))))
        for found in combinations(chunks, 2)
    ]
    assert len(chunks) == 3
    assert max(sizes) < bound
