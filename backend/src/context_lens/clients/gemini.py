import asyncio

import httpx
from google import genai
from google.genai import types

# The SDK has no public import for the errors its Interactions API raises.
from google.genai._interactions import (
    APIConnectionError,
    GeminiNextGenAPIClientError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError


class GeminiError(Exception):
    """Gemini could not answer, and trying again is unlikely to help."""


class GeminiUnavailableError(GeminiError):
    """Gemini is temporarily unavailable, so trying again later may work."""


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                # The SDK counts retries here: 1 means at most two requests.
                retry_options=types.HttpRetryOptions(attempts=1),
                httpx_async_client=http_client,
            ),
        )
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def ask[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> T:
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
            return response_model.model_validate_json(interaction.output_text)
        except ValidationError:
            # "from None": Pydantic's error quotes the output, which can hold document
            # text, and the traceback would carry it into the logs.
            raise GeminiError(
                "Gemini returned an answer in the wrong format."
            ) from None

    async def aclose(self) -> None:
        await self._client.aio.aclose()
