import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from core.logger import get_logger
from core.settings import settings


logger = get_logger(__name__)

API_KEY_NAME = "X-API-Key"
API_KEY = settings.auth.secret_key.get_secret_value()

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str:
    if not api_key:
        logger.warning(
            "API key authentication rejected",
            extra={
                "reason": "missing_api_key",
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=401,
            detail="API Key is required. Please provide X-API-Key header",
        )
    if not secrets.compare_digest(api_key, API_KEY):
        logger.warning(
            "API key authentication rejected",
            extra={
                "reason": "invalid_api_key",
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return api_key
