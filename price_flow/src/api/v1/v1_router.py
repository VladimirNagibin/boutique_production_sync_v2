from fastapi import APIRouter, Depends

from api.deps import verify_api_key

from .prices.closing_codes import closing_codes_router
from .prices.load_prices import load_prices_router
from .prices.load_supplier_product_codes import (
    load_supplier_product_codes_router,
)


v1_router = APIRouter(dependencies=[Depends(verify_api_key)])

v1_router.include_router(
    load_supplier_product_codes_router, prefix="/prices", tags=["load_code"]
)
v1_router.include_router(
    load_prices_router, prefix="/prices", tags=["load_price"]
)
v1_router.include_router(
    closing_codes_router,
    prefix="/prices/clothing-codes",
    tags=["clothing-codes"],
)
