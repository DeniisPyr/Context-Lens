import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from context_lens.answering import SYSTEM_INSTRUCTION, build_prompt
from context_lens.clients.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
)
from context_lens.dependencies import get_document_store, get_gemini_client
from context_lens.documents import DocumentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str
    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str


@router.post("")
async def ask_question(
    body: AskRequest,
    gemini: Annotated[GeminiClient, Depends(get_gemini_client)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> AskResponse:
    document = store.get(body.document_id)
    if document is None:
        raise HTTPException(404, "Document not found.")
    try:
        answer = await gemini.ask(
            build_prompt(body.question, document), SYSTEM_INSTRUCTION
        )
    except GeminiUnavailableError as exc:
        logger.exception("Gemini is unavailable.")
        raise HTTPException(
            503, "Gemini is unavailable right now. Please try again."
        ) from exc
    except GeminiError as exc:
        logger.exception("Gemini could not answer.")
        raise HTTPException(502, "Gemini could not answer this question.") from exc
    return AskResponse(answer=answer)
