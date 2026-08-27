"""
Репозиторий для работы с TinyDB.
Изолирует логику хранения от слоя API.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from passlib.context import CryptContext
from tinydb import Query, TinyDB

from core.logger import get_logger
from core.settings import settings


logger = get_logger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _tiny_db_file_path() -> str:
    """Абсолютный путь к файлу TinyDB под base_dir/data/storage."""
    return str(
        Path(settings.base_dir) / "data" / "storage" / settings.tiny_db_path
    )


class TinyDBRepository:
    """
    Репозиторий для управления состоянием через TinyDB.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # TinyDB синхронный, инициализируем лениво или в фоне
        self._db: TinyDB | None = None

    async def _get_db(self) -> TinyDB:
        """Получает или инициализирует экземпляр TinyDB."""
        if self._db is None:
            try:
                # Инициализация в отдельном потоке, чтобы не блокировать
                # event loop
                self._db = await asyncio.to_thread(
                    TinyDB, self.db_path, create_dirs=True
                )
            except Exception as error:
                logger.error(
                    "TinyDB initialization failed",
                    extra={"db_path": self.db_path, "error": str(error)},
                    exc_info=True,
                )
                raise
        return self._db

    # ----- Публичные методы -----

    async def get_all(self) -> list[dict[str, Any]]:
        """Возвращает все записи из базы данных."""
        db = await self._get_db()
        return await asyncio.to_thread(db.all)

    async def insert(self, key: str, value: str) -> int:
        """
        Вставляет новую запись.

        Returns:
            int: ID новой записи (doc_id)
        """
        db = await self._get_db()
        doc_id = await asyncio.to_thread(
            db.insert, {"key": key, "value": value}
        )
        logger.info(
            "TinyDB record inserted",
            extra={"key": key, "doc_id": doc_id},
        )
        return int(doc_id)

    async def update(self, doc_id: int, key: str, value: str) -> bool:
        """Обновляет существующую запись по ID."""
        db = await self._get_db()
        result = await asyncio.to_thread(
            db.update, {"key": key, "value": value}, doc_ids=[doc_id]
        )
        logger.info(
            "TinyDB record update completed",
            extra={"key": key, "doc_id": doc_id, "updated": bool(result)},
        )
        return bool(result)

    async def remove(self, doc_id: int) -> bool:
        """Удаляет запись по ID."""
        db = await self._get_db()
        result = await asyncio.to_thread(db.remove, doc_ids=[doc_id])
        logger.info(
            "TinyDB record removal completed",
            extra={"doc_id": doc_id, "removed": bool(result)},
        )
        return bool(result)

    async def truncate(self) -> None:
        """Полностью очищает базу данных."""
        db = await self._get_db()
        await asyncio.to_thread(db.truncate)
        logger.info("TinyDB truncated successfully")

    async def get_by_id(self, doc_id: int) -> dict[str, Any] | None:
        """Возвращает запись по ID или None, если не найдена."""
        db = await self._get_db()
        return await asyncio.to_thread(db.get, doc_id=doc_id)

    async def create_user(
        self, username: str, password: str, role: str = "user"
    ) -> bool:
        """Создаёт нового пользователя с хэшированным паролем."""
        db = await self._get_db()
        User = Query()
        if db.search(User.key == username):
            logger.warning(
                "User creation skipped: user already exists",
                extra={"username": username, "role": role},
            )
            return False  # пользователь уже существует
        hashed = pwd_context.hash(password)
        await asyncio.to_thread(
            db.insert, {"key": username, "value": role, "password": hashed}
        )
        logger.info(
            "User created",
            extra={"username": username, "role": role},
        )
        return True

    async def verify_user(self, username: str, password: str) -> bool:
        """Проверяет пароль пользователя."""
        db = await self._get_db()
        User = Query()
        user = db.search(User.key == username)
        if not user:
            return False
        return bool(pwd_context.verify(password, user[0]["password"]))

    async def get_role_user(self, username: str, password: str) -> str | None:
        """Возвращает роль пользователя."""
        db = await self._get_db()
        User = Query()
        user = db.search(User.key == username)
        if not user:
            return None
        if pwd_context.verify(password, user[0]["password"]):
            return str(user[0]["value"])
        return None

    async def ensure_admin_exists(self) -> None:
        """
        Проверяет, существует ли пользователь с ролью admin,
        и создаёт его при необходимости.
        """
        admin_email = settings.ADMIN_EMAIL
        admin_password = settings.ADMIN_PASSWORD

        if not admin_email or not admin_password:
            logger.warning(
                "Admin bootstrap skipped: credentials are not configured"
            )
            return

        try:
            # Проверяем, существует ли пользователь с таким email
            db = await self._get_db()
            User = Query()
            existing = db.search(User.key == admin_email)
            if existing:
                # Если уже есть – ничего не делаем, можно проверить роль
                # (но обычно не нужно)
                logger.info(
                    "Admin user already exists",
                    extra={"username": admin_email},
                )
                return

            # Создаём пользователя с ролью admin
            success = await self.create_user(
                username=admin_email, password=admin_password, role="admin"
            )
            if success:
                logger.info(
                    "Admin user created",
                    extra={"username": admin_email},
                )
            else:
                logger.error(
                    "Admin user creation failed",
                    extra={"username": admin_email},
                )
        except Exception as error:
            logger.error(
                "Admin bootstrap failed",
                extra={"username": admin_email, "error": str(error)},
                exc_info=True,
            )


def get_tinydb_repo() -> TinyDBRepository:
    """Dependency для получения экземпляра репозитория."""
    return TinyDBRepository(db_path=_tiny_db_file_path())
