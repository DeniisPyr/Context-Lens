import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def make_client(handler: Handler, timeout_seconds: float = 5.0) -> GeminiClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiClient("test-key", "test-model", timeout_seconds, http_client)


def gemini_answer(text: str = "Ahoj", status: str = "completed") -> httpx.Response:
    step = {"type": "model_output", "content": [{"type": "text", "text": text}]}
    return httpx.Response(200, json={"id": "", "status": status, "steps": [step]})


async def test_ask_returns_the_answer() -> None:
    gemini = make_client(lambda request: gemini_answer("Ahoj"))

    assert await gemini.ask("Say hello in Czech.", "Be brief.") == "Ahoj"


async def test_ask_sends_the_prompt_and_instruction_and_opts_out_of_storage() -> None:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return gemini_answer()

    await make_client(handler).ask("Say hello in Czech.", "Be brief.")

    assert sent == [
        {
            "model": "test-model",
            "input": "Say hello in Czech.",
            "system_instruction": "Be brief.",
            "store": False,
        }
    ]


@pytest.mark.parametrize("status_code", [429, 503])
async def test_overload_is_unavailable_after_one_retry(status_code: int) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json={"error": {"message": "busy"}})

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).ask("Hi", "Be brief.")

    assert len(requests) == 2


async def test_rejected_request_is_not_retried() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    with pytest.raises(GeminiError) as error:
        await make_client(handler).ask("Hi", "Be brief.")

    assert not isinstance(error.value, GeminiUnavailableError)
    assert len(requests) == 1


async def test_slow_gemini_hits_the_time_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return gemini_answer()

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler, timeout_seconds=0.01).ask("Hi", "Be brief.")


async def test_network_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).ask("Hi", "Be brief.")


async def test_cut_off_answer_is_an_error() -> None:
    gemini = make_client(lambda request: gemini_answer("Aho", status="incomplete"))

    with pytest.raises(GeminiError):
        await gemini.ask("Hi", "Be brief.")


async def test_empty_answer_is_an_error() -> None:
    gemini = make_client(lambda request: gemini_answer(""))

    with pytest.raises(GeminiError):
        await gemini.ask("Hi", "Be brief.")
