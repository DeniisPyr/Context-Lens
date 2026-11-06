import asyncio
from dataclasses import dataclass

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


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


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

    async def aclose(self) -> None:
        await self._client.aio.aclose()
