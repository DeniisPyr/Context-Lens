from pathlib import Path

import pytest
from conftest import FakeGemini
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


def test_ask_returns_only_the_answer(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.answer = "Ahoj"

    response = client.post("/api/ask", json={"question": "Say hello in Czech."})

    assert response.status_code == 200
    assert response.json() == {"answer": "Ahoj"}


def test_ask_strips_whitespace_around_the_question(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    response = client.post("/api/ask", json={"question": "  Say hello in Czech.\n"})

    assert response.status_code == 200
    assert fake_gemini.questions == ["Say hello in Czech."]


@pytest.mark.parametrize(
    "question",
    ["", " \t\n", "x" * 2001],
    ids=["empty", "whitespace_only", "too_long"],
)
def test_invalid_question_is_rejected_without_calling_gemini(
    client: TestClient, fake_gemini: FakeGemini, question: str
) -> None:
    response = client.post("/api/ask", json={"question": question})

    assert response.status_code == 422
    assert fake_gemini.questions == []


def test_longest_allowed_question_is_accepted(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    question = "x" * 2000

    response = client.post("/api/ask", json={"question": question})

    assert response.status_code == 200
    assert fake_gemini.questions == [question]


def test_unavailable_gemini_returns_503(
    client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.error = GeminiUnavailableError("Gemini is unavailable right now.")

    response = client.post("/api/ask", json={"question": "Hi"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Gemini is unavailable right now. Please try again."
    }


def test_gemini_error_returns_502(client: TestClient, fake_gemini: FakeGemini) -> None:
    fake_gemini.error = GeminiError("Gemini rejected the request.")

    response = client.post("/api/ask", json={"question": "Hi"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini could not answer this question."}


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
