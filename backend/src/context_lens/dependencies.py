from typing import Annotated

from fastapi import Depends, Request

from context_lens.clients.gemini import GeminiClient
from context_lens.services.documents import DocumentStore
from context_lens.settings import Settings


def get_gemini_client(request: Request) -> GeminiClient:
    return request.app.state.gemini_client


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.document_store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


GeminiDep = Annotated[GeminiClient, Depends(get_gemini_client)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
