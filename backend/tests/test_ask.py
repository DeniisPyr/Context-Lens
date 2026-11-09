import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import (
    NO_CHUNKS,
    FakeGemini,
    StartApp,
    direction,
    fake_embedding,
    run_sql,
)
from fastapi import Request
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import ValidationError
from sqlalchemy import URL

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)
from context_lens.dependencies import get_document_store, get_gemini_client
from context_lens.main import create_app
from context_lens.services.answering import (
    NOT_FOUND_MESSAGE,
    SYSTEM_INSTRUCTION,
    Citation,
    ModelAnswer,
    ModelAnswerToReply,
)
from context_lens.services.chunking import split_into_chunks
from context_lens.services.documents import Document
from context_lens.services.embeddings import (
    document_embedding_text,
    query_embedding_text,
)

QUESTION = "Which pets are there?"
CLARIFICATION = {"question": "In which file?", "reply": "In notes.txt."}
NOT_FOUND = {"status": "not_found", "answer": NOT_FOUND_MESSAGE, "citations": []}
# Lines too long for one chunk, so each is stored in pieces: this one in four, cut
# between words, and the one without spaces in two, cut in the middle of a "word".
LONG_LINE = " ".join(f"slovo{number}" for number in range(400))
PIECES = [chunk.text for chunk in split_into_chunks([LONG_LINE])]
NO_SPACES = "".join(f"{number:04}" for number in range(400))
FIRST_HALF, SECOND_HALF = (chunk.text for chunk in split_into_chunks([NO_SPACES]))


def new_dataset(client: TestClient) -> str:
    # A name of its own, so that a test can make several.
    response = client.post("/api/datasets", json={"name": uuid4().hex})
    return response.json()["id"]


def upload(
    client: TestClient,
    dataset_id: str,
    text: str = "The cat is orange.",
    filename: str = "notes.txt",
) -> str:
    response = client.post(
        f"/api/datasets/{dataset_id}/documents",
        files={"file": (filename, text.encode())},
    )
    assert response.status_code == 201
    return response.json()["id"]


def ask(client: TestClient, dataset_id: str, question: str = QUESTION) -> Response:
    return client.post(
        "/api/ask", json={"dataset_id": dataset_id, "question": question}
    )


def send_reply(
    client: TestClient,
    dataset_id: str,
    clarification: object = CLARIFICATION,
    question: str = QUESTION,
) -> Response:
    return client.post(
        "/api/ask",
        json={
            "dataset_id": dataset_id,
            "question": question,
            "clarification": clarification,
        },
    )


def long_line(filename: str, number: int) -> str:
    # Too long for two to share a chunk, so each of these lines is a chunk of its own.
    return f"Line {number} of {filename}: {' '.join(['slovo'] * 100)}"


def long_lines(filename: str, count: int) -> str:
    return "".join(f"{long_line(filename, number)}\n" for number in range(1, count + 1))


def place(fake_gemini: FakeGemini, filename: str, number: int, degrees: float) -> None:
    # Puts that line's chunk at this angle to the question: the smaller, the nearer.
    text = document_embedding_text(filename, long_line(filename, number))
    fake_gemini.vectors[text] = direction(degrees)


def citation(file: str, start_line: int, end_line: int, quote: str) -> Citation:
    return Citation(file=file, start_line=start_line, end_line=end_line, quote=quote)


def answered(*citations: Citation) -> ModelAnswer:
    return ModelAnswer(status="answered", answer="An answer.", citations=[*citations])


def clarifying(*citations: Citation) -> ModelAnswer:
    return ModelAnswer(
        status="needs_clarification", answer="Which file?", citations=[*citations]
    )


@dataclass(frozen=True)
class Pets:
    dataset_id: str
    a_id: str
    b_id: str


@pytest.fixture
def client_finding_four(
    clean_database: URL, start_app: StartApp, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("CHUNKS_PER_QUESTION", "4")
    with start_app() as test_client:
        yield test_client


@pytest.fixture
def client_finding_two(
    clean_database: URL, start_app: StartApp, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("CHUNKS_PER_QUESTION", "2")
    with start_app() as test_client:
        yield test_client


@pytest.fixture
def pets(client_finding_four: TestClient, fake_gemini: FakeGemini) -> Pets:
    # Three documents with 11 chunks, of which the four nearest to QUESTION are line 2
    # of b.md, then lines 4, 3 and 1 of a.txt.
    fake_gemini.vectors[query_embedding_text(QUESTION)] = direction(0)
    place(fake_gemini, "b.md", 2, 5)
    place(fake_gemini, "a.txt", 4, 10)
    place(fake_gemini, "a.txt", 3, 15)
    place(fake_gemini, "a.txt", 1, 20)
    dataset_id = new_dataset(client_finding_four)
    a_id = upload(client_finding_four, dataset_id, long_lines("a.txt", 5), "a.txt")
    b_id = upload(client_finding_four, dataset_id, long_lines("b.md", 5), "b.md")
    upload(client_finding_four, dataset_id, "The parrot is green.", "c.txt")
    return Pets(dataset_id, a_id, b_id)


def test_prompt_holds_only_the_chunks_found_grouped_by_file_in_line_order(
    client_finding_four: TestClient, fake_gemini: FakeGemini, pets: Pets
) -> None:
    response = ask(client_finding_four, pets.dataset_id)

    assert response.status_code == 200
    # b.md first, as its chunk is the nearest. Lines 3 and 4 of a.txt touch, so they
    # are one excerpt.
    [prompt] = fake_gemini.prompts
    assert prompt == (
        '<excerpt file="b.md" lines="2-2">\n'
        f"2: {long_line('b.md', 2)}\n"
        "</excerpt>\n"
        "\n"
        '<excerpt file="a.txt" lines="1-1">\n'
        f"1: {long_line('a.txt', 1)}\n"
        "</excerpt>\n"
        "\n"
        '<excerpt file="a.txt" lines="3-4">\n'
        f"3: {long_line('a.txt', 3)}\n"
        f"4: {long_line('a.txt', 4)}\n"
        "</excerpt>\n"
        "\n"
        f"Question: {QUESTION}"
    )


def test_citations_of_two_files_lead_to_their_own_documents(
    client_finding_four: TestClient, fake_gemini: FakeGemini, pets: Pets
) -> None:
    across_two_lines = "slovo Line 4 of a.txt"
    fake_gemini.answer = answered(
        citation("b.md", 2, 2, "Line 2 of b.md"),
        citation("a.txt", 3, 4, across_two_lines),
    )

    response = ask(client_finding_four, pets.dataset_id)

    assert response.status_code == 200
    assert response.json() == {
        "status": "answered",
        "answer": "An answer.",
        "citations": [
            {
                "document_id": pets.b_id,
                "filename": "b.md",
                "start_line": 2,
                "end_line": 2,
                "quote": "Line 2 of b.md",
            },
            {
                "document_id": pets.a_id,
                "filename": "a.txt",
                "start_line": 3,
                "end_line": 4,
                "quote": across_two_lines,
            },
        ],
    }


@pytest.mark.parametrize(
    "unseen",
    [
        # a.txt is loaded to check the other citation, and this line is in it.
        pytest.param(
            citation("a.txt", 2, 2, "Line 2 of a.txt"),
            id="line_in_the_document_not_shown",
        ),
        pytest.param(
            citation("c.txt", 1, 1, "The parrot is green."), id="document_not_found"
        ),
        pytest.param(
            citation("d.txt", 2, 2, "Line 2 of b.md"), id="file_not_in_the_dataset"
        ),
        pytest.param(
            citation("a.txt", 1, 1, "Line 2 of b.md"), id="quote_from_another_file"
        ),
    ],
)
def test_citation_of_something_gemini_was_not_shown_returns_not_found(
    client_finding_four: TestClient,
    fake_gemini: FakeGemini,
    pets: Pets,
    unseen: Citation,
) -> None:
    fake_gemini.answer = answered(citation("b.md", 2, 2, "Line 2 of b.md"), unseen)

    response = ask(client_finding_four, pets.dataset_id)

    assert response.status_code == 200
    assert response.json() == NOT_FOUND


def test_clarifying_question_is_returned_with_citations_to_the_documents(
    client_finding_four: TestClient, fake_gemini: FakeGemini, pets: Pets
) -> None:
    across_two_lines = "slovo Line 4 of a.txt"
    fake_gemini.answer = clarifying(
        citation("b.md", 2, 2, "Line 2 of b.md"),
        citation("a.txt", 3, 4, across_two_lines),
    )

    response = ask(client_finding_four, pets.dataset_id)

    assert response.status_code == 200
    assert response.json() == {
        "status": "needs_clarification",
        "answer": "Which file?",
        "citations": [
            {
                "document_id": pets.b_id,
                "filename": "b.md",
                "start_line": 2,
                "end_line": 2,
                "quote": "Line 2 of b.md",
            },
            {
                "document_id": pets.a_id,
                "filename": "a.txt",
                "start_line": 3,
                "end_line": 4,
                "quote": across_two_lines,
            },
        ],
    }


@pytest.mark.parametrize(
    "citations",
    [
        pytest.param([], id="no_citations"),
        pytest.param(
            [
                citation("b.md", 2, 2, "Line 2 of b.md"),
                citation("a.txt", 2, 2, "Line 2 of a.txt"),
            ],
            id="a_line_not_shown",
        ),
        pytest.param(
            [citation("c.txt", 1, 1, "The parrot is green.")], id="document_not_found"
        ),
    ],
)
def test_clarifying_question_without_verified_citations_returns_not_found(
    client_finding_four: TestClient,
    fake_gemini: FakeGemini,
    pets: Pets,
    citations: list[Citation],
) -> None:
    fake_gemini.answer = clarifying(*citations)

    response = ask(client_finding_four, pets.dataset_id)

    assert response.status_code == 200
    assert response.json() == NOT_FOUND


def test_long_line_found_in_pieces_is_shown_and_cited_whole(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    across_two_pieces = LONG_LINE[950:1050]
    fake_gemini.answer = answered(citation("notes.txt", 1, 1, across_two_pieces))
    dataset_id = new_dataset(client)
    upload(client, dataset_id, f"{LONG_LINE}\n")

    response = ask(client, dataset_id)

    assert len(PIECES) == 4
    assert f'"1-1">\n1: {LONG_LINE}\n</excerpt>' in fake_gemini.prompts[0]
    assert response.json()["status"] == "answered"


@pytest.mark.parametrize(
    ("quote", "status"),
    [
        pytest.param(
            f"{PIECES[0].split()[-1]} {PIECES[2].split()[0]}",
            "not_found",
            id="across_the_piece_not_found",
        ),
        pytest.param(" ".join(PIECES[0].split()[3:6]), "answered", id="first_piece"),
        pytest.param(" ".join(PIECES[2].split()[3:6]), "answered", id="third_piece"),
    ],
)
def test_quote_is_checked_against_the_real_line_not_the_pieces_shown(
    client_finding_two: TestClient, fake_gemini: FakeGemini, quote: str, status: str
) -> None:
    # Only the first and third pieces are found, so Gemini sees them side by side.
    fake_gemini.vectors[query_embedding_text(QUESTION)] = direction(0)
    for piece, degrees in ((PIECES[0], 5), (PIECES[2], 10)):
        fake_gemini.vectors[document_embedding_text("notes.txt", piece)] = direction(
            degrees
        )
    fake_gemini.answer = answered(citation("notes.txt", 1, 1, quote))
    dataset_id = new_dataset(client_finding_two)
    upload(client_finding_two, dataset_id, f"{LONG_LINE}\n")

    response = ask(client_finding_two, dataset_id)

    assert f"\n1: {PIECES[0]} {PIECES[2]}\n" in fake_gemini.prompts[0]
    assert response.json()["status"] == status


@pytest.mark.parametrize(
    ("quote", "status"),
    [
        pytest.param(
            f"{FIRST_HALF[-8:]} {SECOND_HALF[:8]}",
            "not_found",
            id="with_the_space_between_the_pieces",
        ),
        pytest.param(
            f"{FIRST_HALF[-8:]}{SECOND_HALF[:8]}", "answered", id="as_the_line_has_it"
        ),
    ],
)
def test_quote_across_a_cut_in_a_word_must_be_as_the_line_has_it(
    client: TestClient, fake_gemini: FakeGemini, quote: str, status: str
) -> None:
    fake_gemini.answer = answered(citation("notes.txt", 1, 1, quote))
    dataset_id = new_dataset(client)
    upload(client, dataset_id, f"{NO_SPACES}\n")

    response = ask(client, dataset_id)

    # Gemini was shown the two pieces with a space between them.
    assert f"\n1: {FIRST_HALF} {SECOND_HALF}\n" in fake_gemini.prompts[0]
    assert response.json()["status"] == status


def test_document_deleted_before_its_citations_are_checked_gives_not_found(
    client: TestClient, fake_gemini: FakeGemini, clean_database: URL
) -> None:
    dataset_id = new_dataset(client)
    document_id = upload(client, dataset_id)
    fake_gemini.during_call = lambda: run_sql(
        clean_database, f"DELETE FROM documents WHERE id = '{document_id}'"
    )

    response = ask(client, dataset_id)

    assert response.status_code == 200
    assert response.json() == NOT_FOUND


def record_loads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    # The ids of each call to the document store's get_many.
    store = get_document_store(Request({"type": "http", "app": client.app}))
    get_many = store.get_many
    loads: list[list[str]] = []

    async def recording(document_ids: list[str]) -> list[Document]:
        loads.append(document_ids)
        return await get_many(document_ids)

    monkeypatch.setattr(store, "get_many", recording)
    return loads


def test_only_the_cited_documents_are_loaded_each_once(
    client_finding_four: TestClient,
    fake_gemini: FakeGemini,
    pets: Pets,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loads = record_loads(client_finding_four, monkeypatch)
    fake_gemini.answer = answered(
        citation("b.md", 2, 2, "Line 2 of b.md"),
        citation("b.md", 2, 2, "slovo slovo"),
        citation("unknown.txt", 1, 1, "Line 1 of a.txt"),
    )

    ask(client_finding_four, pets.dataset_id)

    # Not a.txt, which Gemini was shown but no citation names.
    assert loads == [[pets.b_id]]


def test_nothing_is_loaded_when_gemini_finds_no_answer(
    client: TestClient, fake_gemini: FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    loads = record_loads(client, monkeypatch)
    fake_gemini.answer = ModelAnswer(
        status="not_found",
        answer="Not there.",
        citations=[citation("notes.txt", 1, 1, "The cat is orange.")],
    )
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    response = ask(client, dataset_id)

    assert response.json() == NOT_FOUND
    assert loads == []


def test_question_is_embedded_once_in_the_query_format(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.embedded.clear()

    ask(client, dataset_id, "  What colour is the cat?\n")

    assert fake_gemini.embedded == [
        ["task: search result | query: What colour is the cat?"]
    ]


def test_reply_is_embedded_once_with_the_question_in_the_query_format(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.embedded.clear()

    send_reply(
        client,
        dataset_id,
        {"question": " Which cat?\n", "reply": "\tThe big one. "},
        "  What colour is the cat?\n",
    )

    # Not the clarifying question, which says only what Gemini didn't know.
    assert fake_gemini.embedded == [
        ["task: search result | query: What colour is the cat?\nThe big one."]
    ]


def test_reply_finds_the_chunks_nearest_to_the_question_with_the_reply(
    client_finding_four: TestClient, fake_gemini: FakeGemini, pets: Pets
) -> None:
    # Line 5 of b.md is far from the question alone, but this puts it at no angle at
    # all to the question with the reply.
    line = long_line("b.md", 5)
    search_text = f"{QUESTION}\n{CLARIFICATION['reply']}"
    fake_gemini.vectors[query_embedding_text(search_text)] = fake_embedding(
        document_embedding_text("b.md", line)
    )

    send_reply(client_finding_four, pets.dataset_id)

    [prompt] = fake_gemini.prompts
    assert f"\n5: {line}\n" in prompt


def test_eight_chunks_per_question_by_default(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id, long_lines("a.txt", 10), "a.txt")

    ask(client, dataset_id)

    [prompt] = fake_gemini.prompts
    assert len(re.findall(r"^\d+: Line ", prompt, flags=re.MULTILINE)) == 8


def test_ask_returns_the_answer_with_citations_to_the_document(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    quote = "The cat is orange.\nThe dog is brown."
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="The cat is orange and the dog is brown.",
        citations=[citation("notes.txt", 2, 3, quote)],
    )
    dataset_id = new_dataset(client)
    document_id = upload(client, dataset_id, f"Pets:\n{quote}")

    response = ask(client, dataset_id, "Describe the pets.")

    assert response.status_code == 200
    assert response.json() == {
        "status": "answered",
        "answer": "The cat is orange and the dog is brown.",
        "citations": [
            {
                "document_id": document_id,
                "filename": "notes.txt",
                "start_line": 2,
                "end_line": 3,
                "quote": quote,
            }
        ],
    }


@pytest.mark.parametrize("file", ["R&amp;D.txt", "R&D.txt"], ids=["as_shown", "plain"])
def test_citation_may_name_the_file_as_shown_or_plain(
    client: TestClient, fake_gemini: FakeGemini, file: str
) -> None:
    fake_gemini.answer = answered(citation(file, 1, 1, "The cat is orange."))
    dataset_id = new_dataset(client)
    document_id = upload(client, dataset_id, filename="R&D.txt")

    response = ask(client, dataset_id)

    assert '<excerpt file="R&amp;D.txt" lines="1-1">' in fake_gemini.prompts[0]
    [cited] = response.json()["citations"]
    assert (cited["document_id"], cited["filename"]) == (document_id, "R&D.txt")


def test_not_found_from_gemini_returns_the_fixed_message(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="not_found", answer="The document does not say.", citations=[]
    )
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    response = ask(client, dataset_id, "How old is the cat?")

    assert response.status_code == 200
    assert response.json() == NOT_FOUND


def test_prompt_holds_only_that_datasets_chunks_and_the_stripped_question(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    upload(client, new_dataset(client), "Another document.")
    dataset_id = new_dataset(client)
    upload(client, dataset_id, "The cat is orange.")

    response = ask(client, dataset_id, "  What colour is the cat?\n")

    assert response.status_code == 200
    [prompt] = fake_gemini.prompts
    assert prompt == (
        '<excerpt file="notes.txt" lines="1-1">\n'
        "1: The cat is orange.\n"
        "</excerpt>\n"
        "\n"
        "Question: What colour is the cat?"
    )


def test_reply_prompt_ends_with_the_stripped_question_what_was_asked_and_the_reply(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id, "The cat is orange.")

    response = send_reply(
        client,
        dataset_id,
        {"question": " Which cat?\n", "reply": "\tThe big one. "},
        "  What colour is the cat?\n",
    )

    assert response.status_code == 200
    [prompt] = fake_gemini.prompts
    assert prompt == (
        '<excerpt file="notes.txt" lines="1-1">\n'
        "1: The cat is orange.\n"
        "</excerpt>\n"
        "\n"
        "Question: What colour is the cat?\n"
        "Your clarifying question: Which cat?\n"
        "The user's reply: The big one."
    )


def test_null_clarification_asks_as_a_question_without_one(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.embedded.clear()
    ask(client, dataset_id)

    response = send_reply(client, dataset_id, None)

    assert response.status_code == 200
    first, second = fake_gemini.prompts
    assert second == first
    first, second = fake_gemini.embedded
    assert second == first
    assert fake_gemini.response_models == [ModelAnswer, ModelAnswer]


def test_prompt_numbers_each_line_of_a_chunk(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id, "first line\nsecond line\n")

    ask(client, dataset_id, "What is on line 2?")

    [prompt] = fake_gemini.prompts
    assert (
        '<excerpt file="notes.txt" lines="1-2">\n1: first line\n2: second line\n'
        "</excerpt>"
    ) in prompt


def test_prompt_numbering_matches_the_line_count_from_the_upload(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    # str.splitlines() would treat this form feed as a line break, making three lines.
    upload(client, dataset_id, "one\x0cstill one\ntwo\n")

    ask(client, dataset_id)

    [prompt] = fake_gemini.prompts
    assert '"1-2">\n1: one\x0cstill one\n2: two\n</excerpt>' in prompt


@pytest.mark.parametrize("send", [ask, send_reply], ids=["question", "reply"])
def test_gemini_receives_the_system_instruction(
    client: TestClient,
    fake_gemini: FakeGemini,
    send: Callable[[TestClient, str], Response],
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    send(client, dataset_id)

    assert fake_gemini.system_instructions == [SYSTEM_INSTRUCTION]


def test_gemini_is_asked_for_a_model_answer(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    ask(client, dataset_id)

    assert fake_gemini.response_models == [ModelAnswer]


def test_reply_asks_gemini_for_an_answer_that_cannot_ask_again(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    send_reply(client, dataset_id)

    assert fake_gemini.response_models == [ModelAnswerToReply]


def test_answer_to_a_reply_is_returned_with_citations_to_the_document(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    document_id = upload(client, dataset_id)

    response = send_reply(client, dataset_id)

    assert response.status_code == 200
    assert response.json() == {
        "status": "answered",
        "answer": "The cat is orange.",
        "citations": [
            {
                "document_id": document_id,
                "filename": "notes.txt",
                "start_line": 1,
                "end_line": 1,
                "quote": "The cat is orange.",
            }
        ],
    }


def test_answer_to_a_reply_with_a_bad_citation_returns_not_found(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = answered(citation("notes.txt", 1, 1, "The cat is purple."))
    dataset_id = new_dataset(client)
    upload(client, dataset_id)

    response = send_reply(client, dataset_id)

    assert response.status_code == 200
    assert response.json() == NOT_FOUND


def store_without_chunks(client: TestClient, dataset_id: str) -> None:
    # As documents uploaded before chunks existed are, until they're indexed.
    store = get_document_store(Request({"type": "http", "app": client.app}))
    client.portal.call(
        store.add, dataset_id, "old.txt", "Stored early.\n", NO_CHUNKS, 1
    )


@pytest.mark.parametrize(
    "fill",
    [
        pytest.param(lambda client, dataset_id: None, id="empty_dataset"),
        pytest.param(store_without_chunks, id="documents_without_chunks"),
    ],
)
def test_nothing_to_search_gives_not_found_without_asking_gemini(
    client: TestClient,
    fake_gemini: FakeGemini,
    fill: Callable[[TestClient, str], None],
) -> None:
    dataset_id = new_dataset(client)
    fill(client, dataset_id)

    response = ask(client, dataset_id)

    assert response.status_code == 200
    assert response.json() == NOT_FOUND
    assert fake_gemini.prompts == []


@pytest.mark.parametrize("dataset_id", ["not-a-uuid", "", "\x00", str(uuid4())])
def test_bad_or_unknown_dataset_id_returns_404_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, dataset_id: str
) -> None:
    upload(client, new_dataset(client))
    fake_gemini.embedded.clear()

    response = ask(client, dataset_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}
    assert fake_gemini.embedded == []
    assert fake_gemini.prompts == []


def test_deleted_dataset_returns_404_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    client.delete(f"/api/datasets/{dataset_id}")
    fake_gemini.embedded.clear()

    response = ask(client, dataset_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}
    assert fake_gemini.embedded == []
    assert fake_gemini.prompts == []


def test_dataset_deleted_while_gemini_embeds_the_question_returns_404(
    client: TestClient, fake_gemini: FakeGemini, clean_database: URL
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.during_embed = lambda texts: run_sql(
        clean_database, f"DELETE FROM datasets WHERE id = '{dataset_id}'"
    )

    response = ask(client, dataset_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}
    assert fake_gemini.prompts == []


def test_no_database_connection_is_held_while_gemini_works(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    pool = client.app.state.engine.pool
    during_the_calls = []
    fake_gemini.during_embed = lambda texts: during_the_calls.append(
        ("embed", pool.checkedout(), pool.checkedin())
    )
    fake_gemini.during_call = lambda: during_the_calls.append(
        ("answer", pool.checkedout(), pool.checkedin())
    )

    response = ask(client, dataset_id)

    assert response.status_code == 200
    # None in use, and the one the store used is back in the pool.
    assert during_the_calls == [("embed", 0, 1), ("answer", 0, 1)]


def test_missing_dataset_id_returns_422_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    response = client.post("/api/ask", json={"question": "Hi"})

    assert response.status_code == 422
    assert fake_gemini.embedded == []
    assert fake_gemini.prompts == []


def test_document_id_is_no_longer_accepted(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    document_id = upload(client, dataset_id)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Hi"}
    )

    assert response.status_code == 422
    assert fake_gemini.prompts == []


@pytest.mark.parametrize(
    "question",
    ["", " \t\n", "x" * 2001],
    ids=["empty", "whitespace_only", "too_long"],
)
def test_invalid_question_is_rejected_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, question: str
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.embedded.clear()

    response = ask(client, dataset_id, question)

    assert response.status_code == 422
    assert fake_gemini.embedded == []
    assert fake_gemini.prompts == []


def test_longest_allowed_question_is_accepted(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    question = "x" * 2000

    response = ask(client, dataset_id, question)

    assert response.status_code == 200
    assert fake_gemini.embedded[-1] == [query_embedding_text(question)]
    assert fake_gemini.prompts[0].endswith(question)


@pytest.mark.parametrize(
    "clarification",
    [
        pytest.param({"reply": "In notes.txt."}, id="no_question"),
        pytest.param({"question": "In which file?"}, id="no_reply"),
        pytest.param({"question": "", "reply": "In notes.txt."}, id="empty_question"),
        pytest.param(
            {"question": " \t\n", "reply": "In notes.txt."},
            id="whitespace_only_question",
        ),
        pytest.param(
            {"question": "x" * 4001, "reply": "In notes.txt."}, id="question_too_long"
        ),
        pytest.param({"question": "In which file?", "reply": ""}, id="empty_reply"),
        pytest.param(
            {"question": "In which file?", "reply": " \t\n"},
            id="whitespace_only_reply",
        ),
        pytest.param(
            {"question": "In which file?", "reply": "x" * 2001}, id="reply_too_long"
        ),
        pytest.param("In notes.txt.", id="not_an_object"),
    ],
)
def test_invalid_clarification_is_rejected_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, clarification: object
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    fake_gemini.embedded.clear()

    response = send_reply(client, dataset_id, clarification)

    assert response.status_code == 422
    assert fake_gemini.embedded == []
    assert fake_gemini.prompts == []


def test_longest_allowed_clarification_is_accepted(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    # Gemini's question may be longer than the user's own.
    clarification = {"question": "x" * 4000, "reply": "y" * 2000}

    response = send_reply(client, dataset_id, clarification)

    assert response.status_code == 200
    assert fake_gemini.embedded[-1] == [
        query_embedding_text(f"{QUESTION}\n{'y' * 2000}")
    ]
    assert f"\nYour clarifying question: {'x' * 4000}\n" in fake_gemini.prompts[0]
    assert fake_gemini.prompts[0].endswith(f"\nThe user's reply: {'y' * 2000}")


GEMINI_FAILURES = [
    pytest.param(
        GeminiUnavailableError("Busy."),
        503,
        "Gemini is unavailable right now. Please try again.",
        "Gemini is unavailable.",
        id="unavailable",
    ),
    pytest.param(
        GeminiError("Rejected."),
        502,
        "Gemini could not answer this question.",
        "Gemini could not answer.",
        id="rejected",
    ),
]


@pytest.mark.parametrize("while_", ["embedding", "answering"])
@pytest.mark.parametrize(("error", "status_code", "detail", "logged"), GEMINI_FAILURES)
def test_gemini_failure_returns_the_ask_error_and_logs_its_cause(
    client: TestClient,
    fake_gemini: FakeGemini,
    caplog: pytest.LogCaptureFixture,
    while_: str,
    error: GeminiError,
    status_code: int,
    detail: str,
    logged: str,
) -> None:
    dataset_id = new_dataset(client)
    upload(client, dataset_id)
    if while_ == "embedding":
        fake_gemini.embed_error = error
    else:
        fake_gemini.error = error

    response = ask(client, dataset_id)

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    records = [record for record in caplog.records if record.getMessage() == logged]
    assert [record.exc_info[1] for record in records if record.exc_info] == [error]


def test_asking_logs_nothing_from_the_question_documents_or_answer(
    client: TestClient, fake_gemini: FakeGemini, caplog: pytest.LogCaptureFixture
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="Private answer.",
        citations=[citation("notes.txt", 1, 1, "Private quote.")],
    )
    dataset_id = new_dataset(client)
    upload(client, dataset_id, "Private text.")

    response = ask(client, dataset_id, "Private question?")

    assert response.json() == NOT_FOUND
    # Only that the answer was rejected.
    assert "Citation verification failed" in caplog.text
    assert "Private" not in caplog.text


def test_replying_logs_nothing_from_the_clarifying_question_or_reply(
    client: TestClient, fake_gemini: FakeGemini, caplog: pytest.LogCaptureFixture
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="Private answer.",
        citations=[citation("notes.txt", 1, 1, "Private quote.")],
    )
    dataset_id = new_dataset(client)
    upload(client, dataset_id, "Private text.")
    clarification = {"question": "Private clarifying question?", "reply": "Private."}

    response = send_reply(client, dataset_id, clarification, "Private question?")

    assert response.json() == NOT_FOUND
    assert "Citation verification failed" in caplog.text
    assert "Private" not in caplog.text


def test_settings_reach_the_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "test-embedding-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "7.5")
    app = create_app()

    with TestClient(app):
        gemini = get_gemini_client(Request({"type": "http", "app": app}))

    assert gemini._model == "test-model"
    assert gemini._embedding_model == "test-embedding-model"
    assert gemini._timeout_seconds == 7.5


def test_starting_the_app_creates_the_real_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()

    with TestClient(app):
        gemini = get_gemini_client(Request({"type": "http", "app": app}))

    assert isinstance(gemini, GeminiClient)
    assert gemini is app.state.gemini_client


def test_app_refuses_to_start_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError), TestClient(create_app()):
        pass
