from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from core.logger import get_logger
from core.settings import settings
from services.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

from schemas.v1.response_schemas import TokenData


logger = get_logger(__name__)

API_KEY_NAME = "X-API-Key"
API_KEY = settings.CLIENT_SECRET

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str | None = Depends(api_key_header)) -> str:
    if api_key != API_KEY:
        logger.warning("Invalid API key rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    assert api_key is not None
    return api_key


async def get_current_user_from_cookie(
    request: Request,
) -> tuple[TokenData, dict[str, Any] | None]:
    """
    Проверяет Access Token. Если истек — пробует обновить через Refresh Token.
    """
    # 1. Пытаемся получить пользователя из Access Token
    access_token = request.cookies.get("access_token")

    if access_token:
        try:
            payload = decode_token(access_token)
            if payload and payload.get("type") == "access":
                token_role = payload.get("role")
                # token_user_bitrix_id = payload.get("user_bitrix_id")
                if token_role:  # and token_user_bitrix_id:
                    return (
                        TokenData(
                            role=str(token_role),
                            # user_bitrix_id=int(token_user_bitrix_id),
                        ),
                        None,
                    )
        except Exception as error:
            # Токен истек или невалиден. Падаем ниже на попытку обновления.
            logger.warning(
                "Access token invalid or expired",
                extra={"path": request.url.path, "error": str(error)},
            )

    # 2. Если пользователь не найден через Access Token, пробуем Refresh Token

    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        # Нет токенов — редирект на логин
        logger.warning(
            "Refresh token missing",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/api/v1/auth/login"},
            detail="Refresh token missing",
        )

    try:
        payload = decode_token(refresh_token)
        if not payload or (payload and payload.get("type") != "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        token_user_id = payload.get("sub")
        token_role = payload.get("role")
        # token_user_bitrix_id = payload.get("user_bitrix_id")
        if not token_user_id or not token_role:  # or not token_user_bitrix_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # 3. ПОЛУЧИЛИ НОВОГО ПОЛЬЗОВАТЕЛЯ ЧЕРЕЗ REFRESH.
        # Генерируем НОВУЮ пару токенов
        # (Refresh Token Rotation - рекомендованная практика)
        data: dict[str, Any] = {
            "sub": str(token_user_id),
            "role": str(token_role),
            # "user_bitrix_id": int(token_user_bitrix_id),
        }
        new_access_token = create_access_token(data=data)
        new_refresh_token = create_refresh_token(data=data)

        new_cookies = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        }

        logger.info(
            "Tokens refreshed",
            extra={
                "username": str(token_user_id),
                "role": str(token_role),
                "path": request.url.path,
            },
        )
        return (
            TokenData(
                role=str(token_role),  # user_bitrix_id=int(token_user_bitrix_id)
            ),
            new_cookies,
        )
    except HTTPException as error:
        logger.warning(
            "Refresh token rejected",
            extra={"path": request.url.path, "reason": error.detail},
        )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/api/v1/auth/login"},
            detail="Could not validate credentials",
        ) from error
    except Exception as error:
        # Refresh токен тоже невалиден — редирект на логин
        logger.warning(
            "Refresh token invalid",
            extra={"path": request.url.path, "error": str(error)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/api/v1/auth/login"},
            detail="Could not validate credentials",
        ) from error
