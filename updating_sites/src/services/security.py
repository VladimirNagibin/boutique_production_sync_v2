import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt  # type: ignore[import-untyped]

from core.settings import settings


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Создает JWT токен"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access", "jti": str(uuid.uuid4())})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return encoded_jwt  # type: ignore[no-any-return]


def create_refresh_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Создает refresh token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode.update({"exp": expire, "type": "refresh", "jti": str(uuid.uuid4())})

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    return encoded_jwt  # type: ignore[no-any-return]


def decode_token(token: str) -> dict[str, Any] | None:
    """Декодирует и проверяет токен"""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload  # type: ignore[no-any-return]
    except JWTError:
        return None


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Проверяет access токен"""
    payload = decode_token(token)

    if not payload:
        return None

    # Проверяем тип токена
    if payload.get("type") != "access":
        return None

    return payload


def verify_refresh_token(token: str) -> dict[str, Any] | None:
    """Проверяет refresh token"""
    payload = decode_token(token)

    if not payload:
        return None

    # Проверяем тип токена
    if payload.get("type") != "refresh":
        return None

    return payload
