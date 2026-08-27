from http import HTTPStatus

from fastapi import APIRouter, Depends, Response

from api.v1.deps import verify_api_key
from core.logger import get_logger
from schemas.v1.entity import UpdFilesDropbox
from services.dropbox_ import DropboxService, get_dropbox

logger = get_logger(__name__)
dropbox_router = APIRouter(dependencies=[Depends(verify_api_key)])


@dropbox_router.get(
    "/check-token",
    summary="check auth token",
    description="Check auth token.",
)
def check_token(
    response: Response,
    dropbox_service: DropboxService = Depends(get_dropbox),
) -> bool:
    result = dropbox_service.check_auth_token()
    if not result:
        response.status_code = HTTPStatus.BAD_REQUEST
    logger.info(
        "Dropbox token check completed",
        extra={"valid": result, "status_code": response.status_code},
    )
    return result


@dropbox_router.get(
    "/upd-token",
    summary="update auth token",
    description="Update auth token by refresh token.",
)
def upd_token(
    response: Response,
    dropbox_service: DropboxService = Depends(get_dropbox),
) -> int:
    result = dropbox_service.get_auth_token_by_refresh()
    if result != HTTPStatus.OK:
        response.status_code = result
    logger.info(
        "Dropbox token refresh completed",
        extra={"result": result, "status_code": response.status_code},
    )
    return result


@dropbox_router.get(
    "/upd_portal_dropbox",
    summary="update portal dropbox",
    description="Update prices in dropbox.",
)
def upd_portal_dropbox(
    response: Response,
    dropbox_service: DropboxService = Depends(get_dropbox),
    # state: State = Depends(get_storage),
) -> list[UpdFilesDropbox]:
    result = dropbox_service.upd_portal_dropbox()  # (state)
    errors = [order["error"] for order in result if order.get("error")]
    if not result or errors:
        response.status_code = HTTPStatus.BAD_REQUEST
    logger.info(
        "Dropbox portal synchronization endpoint completed",
        extra={
            "processed_count": len(result),
            "error_count": len(errors),
            "status_code": response.status_code,
        },
    )
    return [UpdFilesDropbox(**order) for order in result]
