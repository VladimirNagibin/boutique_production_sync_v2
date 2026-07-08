import os
from typing import Any, Awaitable, Callable

import aiofiles.os as aios
import redis.asyncio as asyncio_redis
from redis.asyncio.client import PubSub
from redis.asyncio.client import Redis as ClientRedis

from core.logger import logger
from core.settings import settings
from db.redis_client import RedisClient, get_redis
from services.converter_files import convert_xlsx_to_xls


async def delete_file_async(file_path: str) -> None:
    try:
        # Проверяем, существует ли файл
        if not await aios.path.exists(file_path):
            print(f"Файл {file_path} не найден")
            return

        # Асинхронное удаление файла
        await aios.remove(file_path)
        print(f"Файл {file_path} успешно удален")
    except Exception as e:
        print(f"Ошибка при удалении файла {file_path}: {e}")


async def listen_to_redis_events() -> None:
    redis: RedisClient = await get_redis()
    client: ClientRedis = asyncio_redis.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
    )
    pubsub: PubSub = client.pubsub()

    await pubsub.psubscribe("__keyevent@0__:set", "__keyevent@0__:expired")

    while True:
        message = await pubsub.get_message()
        if message and message["type"] == "pmessage":
            channel = message["channel"].decode("utf-8")
            key = message["data"].decode("utf-8")
            file_path = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "%s", key)
            try:
                value = await redis.get(name=key)
                value = int(value.decode("utf-8"))
            except Exception:
                value = None
            if channel == "__keyevent@0__:set" and value == settings.LOAD:
                await convert_xlsx_to_xls(key)
                await redis.set(name=key, value=settings.CONVERTED, ex=settings.TTL)
                await delete_file_async(file_path % ("in"))
            elif channel == "__keyevent@0__:expired":
                await delete_file_async(file_path % ("out"))


async def delete_files_by_condition(
    folder_path: str,
    condition: Callable[[Any], Awaitable[Any]],
) -> None:
    """
    Асинхронно проходит по файлам в папке и удаляет их,
    если они удовлетворяют условию.

    :param folder_path: Путь к папке.
    :param condition: Функция-условие,
    которая принимает имя файла и возвращает bool.
    """
    try:
        # Получаем список файлов в папке
        files = await aios.listdir(folder_path)

        # Асинхронно обрабатываем каждый файл
        for file_name in files:
            file_path = os.path.join(folder_path, file_name)

            # Проверяем, является ли объект файлом
            if await aios.path.isfile(file_path):
                # Проверяем условие
                if condition(file_name):
                    print(f"Удаление файла: {file_path}")
                    await aios.remove(file_path)
    except Exception as e:
        print(f"Ошибка при обработке файлов: {e}")


async def clear_files() -> None:
    logger.info("start clear files")
    redis: RedisClient = await get_redis()
    file_path = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "%s")

    await delete_files_by_condition(file_path % ("in"), redis.exists)
    await delete_files_by_condition(file_path % ("out"), redis.exists)

    logger.info("finish clear files")
