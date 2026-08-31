"""Загрузка бланка прайса Opt-centre и отправка в converter."""

import asyncio
import uuid

from pathlib import Path
from typing import Annotated, Any, ClassVar
from urllib.parse import unquote, urljoin, urlparse

import requests

from bs4 import BeautifulSoup
from fastapi import Depends

from common.exceptions.app_exceptions import (
    DownloadError,
    PriceProcessingError,
)
from common.exceptions.base import BaseAppException
from common.log_context import bind_class, log_run
from common.log_redact import redact_url
from core.logger import get_logger
from core.settings import settings
from schemas.converter_schemas import UploadResult
from services.converter import FileUploader as Converter
from services.converter import get_file_uploader as get_converter


logger = get_logger(__name__)

HTTP_TIMEOUT_SECONDS: int = 60
USER_AGENT: str = (
    "Mozilla/5.0 (compatible; BoutiquePriceSync/1.0; +https://opt-centre.ru)"
)
DEFAULT_FILE_NAME: str = "opt_blank.xls"


class PriceLoader:
    """Скачивает бланк Opt и отправляет файл в converter."""

    DEFAULT_SUPPLIER: ClassVar[str] = "opt"

    def __init__(
        self,
        converter: Converter,
        blank_url: str,
        upload_dir: Path,
    ) -> None:
        self.converter = converter
        self.blank_url = blank_url
        self.upload_dir = upload_dir

    async def process_price(self) -> tuple[UploadResult, dict[str, Any]]:
        """
        Скачивает xls со страницы Opt и передаёт файл в converter.

        Returns:
            Результат загрузки в converter и детали источника.
        """
        saved_path: Path | None = None
        with bind_class(self), log_run("process_price"):
            logger.info(
                "Starting supplier price processing",
                extra={"supplier": self.DEFAULT_SUPPLIER},
            )
            try:
                html = await asyncio.to_thread(self._get_page_text)
                href = extract_blank_href(html)
                file_url = urljoin(self.blank_url, href)
                saved_path = await asyncio.to_thread(
                    self._download_file, file_url
                )
                logger.info(
                    "Uploading processed price to converter",
                    extra={
                        "supplier": self.DEFAULT_SUPPLIER,
                        "file_name": saved_path.name,
                    },
                )
                upload_result = await asyncio.to_thread(
                    self.converter.upload_file, saved_path
                )
            except BaseAppException:
                logger.warning(
                    "Supplier price processing failed",
                    extra={
                        "supplier": self.DEFAULT_SUPPLIER,
                        "error_type": "BaseAppException",
                    },
                )
                raise
            except Exception as error:
                logger.exception(
                    "Unexpected supplier price processing error",
                    extra={
                        "supplier": self.DEFAULT_SUPPLIER,
                        "error_type": type(error).__name__,
                    },
                )
                raise PriceProcessingError(
                    error_code="PRICE_PROCESSING_ERROR",
                    message="Unexpected error during price processing",
                    details=str(error),
                ) from error
            else:
                details: dict[str, Any] = {
                    "source_url": redact_url(file_url),
                    "file_name": saved_path.name,
                    "converter_success": upload_result.success,
                }
                logger.info(
                    "Price processing completed",
                    extra={
                        "supplier": self.DEFAULT_SUPPLIER,
                        "converter_success": upload_result.success,
                        "file_name": saved_path.name,
                    },
                )
                return upload_result, details
            finally:
                if saved_path is not None and saved_path.exists():
                    saved_path.unlink(missing_ok=True)

    def _get_page_text(self) -> str:
        """Загружает HTML страницы бланка."""
        response = self._request(self.blank_url)
        return response.text

    def _download_file(self, file_url: str) -> Path:
        """Скачивает файл бланка во временный каталог uploads."""
        response = self._request(file_url)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        file_name = _file_name_from_url(file_url)
        saved_path = self.upload_dir / f"{uuid.uuid4().hex}_{file_name}"
        saved_path.write_bytes(response.content)
        logger.info(
            "Supplier price file downloaded",
            extra={
                "supplier": self.DEFAULT_SUPPLIER,
                "file_name": saved_path.name,
                "byte_count": len(response.content),
            },
        )
        return saved_path

    def _request(self, url: str) -> requests.Response:
        """GET с проверкой статуса. Не логирует тело ответа."""
        try:
            response = requests.get(
                url,
                timeout=HTTP_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as error:
            logger.exception(
                "Opt price request failed",
                extra={
                    "supplier": self.DEFAULT_SUPPLIER,
                    "error_type": type(error).__name__,
                    "url": redact_url(url),
                },
            )
            raise DownloadError(
                details={"url": redact_url(url)},
            ) from error
        if response.status_code != requests.codes.ok:
            logger.error(
                "Opt price request returned unexpected status",
                extra={
                    "supplier": self.DEFAULT_SUPPLIER,
                    "status_code": response.status_code,
                    "url": redact_url(url),
                },
            )
            raise DownloadError(
                details={
                    "url": redact_url(url),
                    "status_code": response.status_code,
                },
            )
        return response


def extract_blank_href(html: str) -> str:
    """
    Берёт href первой ссылки в первом списке ol.

    Args:
        html: HTML страницы blank-zakaza.

    Returns:
        Относительный или абсолютный href файла бланка.

    Raises:
        PriceProcessingError: Если список или ссылка не найдены.
    """
    soup = BeautifulSoup(html, "html.parser")
    lists = soup.find_all("ol")
    if not lists:
        raise PriceProcessingError(
            error_code="OPT_BLANK_LIST_NOT_FOUND",
            message="Opt blank page does not contain an order list",
        )
    for child in lists[0].children:
        anchor = getattr(child, "a", None)
        if anchor is None:
            continue
        href = anchor.get("href")
        if href:
            return str(href)
    raise PriceProcessingError(
        error_code="OPT_BLANK_LINK_NOT_FOUND",
        message="Opt blank page does not contain a download link",
    )


def _file_name_from_url(file_url: str) -> str:
    """Имя файла из URL, иначе opt_blank.xls."""
    path_name = Path(unquote(urlparse(file_url).path)).name
    if path_name:
        return path_name
    return DEFAULT_FILE_NAME


def get_price_loader(
    converter: Annotated[Converter, Depends(get_converter)],
) -> PriceLoader:
    """Фабрика загрузчика прайса Opt."""
    return PriceLoader(
        converter=converter,
        blank_url=settings.price.opt_blank_url,
        upload_dir=settings.app.base_dir / "uploads",
    )
