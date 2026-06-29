import uvicorn

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, ORJSONResponse

from api.health_checker import healht_router
from api.v1.v1_router import v1_router
from core.exceptions import BaseAppException
from core.logger import LOGGING_CONFIG, logger
from core.settings import settings
from schemas.response_schemas import ErrorResponse


def setup_routes(app: FastAPI) -> None:
    """Настройка маршрутов приложения."""
    app.include_router(v1_router, prefix="/api/v1", tags=["api_v1"])
    # app.include_router(test_router, prefix="/api/v1/test", tags=["test"])
    app.include_router(healht_router, prefix="/api", tags=["health"])


def register_exception_handler(app: FastAPI) -> None:
    """
    Регистрирует глобальные обработчики исключений для приложения.
    """

    @app.exception_handler(BaseAppException)  # type: ignore[misc]
    async def app_exception_handler(  # type: ignore
        request: Request, exc: BaseAppException
    ):
        """Обработчик для всех наших бизнес-исключений."""
        _ = request
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error_code=exc.error_code, message=exc.message
            ).model_dump(mode="json"),
        )


def create_app() -> FastAPI:
    """Фабрика для создания приложения."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        docs_url="/api/openapi",
        openapi_url="/api/openapi.json",
        default_response_class=ORJSONResponse,
        # lifespan=lifespan,
    )

    setup_routes(app)
    register_exception_handler(app)

    return app


def start_server() -> None:
    logger.info("Start bp_sync.")
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        log_config=LOGGING_CONFIG,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.APP_RELOAD,
    )


app = create_app()


if __name__ == "__main__":
    start_server()
