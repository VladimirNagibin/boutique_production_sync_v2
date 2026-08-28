import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis

from api.v1.upload_files import upload_file_router
from common.request_context_middleware import RequestContextMiddleware
from core.logger import get_logger
from core.settings import settings
from db import redis_client
from services.tasks import clear_files, listen_to_redis_events


logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

INTERVAL_TRIGGER = 60


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет запуском и остановкой ресурсов приложения."""
    listener_task: asyncio.Task[None] | None = None
    logger.info(
        "Converter application startup started",
        extra={"component": "application", "phase": "startup"},
    )
    try:
        try:
            redis_client.redis = Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
            )
        except Exception:
            logger.exception(
                "Redis client initialization failed",
                extra={"component": "redis", "phase": "startup"},
            )
            raise
        logger.info(
            "Redis client initialized",
            extra={
                "component": "redis",
                "phase": "startup",
                "redis_host": settings.REDIS_HOST,
                "redis_port": settings.REDIS_PORT,
            },
        )

        try:
            listener_task = asyncio.create_task(listen_to_redis_events())
        except Exception:
            logger.exception(
                "Redis listener task creation failed",
                extra={"component": "redis_listener", "phase": "startup"},
            )
            raise
        logger.info(
            "Redis listener task created",
            extra={"component": "redis_listener", "phase": "startup"},
        )

        try:
            scheduler.add_job(
                clear_files,
                trigger=IntervalTrigger(minutes=INTERVAL_TRIGGER),
                id="clear_files",
                replace_existing=True,
            )
            scheduler.start()
        except Exception:
            logger.exception(
                "File cleanup scheduler startup failed",
                extra={"component": "scheduler", "phase": "startup"},
            )
            raise
        logger.info(
            "File cleanup scheduler started",
            extra={
                "component": "scheduler",
                "phase": "startup",
                "interval_minutes": INTERVAL_TRIGGER,
            },
        )
        logger.info(
            "Converter application startup completed",
            extra={"component": "application", "phase": "startup"},
        )
        yield
    except Exception:
        logger.exception(
            "Converter application lifespan failed",
            extra={"component": "application", "phase": "runtime"},
        )
        raise
    finally:
        logger.info(
            "Converter application shutdown started",
            extra={"component": "application", "phase": "shutdown"},
        )

        if listener_task is not None:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                logger.info(
                    "Redis listener task cancelled",
                    extra={"component": "redis_listener", "phase": "shutdown"},
                )
            except Exception:
                logger.exception(
                    "Redis listener task shutdown failed",
                    extra={"component": "redis_listener", "phase": "shutdown"},
                )

        if redis_client.redis is not None:
            try:
                await redis_client.redis.close()
                logger.info(
                    "Redis client closed",
                    extra={"component": "redis", "phase": "shutdown"},
                )
            except Exception:
                logger.exception(
                    "Redis client shutdown failed",
                    extra={"component": "redis", "phase": "shutdown"},
                )
            finally:
                redis_client.redis = None

        if scheduler.running:
            try:
                scheduler.shutdown()
                logger.info(
                    "File cleanup scheduler stopped",
                    extra={"component": "scheduler", "phase": "shutdown"},
                )
            except Exception:
                logger.exception(
                    "File cleanup scheduler shutdown failed",
                    extra={"component": "scheduler", "phase": "shutdown"},
                )

        logger.info(
            "Converter application shutdown completed",
            extra={"component": "application", "phase": "shutdown"},
        )


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/api/openapi",
    openapi_url="/api/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(upload_file_router, prefix="/api/v1/files", tags=["files"])
app.add_middleware(RequestContextMiddleware)


if __name__ == "__main__":
    logger.info(
        "Starting Uvicorn server",
        extra={"component": "uvicorn", "phase": "startup"},
    )
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        log_config=None,
        log_level=settings.APP_LOG_LEVEL.lower(),
        reload=False,
    )
