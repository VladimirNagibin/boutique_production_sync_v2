from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from core.settings import settings


API_KEY_NAME = "X-API-Key"
API_KEY = settings.SECRET_KEY

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str | None = Depends(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API Key is required. Please provide X-API-Key header",
        )

    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid API Key: {api_key[:3]}...",
        )
    return api_key
