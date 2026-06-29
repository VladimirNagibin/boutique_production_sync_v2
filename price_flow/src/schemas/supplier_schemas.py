import math

from typing import Any

from pydantic import BaseModel, Field, field_validator


class SupplierProduct(BaseModel):
    """
    Группа, подгруппа и код поставщика .
    """

    code: int
    category: str
    subcategory: str


class SupplierProductPrice(BaseModel):
    """
    Группа, подгруппа и код поставщика .
    """

    code: int
    name: str
    category: str
    subcategory: str
    supplier_id: int
    product_summary: str
    size: str
    color: str
    price: float


class ClothingCodeBase(BaseModel):
    """Базовая схема"""
    code: int = Field(..., gt=0, description="Код товара у поставщика")
    name: str = Field(..., min_length=1, description="Наименование товара")
    category: str | None = None
    subcategory: str | None = None
    supplier_id: int = Field(..., gt=0, description="ID поставщика")
    product_summary: str = Field(..., min_length=1, description="Сводка по товару")
    size: str | None = None
    color: str | None = None
    supplier_code: str | None = None
    description: str | None = None

    @field_validator('name', 'product_summary')
    def validate_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            error_message = "Поле не может быть пустым"
            raise ValueError(error_message)
        return v.strip()


class ClothingCodeCreate(ClothingCodeBase):
    """Создание записи"""

    @field_validator('supplier_code', 'description', mode='before')
    @classmethod
    def convert_nan_to_none(cls, v: Any) -> Any:
        """Преобразует float('nan') в None перед валидацией."""
        if isinstance(v, float) and math.isnan(v):
            return None
        # Если это строка 'nan' (редко, но бывает), тоже можно преобразовать
        if isinstance(v, str) and v.lower() == 'nan':
            return None
        return v


class ClothingCodeUpdate(BaseModel):
    """Обновление записи (все поля опциональны)"""
    code: int | None = Field(None, gt=0)
    name: str | None = Field(None, min_length=1)
    category: str | None = None
    subcategory: str | None = None
    supplier_id: str | None = Field(None, gt=0)
    product_summary: str | None = Field(None, min_length=1)
    size: str | None = None
    color: str | None = None
    supplier_code: str | None = None
    description: str | None = None


class ClothingCodeInDB(ClothingCodeBase):
    """Запись из БД"""
    id: int

    class Config:
        from_attributes = True


class ClothingCodeExport(ClothingCodeBase):
    """Для экспорта (без ID и дат)"""


class ImportResult(BaseModel):
    """Результат импорта"""
    message: str
    total_records: int
    created: int
    updated: int
    skipped: int = 0
    errors: list[dict[str, Any]]
    errors_count: int


class BatchOperationResult(BaseModel):
    """Результат массовой операции"""
    success: bool
    message: str
    affected_rows: int
