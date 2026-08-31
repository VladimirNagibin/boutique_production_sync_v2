import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.v1 import upload_file as upload_mod
from common.logger import SafeExtraLogger, sanitize_log_extra


def test_sanitize_log_extra_renames_filename() -> None:
    cleaned = sanitize_log_extra({"filename": "a.xls", "path": "prices"})
    assert cleaned == {"file_name": "a.xls", "path": "prices"}


def test_safe_extra_logger_emits_with_filename_key() -> None:
    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = SafeExtraLogger("test.safe.extra")
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    logger.addHandler(ListHandler())
    logger.error("File upload failed", extra={"filename": "x.xls"})
    assert records
    record = records[0]
    assert record.file_name == "x.xls"  # type: ignore[attr-defined]
    assert record.filename != "x.xls"


def test_upload_creates_data_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload_mod.settings, "base_dir", str(tmp_path))
    uploaded = MagicMock()
    uploaded.filename = "КП Косметика.xls"
    uploaded.file.read.return_value = b"xls-bytes"
    result = upload_mod.upload_file(
        path="prices", filename=None, file=uploaded
    )
    saved = tmp_path / "data" / "prices" / "КП Косметика.xls"
    assert saved.read_bytes() == b"xls-bytes"
    assert result["result"] == 200
    uploaded.file.close.assert_called_once()


def test_upload_without_name_returns_error() -> None:
    uploaded = MagicMock()
    uploaded.filename = None
    uploaded.file.read.return_value = b""
    try:
        upload_mod.upload_file(path="prices", filename=None, file=uploaded)
    except HTTPException as error:
        assert error.status_code == 500
    else:
        raise AssertionError("expected HTTPException")
