import asyncio
import json
import traceback
import zlib
from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import BaseModel

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
    TokenUsage,
)

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


class Reply(BaseModel):
    text: str


def make_client(handler: Handler, timeout_seconds: float = 5.0) -> GeminiClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiClient(
        "test-key", "test-model", "test-embedding-model", timeout_seconds, http_client
    )


def gemini_answer(
    text: str = '{"text": "Ahoj"}', status: str = "completed", **fields: object
) -> httpx.Response:
    # fields are more of the interaction's top-level fields, such as usage.
    step = {"type": "model_output", "content": [{"type": "text", "text": text}]}
    return httpx.Response(
        200, json={"id": "", "status": status, "steps": [step], **fields}
    )


async def test_ask_parses_the_answer_into_the_response_model() -> None:
    gemini = make_client(lambda request: gemini_answer('{"text": "Ahoj"}'))

    answer = await gemini.ask("Say hello in Czech.", "Be brief.", Reply)

    assert answer == Reply(text="Ahoj")


async def test_ask_sends_the_prompt_and_schema_and_opts_out_of_storage() -> None:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return gemini_answer()

    await make_client(handler).ask("Say hello in Czech.", "Be brief.", Reply)

    assert sent == [
        {
            "model": "test-model",
            "input": "Say hello in Czech.",
            "system_instruction": "Be brief.",
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": Reply.model_json_schema(),
            },
            "store": False,
        }
    ]


async def test_ask_with_usage_returns_the_answer_and_its_token_counts() -> None:
    usage = {
        "total_input_tokens": 120,
        "total_output_tokens": 30,
        "total_thought_tokens": 45,
    }
    gemini = make_client(lambda request: gemini_answer(usage=usage))

    answer = await gemini.ask_with_usage("Say hello in Czech.", "Be brief.", Reply)

    assert answer == (
        Reply(text="Ahoj"),
        TokenUsage(input_tokens=120, output_tokens=30, thought_tokens=45),
    )


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({}, id="no_usage_field"),
        pytest.param({"usage": None}, id="null_usage"),
        pytest.param({"usage": {}}, id="empty_usage"),
    ],
)
async def test_missing_usage_counts_as_no_tokens(fields: dict[str, object]) -> None:
    gemini = make_client(lambda request: gemini_answer(**fields))

    _, tokens = await gemini.ask_with_usage("Hi", "Be brief.", Reply)

    assert tokens == TokenUsage(input_tokens=0, output_tokens=0, thought_tokens=0)


@pytest.mark.parametrize(
    "usage",
    [
        pytest.param({"total_input_tokens": 120}, id="fields_left_out"),
        pytest.param(
            {
                "total_input_tokens": 120,
                "total_output_tokens": None,
                "total_thought_tokens": None,
            },
            id="null_fields",
        ),
    ],
)
async def test_missing_token_count_is_zero(usage: dict[str, int | None]) -> None:
    gemini = make_client(lambda request: gemini_answer(usage=usage))

    _, tokens = await gemini.ask_with_usage("Hi", "Be brief.", Reply)

    assert tokens == TokenUsage(input_tokens=120, output_tokens=0, thought_tokens=0)


async def test_ask_returns_only_the_answer_when_gemini_reports_usage() -> None:
    usage = {"total_input_tokens": 120, "total_output_tokens": 30}
    gemini = make_client(lambda request: gemini_answer(usage=usage))

    answer = await gemini.ask("Hi", "Be brief.", Reply)

    assert answer == Reply(text="Ahoj")


@pytest.mark.parametrize("status_code", [429, 503])
async def test_overload_is_unavailable_after_one_retry(status_code: int) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json={"error": {"message": "busy"}})

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).ask("Hi", "Be brief.", Reply)

    assert len(requests) == 2


async def test_rejected_request_is_not_retried() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    with pytest.raises(GeminiError) as error:
        await make_client(handler).ask("Hi", "Be brief.", Reply)

    assert not isinstance(error.value, GeminiUnavailableError)
    assert len(requests) == 1


async def test_slow_gemini_hits_the_time_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return gemini_answer()

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler, timeout_seconds=0.01).ask("Hi", "Be brief.", Reply)


async def test_network_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).ask("Hi", "Be brief.", Reply)


async def test_cut_off_answer_is_an_error() -> None:
    gemini = make_client(lambda request: gemini_answer(status="incomplete"))

    with pytest.raises(GeminiError, match="no answer"):
        await gemini.ask("Hi", "Be brief.", Reply)


async def test_empty_answer_is_an_error() -> None:
    gemini = make_client(lambda request: gemini_answer(""))

    with pytest.raises(GeminiError, match="no answer"):
        await gemini.ask("Hi", "Be brief.", Reply)


@pytest.mark.parametrize(
    "text",
    ["this is not JSON", '{"wrong": "shape"}'],
    ids=["invalid_json", "wrong_shape"],
)
async def test_answer_in_the_wrong_format_is_an_error(text: str) -> None:
    gemini = make_client(lambda request: gemini_answer(text))

    with pytest.raises(GeminiError, match="wrong format") as error:
        await gemini.ask("Hi", "Be brief.", Reply)

    assert not isinstance(error.value, GeminiUnavailableError)


async def test_wrong_format_error_does_not_quote_the_output() -> None:
    gemini = make_client(lambda request: gemini_answer("The salary is 900 CZK"))

    with pytest.raises(GeminiError) as error:
        await gemini.ask("Hi", "Be brief.", Reply)

    assert "900 CZK" not in "".join(traceback.format_exception(error.value))


def texts(count: int) -> list[str]:
    return [f"text {number}" for number in range(count)]


def embedding_for(text: str) -> list[float]:
    # Starts with a checksum of the text, so a test can tell which text it's for.
    return [float(zlib.crc32(text.encode())), *[0.5] * 767]


def embeddings_for_each_text(request: httpx.Request) -> httpx.Response:
    sent = json.loads(request.content)["requests"]
    embeddings = [
        {"values": embedding_for(text["content"]["parts"][0]["text"])} for text in sent
    ]
    return httpx.Response(200, json={"embeddings": embeddings})


def recording(
    handler: Callable[[httpx.Request], httpx.Response], into: list[httpx.Request]
) -> Handler:
    def record(request: httpx.Request) -> httpx.Response:
        into.append(request)
        return handler(request)

    return record


async def test_embed_returns_an_embedding_for_each_text_in_order() -> None:
    gemini = make_client(embeddings_for_each_text)

    embeddings = await gemini.embed(texts(3))

    assert embeddings == [embedding_for(text) for text in texts(3)]


async def test_embed_sends_each_text_as_its_own_content_with_the_model() -> None:
    requests = []

    await make_client(recording(embeddings_for_each_text, requests)).embed(
        ["Příliš žluťoučký kůň", "second"]
    )

    [request] = requests
    assert request.url.path.endswith("/models/test-embedding-model:batchEmbedContents")
    assert json.loads(request.content) == {
        "requests": [
            {
                "content": {"parts": [{"text": "Příliš žluťoučký kůň"}]},
                "outputDimensionality": 768,
                "model": "models/test-embedding-model",
            },
            {
                "content": {"parts": [{"text": "second"}]},
                "outputDimensionality": 768,
                "model": "models/test-embedding-model",
            },
        ]
    }


@pytest.mark.parametrize(
    ("count", "sizes"),
    [
        pytest.param(1, [1], id="one"),
        pytest.param(100, [100], id="exactly_100"),
        pytest.param(101, [100, 1], id="one_over_100"),
        pytest.param(250, [100, 100, 50], id="250"),
    ],
)
async def test_embed_sends_at_most_100_texts_in_a_request(
    count: int, sizes: list[int]
) -> None:
    requests = []
    gemini = make_client(recording(embeddings_for_each_text, requests))

    embeddings = await gemini.embed(texts(count))

    assert [len(json.loads(r.content)["requests"]) for r in requests] == sizes
    assert embeddings == [embedding_for(text) for text in texts(count)]


async def test_embedding_no_texts_sends_no_request() -> None:
    requests = []
    gemini = make_client(recording(embeddings_for_each_text, requests))

    assert await gemini.embed([]) == []
    assert requests == []


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"embeddings": [{"values": [0.5] * 768}]}, id="fewer"),
        pytest.param({"embeddings": [{"values": [0.5] * 768}] * 3}, id="more"),
        pytest.param({"embeddings": []}, id="none"),
        pytest.param({}, id="no_embeddings_field"),
    ],
)
async def test_wrong_number_of_embeddings_is_an_error(body: dict) -> None:
    gemini = make_client(lambda request: httpx.Response(200, json=body))

    with pytest.raises(GeminiError, match="embeddings for 2 texts") as error:
        await gemini.embed(texts(2))

    assert not isinstance(error.value, GeminiUnavailableError)


@pytest.mark.parametrize(
    "embedding",
    [
        pytest.param({"values": [0.5] * 767}, id="767_numbers"),
        pytest.param({"values": [0.5] * 769}, id="769_numbers"),
        pytest.param({"values": []}, id="no_numbers"),
        pytest.param({}, id="no_values_field"),
    ],
)
async def test_embedding_of_the_wrong_size_is_an_error(embedding: dict) -> None:
    body = {"embeddings": [{"values": [0.5] * 768}, embedding]}
    gemini = make_client(lambda request: httpx.Response(200, json=body))

    with pytest.raises(GeminiError, match="wrong size"):
        await gemini.embed(texts(2))


async def test_embedding_in_the_wrong_format_is_an_error() -> None:
    body = {"embeddings": [{"values": ["not a number"] * 768}]}
    gemini = make_client(lambda request: httpx.Response(200, json=body))

    with pytest.raises(GeminiError, match="wrong format") as error:
        await gemini.embed(texts(1))

    assert not isinstance(error.value, GeminiUnavailableError)


@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_overloaded_embedding_is_unavailable_without_a_retry(
    status_code: int,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json={"error": {"message": "busy"}})

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).embed(texts(1))

    assert len(requests) == 1


@pytest.mark.parametrize("status_code", [400, 403, 404])
async def test_rejected_embedding_request_is_an_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "rejected"}})

    with pytest.raises(GeminiError, match="rejected") as error:
        await make_client(handler).embed(texts(1))

    assert not isinstance(error.value, GeminiUnavailableError)


async def test_slow_embedding_hits_the_time_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return embeddings_for_each_text(request)

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler, timeout_seconds=0.01).embed(texts(1))


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(httpx.ConnectError("Connection refused"), id="connect"),
        pytest.param(httpx.ReadTimeout("Timed out"), id="read_timeout"),
        pytest.param(httpx.RemoteProtocolError("Disconnected"), id="disconnected"),
    ],
)
async def test_network_failure_while_embedding_is_unavailable(
    error: httpx.TransportError,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).embed(texts(1))


async def test_failure_of_a_later_request_fails_the_whole_embed() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 2:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return embeddings_for_each_text(request)

    with pytest.raises(GeminiUnavailableError):
        await make_client(handler).embed(texts(150))

    assert len(requests) == 2
