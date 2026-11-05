from fastapi import APIRouter

from context_lens.dependencies import DatasetStoreDep
from context_lens.schemas.datasets import DatasetCreate, DatasetResponse

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
