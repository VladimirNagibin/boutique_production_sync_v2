from typing import TYPE_CHECKING, Annotated, Any, cast

import pandas as pd

from fastapi import Depends
from pandas import DataFrame
from sqlalchemy import bindparam, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import get_logger
from db.postgres import get_session_generator
from models.supplier_models import SupplierPrice
from schemas.supplier_schemas import SupplierProductPrice


if TYPE_CHECKING:
    from sqlalchemy import Table

logger = get_logger(__name__)

DEFAULT_BATCH_SIZE: int = 1000
PRICE_COLUMNS: tuple[str, ...] = (
    "id",
    "code",
    "name",
    "category",
    "subcategory",
    "supplier_id",
    "product_summary",
    "size",
    "color",
    "price",
)


class SupplierPriceRepository:
    """Репозиторий таблицы supplier_price в PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_by_supplier(self, supplier_id: int) -> None:
        """Удаляет прайс указанного поставщика."""
        stmt = delete(SupplierPrice).where(
            SupplierPrice.supplier_id == supplier_id
        )
        result = await self._session.execute(stmt)
        deleted_count = int(getattr(result, "rowcount", 0) or 0)
        logger.info(
            "Supplier price records deleted",
            extra={
                "supplier_id": supplier_id,
                "deleted_count": deleted_count,
            },
        )

    async def insert_batch(
        self,
        supplier_prices: list[SupplierProductPrice],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """
        Вставляет или обновляет строки прайса по (code, supplier_id).

        Args:
            supplier_prices: Строки прайса.
            batch_size: Размер пакета.

        Returns:
            Количество обработанных строк.
        """
        if not supplier_prices:
            logger.info(
                "Supplier price bulk upsert skipped", extra={"row_count": 0}
            )
            return 0

        inserted = 0
        for offset in range(0, len(supplier_prices), batch_size):
            batch = supplier_prices[offset : offset + batch_size]
            values = [self._to_row(item) for item in batch]
            stmt = insert(SupplierPrice).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_supplier_price_code_supplier",
                set_={
                    "name": stmt.excluded.name,
                    "category": stmt.excluded.category,
                    "subcategory": stmt.excluded.subcategory,
                    "product_summary": stmt.excluded.product_summary,
                    "size": stmt.excluded.size,
                    "color": stmt.excluded.color,
                    "price": stmt.excluded.price,
                },
            )
            await self._session.execute(stmt)
            inserted += len(batch)

        logger.info(
            "Supplier price bulk upsert completed",
            extra={"row_count": inserted},
        )
        return inserted

    async def update_categories(self, rows: list[dict[str, Any]]) -> None:
        """Обновляет category и subcategory по code и supplier_id."""
        if not rows:
            return
        # Core UPDATE по таблице: ORM bulk требует PK (id),
        # а мы матчим строки по (code, supplier_id).
        price_table = cast("Table", SupplierPrice.__table__)
        stmt = (
            update(price_table)
            .where(
                price_table.c.code == bindparam("p_code"),
                price_table.c.supplier_id == bindparam("p_supplier_id"),
            )
            .values(
                category=bindparam("p_category"),
                subcategory=bindparam("p_subcategory"),
            )
        )
        await self._session.execute(stmt, rows)
        logger.info(
            "Supplier price categories bulk update completed",
            extra={"row_count": len(rows)},
        )

    async def fetch_all(self) -> DataFrame:
        """Возвращает весь прайс без сортировки."""
        return await self._fetch_dataframe()

    async def fetch_ordered(self) -> DataFrame:
        """Возвращает прайс, отсортированный для выгрузки в converter."""
        return await self._fetch_dataframe(ordered=True)

    async def _fetch_dataframe(self, ordered: bool = False) -> DataFrame:
        stmt = select(SupplierPrice)
        if ordered:
            stmt = stmt.order_by(
                SupplierPrice.category,
                SupplierPrice.subcategory,
                SupplierPrice.name,
            )
        rows = (await self._session.execute(stmt)).scalars().all()
        records = [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "category": row.category,
                "subcategory": row.subcategory,
                "supplier_id": row.supplier_id,
                "product_summary": row.product_summary,
                "size": row.size,
                "color": row.color,
                "price": row.price,
            }
            for row in rows
        ]
        return pd.DataFrame(records, columns=list(PRICE_COLUMNS))

    @staticmethod
    def _to_row(item: SupplierProductPrice) -> dict[str, Any]:
        """Преобразует DTO прайса в словарь для INSERT."""
        return {
            "code": item.code,
            "name": item.name.strip(),
            "category": item.category.strip() if item.category else None,
            "subcategory": (
                item.subcategory.strip() if item.subcategory else None
            ),
            "supplier_id": item.supplier_id,
            "product_summary": item.product_summary.strip(),
            "size": item.size.strip() if item.size else None,
            "color": item.color.strip() if item.color else None,
            "price": round(item.price, 2),
        }


def get_supplier_price_repo(
    session: Annotated[AsyncSession, Depends(get_session_generator)],
) -> SupplierPriceRepository:
    """Фабрика репозитория прайса."""
    return SupplierPriceRepository(session)
