import os
from http import HTTPStatus

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile  # , Response
from fastapi.responses import Response, JSONResponse, FileResponse

from api.v1.deps import verify_api_key
from core.logger import get_logger
from core.settings import settings
from services.helper import decode_val

logger = get_logger(__name__)
upload_file_router = APIRouter(dependencies=[Depends(verify_api_key)])


@upload_file_router.post(
    "/upload",
    summary="upload file",
    description="Upload file by the path.",
)
def upload_file(
    path: str, filename: str | None = None, file: UploadFile = File(...)
) -> dict[str, int]:
    try:
        contents = file.file.read()
        filename = filename if filename else file.filename
        if filename:
            decoded_filename = decode_val(filename)
            destination = f"data/{path}/{decoded_filename}"
            logger.info(
                "File upload started",
                extra={
                    "path": path,
                    "file_name": decoded_filename,
                    "file_size": len(contents),
                },
            )
            with open(destination, "wb") as f:
                f.write(contents)
            logger.info(
                "File upload completed",
                extra={
                    "path": path,
                    "filename": decoded_filename,
                    "bytes_written": len(contents),
                },
            )
        else:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Filename not found",
            )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "File upload failed",
            extra={
                "path": path,
                "filename": filename or file.filename,
                "error": str(error),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Something went wrong",
        ) from error
    finally:
        file.file.close()
    return {"result": HTTPStatus.OK}


@upload_file_router.get(
    "/export",
    summary="export file",
    description="Export file by the path.",
    response_model=None,
)
async def export_file(response: Response, file: str) -> Response:
    if not os.path.exists(os.path.join(settings.base_dir, file)):
        logger.warning("Export file not found", extra={"file": file})
        # response.status_code = HTTPStatus.BAD_REQUEST
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST, content={"error": "File not found"}
        )
    logger.info("Export file served", extra={"file": file})
    return FileResponse(file, filename=file.rsplit("/")[-1])
