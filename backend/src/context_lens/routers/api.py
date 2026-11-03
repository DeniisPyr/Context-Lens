from fastapi import APIRouter

from context_lens.routers import ask, health

router = APIRouter(prefix="/api")

router.include_router(health.router)
router.include_router(ask.router)
