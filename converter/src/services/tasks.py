import asyncio
import os
from typing import Any, Awaitable, Callable

import aiofiles.os as aios

# import redis.asyncio as asyncio_redis
from redis.asyncio.client import PubSub
# from redis.asyncio.client import Redis as ClientRedis

from core.logger import logger
from core.settings import settings
from db.redis_client import RedisClient, get_redis
from services.converter_files import convert_xlsx_to_xls


async def delete_file_async(file_path: str) -> None:
    try:
        # Проверяем, существует ли файл
        if not await aios.path.exists(file_path):
            logger.warning(f"Файл {file_path} не найден")
            return

        # Асинхронное удаление файла
        await aios.remove(file_path)
        logger.debug(f"Файл {file_path} успешно удален")
    except Exception as e:
        logger.error(f"Ошибка при удалении файла {file_path}: {e}")


async def listen_to_redis_events() -> None:
    pubsub: PubSub | None = None
    redis_client: RedisClient = await get_redis()
    if not redis_client.redis:
        logger.error("Redis не инициализирован для listen_to_redis_events")
        return
    # client: ClientRedis = asyncio_redis.from_url(
    #     f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}"
    # )
    try:
        pubsub = redis_client.redis.pubsub()
        if not pubsub:
            logger.error("pubsub не определён для listen_to_redis_events")
            return
        await pubsub.psubscribe("__keyevent@0__:set", "__keyevent@0__:expired")
        logger.info("Слушатель событий Redis запущен...")

        async for message in pubsub.listen():
            try:
                if message["type"] == "pmessage":
                    channel = message["channel"].decode("utf-8")
                    key = message["data"].decode("utf-8")

                    # ИСПРАВЛЕНИЕ: Убрали сложное форматирование через %s
                    in_path = os.path.join(
                        settings.BASE_DIR, settings.UPLOAD_DIR, "in", key
                    )
                    out_path = os.path.join(
                        settings.BASE_DIR, settings.UPLOAD_DIR, "out", key
                    )

                    if channel == "__keyevent@0__:set":
                        value = await redis_client.get(name=key)
                        if value and int(value.decode("utf-8")) == settings.LOAD:
                            logger.info(f"Обнаружен файл на конвертацию: {key}")
                            await convert_xlsx_to_xls(key)
                            await redis_client.set(
                                name=key,
                                value=settings.CONVERTED,
                                ex=settings.TTL,
                            )
                            await delete_file_async(in_path)

                    elif channel == "__keyevent@0__:expired":
                        logger.debug(
                            f"Истек срок жизни ключа (файл готов к выдаче/удалению): {key}"
                        )
                        await delete_file_async(out_path)
            except Exception as e:
                logger.error(
                    f"Ошибка в цикле обработки событий Redis: {e}", exc_info=True
                )

    except asyncio.CancelledError:
        # Задача была отменена – корректно закрываем подписку
        # if pubsub:
        #     await pubsub.unsubscribe()
        #     await pubsub.close()
        # Пробрасываем исключение, чтобы признать отмену
        raise

    except ConnectionError:
        # Соединение с Redis закрыто – завершаем задачу без ошибки
        # (например, если Redis перезапускается или приложение останавливается)
        pass

    finally:
        # Дополнительная очистка, если pubsub ещё открыт
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass


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
        if not await aios.path.exists(folder_path):
            return

        # Получаем список файлов в папке
        files = await aios.listdir(folder_path)

        # Асинхронно обрабатываем каждый файл
        for file_name in files:
            file_path = os.path.join(folder_path, file_name)

            # Проверяем, является ли объект файлом
            if await aios.path.isfile(file_path):
                # Проверяем условие
                if not await condition(file_name):
                    logger.debug(f"Удаление файла: {file_path}")
                    await aios.remove(file_path)
    except Exception as e:
        logger.error(f"Ошибка при очистке файлов в {folder_path}: {e}")


async def clear_files() -> None:
    logger.info("start clear files")
    redis: RedisClient = await get_redis()
    in_dir = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "in")
    out_dir = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "out")

    await delete_files_by_condition(in_dir, lambda f: redis.exists(f))
    await delete_files_by_condition(out_dir, lambda f: redis.exists(f))

    logger.info("finish clear files")
