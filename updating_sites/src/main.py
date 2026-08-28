from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from api.v1.auth import auth_router
from api.v1.dropbox import dropbox_router
from api.v1.storage import storage
from api.v1.tiny_admin import router as admin_router
from api.v1.update_portal import upd_portal
from api.v1.upload_file import upload_file_router
from common.request_context_middleware import RequestContextMiddleware
from core.logger import get_logger
from core.settings import settings
from middleware.auth_middleware import AuthMiddleware
from repositories.tinydb_repo import TinyDBRepository, get_tinydb_repo


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
    default_response_class=ORJSONResponse,
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

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        log_config=None,
        log_level=settings.APP_LOG_LEVEL,
        reload=settings.APP_RELOAD,
    )
