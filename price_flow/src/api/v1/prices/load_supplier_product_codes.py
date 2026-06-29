from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from api.deps import verify_api_key
from schemas.response_schemas import SuccessResponse
from services.prices.load_codes import LoaderCodes, get_loader_codes


load_supplier_product_codes_router = APIRouter(dependencies=[Depends(verify_api_key)])


@load_supplier_product_codes_router.post(  # type: ignore[misc]
    "/load-all-codes", summary="Upload supplier product codes"
)
async def load_all_codes(
    file: Annotated[
        UploadFile, File(..., description="zip file with csv product codes")
    ],
    loader_codes: Annotated[LoaderCodes, Depends(get_loader_codes)],
) -> SuccessResponse:
    return await loader_codes.load_file(file)
