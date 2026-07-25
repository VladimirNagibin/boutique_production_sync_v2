from core.settings import settings
from schemas.v1.response_schemas import TokenResponse

from .security import (
    create_access_token,
    create_refresh_token,
)


class UserAuthService:
    """Репозиторий авторизации."""

    async def create_tokens(self, username: str, role: str = "user") -> TokenResponse:
        # Создаем токены
        access_token = create_access_token(
            data={
                "sub": username,
                "role": role,
            }
        )

        refresh_token = create_refresh_token(
            data={
                "sub": username,
                "role": role,
            }
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.TOKEN_EXPIRE_MINUTES * 60,
        )


def get_auth_service() -> UserAuthService:
    return UserAuthService()
