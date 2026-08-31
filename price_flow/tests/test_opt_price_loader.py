from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from common.exceptions.app_exceptions import (
    DownloadError,
    PriceProcessingError,
)
from schemas.converter_schemas import UploadResult
from services.prices.opt.price_loader import (
    PriceLoader,
    extract_blank_href,
)


BLANK_HTML = """
<html><body>
<ol>
  <li>skip</li>
  <li><a href="/files/blank.xls">Бланк заказа</a></li>
</ol>
</body></html>
"""


def test_extract_blank_href_takes_first_ol_link() -> None:
    href = extract_blank_href(BLANK_HTML)
    assert href == "/files/blank.xls"


def test_extract_blank_href_requires_ol() -> None:
    with pytest.raises(PriceProcessingError) as exc:
        extract_blank_href("<html><body><p>no list</p></body></html>")
    assert exc.value.error_code == "OPT_BLANK_LIST_NOT_FOUND"


def test_extract_blank_href_requires_anchor() -> None:
    with pytest.raises(PriceProcessingError) as exc:
        extract_blank_href("<html><body><ol><li>empty</li></ol></body></html>")
    assert exc.value.error_code == "OPT_BLANK_LINK_NOT_FOUND"


@pytest.mark.asyncio
async def test_process_price_downloads_and_converts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    converter = MagicMock()
    converter.upload_file.return_value = UploadResult(
        filename="blank.xls",
        token="file-id",  # noqa: S106
        message="ok",
        success=True,
    )
    loader = PriceLoader(
        converter=converter,
        blank_url="https://opt-centre.ru/blank-zakaza",
        upload_dir=tmp_path,
    )

    page = MagicMock()
    page.status_code = 200
    page.text = BLANK_HTML
    page.content = b"xls-bytes"
    file_resp = MagicMock()
    file_resp.status_code = 200
    file_resp.content = b"xls-bytes"

    def fake_get(url: str, *_args: object, **_kwargs: object) -> MagicMock:
        if url.endswith("blank-zakaza"):
            return page
        return file_resp

    monkeypatch.setattr(
        "services.prices.opt.price_loader.requests.get", fake_get
    )

    result, details = await loader.process_price()
    assert result.success is True
    converter.upload_file.assert_called_once()
    uploaded_path = converter.upload_file.call_args.args[0]
    assert uploaded_path.name.endswith("blank.xls")
    assert not uploaded_path.exists()
    assert details["converter_success"] is True


@pytest.mark.asyncio
async def test_process_price_raises_on_http_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = PriceLoader(
        converter=MagicMock(),
        blank_url="https://opt-centre.ru/blank-zakaza",
        upload_dir=tmp_path,
    )
    page = MagicMock()
    page.status_code = 503

    monkeypatch.setattr(
        "services.prices.opt.price_loader.requests.get",
        lambda *args, **kwargs: page,
    )
    with pytest.raises(DownloadError):
        await loader.process_price()


@pytest.mark.asyncio
async def test_process_price_raises_on_connection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = PriceLoader(
        converter=MagicMock(),
        blank_url="https://opt-centre.ru/blank-zakaza",
        upload_dir=tmp_path,
    )

    def boom(*args: object, **kwargs: object) -> None:
        message = "down"
        raise requests.ConnectionError(message)

    monkeypatch.setattr("services.prices.opt.price_loader.requests.get", boom)
    with pytest.raises(DownloadError):
        await loader.process_price()
