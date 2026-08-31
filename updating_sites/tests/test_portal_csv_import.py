from pathlib import Path

from sqlalchemy import create_engine, text

from services.portals import PortalServices


def test_update_table_writes_csv_via_sqlalchemy_connection(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "Products.txt"
    csv_path.write_text("id;name\n1;alpha\n2;beta\n", encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'portal.db'}")
    service = PortalServices.__new__(PortalServices)
    service.portal = "ornam"
    service.engine = engine

    rows, error = service.update_table(str(csv_path), "Products")
    assert error == ""
    assert rows == 2
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM Products")
        ).scalar_one()
    assert count == 2
