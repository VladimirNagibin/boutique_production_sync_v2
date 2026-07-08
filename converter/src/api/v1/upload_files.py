from http import HTTPStatus
import os
from typing import Any
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import UUID4
from redis import exceptions as redis_errors

from core.logger import logger
from core.settings import settings
from db.redis_client import RedisClient, get_redis

upload_file_router = APIRouter()


@upload_file_router.post(
    "/send_convert",
    summary="send file",
    description="Upload file for convert.",
)
async def upload_file(
    file: UploadFile = File(...), redis: RedisClient = Depends(get_redis)
) -> dict[str, Any]:
    """
    Асинхронно загружает файл на сервер.
    """
    logger.debug("Start to load file")
    try:
        file_name = str(uuid.uuid4())
        tmp_file_path = os.path.join(
            settings.BASE_DIR, settings.UPLOAD_DIR, "in", file_name
        )
        with open(tmp_file_path, "wb") as buffer:
            while chunk := await file.read(settings.CHUNK):
                buffer.write(chunk)
        await redis.set(name=file_name, value=settings.LOAD, ex=settings.TTL)
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"File storage error: {e}")
        raise HTTPException(
            HTTPStatus.INTERNAL_SERVER_ERROR, f"File storage error: {e}"
        )
    except redis_errors.ConnectionError as e:
        logger.error(f"Redis unavailable: {e}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, "Redis unavailable: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal error: {e}")
    return {
        "filename": file.filename,
        "token": file_name,
        "message": "Файл успешно загружен",
    }


@upload_file_router.get(
    "/get_convert",
    summary="get file",
    description="Get converted file.",
)
async def get_file(
    id: UUID4, response: Response, redis: RedisClient = Depends(get_redis)
) -> FileResponse:
    """
    Асинхронно получает файл с сервера.
    """
    file_path = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "out", str(id))
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="File not found",
        )
    return FileResponse(file_path, filename="tmp.xls")
