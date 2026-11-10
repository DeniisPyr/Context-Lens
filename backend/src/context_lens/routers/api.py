from fastapi import APIRouter, Depends

from context_lens.dependencies import require_session
from context_lens.routers import ask, datasets, documents, health, session

router = APIRouter(prefix="/api")

# Open, so that the app can be checked and a visitor can log in.
router.include_router(health.router)
router.include_router(session.router)
# Every other router needs a session, set here for all of its routes so that none of
# them can be left open by mistake.
router.include_router(ask.router, dependencies=[Depends(require_session)])
router.include_router(datasets.router, dependencies=[Depends(require_session)])
router.include_router(documents.router, dependencies=[Depends(require_session)])
