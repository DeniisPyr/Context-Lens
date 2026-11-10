import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from context_lens.clients.gemini import GeminiClient
from context_lens.db.chunk_store import ChunkStore
from context_lens.db.dataset_store import DatasetStore
from context_lens.db.document_store import DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.exception_handlers import register_exception_handlers
from context_lens.routers import api
from context_lens.settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    if settings.access_password is None:
        # A warning rather than an error: on a developer's own machine it's fine.
        logger.warning(
            "ACCESS_PASSWORD isn't set, so anyone who can reach the app can read "
            "every document and spend the Gemini credits."
        )
    # Doesn't connect until the first query, so the app starts with the database down.
    engine = create_database_engine(settings)
    gemini_client = GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        settings.gemini_model,
        settings.gemini_embedding_model,
        settings.gemini_timeout_seconds,
    )
    app.state.settings = settings
    app.state.gemini_client = gemini_client
    app.state.engine = engine
    app.state.dataset_store = DatasetStore(engine)
    app.state.document_store = DocumentStore(engine)
    app.state.chunk_store = ChunkStore(engine)
    yield
    try:
        await gemini_client.aclose()
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Context-Lens API", lifespan=lifespan)
    app.include_router(api.router)
    register_exception_handlers(app)
    return app


app = create_app()
