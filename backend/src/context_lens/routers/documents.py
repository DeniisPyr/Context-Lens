from fastapi import APIRouter, UploadFile

from context_lens.dependencies import DocumentStoreDep, SettingsDep
from context_lens.schemas.documents import DocumentSummary
from context_lens.services.documents import add_upload

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
