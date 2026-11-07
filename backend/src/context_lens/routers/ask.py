from fastapi import APIRouter

from context_lens.dependencies import (
    ChunkStoreDep,
    DocumentStoreDep,
    GeminiDep,
    SettingsDep,
)
from context_lens.schemas.ask import AskRequest, AskResponse
from context_lens.services.search import answer_from_dataset

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("")
async def ask_question(
    body: AskRequest,
    gemini: GeminiDep,
    chunks: ChunkStoreDep,
    documents: DocumentStoreDep,
    settings: SettingsDep,
) -> AskResponse:
    answer = await answer_from_dataset(
        body.question,
        body.dataset_id,
        chunks,
        documents,
        gemini,
        settings.chunks_per_question,
    )
    return AskResponse.from_answer(answer)
