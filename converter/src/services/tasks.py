import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiofiles.os as aios
from redis import exceptions as redis_errors
from redis.asyncio.client import PubSub

from common.log_context import log_run
from core.logger import get_logger
from core.settings import settings
from db.redis_client import RedisClient, get_redis
from services.converter_files import convert_xlsx_to_xls


logger = get_logger(__name__)

CORR_KEY_PREFIX = "corr:"


async def delete_file_async(file_path: str) -> None:
    """Удаляет файл асинхронно, если он существует."""
    file_name = os.path.basename(file_path)
    try:
        if not await aios.path.exists(file_path):
            logger.debug("File already absent", extra={"file_name": file_name})
            return

        await aios.remove(file_path)
        logger.debug("File deleted", extra={"file_name": file_name})
    except asyncio.CancelledError:
        logger.info("File deletion cancelled", extra={"file_name": file_name})
        raise
    except Exception:
        logger.exception(
            "File deletion failed", extra={"file_name": file_name}
        )


async def _load_correlation_id(
    redis_client: RedisClient, file_id: str
) -> str | None:
    """Читает request_id, сохранённый при HTTP-загрузке файла."""
    raw = await redis_client.get(name=f"{CORR_KEY_PREFIX}{file_id}")
    if not raw:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def listen_to_redis_events() -> None:
    """Слушает события Redis и запускает конвертацию файлов."""
    pubsub: PubSub | None = None
    redis_client: RedisClient = await get_redis()
    if not redis_client.redis:
        logger.error(
            "Redis connection unavailable for event listener",
            extra={"component": "redis_listener"},
        )
        return

    try:
        pubsub = redis_client.redis.pubsub()
        if not pubsub:
            logger.error(
                "Redis pubsub unavailable for event listener",
                extra={"component": "redis_listener"},
            )
            return
        await pubsub.psubscribe("__keyevent@0__:set", "__keyevent@0__:expired")
        logger.info(
            "Redis event listener started",
            extra={"component": "redis_listener"},
        )

        async for message in pubsub.listen():
            try:
                if message["type"] == "pmessage":
                    channel = message["channel"].decode("utf-8")
                    key = message["data"].decode("utf-8")
                    if key.startswith(CORR_KEY_PREFIX):
                        continue

                    in_path = os.path.join(
                        settings.BASE_DIR, settings.UPLOAD_DIR, "in", key
                    )
                    out_path = os.path.join(
                        settings.BASE_DIR, settings.UPLOAD_DIR, "out", key
                    )

                    if channel == "__keyevent@0__:set":
                        value = await redis_client.get(name=key)
                        if (
                            value
                            and int(value.decode("utf-8")) == settings.LOAD
                        ):
                            correlation_id = await _load_correlation_id(
                                redis_client, key
                            )
                            with log_run("convert", request_id=correlation_id):
                                logger.info(
                                    "Conversion event received",
                                    extra={"file_id": key},
                                )
                                converted = await convert_xlsx_to_xls(key)
                                if not converted:
                                    logger.warning(
                                        "Conversion failed, "
                                        "status left as LOAD",
                                        extra={"file_id": key},
                                    )
                                    continue
                                await redis_client.set(
                                    name=key,
                                    value=settings.CONVERTED,
                                    ex=settings.TTL,
                                )
                                await delete_file_async(in_path)

                    elif channel == "__keyevent@0__:expired":
                        logger.debug(
                            "Converted file expired",
                            extra={"file_id": key},
                        )
                        await delete_file_async(out_path)
            except redis_errors.ConnectionError as error:
                logger.error(
                    "Redis connection lost while processing event",
                    extra={
                        "component": "redis_listener",
                        "error_type": type(error).__name__,
                    },
                )
                return
            except Exception:
                logger.exception(
                    "Redis event processing failed",
                    extra={"component": "redis_listener"},
                )

    except asyncio.CancelledError:
        logger.info(
            "Redis event listener cancelled",
            extra={"component": "redis_listener"},
        )
        raise

    except redis_errors.ConnectionError as error:
        logger.error(
            "Redis connection unavailable for event listener",
            extra={
                "component": "redis_listener",
                "error_type": type(error).__name__,
            },
        )

    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except redis_errors.ConnectionError as error:
                logger.warning(
                    "Redis connection unavailable during listener cleanup",
                    extra={
                        "component": "redis_listener",
                        "error_type": type(error).__name__,
                    },
                )
            except Exception:
                logger.exception(
                    "Redis listener cleanup failed",
                    extra={"component": "redis_listener"},
                )


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
    started_at = time.perf_counter()
    deleted_count = 0
    folder_name = os.path.basename(folder_path)
    try:
        if not await aios.path.exists(folder_path):
            logger.info(
                "File cleanup directory absent",
                extra={
                    "folder": folder_name,
                    "deleted_count": deleted_count,
                    "duration_seconds": time.perf_counter() - started_at,
                },
            )
            return

        files = await aios.listdir(folder_path)

        for file_name in files:
            file_path = os.path.join(folder_path, file_name)

            if await aios.path.isfile(file_path):
                if not await condition(file_name):
                    await aios.remove(file_path)
                    deleted_count += 1
        logger.info(
            "File cleanup directory completed",
            extra={
                "folder": folder_name,
                "deleted_count": deleted_count,
                "duration_seconds": time.perf_counter() - started_at,
            },
        )
    except asyncio.CancelledError:
        logger.info(
            "File cleanup directory cancelled",
            extra={
                "folder": folder_name,
                "deleted_count": deleted_count,
                "duration_seconds": time.perf_counter() - started_at,
            },
        )
        raise
    except redis_errors.ConnectionError as error:
        logger.error(
            "Redis connection unavailable during file cleanup",
            extra={
                "folder": folder_name,
                "deleted_count": deleted_count,
                "duration_seconds": time.perf_counter() - started_at,
                "error_type": type(error).__name__,
            },
        )
    except Exception:
        logger.exception(
            "File cleanup directory failed",
            extra={
                "folder": folder_name,
                "deleted_count": deleted_count,
                "duration_seconds": time.perf_counter() - started_at,
            },
        )


async def clear_files() -> None:
    """Удаляет файлы, для которых больше нет ключей Redis."""
    with log_run("clear_files"):
        started_at = time.perf_counter()
        logger.info("Scheduled file cleanup started")
        redis: RedisClient = await get_redis()
        in_dir = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "in")
        out_dir = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "out")

        try:
            await delete_files_by_condition(in_dir, lambda f: redis.exists(f))
            await delete_files_by_condition(out_dir, lambda f: redis.exists(f))
        except asyncio.CancelledError:
            logger.info(
                "Scheduled file cleanup cancelled",
                extra={"duration_seconds": time.perf_counter() - started_at},
            )
            raise
        else:
            logger.info(
                "Scheduled file cleanup completed",
                extra={"duration_seconds": time.perf_counter() - started_at},
            )
