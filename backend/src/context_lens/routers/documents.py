from fastapi import APIRouter, UploadFile

from context_lens.dependencies import DocumentStoreDep, SettingsDep
from context_lens.schemas.documents import DocumentDetail, DocumentSummary
from context_lens.services.documents import add_upload, get_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile, store: DocumentStoreDep, settings: SettingsDep
) -> DocumentSummary:
    data = await file.read(settings.max_upload_bytes + 1)
    document = add_upload(store, file.filename, data, settings.max_upload_bytes)
    return DocumentSummary.from_document(document)


@router.get("")
async def list_documents(store: DocumentStoreDep) -> list[DocumentSummary]:
    return [DocumentSummary.from_document(document) for document in store.list_all()]


@router.get("/{document_id}")
async def read_document(document_id: str, store: DocumentStoreDep) -> DocumentDetail:
    return DocumentDetail.from_document(get_document(store, document_id))
