from fastapi import APIRouter, UploadFile

from context_lens.dependencies import DatasetStoreDep, DocumentStoreDep, SettingsDep
from context_lens.schemas.datasets import DatasetCreate, DatasetResponse
from context_lens.schemas.documents import DocumentSummary
from context_lens.services.documents import add_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", status_code=201)
async def create_dataset(
    body: DatasetCreate, store: DatasetStoreDep
) -> DatasetResponse:
    return DatasetResponse.from_dataset(await store.add(body.name))


@router.get("")
async def list_datasets(store: DatasetStoreDep) -> list[DatasetResponse]:
    datasets = await store.list_all()
    return [DatasetResponse.from_dataset(dataset) for dataset in datasets]


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, store: DatasetStoreDep) -> None:
    await store.delete(dataset_id)


@router.post("/{dataset_id}/documents", status_code=201)
async def upload_document(
    dataset_id: str, file: UploadFile, store: DocumentStoreDep, settings: SettingsDep
) -> DocumentSummary:
    data = await file.read(settings.max_upload_bytes + 1)
    document = await add_upload(
        store, dataset_id, file.filename, data, settings.max_upload_bytes
    )
    return DocumentSummary.from_document(document)


@router.get("/{dataset_id}/documents")
async def list_documents(
    dataset_id: str, store: DocumentStoreDep
) -> list[DocumentSummary]:
    documents = await store.list_in_dataset(dataset_id)
    return [DocumentSummary.from_document(document) for document in documents]
