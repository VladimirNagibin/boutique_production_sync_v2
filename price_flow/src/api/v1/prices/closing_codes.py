from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from core.logger import get_logger
from schemas.response_schemas import SuccessResponse
from schemas.supplier_schemas import ImportResult
from services.prices.clothing_codes_service import (
    ClothingCodesService,
    get_clothing_codes_service,
)
from services.prices.load_clothing_codes import (
    LoaderClothingCodes,
    get_loader_clothing_codes,
)


logger = get_logger(__name__)

CLOTHING_CODES_SERVICE_DEPENDENCY = cast("ClothingCodesService", ...)

closing_codes_router = APIRouter()  # dependencies=[Depends(verify_api_key)])


@closing_codes_router.get("/export")
async def export_clothing_codes(
    supplier_id: int | None = Query(None, description="Фильтр по поставщику"),
    packing_format: str = Query("zip", pattern="^(zip|gzip|csv|json)$"),
    # clothing_codes_service: ClothingCodesService = Depends(
    #     get_clothing_codes_service
    # ),
    clothing_codes_service: Annotated[
        ClothingCodesService, Depends(get_clothing_codes_service)
    ] = CLOTHING_CODES_SERVICE_DEPENDENCY,
) -> StreamingResponse:
    """
    Экспортировать данные в файл (ZIP/GZIP/CSV/JSON)
    """
    logger.info(
        "Clothing codes export started",
        extra={
            "supplier_id": supplier_id,
            "packing_format": packing_format,
        },
    )
    response = await clothing_codes_service.export_clothing_codes(
        supplier_id, packing_format
    )
    logger.info(
        "Clothing codes export prepared",
        extra={
            "supplier_id": supplier_id,
            "packing_format": packing_format,
        },
    )
    return response


@closing_codes_router.post("/import", response_model=ImportResult)
async def import_clothing_codes(
    file: Annotated[
        UploadFile,
        File(..., description="ZIP/GZIP/CSV/JSON файл с данными"),
    ],
    # file: UploadFile = File(
    #     ..., description="ZIP/GZIP/CSV/JSON файл с данными"
    # ),
    clothing_codes_service: Annotated[
        ClothingCodesService,
        Depends(get_clothing_codes_service),
    ],
    # clothing_codes_service: ClothingCodesService = Depends(
    #     get_clothing_codes_service
    # ),
    strategy: str = Query(
        "upsert",
        pattern="^(upsert|skip|replace_supplier|replace_all|validate_only)$",
        description="Стратегия импорта",
    ),
    supplier_id_filter: int | None = Query(
        None, description="Ограничить импорт конкретным поставщиком"
    ),
) -> ImportResult:
    """
    Импортировать данные из файла

    Стратегии:
    - **upsert**: обновлять существующие, создавать новые
    - **skip**: пропускать существующие, создавать только новые
    - **replace_supplier**: удалить все записи поставщика перед импортом
    - **replace_all**: очистить всю таблицу перед импортом
    - **validate_only**: только проверить данные, не сохранять
    """
    logger.info(
        "Clothing codes import started",
        extra={
            "strategy": strategy,
            "supplier_id_filter": supplier_id_filter,
        },
    )
    result = await clothing_codes_service.import_clothing_codes(
        file, strategy, supplier_id_filter
    )
    logger.info(
        "Clothing codes import completed",
        extra={
            "strategy": strategy,
            "supplier_id_filter": supplier_id_filter,
            "total_records": result.total_records,
            "created_count": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "errors_count": result.errors_count,
        },
    )
    return result


@closing_codes_router.post(
    "/load-all",
    summary="Load supplier clothing codes from CSV",
)
async def load_all_clothing_codes(
    file: Annotated[
        UploadFile,
        File(
            ...,
            description=(
                "CSV or ZIP with CSV: id,code,name,category,subcategory,"
                "supplier_id,product_summary,size,color,supplier_code,"
                "description"
            ),
        ),
    ],
    loader: Annotated[LoaderClothingCodes, Depends(get_loader_clothing_codes)],
) -> SuccessResponse:
    """
    Заменяет таблицу supplier_clothing_codes данными из CSV большого объёма.

    Файл читается пакетами, таблица очищается (TRUNCATE) и заполняется заново.
    Поддерживаются разделители запятая и точка с запятой.
    """
    logger.info(
        "Clothing codes bulk load started",
        extra={"file_name": file.filename},
    )
    result = await loader.load_file(file)
    logger.info(
        "Clothing codes bulk load completed",
        extra={
            "file_name": file.filename,
            "rows_loaded": (result.details or {}).get("rows_loaded"),
        },
    )
    return result


# ----------------------------------------------------------------------
# CRUD операции
# ----------------------------------------------------------------------

# @router.get("", response_model=List[ClothingCodeInDB])
# async def get_clothing_codes(
#     supplier_id: Optional[int] = Query(None),
#     skip: int = Query(0, ge=0),
#     limit: int = Query(100, ge=1, le=1000),
#     only_active: bool = Query(False),
#     repo: ClothingCodeRepository = Depends(get_repository)
# ):
#     """Получить список кодов товаров"""
#     items = await repo.get_all(
#         supplier_id=supplier_id,
#         skip=skip,
#         limit=limit,
#         only_active=only_active
#     )
#     return [ClothingCodeInDB(**item) for item in items]


# @router.get("/search", response_model=List[ClothingCodeInDB])
# async def search_clothing_codes(
#     q: str = Query(..., min_length=1, description="Поисковый запрос"),
#     supplier_id: Optional[int] = Query(None),
#     limit: int = Query(50, ge=1, le=200),
#     repo: ClothingCodeRepository = Depends(get_repository)
# ):
#     """Поиск по кодам товаров"""
#     items = await repo.search(q, supplier_id=supplier_id, limit=limit)
#     return [ClothingCodeInDB(**item) for item in items]


# @router.get("/{item_id}", response_model=ClothingCodeInDB)
# async def get_clothing_code(
#     item_id: int,
#     repo: ClothingCodeRepository = Depends(get_repository)
# ):
#     """Получить запись по ID"""
#     item = await repo.get_by_id(item_id)

#     if not item:
#         raise HTTPException(status_code=404, detail="Запись не найдена")

#     return ClothingCodeInDB(**item)


# @router.post("", response_model=ClothingCodeInDB, status_code=201)
# async def create_clothing_code(
#     data: ClothingCodeCreate,
#     repo: ClothingCodeRepository = Depends(get_repository)
# ):
#     """Создать новую запись"""
#     # Проверяем на дубликат
#     existing = await repo.get_by_supplier_code(data.supplier_id, data.code)
#     if existing:
#         raise HTTPException(
#             status_code=409,
#             detail=(
#                 f"Запись с кодом {data.code} для поставщика "
#                 f"{data.supplier_id} уже существует"
#             )
#         )

#     new_id = await repo.create(data)

#     # Получаем созданную запись
#     new_item = await repo.get_by_id(new_id)
#     return ClothingCodeInDB(**new_item)


# @router.patch("/{item_id}", response_model=ClothingCodeInDB)
# async def update_clothing_code(
#     item_id: int,
#     data: ClothingCodeUpdate,
#     repo: ClothingCodeRepository = Depends(get_repository)
# ):
#     """Обновить запись"""
#     # Проверяем существование
#     existing = await repo.get_by_id(item_id)
#     if not existing:
#         raise HTTPException(status_code=404, detail="Запись не найдена")

#     # Если обновляем code или supplier_id, проверяем уникальность
#     if data.code is not None or data.supplier_id is not None:
#         new_code = data.code if data.code is not None else existing['code']
#         new_supplier = (
#             data.supplier_id if data.supplier_id is not None
#             else existing['supplier_id']
#         )

#         duplicate = await repo.get_by_supplier_code(new_supplier, new_code)
#         if duplicate and duplicate['id'] != item_id:
#             raise
