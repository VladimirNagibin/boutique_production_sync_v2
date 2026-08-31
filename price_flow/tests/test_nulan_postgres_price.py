from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from repositories.supplier_price_repo import SupplierPriceRepository
from schemas.supplier_schemas import SupplierProduct, SupplierProductPrice
from services.prices.nulan.price_loader import PriceLoader


def _loader(tmp_path: Path) -> PriceLoader:
    return PriceLoader(
        clothing_codes_repo=MagicMock(),
        price_repo=MagicMock(),
        product_codes_repo=MagicMock(),
        file_uploader=MagicMock(),
        converter=MagicMock(),
        base_dir=tmp_path,
    )


def test_resolve_product_uses_clothing_lookup(tmp_path: Path) -> None:
    loader = _loader(tmp_path)
    clothing = {
        "BALLERINA CHERI чулки L/XL bianco": SupplierProduct(
            code=100001, category="Колготки", subcategory="BALLERINA"
        )
    }
    code, brand, subgroup, next_code = loader._resolve_product(
        "BALLERINA CHERI чулки",
        "L/XL",
        "bianco",
        clothing,
        {},
        200000,
    )
    assert code == 100001
    assert brand == "Колготки"
    assert subgroup == "BALLERINA"
    assert next_code == 200000


def test_resolve_product_overrides_category_from_product_codes(
    tmp_path: Path,
) -> None:
    loader = _loader(tmp_path)
    clothing = {
        "ITEM S nero": SupplierProduct(
            code=10, category="old", subcategory="old-sub"
        )
    }
    categories = {
        10: SupplierProduct(code=10, category="new", subcategory="new-sub")
    }
    code, brand, subgroup, next_code = loader._resolve_product(
        "ITEM", "S", "nero", clothing, categories, 99
    )
    assert code == 10
    assert brand == "new"
    assert subgroup == "new-sub"
    assert next_code == 99


def test_resolve_product_assigns_new_code_and_reuses_it(
    tmp_path: Path,
) -> None:
    loader = _loader(tmp_path)
    clothing: dict[str, SupplierProduct] = {}
    code, brand, subgroup, next_code = loader._resolve_product(
        "NEW", "M", "red", clothing, {}, 500
    )
    assert code == 500
    assert brand == "?"
    assert subgroup == "?"
    assert next_code == 501
    code2, _, _, next_code2 = loader._resolve_product(
        "NEW", "M", "red", clothing, {}, next_code
    )
    assert code2 == 500
    assert next_code2 == 501


def test_price_row_mapping() -> None:
    item = SupplierProductPrice(
        code=1,
        name="  name  ",
        category=" cat ",
        subcategory="",
        supplier_id=564,
        product_summary=" summary ",
        size=" S ",
        color=" nero ",
        price=12.345,
    )
    row = SupplierPriceRepository._to_row(item)
    assert row["name"] == "name"
    assert row["category"] == "cat"
    assert row["subcategory"] is None
    assert row["price"] == 12.35


@pytest.mark.asyncio
async def test_update_categories_uses_core_table_update() -> None:
    """ORM bulk UPDATE требует id; категории матчим по (code, supplier_id)."""
    session = AsyncMock()
    repo = SupplierPriceRepository(session)
    rows = [
        {
            "p_code": 1,
            "p_supplier_id": 564,
            "p_category": "cat",
            "p_subcategory": "sub",
        }
    ]
    await repo.update_categories(rows)
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    assert stmt.table.name == "supplier_price"
    assert session.execute.await_args.args[1] == rows
