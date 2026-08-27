from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, Depends, Response

from api.v1.deps import verify_api_key
from core.logger import get_logger
from services.storage import get_storage, State


logger = get_logger(__name__)
storage = APIRouter(dependencies=[Depends(verify_api_key)])


@storage.post(
    "/add-in-storage",
    summary="add in storage",
    description="Add key:value in storage.",
)
def add_in_storage(
    response: Response,
    key: str,
    value: str,
    storage: State = Depends(get_storage),
) -> bool:
    result = storage.set_state(key, str(value))
    if not result:
        response.status_code = HTTPStatus.BAD_REQUEST
    logger.info(
        "Storage write endpoint completed",
        extra={
            "key": key,
            "success": result,
            "status_code": response.status_code,
        },
    )
    return result


@storage.get(
    "/get-from-storage",
    summary="get from storage",
    description="Get value by key from storage.",
)
def get_from_storage(
    response: Response,
    key: str,
    storage: State = Depends(get_storage),
) -> Any | str | None:
    result = storage.get_state(key)
    if not result:
        response.status_code = HTTPStatus.BAD_REQUEST
    logger.debug(
        "Storage read endpoint completed",
        extra={
            "key": key,
            "found": result is not None,
            "status_code": response.status_code,
        },
    )
    return result
