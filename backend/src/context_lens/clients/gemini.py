import asyncio
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import errors, types

# The SDK has no public import for the errors its Interactions API raises.
from google.genai._interactions import (
    APIConnectionError,
    GeminiNextGenAPIClientError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from context_lens.services.embeddings import EMBEDDING_DIMENSIONS

# The most texts Gemini embeds in one request.
MAX_TEXTS_PER_EMBEDDING_REQUEST = 100


class GeminiError(Exception):
    """Gemini could not answer, and trying again is unlikely to help."""


class GeminiUnavailableError(GeminiError):
    """Gemini is temporarily unavailable, so trying again later may work."""


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


def _embedding_values(
    response: types.EmbedContentResponse, count: int
) -> list[list[float]]:
    embeddings = [embedding.values for embedding in response.embeddings or []]
    if len(embeddings) != count:
        raise GeminiError(
            f"Gemini returned {len(embeddings)} embeddings for {count} texts."
        )
    for values in embeddings:
        if values is None or len(values) != EMBEDDING_DIMENSIONS:
            raise GeminiError("Gemini returned an embedding of the wrong size.")
    return embeddings


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        embedding_model: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                # The Interactions API counts this as retries, so ask makes at most two
                # requests. Embedding counts it as attempts, so it makes one.
                retry_options=types.HttpRetryOptions(attempts=1),
                httpx_async_client=http_client,
            ),
        )
        self._model = model
        self._embedding_model = embedding_model
        self._timeout_seconds = timeout_seconds

    async def ask[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> T:
        answer, _ = await self.ask_with_usage(
            prompt, system_instruction, response_model
        )
        return answer

    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]:
        try:
            interaction = await asyncio.wait_for(
                self._client.aio.interactions.create(
                    model=self._model,
                    input=prompt,
                    system_instruction=system_instruction,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": response_model.model_json_schema(),
                    },
                    # Gemini keeps requests for 55 days unless told not to.
                    store=False,
                ),
                timeout=self._timeout_seconds,
            )
        except (
            TimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as exc:
            raise GeminiUnavailableError("Gemini is unavailable right now.") from exc
        except GeminiNextGenAPIClientError as exc:
            raise GeminiError("Gemini rejected the request.") from exc

        if interaction.status != "completed" or not interaction.output_text:
            raise GeminiError(f"Gemini gave no answer: {interaction.status}.")
        try:
            answer = response_model.model_validate_json(interaction.output_text)
        except ValidationError:
            # "from None": Pydantic's error quotes the output, which can hold document
            # text, and the traceback would carry it into the logs.
            raise GeminiError(
                "Gemini returned an answer in the wrong format."
            ) from None

        # Gemini leaves out the usage, or any count in it, when it has none to report.
        usage = interaction.usage
        if usage is None:
            return answer, TokenUsage()
        return answer, TokenUsage(
            input_tokens=usage.total_input_tokens or 0,
            output_tokens=usage.total_output_tokens or 0,
            thought_tokens=usage.total_thought_tokens or 0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        for start in range(0, len(texts), MAX_TEXTS_PER_EMBEDDING_REQUEST):
            batch = texts[start : start + MAX_TEXTS_PER_EMBEDDING_REQUEST]
            embeddings += await self._embed_batch(batch)
        return embeddings

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self._embedding_model,
                    # gemini-embedding-2 turns a list of plain strings into a single
                    # embedding, so each text goes in a Content of its own.
                    contents=[
                        types.Content(parts=[types.Part(text=text)]) for text in texts
                    ],
                    config=types.EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIMENSIONS
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        # Unlike the Interactions API, this one lets httpx's own errors through.
        except (TimeoutError, httpx.TransportError) as exc:
            raise GeminiUnavailableError("Gemini is unavailable right now.") from exc
        except errors.APIError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise GeminiUnavailableError(
                    "Gemini is unavailable right now."
                ) from exc
            raise GeminiError("Gemini rejected the request.") from exc
        except ValidationError:
            # "from None": Pydantic's error repeats the response, hundreds of numbers.
            raise GeminiError(
                "Gemini returned embeddings in the wrong format."
            ) from None
        return _embedding_values(response, len(texts))

    async def aclose(self) -> None:
        await self._client.aio.aclose()
