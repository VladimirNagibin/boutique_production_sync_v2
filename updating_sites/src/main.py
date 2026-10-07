from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from api.v1.auth import auth_router
from api.v1.dropbox import dropbox_router
from api.v1.storage import storage
from api.v1.tiny_admin import router as admin_router
from api.v1.update_portal import upd_portal
from api.v1.upload_file import upload_file_router
from common.exceptions.base import BaseAppException
from common.exceptions.enums import ErrorCode
from common.request_context_middleware import RequestContextMiddleware
from core.logger import get_logger
from core.settings import settings
from middleware.auth_middleware import AuthMiddleware
from repositories.tinydb_repo import TinyDBRepository, get_tinydb_repo
from schemas.v1.response_schemas import ErrorResponse


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    repo: TinyDBRepository = get_tinydb_repo()
    logger.info(
        "Application startup initializing",
        extra={
            "project_name": settings.PROJECT_NAME,
            "log_level": settings.APP_LOG_LEVEL,
        },
    )
    try:
        await repo.ensure_admin_exists()
    except Exception as error:
        logger.critical(
            "Application startup failed",
            extra={"error": str(error)},
            exc_info=True,
        )
        raise

    logger.info("Application startup completed")
    try:
        yield
    finally:
        logger.info("Application shutdown completed")


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/api/openapi",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(storage, prefix="/api/v1/storage", tags=["storage"])
app.include_router(upload_file_router, prefix="/api/v1/files", tags=["files"])
app.include_router(upd_portal, prefix="/api/v1/update", tags=["update"])
app.include_router(dropbox_router, prefix="/api/v1/dropbox", tags=["dropbox"])
app.include_router(admin_router, prefix="/api/v1/tiny", tags=["storage"])

app.add_middleware(AuthMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(BaseAppException)
async def handle_base_app_exception(
    request: Request, exc: BaseAppException
) -> JSONResponse:
    """
    Обрабатывает все бизнес-исключения приложения.

    Args:
        request: Входящий HTTP-запрос.
        exc: Исключение приложения.

    Returns:
        JSON-ответ со стандартизированной ошибкой.
    """
    request_id = getattr(request.state, "request_id", None)
    status_code = exc.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR
    log_method = (
        logger.warning
        if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
        else logger.error
    )
    log_method(
        "Application exception handled",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "error_code": exc.error_code,
            "error_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ).model_dump(mode="json"),
        headers={"X-Request-ID": request_id or ""},
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Обрабатывает непредвиденные исключения.

    Args:
        request: Входящий HTTP-запрос.
        exc: Непредвиденное исключение.

    Returns:
        JSON-ответ с внутренней ошибкой.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unexpected request exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="Internal server error",
            details={"error_type": type(exc).__name__},
        ).model_dump(mode="json"),
        headers={"X-Request-ID": request_id or ""},
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        log_config=None,
        log_level=settings.APP_LOG_LEVEL,
        reload=settings.APP_RELOAD,
    )
