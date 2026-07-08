from fastapi import APIRouter

from schemas.response_schemas import SuccessResponse


health_router = APIRouter()


@health_router.get(
    "/health",
    summary="check health",
    description="Check health.",
)
async def health_check() -> SuccessResponse:
    return SuccessResponse(
        message="check was successful", data={"status": "healthy"}
    )
