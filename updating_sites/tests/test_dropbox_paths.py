from pathlib import Path

from core.settings import settings
from services.local_paths import resolve_local_path


def test_resolve_relative_data_prices(tmp_path: Path) -> None:
    stored = "data/prices/КП Косметика.xls"
    resolved = resolve_local_path(stored, base_dir=tmp_path)
    assert resolved == tmp_path / stored


def test_resolve_filename_only_uses_prices_dir(tmp_path: Path) -> None:
    resolved = resolve_local_path("blank.xls", base_dir=tmp_path)
    assert resolved == tmp_path / "data" / "prices" / "blank.xls"


def test_resolve_absolute_path_unchanged(tmp_path: Path) -> None:
    absolute = tmp_path / "other" / "file.xls"
    resolved = resolve_local_path(str(absolute), base_dir=tmp_path)
    assert resolved == absolute


def test_ornam_csv_resolves_under_base_dir() -> None:
    resolved = resolve_local_path("data/ornam/Products.txt")
    expected = Path(settings.base_dir) / "data" / "ornam" / "Products.txt"
    assert resolved == expected
