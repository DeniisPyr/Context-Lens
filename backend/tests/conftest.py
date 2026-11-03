from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from context_lens.dependencies import get_gemini_client
from context_lens.main import create_app


class FakeGemini:
    def __init__(self) -> None:
        self.answer = "Ahoj"
        self.error: Exception | None = None
        self.prompts: list[str] = []
        self.system_instructions: list[str] = []

    async def ask(self, prompt: str, system_instruction: str) -> str:
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        if self.error is not None:
            raise self.error
        return self.answer


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
