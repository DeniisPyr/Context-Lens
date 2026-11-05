import pytest
from conftest import StartApp
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from context_lens.clients.gemini import GeminiClient


@pytest.fixture
def recorded_closes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    closes = []
    close_gemini = GeminiClient.aclose
    dispose_engine = AsyncEngine.dispose

    async def recording_close(self: GeminiClient) -> None:
        closes.append("gemini")
        await close_gemini(self)

    async def recording_dispose(self: AsyncEngine) -> None:
        closes.append("engine")
        await dispose_engine(self)

    monkeypatch.setattr(GeminiClient, "aclose", recording_close)
    monkeypatch.setattr(AsyncEngine, "dispose", recording_dispose)
    return closes


def test_starting_the_app_does_not_connect(client_without_database: TestClient) -> None:
    pool = client_without_database.app.state.engine.pool

    assert pool.checkedout() == 0
    assert pool.checkedin() == 0


@pytest.mark.usefixtures("clean_database")
def test_stopping_the_app_closes_the_database_connections(start_app: StartApp) -> None:
    with start_app() as client:
        client.post("/api/documents", files={"file": ("a.txt", b"hello")})
        engine = client.app.state.engine
        assert engine.pool.checkedin() == 1

    assert engine.pool.checkedin() == 0


def test_stopping_the_app_closes_both_clients(
    start_app: StartApp, recorded_closes: list[str]
) -> None:
    with start_app():
        pass

    assert sorted(recorded_closes) == ["engine", "gemini"]


def test_engine_is_disposed_when_closing_gemini_fails(
    start_app: StartApp,
    recorded_closes: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_close(self: GeminiClient) -> None:
        raise RuntimeError("close failed")

    monkeypatch.setattr(GeminiClient, "aclose", failing_close)

    with pytest.raises(RuntimeError, match="close failed"), start_app():
        pass

    assert recorded_closes == ["engine"]


def test_gemini_is_closed_when_disposing_the_engine_fails(
    start_app: StartApp,
    recorded_closes: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_dispose(self: AsyncEngine) -> None:
        raise RuntimeError("dispose failed")

    monkeypatch.setattr(AsyncEngine, "dispose", failing_dispose)

    with pytest.raises(RuntimeError, match="dispose failed"), start_app():
        pass

    assert recorded_closes == ["gemini"]
