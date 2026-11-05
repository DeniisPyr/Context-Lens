from typing import Annotated

from fastapi import Depends, Request

from context_lens.clients.gemini import GeminiClient
from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentStore
from context_lens.settings import Settings


def get_gemini_client(request: Request) -> GeminiClient:
    return request.app.state.gemini_client


def get_dataset_store(request: Request) -> DatasetStore:
    return request.app.state.dataset_store


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.document_store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


GeminiDep = Annotated[GeminiClient, Depends(get_gemini_client)]
DatasetStoreDep = Annotated[DatasetStore, Depends(get_dataset_store)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
