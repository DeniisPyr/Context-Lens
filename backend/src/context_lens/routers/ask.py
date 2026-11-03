import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)
from context_lens.dependencies import get_gemini_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str


@router.post("")
async def ask_question(
    body: AskRequest,
    gemini: Annotated[GeminiClient, Depends(get_gemini_client)],
) -> AskResponse:
    try:
        answer = await gemini.ask(body.question)
    except GeminiUnavailableError as exc:
        logger.exception("Gemini is unavailable.")
        raise HTTPException(
            503, "Gemini is unavailable right now. Please try again."
        ) from exc
    except GeminiError as exc:
        logger.exception("Gemini could not answer.")
        raise HTTPException(502, "Gemini could not answer this question.") from exc
    return AskResponse(answer=answer)
