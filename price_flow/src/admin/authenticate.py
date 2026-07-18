from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from jose import jwt
from jose.exceptions import JWTError

# from pydantic import SecretStr
from sqladmin.authentication import AuthenticationBackend

from common.exceptions.auth import TokenCreationError
from common.logger import logger
from core.settings import settings


class BasicAuthBackend(AuthenticationBackend):  # type: ignore
    """
    Аутентификационный бекенд для SQLAdmin с использованием JWT.

    Управляет входом, выходом и проверкой JWT-токенов, хранящихся в сессии.
    """

    def __init__(
        self,
        username: str = settings.auth.admin_username,
        password: str = settings.auth.admin_password.get_secret_value(),
        secret_key: str = settings.auth.secret_key.get_secret_value(),
        algorithm: str = settings.auth.algorithm,
        token_expiry_minutes: int = settings.auth.access_token_expire_minutes,
    ) -> None:
        """
        Инициализирует бекенд с учётными данными и параметрами JWT.

        Args:
            username: Имя пользователя для аутентификации.
            password: Пароль (извлекается из SecretStr).
            secret_key: Секретный ключ для подписи JWT.
            algorithm: Алгоритм подписи (по умолчанию HS256).
            token_expiry_minutes: Время жизни токена в минутах.
        """
        super().__init__(secret_key)
        self.username = username
        self.password = password
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.token_expiry_minutes = token_expiry_minutes
        logger.info(
            "Admin authentication backend initialized",
            extra={"username": username, "algorithm": algorithm},
        )

    async def login(self, request: Request) -> bool:
        """
        Обрабатывает вход: проверяет учётные данные и создаёт JWT-токен.

        Args:
            request: Объект запроса FastAPI.

        Returns:
            True если вход успешен, иначе False.
        """
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")

            username_validate = self._to_str(username)
            password_validate = self._to_str(password)

            if not self._validate_credentials(
                username_validate, password_validate
            ):
                logger.warning(
                    "Failed login attempt",
                    extra={"username": username_validate or "unknown"},
                )
                return False

            logger.info(
                "Successful login",
                extra={"username": username_validate},
            )
            if not username_validate:
                return False
            token = self._create_jwt_token(username_validate)
            request.session.update({"token": token})
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Login error",
                extra={"error": str(e)},
                exc_info=True,
            )
            return False
        else:
            return True

    async def logout(self, request: Request) -> bool:
        """
        Очищает сессию при выходе.

        Args:
            request: Объект запроса FastAPI.

        Returns:
            Всегда True при успешной очистке.
        """
        try:
            request.session.clear()
            logger.info("User logged out successfully")
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Logout error",
                extra={"error": str(e)},
                exc_info=True,
            )
            return False
        else:
            return True

    async def authenticate(self, request: Request) -> bool:
        """
        Проверяет валидность JWT-токена в сессии.

        Args:
            request: Объект запроса FastAPI.

        Returns:
            True если токен валиден, иначе False.
        """
        token = request.session.get("token")
        if not token:
            logger.debug("No token found in session")
            return False
        try:
            username = self._validate_jwt_token(token)
            if not username:
                logger.debug("Token validation failed")
                return False

            logger.debug(
                "Authentication successful",
                extra={"username": username},
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Authentication error",
                extra={"error": str(e)},
                exc_info=True,
            )
            return False
        else:
            return True

    def get_current_user(self, request: Request) -> str | None:
        """
        Возвращает имя текущего аутентифицированного пользователя.

        Args:
            request: Объект запроса FastAPI.

        Returns:
            Имя пользователя или None, если токен невалиден.
        """
        token = request.session.get("token")
        if not token:
            return None
        try:
            return self._validate_jwt_token(token)
        except Exception:  # noqa: BLE001
            return None

    # ----- Приватные методы -----

    @staticmethod
    def _to_str(value: Any) -> str | None:
        """
        Безопасно преобразует значение формы в строку.

        Args:
            value: Значение из form (может быть str, UploadFile, None).

        Returns:
            Строка или None.
        """
        if value is None:
            return None

        if hasattr(value, "read"):  # UploadFile-like object
            return None

        return str(value)

    def _validate_credentials(
        self, username: str | None, password: str | None
    ) -> bool:
        """
        Проверяет соответствие введённых учётных данных сохранённым.

        Args:
            username: Введённое имя.
            password: Введённый пароль.

        Returns:
            True если совпадают.
        """
        if not username or not password:
            return False
        return username == self.username and password == self.password

    def _create_jwt_token(self, username: str) -> str:
        """
        Создаёт JWT-токен с временем жизни.

        Args:
            username: Имя пользователя.

        Returns:
            Подписанный JWT-токен.

        Raises:
            TokenCreationError: Если не удалось создать токен.
        """
        try:
            now = datetime.now(UTC)
            expire = now + timedelta(minutes=self.token_expiry_minutes)

            payload: dict[str, Any] = {
                "sub": username,
                "exp": expire,
                "iat": now,
            }

            return jwt.encode(  # type: ignore[no-any-return]
                payload,
                self.secret_key,
                algorithm=self.algorithm,
            )

        except Exception as e:
            logger.error(
                "Token creation failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise TokenCreationError(
                error_code="TOKEN_CREATION_ERROR",
                message="Could not create authentication token",
                details={"algorithm": self._algorithm},
            ) from e

    def _validate_jwt_token(self, token: str) -> str | None:
        """
        Проверяет подпись и срок действия JWT-токена.

        Args:
            token: JWT-токен из сессии.

        Returns:
            Имя пользователя (sub) если токен валиден, иначе None.

        """
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm]
            )

            username = payload.get("sub")
            if not username:
                logger.warning(
                    "Token missing 'sub' claim",
                    extra={"token_preview": token[:10] + "..."},
                )
                return None

            # Проверка срока действия уже выполняется в jwt.decode,
            # но дополнительная проверка не помешает.
            exp = payload.get("exp")
            if exp:
                exp_dt = datetime.fromtimestamp(exp, UTC)
                if datetime.now(UTC) > exp_dt:
                    logger.warning("Token expired")
                    return None
            # Возвращаем username только если он совпадает с ожидаемым
            if username != self.username:
                logger.warning(
                    "Token username mismatch",
                    extra={"expected": self.username, "actual": username},
                )
                return None

        except JWTError as e:
            logger.warning(
                "JWT validation error",
                extra={"error": str(e)},
            )
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Unexpected token validation error",
                extra={"error": str(e)},
                exc_info=True,
            )
            return None
        else:
            return str(username)
