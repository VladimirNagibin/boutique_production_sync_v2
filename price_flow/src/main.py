import sys

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin

from admin.admin_models import register_models
from admin.authenticate import BasicAuthBackend
from api.health_checker import health_router
from api.v1.v1_router import v1_router
from common.exceptions.base import BaseAppException
from common.exceptions.enums import ErrorCode
from common.logger import logger
from core.settings import settings
from db.postgres import db_manager

# from db.redis import close_redis, init_redis
from middleware.execution_time_middleware import ExecutionTimeMiddleware
from schemas.response_schemas import ErrorResponse


# ===== Константы =====
STATIC_DIR_ENV_VAR = "STATIC_DIR"
DEFAULT_STATIC_DIR = "static"


# ===== Lifespan менеджер =====


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управляет жизненным циклом приложения FastAPI.

    Выполняет инициализацию при старте и корректное завершение при остановке.

    Args:
        app: Экземпляр FastAPI.

    Yields:
        None
    """
    logger.info("Initializing %s ...", app.title)
    try:
        await db_manager.initialize()
        logger.info("✅ Database initialized successfully")
        configure_admin_panel(app)
        # await init_redis()
        # await initialize_bitrix_container()
    except Exception as e:  # noqa: BLE001
        logger.critical("Fatal error during startup: %s", e)
        # При фатальной ошибке инициализации завершаем процесс
        sys.exit(1)

    yield

    logger.info("Closing %s ...", app.title)
    # await close_redis()
    # await shutdown_bitrix_container()
    try:
        await db_manager.dispose()
        logger.info("✅ Database connections closed")
    except Exception as e:  # noqa: BLE001
        logger.error("⚠️ Error during database shutdown: %s", e)

    logger.info("Application shutdown complete.")


# ===== Настройка маршрутов =====


def configure_routes(app: FastAPI) -> None:
    """
    Подключает роутеры к приложению.

    Args:
        app: Экземпляр FastAPI.
    """
    app.include_router(health_router, prefix="/api/health", tags=["health"])
    app.include_router(v1_router, prefix="/api/v1", tags=["v1"])


# ===== Настройка админ-панели =====


def configure_admin_panel(app: FastAPI) -> None:
    """Настройка админ-панели."""
    auth_backend = BasicAuthBackend()
    admin = Admin(
        app,
        db_manager.engine,
        title="Админка",
        templates_dir="templates/admin",
        authentication_backend=auth_backend,
    )
    register_models(admin)
    logger.info("Admin panel configured.")


# ===== Глобальные обработчики исключений =====


def configure_exception_handlers(app: FastAPI) -> None:
    """
    Регистрирует глобальные обработчики исключений для приложения.
    """

    @app.exception_handler(BaseAppException)
    async def handle_base_app_exception(  # pyright: ignore [reportUnusedFunction]
        request: Request, exc: BaseAppException
    ) -> JSONResponse:
        """
        Обрабатывает все бизнес-исключения приложения (наследники
        BaseAppException).
        """
        request_id = request.headers.get("X-Request-ID")
        execution_time_ms = float(
            request.headers.get("X-Execution-Time-Ms", 0)
        )
        status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                request_id=request_id,
            ).model_dump(mode="json"),
            headers={
                "X-Request-ID": request_id or "",
                "X-Execution-Time-Ms": str(execution_time_ms),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(  # pyright: ignore [reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Обрабатывает все непредвиденные исключения
        (500 Internal Server Error).
        """
        request_id = request.headers.get("X-Request-ID")
        execution_time_ms = float(
            request.headers.get("X-Execution-Time-Ms", 0)
        )

        logger.error(
            "Unexpected error",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "path": request.url.path,
                "method": request.method,
            },
            exc_info=True,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Internal server error",
                details={"error_type": type(exc).__name__},
                request_id=request_id,
                execution_time=execution_time_ms,
            ).model_dump(mode="json"),
            headers={
                "X-Request-ID": request_id or "",
                "X-Execution-Time-Ms": str(execution_time_ms),
            },
        )


# ===== Статические файлы =====


def mount_static_files(app: FastAPI) -> None:
    """
    Монтирует директорию статических файлов, если она существует.
    """
    static_dir = Path(settings.app.base_dir) / DEFAULT_STATIC_DIR
    if static_dir.exists() and static_dir.is_dir():
        app.mount(
            "/static", StaticFiles(directory=str(static_dir)), name="static"
        )
        logger.debug(f"Mounted static files from {static_dir}")
    else:
        logger.warning(f"Static directory not found: {static_dir}")


# ===== Фабрика приложения =====


def create_fastapi_application() -> FastAPI:
    """
    Создаёт и настраивает экземпляр FastAPI приложения.

    Returns:
        Настроенный экземпляр FastAPI.
    """
    app = FastAPI(
        title=settings.app.project_name,
        docs_url="/api/openapi",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    configure_routes(app)
    configure_exception_handlers(app)
    mount_static_files(app)

    # Добавляем middleware для измерения времени выполнения запросов
    app.add_middleware(ExecutionTimeMiddleware)

    return app


# ===== Запуск сервера =====


def start_server() -> None:
    """
    Запускает Uvicorn сервер с настройками из конфигурации.
    """
    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        log_config=None,  # Используем собственную конфигурацию логов
        log_level=settings.app.log_level.lower(),
        reload=settings.app.reload,
    )


# ===== Глобальный экземпляр приложения =====
app = create_fastapi_application()


# ===== Точка входа =====
if __name__ == "__main__":
    logger.info("Starting server %s ...", app.title)
    start_server()
