from fastapi import APIRouter

from schemas.response_schemas import SuccessResponse


healht_router = APIRouter()


@healht_router.get(
    "/health",
    summary="check health",
    description="Check health.",
)  # type: ignore[misc]
async def health_check() -> SuccessResponse:
    return SuccessResponse(message="check was successful", data={"status": "healthy"})
