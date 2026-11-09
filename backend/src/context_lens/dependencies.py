import time
from typing import Annotated

from fastapi import Depends, Request

from context_lens.clients.gemini import GeminiClient
from context_lens.db.chunk_store import ChunkStore
from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentStore
from context_lens.services.sessions import require_login
from context_lens.session_cookie import COOKIE_NAME
from context_lens.settings import Settings


def get_gemini_client(request: Request) -> GeminiClient:
    return request.app.state.gemini_client


def get_dataset_store(request: Request) -> DatasetStore:
    return request.app.state.dataset_store


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.document_store


def get_chunk_store(request: Request) -> ChunkStore:
    return request.app.state.chunk_store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_cookie(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)


GeminiDep = Annotated[GeminiClient, Depends(get_gemini_client)]
DatasetStoreDep = Annotated[DatasetStore, Depends(get_dataset_store)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
ChunkStoreDep = Annotated[ChunkStore, Depends(get_chunk_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionCookieDep = Annotated[str | None, Depends(get_session_cookie)]


def require_session(session: SessionCookieDep, settings: SettingsDep) -> None:
    require_login(session, settings.access_password, time.time())
