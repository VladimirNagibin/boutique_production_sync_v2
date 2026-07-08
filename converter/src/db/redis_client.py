from typing import Any

from redis.asyncio import Redis as AsyncioRedis

redis: AsyncioRedis | None = None


class RedisClient:
    def __init__(self, db: AsyncioRedis | None):
        self.redis = db

    async def get(self, name: Any) -> Any:
        if self.redis:
            return await self.redis.get(name)

    async def set(self, name: Any, value: Any, ex: int | None = None) -> None:
        if self.redis:
            await self.redis.set(name, value, ex=ex)

    async def delete(self, name: Any) -> None:
        if self.redis:
            await self.redis.delete(name)

    async def exists(self, name: Any) -> bool | None:
        if self.redis:
            return bool(await self.redis.exists(name))
        return None

    async def sadd(self, name: Any, values: Any) -> int | None:
        if self.redis is not None:
            result = await self.redis.sadd(name, values)
            return int(result)
        return None


async def get_redis() -> RedisClient:
    return RedisClient(redis)
