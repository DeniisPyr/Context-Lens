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


class GeminiError(Exception):
    """Gemini could not answer, and trying again is unlikely to help."""


class GeminiUnavailableError(GeminiError):
    """Gemini is temporarily unavailable, so trying again later may work."""


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
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

    async def ask(self, prompt: str, system_instruction: str) -> str:
        try:
            interaction = await asyncio.wait_for(
                self._client.aio.interactions.create(
                    model=self._model,
                    input=prompt,
                    system_instruction=system_instruction,
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
        return interaction.output_text

    async def aclose(self) -> None:
        await self._client.aio.aclose()
