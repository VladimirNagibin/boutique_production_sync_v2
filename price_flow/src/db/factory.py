"""Async database factory and connection managers."""

import asyncio

from typing import Any, ClassVar

from core.logger import get_logger
from core.settings import settings
from interfaces.db.base import IDatabaseManager

from .sqlite_manager import SQLiteManager


logger = get_logger(__name__)


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
        key = connection_string or str(settings.sqlite.sqlite_file)

        if key not in AsyncDatabaseFactory._instances:
            async with AsyncDatabaseFactory._lock:
                if key not in AsyncDatabaseFactory._instances:
                    manager: IDatabaseManager = SQLiteManager(key, **kwargs)

                    logger.info(
                        "Initializing database manager instance",
                        extra={
                            "manager_type": type(manager).__name__,
                            "cached_manager_count": len(
                                AsyncDatabaseFactory._instances
                            ),
                        },
                    )
                    try:
                        await manager.initialize()
                    except Exception as e:
                        logger.error(
                            "Database manager initialization failed",
                            extra={
                                "manager_type": type(manager).__name__,
                                "error_type": type(e).__name__,
                            },
                            exc_info=True,
                        )
                        raise
                    AsyncDatabaseFactory._instances[key] = manager

        return AsyncDatabaseFactory._instances[key]

    @staticmethod
    async def close_all() -> None:
        """Close all database connections."""
        managers = list(AsyncDatabaseFactory._instances.values())
        close_errors = 0
        for manager in managers:
            try:
                await manager.close()
            except Exception as e:
                close_errors += 1
                logger.error(
                    "Database manager close failed",
                    extra={
                        "manager_type": type(manager).__name__,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
        AsyncDatabaseFactory._instances.clear()
        logger.info(
            "Database managers closed",
            extra={
                "manager_count": len(managers),
                "error_count": close_errors,
            },
        )
