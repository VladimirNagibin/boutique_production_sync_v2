"""Async database factory and connection managers."""

import asyncio

from typing import Any, ClassVar

from core.logger import logger
from core.settings import settings
from interfaces.db.base import IDatabaseManager

from .sqlite_manager import SQLiteManager


class AsyncDatabaseFactory:
    """Factory for creating async database managers."""

    _instances: ClassVar[dict[str, IDatabaseManager]] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @staticmethod
    async def get_manager(
        connection_string: str | None = None,
        **kwargs: Any,
    ) -> IDatabaseManager:
        """Get async database manager instance."""
        key = connection_string or str(settings.DB_SQLITE_PATH)

        if key not in AsyncDatabaseFactory._instances:
            async with AsyncDatabaseFactory._lock:
                if key not in AsyncDatabaseFactory._instances:
                    manager: IDatabaseManager = SQLiteManager(key, **kwargs)

                    await manager.initialize()
                    AsyncDatabaseFactory._instances[key] = manager

        return AsyncDatabaseFactory._instances[key]

    @staticmethod
    async def close_all() -> None:
        """Close all database connections."""
        managers = list(AsyncDatabaseFactory._instances.values())
        for manager in managers:
            try:
                await manager.close()
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error closing database manager: {e}")
        AsyncDatabaseFactory._instances.clear()
