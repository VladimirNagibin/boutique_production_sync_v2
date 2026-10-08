import os
import uuid
from http import HTTPStatus
from typing import Annotated, Any

import aiofiles
import aiofiles.os as aios
from fastapi import (
    APIRouter,
    Depends,
    File,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import UUID4
from redis import exceptions as redis_errors

from common.exceptions.file import (
    FileAppNotFoundError,
    FileTooLargeError,
    FileUploadError,
)
from common.exceptions.redis import (
    RedisManagerConnectionError,
    RedisManagerTimeoutError,
)
from common.log_context import get_request_id
from core.logger import get_logger
from core.settings import settings
from db.redis_client import RedisClient, get_redis
from services.tasks import CORR_KEY_PREFIX


logger = get_logger(__name__)

upload_file_router = APIRouter()


@upload_file_router.post(
    "/send_convert",
    summary="send file",
    description="Upload file for convert.",
)
async def upload_file(
    file: Annotated[UploadFile, File(...)],
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> dict[str, Any]:
    """
    Асинхронно загружает файл на сервер.
    """
    file_name = str(uuid.uuid4())
    byte_count = 0
    original_file_name = file.filename or "<unnamed>"
    logger.info(
        "File upload started",
        extra={
            "file_id": file_name,
            "original_file_name": original_file_name,
        },
    )
    tmp_file_path = os.path.join(
        settings.BASE_DIR, settings.UPLOAD_DIR, "in", file_name
    )
    try:
        async with aiofiles.open(tmp_file_path, "wb") as buffer:
            while chunk := await file.read(settings.CHUNK):
                await buffer.write(chunk)
                byte_count += len(chunk)
                if byte_count > settings.MAX_UPLOAD_BYTES:
                    raise FileTooLargeError(
                        path=tmp_file_path,
                        file_size=byte_count,
                        max_file_size=settings.MAX_UPLOAD_BYTES,
                        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
        await redis.set(name=file_name, value=settings.LOAD, ex=settings.TTL)
        correlation_id = get_request_id()
        if correlation_id:
            await redis.set(
                name=f"{CORR_KEY_PREFIX}{file_name}",
                value=correlation_id,
                ex=settings.TTL,
            )
    except FileTooLargeError:
        logger.warning(
            "File upload rejected: size limit exceeded",
            extra={
                "file_id": file_name,
                "original_file_name": original_file_name,
                "byte_count": byte_count,
            },
        )
        await _cleanup_partial_upload(tmp_file_path, file_name)
        raise
    except (FileNotFoundError, PermissionError) as error:
        logger.exception(
            "File upload storage failed",
            extra={
                "file_id": file_name,
                "original_file_name": original_file_name,
                "byte_count": byte_count,
            },
        )
        await _cleanup_partial_upload(tmp_file_path, file_name)
        raise FileUploadError(
            path=tmp_file_path,
            message="File storage error",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
    except redis_errors.ConnectionError as error:
        logger.error(
            "File upload Redis update failed",
            extra={
                "file_id": file_name,
                "original_file_name": original_file_name,
                "byte_count": byte_count,
                "error_type": type(error).__name__,
            },
        )
        await _cleanup_partial_upload(tmp_file_path, file_name)
        raise RedisManagerConnectionError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
    except redis_errors.TimeoutError as error:
        logger.error(
            "File upload Redis update timed out",
            extra={
                "file_id": file_name,
                "original_file_name": original_file_name,
                "byte_count": byte_count,
                "error_type": type(error).__name__,
            },
        )
        await _cleanup_partial_upload(tmp_file_path, file_name)
        raise RedisManagerTimeoutError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
    except Exception:
        logger.exception(
            "Unexpected file upload failure",
            extra={
                "file_id": file_name,
                "original_file_name": original_file_name,
                "byte_count": byte_count,
            },
        )
        await _cleanup_partial_upload(tmp_file_path, file_name)
        raise

    logger.info(
        "File upload completed",
        extra={
            "file_id": file_name,
            "original_file_name": original_file_name,
            "byte_count": byte_count,
        },
    )
    return {
        "filename": original_file_name,
        "token": file_name,
        "message": "Файл успешно загружен",
    }


@upload_file_router.get(
    "/get_convert",
    summary="get file",
    description="Get converted file.",
)
async def get_file(
    id: UUID4,
    response: Response,
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> FileResponse:
    """
    Асинхронно получает файл с сервера.  # noqa: RUF000
    """
    token = str(id)
    download_filename = "tmp.xls"
    file_path = os.path.join(
        settings.BASE_DIR, settings.UPLOAD_DIR, "out", token
    )
    logger.info(
        "File download started",
        extra={
            "file_id": token,
            "original_file_name": download_filename,
            "byte_count": 0,
        },
    )
    if not await aios.path.exists(file_path):
        logger.warning(
            "File download not found",
            extra={
                "file_id": token,
                "original_file_name": download_filename,
                "byte_count": 0,
            },
        )
        raise FileAppNotFoundError(
            path=file_path,
            status_code=HTTPStatus.BAD_REQUEST,
        )
    stat_result = await aios.stat(file_path)
    logger.info(
        "File download prepared",
        extra={
            "file_id": token,
            "original_file_name": download_filename,
            "byte_count": stat_result.st_size,
        },
    )
    return FileResponse(
        file_path,
        filename=download_filename,
        stat_result=stat_result,
    )


async def _cleanup_partial_upload(tmp_file_path: str, file_id: str) -> None:
    """Удаляет частично записанный файл после ошибки загрузки."""
    try:
        await aios.remove(tmp_file_path)
    except FileNotFoundError:
        return
    except OSError:
        logger.exception(
            "Partial upload cleanup failed",
            extra={"file_id": file_id, "path": tmp_file_path},
        )
