from fastapi import APIRouter

from context_lens.routers import health

router = APIRouter(prefix="/api")

router.include_router(health.router)
