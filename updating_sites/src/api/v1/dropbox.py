from http import HTTPStatus
from typing import Any

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
    items = [_to_dropbox_dto(order) for order in result]
    errors = [item.error for item in items if item.error]
    if not items or errors:
        response.status_code = HTTPStatus.BAD_REQUEST
    logger.info(
        "Dropbox portal synchronization endpoint completed",
        extra={
            "processed_count": len(items),
            "error_count": len(errors),
            "status_code": response.status_code,
        },
    )
    return items


def _to_dropbox_dto(order: dict[str, Any]) -> UpdFilesDropbox:
    """Преобразует внутренний результат сервиса в DTO ответа."""
    old_file = order.get("old_file") or {}
    return UpdFilesDropbox(
        filename=order["file_name"],
        load=order.get("uploaded"),
        del_dropbox=old_file.get("del_dropbox"),
        del_lockal=old_file.get("del_local"),
        # пробрасываем и вложенную ошибку удаления старого файла
        error=order.get("error") or old_file.get("error"),
    )
