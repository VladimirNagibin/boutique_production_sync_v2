import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from api.v1.dropbox import dropbox_router
from api.v1.storage import storage
from api.v1.update_portal import upd_portal
from api.v1.upload_file import upload_file_router
from core.logger import LOGGING
from core.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ...
    yield
    ...


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/api/openapi",
    openapi_url="/api/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(storage, prefix="/api/v1/storage", tags=["storage"])
app.include_router(upload_file_router, prefix="/api/v1/files", tags=["files"])
app.include_router(upd_portal, prefix="/api/v1/update", tags=["update"])
app.include_router(dropbox_router, prefix="/api/v1/dropbox", tags=["dropbox"])

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING,
        log_level=logging.DEBUG,
        reload=settings.APP_RELOAD,
    )
