from fastapi import APIRouter

from core.logger import get_logger
from schemas.response_schemas import SuccessResponse


logger = get_logger(__name__)

health_router = APIRouter()


@health_router.get(
    "/health",
    summary="check health",
    description="Check health.",
)
async def health_check() -> SuccessResponse:
    logger.debug(
        "Health check completed",
        extra={"status": "healthy"},
    )
    return SuccessResponse(
        message="check was successful", data={"status": "healthy"}
    )
