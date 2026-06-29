import io

from typing import Annotated

import pandas as pd

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

# from api.deps import verify_api_key
from schemas.response_schemas import SuccessResponse
from services.prices.lanseti.price_loader import PriceLoader as PriceLoaderLancet
from services.prices.lanseti.price_loader import (
    get_price_loader as get_price_loader_lancet,
)
from services.prices.nulan.price_loader import PriceLoader as PriceLoaderNulan
from services.prices.nulan.price_loader import (
    get_price_loader as get_price_loader_nulan,
)


load_prices_router = APIRouter()  # dependencies=[Depends(verify_api_key)])


@load_prices_router.post(  # type: ignore[misc]
    "/load-price-lancet", summary="Load price of Lancet"
)
async def load_price(
    # supplier: Annotated[
    #    str, (..., description="supplier")
    # ],
    price_loader: Annotated[PriceLoaderLancet, Depends(get_price_loader_lancet)],
) -> SuccessResponse:
    upload_result = await price_loader.process_price()
    return SuccessResponse(data=upload_result.model_dump(), message="Price lancet loaded")


@load_prices_router.post(  # type: ignore[misc]
    "/load-price-nulan", summary="Load price of nulan"
)
async def load_price_nulan(
    # supplier: Annotated[
    #    str, (..., description="supplier")
    # ],
    price_loader: Annotated[PriceLoaderNulan, Depends(get_price_loader_nulan)],
) -> StreamingResponse:
    df = await price_loader.process_price()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Прайс-лист', index=False)

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=price_list.xlsx",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
    )


@load_prices_router.post(  # type: ignore[misc]
    "/load-codes-nulan", summary="Upload new product codes of nulan"
)
async def load_codes_nulan(
    file: Annotated[
        UploadFile, File(..., description="zip file with xlsx product codes")
    ],
    price_loader: Annotated[PriceLoaderNulan, Depends(get_price_loader_nulan)],
) -> SuccessResponse:
    upload_result = await price_loader.load_products(file)
    return SuccessResponse(data=upload_result.model_dump(), message="Price lancet loaded")
    #await price_loader.upd_table()
    #return SuccessResponse(message="OK")
