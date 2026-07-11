from sqlalchemy import (
    BigInteger,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres import Base


# ===== Миксины =====


class CommonFieldsMixin:
    """Базовые поля для всех таблиц с товарами."""

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    code: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True)
    supplier_id: Mapped[int] = mapped_column(Integer, nullable=False)


class ProductDetailsMixin:
    """Поля с деталями товара (общие для Clothing и Price)."""

    product_summary: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[str | None] = mapped_column(String, nullable=True)
    color: Mapped[str | None] = mapped_column(String, nullable=True)


class ClothingExtraMixin:
    """Дополнительные поля для таблицы одежды."""

    supplier_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class PriceExtraMixin:
    """Дополнительные поля для таблицы прайса."""

    price: Mapped[float] = mapped_column(Float, nullable=False)


# ===== Модели =====


class SupplierProductCode(Base, CommonFieldsMixin):  # type: ignore[misc]
    __tablename__ = "supplier_product_codes"

    __table_args__ = (
        UniqueConstraint(
            "code",
            "supplier_id",
            name="uq_supplier_product_codes_code_supplier",
        ),
        Index(
            "idx_supplier_product_codes_supplier_code",
            "supplier_id",
            "code",
        ),
        Index("idx_supplier_product_codes_name", "name"),
    )


class SupplierClothingCode(
    Base,  # type: ignore[misc]
    CommonFieldsMixin,
    ProductDetailsMixin,
    ClothingExtraMixin,
):
    __tablename__ = "supplier_clothing_codes"

    __table_args__ = (
        UniqueConstraint(
            "code",
            "supplier_id",
            name="uq_supplier_clothing_codes_code_supplier",
        ),
        Index(
            "idx_supplier_clothing_codes_supplier_code", "supplier_id", "code"
        ),
        Index("idx_supplier_clothing_codes_name", "name"),
    )


class SupplierPrice(
    Base,  # type: ignore[misc]
    CommonFieldsMixin,
    ProductDetailsMixin,
    PriceExtraMixin,
):
    __tablename__ = "supplier_price"

    __table_args__ = (
        UniqueConstraint(
            "code", "supplier_id", name="uq_supplier_price_code_supplier"
        ),
        Index("idx_supplier_price_supplier_code", "supplier_id", "code"),
        Index("idx_supplier_price_name", "name"),
    )
