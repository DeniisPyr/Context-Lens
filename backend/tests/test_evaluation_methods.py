import pytest

from context_lens.evaluation.cases import Question
from context_lens.evaluation.methods import WholeDocuments, document_excerpt
from context_lens.services.answering import SYSTEM_INSTRUCTION, Excerpt, build_prompt
from context_lens.services.documents import Document

pytestmark = pytest.mark.anyio

HANDBOOK = Document(
    id="handbook.md",
    filename="handbook.md",
    text="# Handbook\nEmployees can work from home 3 days a week.\n",
)
RULES = Document(id="rules.md", filename="rules.md", text="# Rules\nDress well.\n")
POLICY = Document(id="policy.md", filename="policy.md", text="Lock your screen.\n")
DOCUMENTS = {document.id: document for document in (HANDBOOK, RULES, POLICY)}


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
