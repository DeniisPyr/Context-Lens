from fastapi import APIRouter

from context_lens.dependencies import DocumentStoreDep
from context_lens.schemas.documents import DocumentDetail
from context_lens.services.documents import get_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}")
async def read_document(document_id: str, store: DocumentStoreDep) -> DocumentDetail:
    return DocumentDetail.from_document(await get_document(store, document_id))
