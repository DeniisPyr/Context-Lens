from fastapi import Request

from context_lens.clients.gemini import GeminiClient
from context_lens.documents import DocumentStore
from context_lens.settings import Settings


def get_gemini_client(request: Request) -> GeminiClient:
    return request.app.state.gemini_client


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.document_store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
