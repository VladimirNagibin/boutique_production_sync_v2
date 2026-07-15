import os
from http import HTTPStatus

from fastapi import APIRouter, File, HTTPException, UploadFile  # , Response
from fastapi.responses import Response, JSONResponse, FileResponse

from core.settings import settings
from services.helper import decode_val

upload_file_router = APIRouter()


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
            with open(f"data/{path}/{decode_val(filename)}", "wb") as f:
                f.write(contents)
        else:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Filename not found",
            )
    except Exception:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Something went wrong",
        )
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
        # response.status_code = HTTPStatus.BAD_REQUEST
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST, content={"error": "File not found"}
        )
    return FileResponse(file, filename=file.rsplit("/")[-1])
