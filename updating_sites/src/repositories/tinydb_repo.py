"""
Репозиторий для работы с TinyDB.
Изолирует логику хранения от слоя API.
"""

from __future__ import annotations

import asyncio
from typing import Any

from passlib.context import CryptContext  # type: ignore[import-untyped]
from tinydb import Query, TinyDB  # type: ignore[import-not-found]

from common.logger import logger
from core.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
            # Инициализация в отдельном потоке, чтобы не блокировать event loop
            self._db = await asyncio.to_thread(TinyDB, self.db_path)
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
        return await asyncio.to_thread(db.insert, {"key": key, "value": value})

    async def update(self, doc_id: int, key: str, value: str) -> bool:
        """Обновляет существующую запись по ID."""
        db = await self._get_db()
        result = await asyncio.to_thread(
            db.update, {"key": key, "value": value}, doc_ids=[doc_id]
        )
        return bool(result)

    async def remove(self, doc_id: int) -> bool:
        """Удаляет запись по ID."""
        db = await self._get_db()
        result = await asyncio.to_thread(db.remove, doc_ids=[doc_id])
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
            return False  # пользователь уже существует
        hashed = pwd_context.hash(password)
        await asyncio.to_thread(
            db.insert, {"key": username, "value": role, "password": hashed}
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


def get_tinydb_repo() -> TinyDBRepository:
    """Dependency для получения экземпляра репозитория."""
    return TinyDBRepository(db_path=f"data/storage/{settings.tiny_db_path}")
