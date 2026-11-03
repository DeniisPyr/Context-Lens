from fastapi import APIRouter

from context_lens.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
