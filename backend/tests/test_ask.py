from pathlib import Path
from uuid import uuid4

import pytest
from conftest import FakeGemini, create_dataset
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)
from context_lens.dependencies import get_gemini_client
from context_lens.main import create_app
from context_lens.services.answering import (
    NOT_FOUND_MESSAGE,
    SYSTEM_INSTRUCTION,
    Citation,
    ModelAnswer,
)


def upload_document(client: TestClient, text: str = "The cat is orange.") -> str:
    # A dataset of its own, so that a test can upload this filename more than once.
    documents_url = create_dataset(client, uuid4().hex)
    response = client.post(documents_url, files={"file": ("notes.txt", text.encode())})
    return response.json()["id"]


def test_ask_returns_the_answer_with_citations_to_the_document(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    quote = "The cat is orange.\nThe dog is brown."
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="The cat is orange and the dog is brown.",
        citations=[Citation(start_line=2, end_line=3, quote=quote)],
    )
    document_id = upload_document(client, f"Pets:\n{quote}")

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Describe the pets."}
    )

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


def test_fabricated_citation_returns_the_not_found_message(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="answered",
        answer="The cat is purple.",
        citations=[Citation(start_line=1, end_line=1, quote="The cat is purple.")],
    )
    document_id = upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "What colour is it?"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "not_found",
        "answer": NOT_FOUND_MESSAGE,
        "citations": [],
    }


def test_not_found_from_gemini_returns_the_fixed_message(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = ModelAnswer(
        status="not_found", answer="The document does not say.", citations=[]
    )
    document_id = upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "How old is the cat?"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "not_found",
        "answer": NOT_FOUND_MESSAGE,
        "citations": [],
    }


def test_prompt_has_the_requested_document_and_the_stripped_question(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    upload_document(client, "Another document.")
    document_id = upload_document(client, "The cat is orange.")

    response = client.post(
        "/api/ask",
        json={"document_id": document_id, "question": "  What colour is the cat?\n"},
    )

    assert response.status_code == 200
    [prompt] = fake_gemini.prompts
    assert "<document>\n1: The cat is orange.\n</document>" in prompt
    assert prompt.endswith("What colour is the cat?")
    assert "Another document." not in prompt
    assert "notes.txt" not in prompt


def test_prompt_numbers_each_line_of_the_document(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    document_id = upload_document(client, "first line\nsecond line\n")

    client.post(
        "/api/ask", json={"document_id": document_id, "question": "What is on line 2?"}
    )

    [prompt] = fake_gemini.prompts
    assert "<document>\n1: first line\n2: second line\n</document>" in prompt
    assert prompt.endswith("What is on line 2?")


def test_prompt_numbering_matches_the_line_count_from_the_upload(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    # str.splitlines() would treat this form feed as a line break, making three lines.
    upload = client.post(
        create_dataset(client),
        files={"file": ("notes.txt", b"one\x0cstill one\ntwo\n")},
    )

    client.post("/api/ask", json={"document_id": upload.json()["id"], "question": "Hi"})

    assert upload.json()["line_count"] == 2
    [prompt] = fake_gemini.prompts
    assert "<document>\n1: one\x0cstill one\n2: two\n</document>" in prompt


def test_gemini_receives_the_system_instruction(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    document_id = upload_document(client)

    client.post("/api/ask", json={"document_id": document_id, "question": "Hi"})

    assert fake_gemini.system_instructions == [SYSTEM_INSTRUCTION]


def test_gemini_is_asked_for_a_model_answer(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    document_id = upload_document(client)

    client.post("/api/ask", json={"document_id": document_id, "question": "Hi"})

    assert fake_gemini.response_models == [ModelAnswer]


def test_unknown_document_returns_404_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    response = client.post(
        "/api/ask", json={"document_id": "unknown", "question": "Hi"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}
    assert fake_gemini.prompts == []


@pytest.mark.parametrize("document_id", ["not-a-uuid", "", "\x00", str(uuid4())])
def test_bad_or_unknown_document_id_returns_404_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, document_id: str
) -> None:
    upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Hi"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}
    assert fake_gemini.prompts == []


def test_no_database_connection_is_held_while_gemini_answers(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    document_id = upload_document(client)
    pool = client.app.state.engine.pool
    during_the_call = []
    fake_gemini.during_call = lambda: during_the_call.append(
        (pool.checkedout(), pool.checkedin())
    )

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Hi"}
    )

    assert response.status_code == 200
    # None in use, and the one the store used is back in the pool.
    assert during_the_call == [(0, 1)]


def test_missing_document_id_returns_422_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    response = client.post("/api/ask", json={"question": "Hi"})

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
    document_id = upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": question}
    )

    assert response.status_code == 422
    assert fake_gemini.prompts == []


def test_longest_allowed_question_is_accepted(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    document_id = upload_document(client)
    question = "x" * 2000

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": question}
    )

    assert response.status_code == 200
    assert fake_gemini.prompts[0].endswith(question)


def test_unavailable_gemini_returns_503(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.error = GeminiUnavailableError("Gemini is unavailable right now.")
    document_id = upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Hi"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Gemini is unavailable right now. Please try again."
    }


def test_gemini_error_returns_502(client: TestClient, fake_gemini: FakeGemini) -> None:
    fake_gemini.error = GeminiError("Gemini rejected the request.")
    document_id = upload_document(client)

    response = client.post(
        "/api/ask", json={"document_id": document_id, "question": "Hi"}
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini could not answer this question."}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (GeminiUnavailableError("Busy."), "Gemini is unavailable."),
        (GeminiError("Rejected."), "Gemini could not answer."),
    ],
    ids=["unavailable", "rejected"],
)
def test_gemini_failure_is_logged_with_its_cause(
    client: TestClient,
    fake_gemini: FakeGemini,
    caplog: pytest.LogCaptureFixture,
    error: GeminiError,
    message: str,
) -> None:
    fake_gemini.error = error
    document_id = upload_document(client)

    client.post("/api/ask", json={"document_id": document_id, "question": "Hi"})

    logged = [record for record in caplog.records if record.getMessage() == message]
    assert [record.exc_info[1] for record in logged if record.exc_info] == [error]


def test_settings_reach_the_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "7.5")
    app = create_app()

    with TestClient(app):
        gemini = get_gemini_client(Request({"type": "http", "app": app}))

    assert gemini._model == "test-model"
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
