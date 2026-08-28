from pathlib import Path

import pandas as pd
import pytest

from common.exceptions.file import CsvParsingError
from repositories.supplier_clothing_codes_repo import (
    SupplierClothingCodeRepository,
)


CSV_HEADER = (
    "id,code,name,category,subcategory,supplier_id,product_summary,"
    "size,color,supplier_code,description\n"
)
CSV_ROW = (
    "1,100001,BALLERINA CHERI чулки L/XL bianco,Колготки,BALLERINA,564,"
    "BALLERINA CHERI чулки,L/XL,bianco,,\n"
)


def test_detect_comma_separator(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text(CSV_HEADER + CSV_ROW, encoding="utf-8")
    separator = SupplierClothingCodeRepository._detect_separator(
        csv_path, "utf-8"
    )
    assert separator == ","


def test_detect_semicolon_separator(tmp_path: Path) -> None:
    csv_path = tmp_path / "codes.csv"
    header = CSV_HEADER.replace(",", ";")
    csv_path.write_text(header, encoding="utf-8")
    separator = SupplierClothingCodeRepository._detect_separator(
        csv_path, "utf-8"
    )
    assert separator == ";"


def test_prepare_dataframe_converts_types_and_empty_strings() -> None:
    raw = pd.DataFrame(
        [
            {
                "id": "1",
                "code": "100001",
                "name": "  BALLERINA CHERI  ",
                "category": "Колготки",
                "subcategory": "BALLERINA",
                "supplier_id": "564",
                "product_summary": "BALLERINA CHERI чулки",
                "size": "L/XL",
                "color": "bianco",
                "supplier_code": "",
                "description": "",
            }
        ]
    )
    prepared = SupplierClothingCodeRepository.prepare_dataframe(raw)
    assert prepared.loc[0, "id"] == 1
    assert prepared.loc[0, "code"] == 100001
    assert prepared.loc[0, "supplier_id"] == 564
    assert prepared.loc[0, "name"] == "BALLERINA CHERI"
    assert prepared.loc[0, "supplier_code"] is None
    assert prepared.loc[0, "description"] is None


def test_validate_columns_raises_on_missing(tmp_path: Path) -> None:
    repo = SupplierClothingCodeRepository(session=None)  # type: ignore[arg-type]
    df = pd.DataFrame([{"id": "1", "name": "x"}])
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("id,name\n1,x\n", encoding="utf-8")
    with pytest.raises(CsvParsingError):
        repo._validate_columns(df, csv_path)
