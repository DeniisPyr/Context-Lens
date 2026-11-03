from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from context_lens.clients.gemini import GeminiClient
from context_lens.documents import DocumentStore
from context_lens.routers import api
from context_lens.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    gemini_client = GeminiClient(
        settings.gemini_api_key.get_secret_value(), settings.gemini_model
    )
    app.state.gemini_client = gemini_client
    app.state.document_store = DocumentStore()
    yield
    await gemini_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Context-Lens API", lifespan=lifespan)
    app.include_router(api.router)
    return app


app = create_app()
