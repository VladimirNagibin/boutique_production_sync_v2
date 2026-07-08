from typing import Any, ClassVar

from sqladmin import Admin
from sqladmin.filters import OperationColumnFilter

from models.supplier_models import (
    SupplierClothingCode,
    SupplierPrice,
    SupplierProductCode,
)

from .base_admin import BaseAdmin
from .mixins import COLUMN_LABELS


class SupplierProductCodeAdmin(BaseAdmin, model=SupplierProductCode):  # type: ignore[call-arg]
    name = "Код поставщика"
    name_plural = "Все коды поставщиков"
    category = "Коды"
    icon = "fa-solid fa-barcode"

    column_list: ClassVar[tuple[str, ...]] = (  # Поля в списке
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_labels_local: ClassVar[dict[str, str]] = {}  # Надписи в списке
    column_labels = COLUMN_LABELS | column_labels_local
    column_default_sort: ClassVar[list[tuple[str, bool]]] = [
        ("id", True),
        ("code", True),
    ]  # Сортировка по умолчанию
    column_sortable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможна сортировка
    column_searchable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможен поиск
    form_columns: ClassVar[tuple[str, ...]] = (  # Поля на форме
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_details_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Поля на форме просмотра
    column_filters: ClassVar[tuple[Any, ...]] = (
        # BooleanFilter(User.is_admin),
        # AllUniqueStringValuesFilter(User.name),
        # ForeignKeyFilter(
        #     SourceColumnMapping.config,
        #     SourceImportConfig.source, title="Config"
        # ),
        # OperationColumnFilter provides dropdown UI with multiple operations
        OperationColumnFilter(SupplierProductCode.category),
        OperationColumnFilter(SupplierProductCode.subcategory),
        # String operations: Contains, Equals, Starts with, Ends with
        # OperationColumnFilter(User.age),
        # # Numeric operations: Equals, Greater than, Less than
        # OperationColumnFilter(User.created_at),
        # # DateTime operations: Equals, Greater than, Less than
    )


class SupplierClothingCodeAdmin(BaseAdmin, model=SupplierClothingCode):  # type: ignore[call-arg]
    name = "Код поставщика одежды"
    name_plural = "Коды поставщиков одежды"
    category = "Коды"
    icon = "fa-solid fa-tshirt"

    column_list: ClassVar[tuple[str, ...]] = (  # Поля в списке
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_labels_local: ClassVar[dict[str, str]] = {}  # Надписи в списке
    column_labels = COLUMN_LABELS | column_labels_local
    column_default_sort: ClassVar[list[tuple[str, bool]]] = [
        ("id", True),
        ("code", True),
    ]  # Сортировка по умолчанию
    column_sortable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможна сортировка
    column_searchable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможен поиск
    form_columns: ClassVar[tuple[str, ...]] = (  # Поля на форме
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_details_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Поля на форме просмотра
    column_filters: ClassVar[tuple[Any, ...]] = (
        OperationColumnFilter(SupplierProductCode.category),
        OperationColumnFilter(SupplierProductCode.subcategory),
    )


class SupplierPriceAdmin(BaseAdmin, model=SupplierPrice):  # type: ignore[call-arg]
    name = "Прайс поставщика"
    name_plural = "Прайсы поставщиков"
    category = "Коды"
    icon = "fa-solid fa-tag"

    column_list: ClassVar[tuple[str, ...]] = (  # Поля в списке
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_labels_local: ClassVar[dict[str, str]] = {}  # Надписи в списке
    column_labels = COLUMN_LABELS | column_labels_local
    column_default_sort: ClassVar[list[tuple[str, bool]]] = [
        ("id", True),
        ("code", True),
    ]  # Сортировка по умолчанию
    column_sortable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможна сортировка
    column_searchable_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Список полей по которым возможен поиск
    form_columns: ClassVar[tuple[str, ...]] = (  # Поля на форме
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )
    column_details_list: ClassVar[tuple[str, ...]] = (
        "id",
        "code",
        "name",
        "category",
        "subcategory",
        "supplier_id",
    )  # Поля на форме просмотра
    column_filters: ClassVar[tuple[Any, ...]] = (
        OperationColumnFilter(SupplierProductCode.category),
        OperationColumnFilter(SupplierProductCode.subcategory),
    )


# Регистрация всех моделей
def register_models(admin: Admin) -> None:
    admin.add_view(SupplierProductCodeAdmin)
    admin.add_view(SupplierClothingCodeAdmin)
    admin.add_view(SupplierPriceAdmin)
