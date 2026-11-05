from fastapi import APIRouter

from context_lens.dependencies import DocumentStoreDep, GeminiDep
from context_lens.schemas.ask import AskRequest, AskResponse
from context_lens.services.answering import answer_question
from context_lens.services.documents import get_document

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("")
async def ask_question(
    body: AskRequest, gemini: GeminiDep, store: DocumentStoreDep
) -> AskResponse:
    document = await get_document(store, body.document_id)
    answer = await answer_question(body.question, document, gemini)
    return AskResponse.from_answer(answer, document)
