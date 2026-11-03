from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from context_lens.answering import Citation, ModelAnswer
from context_lens.dependencies import get_gemini_client
from context_lens.main import create_app


class FakeGemini:
    def __init__(self) -> None:
        # Passes verification against the default document in test_ask.upload_document.
        self.answer = ModelAnswer(
            status="answered",
            answer="The cat is orange.",
            citations=[Citation(start_line=1, end_line=1, quote="The cat is orange.")],
        )
        self.error: Exception | None = None
        self.prompts: list[str] = []
        self.system_instructions: list[str] = []
        self.response_models: list[type[BaseModel]] = []

    async def ask(
        self, prompt: str, system_instruction: str, response_model: type[BaseModel]
    ) -> ModelAnswer:
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        self.response_models.append(response_model)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def no_developer_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Settings reads .env from the working directory and then the environment, and a
    # developer's own values there must not change the results.
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS", "MAX_UPLOAD_BYTES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, fake_gemini: FakeGemini
) -> Iterator[TestClient]:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_gemini_client] = lambda: fake_gemini
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
