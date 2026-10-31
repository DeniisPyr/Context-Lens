from fastapi import FastAPI

from context_lens.routers import api


def create_app() -> FastAPI:
    app = FastAPI(title="Context-Lens API")
    app.include_router(api.router)
    return app


app = create_app()
