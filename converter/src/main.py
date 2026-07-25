import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis
import uvicorn

from api.v1.upload_files import upload_file_router
from core.logger import LOGGING_CONFIG, logger
from core.settings import settings
from db import redis_client
from services.tasks import clear_files, listen_to_redis_events

scheduler = AsyncIOScheduler()

INTERVAL_TRIGGER = 60


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    redis_client.redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
    )
    task = asyncio.create_task(listen_to_redis_events())
    scheduler.add_job(
        clear_files,
        trigger=IntervalTrigger(minutes=INTERVAL_TRIGGER),
        id="clear_files",
        replace_existing=True,
    )
    scheduler.start()
    try:
        yield  # здесь работает приложение
    finally:
        # 1. Сначала отменяем задачу слушателя Redis
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # ожидаемое поведение

        # 2. Закрываем соединение Redis
        await redis_client.redis.close()

        # 3. Останавливаем планировщик
        scheduler.shutdown()


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/api/openapi",
    openapi_url="/api/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(upload_file_router, prefix="/api/v1/files", tags=["files"])


if __name__ == "__main__":
    logger.info("Start app.")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING_CONFIG,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,  #  settings.APP_RELOAD,
    )
