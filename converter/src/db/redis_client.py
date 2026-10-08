from typing import Any

from redis.asyncio import Redis as AsyncioRedis

from common.exceptions.redis import RedisManagerNotInitializedError
from core.logger import get_logger


logger = get_logger(__name__)

redis: AsyncioRedis | None = None
_connection_unavailable_logged = False


class RedisClient:
    """Предоставляет минимальную асинхронную обёртку над Redis."""

    def __init__(self, db: AsyncioRedis | None):
        self.redis = db

    async def get(self, name: Any) -> Any:
        connection = self._get_connection("get")
        return await connection.get(name)

    async def set(self, name: Any, value: Any, ex: int | None = None) -> None:
        connection = self._get_connection("set")
        await connection.set(name, value, ex=ex)

    async def delete(self, name: Any) -> None:
        connection = self._get_connection("delete")
        await connection.delete(name)

    async def exists(self, name: Any) -> bool:
        connection = self._get_connection("exists")
        return bool(await connection.exists(name))

    async def sadd(self, name: Any, values: Any) -> int:
        connection = self._get_connection("sadd")
        return int(await connection.sadd(name, values))

    def _get_connection(self, operation: str) -> AsyncioRedis:
        """Возвращает соединение либо бросает исключение неинициализации."""
        global _connection_unavailable_logged

        if self.redis is None:
            if not _connection_unavailable_logged:
                logger.warning(
                    "Redis connection unavailable",
                    extra={"operation": operation},
                )
                _connection_unavailable_logged = True
            raise RedisManagerNotInitializedError(
                details={"operation": operation},
            )

        _connection_unavailable_logged = False
        return self.redis


async def get_redis() -> RedisClient:
    """Возвращает обёртку над текущим соединением Redis."""
    return RedisClient(redis)
