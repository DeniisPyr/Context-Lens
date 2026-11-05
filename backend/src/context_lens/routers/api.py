from fastapi import APIRouter

from context_lens.routers import ask, datasets, documents, health

router = APIRouter(prefix="/api")

router.include_router(health.router)
router.include_router(ask.router)
router.include_router(datasets.router)
router.include_router(documents.router)
