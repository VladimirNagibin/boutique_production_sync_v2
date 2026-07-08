import asyncio
import binascii
import email
import imaplib
import os
import re

from collections.abc import Callable
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Annotated, Any, ClassVar

import pandas as pd
import requests

from bs4 import BeautifulSoup
from fastapi import Depends
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from core.exceptions.app_exceptions import (
    DriveApiError,
    EmailFetchError,
    ExcelProcessingError,
    PriceProcessingError,
    SupplierDataError,
)
from core.exceptions.base import BaseAppException
from core.exceptions.file import FileAppNotFoundError
from core.logger import logger
from core.settings import settings
from repositories.supplier_codes_repo import (
    SupplierCodesRepo,
    get_supplier_codes_repo,
)
from schemas.converter_schemas import UploadResult
from services.converter import FileUploader, get_file_uploader


class PriceLoader:
    """
    Сервис для загрузки и обработки прайс-листов.
    Поддерживает загрузку из Gmail, поиск в Google Drive и обогащение данных.
    """

    # Константы
    EMAIL_SCAN_LIMIT: ClassVar[int] = 200
    IMAP_HOST: ClassVar[str] = "imap.gmail.com"
    LINK_TRACKER_SUBSTR: ClassVar[str] = "geteml.com/ru/mail_link_tracker"
    DEFAULT_SUPPLIER_ID: ClassVar[int] = 201
    TARGET_FILENAME: ClassVar[str] = "Нал основной прайс на элитку BY"

    # Правила для автоматического заполнения
    PRODUCT_NAME_RULES: ClassVar[
        list[tuple[Callable[[str], bool], str, str]]
    ] = [
        # (условие, группа, подгруппа)
        (
            lambda name: any(
                keyword in name.lower() for keyword in ["лицензия", "***"]
            ),
            "Элит Парфюм",
            "Лицензия***",
        ),
        (
            lambda name: any(
                keyword in name.lower()
                for keyword in [
                    "vintag",
                    "винтаж",
                    "novaya zarya",
                    "косметика",
                    "новая заря",
                ]
            ),
            "NO",
            "NO",
        ),
        (
            lambda name: "montale" in name.lower()
            and "декодированный" in name.lower(),
            "NO",
            "NO",
        ),
    ]

    def __init__(
        self,
        settings: Any,
        supplier_codes_repo: SupplierCodesRepo,
        file_uploader: FileUploader,
        supplier_id: int = DEFAULT_SUPPLIER_ID,
        target_filename: str = TARGET_FILENAME,
    ):
        """
        Инициализация сервиса.

        Args:
            settings: Объект настроек приложения
            supplier_codes_repo: Репозиторий для работы с данными поставщика
            supplier_id: ID поставщика для обработки
        """
        self.settings = settings
        self.supplier_codes_repo = supplier_codes_repo
        self.file_uploader = file_uploader
        self.supplier_id = supplier_id
        self.target_filename = target_filename
        self._drive_service = None

        logger.info(
            f"Инициализирован PriceLoader для supplier_id={supplier_id}"
        )

    async def process_price(
        self,
        output_filename: str | None = None,
        # target_filename: str = (
        #     # "Нал миниатюры дезодоранты тестеры основной прайс на элитку"
        #     "Нал основной прайс на элитку KZ"
        # ),
    ) -> UploadResult:
        """
        Основной метод:
        получение ссылки -> поиск файла -> скачивание -> обработка.

        Returns:
            Path: Путь к обработанному файлу
        """
        logger.info("Начало обработки прайс-листа")
        start_time = datetime.now(UTC)
        try:
            # 1. Получение ссылки из почты
            logger.info("Поиск ссылки в почте...")
            drive_link = await self._get_latest_drive_link()
            self._validate_drive_link(drive_link)
            logger.info(
                f"Найдена ссылка на Google Drive: {drive_link[:50]}..."  # type: ignore[index]
            )

            # 2. Поиск файла в Google Drive
            logger.info(
                f"Поиск файла '{self.target_filename}' в Google Drive..."
            )
            file_id = await self._find_file_in_drive(
                drive_link,  # type: ignore[arg-type]
                self.target_filename,
            )
            self._validate_file_id(file_id, self.target_filename, drive_link)  # type: ignore[arg-type]
            logger.info(f"Найден файл с ID: {file_id}")

            # 3. Скачивание файла
            if not output_filename:
                timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                output_filename = f"price_{self.supplier_id}_{timestamp}.xlsx"

            output_path = settings.BASE_DIR / Path(
                f"uploads/{output_filename}"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Скачивание файла в: {output_path}")
            await self._download_file(file_id, output_path)  # type: ignore[arg-type]

            # 4. Получение данных поставщика
            logger.info(
                f"Загрузка данных поставщика ID={self.supplier_id}..."
            )
            supplier_data = await self._get_supplier_data_async()

            # 5. Обработка Excel файла
            logger.info("Обработка Excel файла...")
            enriched_file_path = await self._process_excel_file(
                output_path, supplier_data
            )

            # 6. Конвертация
            logger.info("Конвертация Excel файла...")
            upload_result = self.file_uploader.upload_file(enriched_file_path)

            # 7. Статистика
            processing_time = (datetime.now(UTC) - start_time).total_seconds()
            logger.info(
                f"Обработка завершена за {processing_time:.2f} секунд. "
                f"Результат: {enriched_file_path}"
            )
        except BaseAppException:
            raise
        except Exception as e:
            logger.error(f"Ошибка при обработке прайса: {e}")
            # Оборачиваем неизвестные исключения
            raise PriceProcessingError(
                error_code="PRICE_PROCESSING_ERROR",
                message="Неизвестная ошибка при обработке прайса",
                details=str(e),
            ) from e
        else:
            return upload_result
        finally:
            # await self._cleanup_temp_files(
            #     [output_path, enriched_file_path]
            # )
            await self._cleanup_temp_files([enriched_file_path])

    async def _get_latest_drive_link(self) -> str | None:
        """
        Получает ссылку на папку Google Drive из последнего письма.

        Returns:
            str: Ссылка на Google Drive или None если не найдена
        """
        try:
            link = await asyncio.to_thread(self._fetch_link_from_email)

            if link:
                # Очистка ссылки от трекеров
                clean_link = self._clean_tracker_url(link)
                logger.debug(f"Очищенная ссылка: {clean_link[:100]}...")
                return clean_link

        except imaplib.IMAP4.error as e:
            raise EmailFetchError(
                error_code="IMAP4_ERROR",
                message="Ошибка подключения к почтовому серверу",
                details=str(e),
            ) from e
        except Exception as e:
            raise EmailFetchError(
                message="Ошибка при поиске ссылки в почте", details=str(e)
            ) from e
        else:
            return None

    def _fetch_link_from_email(self) -> str | None:
        """
        Синхронный метод поиска ссылки в почте через IMAP.
        """
        try:
            mail = imaplib.IMAP4_SSL(self.IMAP_HOST)
            mail.login(self.settings.USER_GMAIL, self.settings.PASS_GMAIL)

            mail.select("INBOX")

            # Получаем общее количество сообщений
            _, messages_data = mail.search(None, "ALL")
            if not messages_data[0]:
                logger.warning("В почтовом ящике нет сообщений")
                return None

            message_ids = messages_data[0].split()
            total_messages = len(message_ids)
            scan_limit = min(self.EMAIL_SCAN_LIMIT, total_messages)

            logger.info(
                f"Всего писем: {total_messages}. "
                f"Сканируем последние {scan_limit}."
            )

            # Ищем с конца (последние письма)
            for i in range(total_messages, total_messages - scan_limit, -1):
                message_id = message_ids[i - 1].decode()

                # Получаем заголовок письма для логирования
                # _, header_data = mail.fetch(
                #    message_id, '(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])'
                # )

                # Получаем полное письмо
                _, msg_data = mail.fetch(message_id, "(RFC822)")

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        sender = msg.get("From", "")

                        # Проверяем отправителя
                        if self.settings.SENDER_PRICE_LANSETI in sender:
                            logger.debug(
                                "Найдено письмо от искомого отправителя: "
                                f"{sender}"
                            )

                            # Извлекаем ссылку
                            link = self._extract_link_from_email_body(msg)
                            if link:
                                logger.info(
                                    "Найдена ссылка в письме от "
                                    f"{msg.get('Date', 'unknown')}"
                                )
                                mail.close()
                                mail.logout()
                                return link
            mail.close()
            mail.logout()
            logger.warning(
                f"Ссылка не найдена в последних {scan_limit} письмах"
            )

        except Exception as e:
            logger.error(f"Ошибка при работе с почтой: {e}")
            raise
        else:
            return None

    def _extract_link_from_email_body(self, msg: Message) -> str | None:
        """
        Извлекает ссылку из тела email.

        Args:
            msg: Объект email сообщения

        Returns:
            str: Найденная ссылка или None
        """
        try:
            body = self._get_email_body(msg)
            if not body:
                return None

            soup = BeautifulSoup(body, "html.parser")

            # Ищем все ссылки содержащие трекер
            links = [
                a["href"]
                for a in soup.find_all("a", href=True)
                if self.LINK_TRACKER_SUBSTR in a["href"]
            ]

            if links:
                logger.debug(f"Найдено {len(links)} ссылок с трекером")
                return links[0]  # type: ignore

            # Дополнительный поиск ссылок на Google Drive
            drive_links = [
                a["href"]
                for a in soup.find_all("a", href=True)
                if "drive.google.com" in a["href"]
            ]

            if drive_links:
                logger.debug(
                    f"Найдено {len(drive_links)} прямых ссылок на "
                    "Google Drive"
                )
                return drive_links[0]  # type: ignore

        except (AttributeError, KeyError, TypeError, ValueError) as e:
            # Ошибки парсинга HTML или доступа к атрибутам
            logger.warning(
                "Ошибка парсинга HTML при извлечении ссылки: "
                f"{type(e).__name__}: {e}"
            )
            return None
        # except Exception as e:
        #     # Ловим только неизвестные исключения и логируем, но не прячем
        #     logger.error(
        #         f"Неожиданная ошибка при извлечении ссылки из письма: "
        #         f"{type(e).__name__}: {e}"
        #     )
        #     # Можно рейзить дальше или вернуть None в зависимости от
        #     # требований
        #     return None
        return None

    def _get_email_body(self, msg: Message) -> str | None:
        """Получает текстовое тело email сообщения."""
        # body_payload = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Пропускаем вложения
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/html":
                    try:
                        body_payload = part.get_payload(decode=True)
                        if body_payload and isinstance(body_payload, bytes):
                            return body_payload.decode(
                                "utf-8", errors="ignore"
                            )
                        elif body_payload and isinstance(body_payload, str):
                            # Если уже строка, просто возвращаем
                            return body_payload
                    except UnicodeDecodeError:
                        # Логируем ошибку декодирования и идем к следующей
                        # части
                        logger.debug(
                            "Не удалось декодировать HTML часть как UTF-8"
                        )
                        continue
                    except (AttributeError, TypeError, ValueError) as e:
                        # Если payload пустой или имеет неожиданный тип
                        # (например, None)
                        logger.debug(
                            "Ошибка структуры payload при чтении тела "
                            f"письма: {e}"
                        )
                        continue
                    # except Exception as e:
                    #     logger.warning(
                    #         "Неожиданная ошибка при обработке части "
                    #         f"письма: {type(e).__name__}: {e}"
                    #     )
                    #     continue
        else:
            try:
                body_payload = msg.get_payload(decode=True)
                if body_payload and isinstance(body_payload, bytes):
                    return body_payload.decode("utf-8", errors="ignore")
                elif body_payload and isinstance(body_payload, str):
                    # Если уже строка, просто возвращаем
                    return body_payload
            except (
                UnicodeDecodeError,
                LookupError,
                TypeError,
                ValueError,
            ) as e:
                logger.warning(
                    f"Ошибка декодирования тела письма: "
                    f"{type(e).__name__}: {e}"
                )
                return None
            # except Exception as e:
            #     logger.error(
            #         f"Критическая ошибка при получении тела письма: "
            #         f"{type(e).__name__}: {e}",
            #         exc_info=True
            #     )
            #     return None
        return None

    def _clean_tracker_url(self, url: str) -> str:
        """
        Очищает URL от email трекеров.

        Args:
            url: URL с трекером

        Returns:
            str: Очищенный URL
        """
        try:
            if "geteml.com" in url or "mail_link_tracker" in url:
                # Пробуем извлечь оригинальный URL из параметров
                match = re.search(r"url=([^&]+)", url)
                if match:
                    import base64

                    encoded_url = match.group(1)
                    try:
                        decoded = base64.b64decode(encoded_url).decode(
                            "utf-8"
                        )
                        logger.debug(f"Декодирован URL из трекера: {url}")
                    except (binascii.Error, UnicodeDecodeError) as e:
                        logger.debug(
                            f"Ошибка при декодировании URL из трекера: {e}, "
                            f"URL: {url}"
                        )
                    else:
                        return decoded
        except (AttributeError, ValueError, KeyError, IndexError) as e:
            logger.warning(f"Не удалось очистить URL от трекера: {e}")
            return url
        else:
            return url

    def _validate_drive_link(self, drive_link: str | None) -> None:
        if not drive_link:
            raise EmailFetchError(
                error_code="DRIVE_LINK_NOT_FOUND",
                message="Ссылка на папку Google Drive не найдена в почте",
                details="Проверьте наличие писем от отправителя прайсов",
            )

    async def _find_file_in_drive(
        self, folder_link: str, filename: str
    ) -> str | None:
        """
        Ищет файл в папке Google Drive.

        Args:
            folder_link: Ссылка на папку Google Drive
            filename: Имя искомого файла

        Returns:
            str: ID файла или None если не найден
        """
        try:
            return await asyncio.to_thread(
                self._find_file_in_drive_sync, folder_link, filename
            )

        except HttpError as e:
            if e.resp.status == 429:
                raise DriveApiError(
                    error_code="DRIVE_001",
                    message="Превышен лимит запросов к Google Drive API",
                    details=(
                        "Попробуйте позже или увеличьте интервалы между "
                        "запросами"
                    ),
                ) from e
            raise DriveApiError(
                error_code="DRIVE_002",
                message="Ошибка при работе с Google Drive API",
                details=str(e),
            ) from e
        except Exception as e:
            raise DriveApiError(
                error_code="DRIVE_003",
                message="Ошибка при поиске файла в Google Drive",
                details=str(e),
            ) from e

    def _find_file_in_drive_sync(
        self, folder_link: str, filename: str
    ) -> str | None:
        """
        Синхронный метод поиска файла в Google Drive.
        """
        try:
            # First variant:
            # response = requests.head(link, allow_redirects=True)
            # response.raise_for_status()
            # final_url = response.url
            # Извлекаем ID папки из URL
            # folder_id = final_url.split('/')[-1].split('?')[0]

            folder_id = self._extract_folder_id(folder_link)
            if not folder_id:
                logger.error(
                    f"Не удалось извлечь ID папки из ссылки: {folder_link}"
                )
                return None

            logger.debug(f"Ищем файл '{filename}' в папке ID: {folder_id}")

            # Создаем сервис Google Drive
            service = build(
                "drive",
                "v3",
                developerKey=self.settings.API_KEY_GOOGLE,
                cache_discovery=False,
            )

            # Ищем файлы в папке
            query = f"'{folder_id}' in parents and trashed = false"
            results = (
                service.files()
                .list(
                    q=query,
                    pageSize=100,
                    fields="files(id, name, mimeType)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            files = results.get("files", [])
            logger.debug(f"Найдено {len(files)} файлов в папке")

            # Ищем файл по имени (частичное совпадение)
            filename_lower = filename.lower()
            for file in files:
                if filename_lower in file["name"].lower():
                    logger.info(
                        f"Найден файл: {file['name']} (ID: {file['id']})"
                    )
                    return file["id"]  # type: ignore[no-any-return]

            # Если точное совпадение не найдено, логируем список файлов
            logger.warning(f"Файл '{filename}' не найден. Доступные файлы:")
            for file in files:
                logger.warning(f"  - {file['name']}")
        except Exception as e:
            logger.error(f"Ошибка при поиске файла в Google Drive: {e}")
            raise
        else:
            return None

    def _extract_folder_id(self, url: str) -> str | None:
        """
        Извлекает ID папки из URL Google Drive.

        Args:
            url: URL папки Google Drive

        Returns:
            str: ID папки или None
        """
        patterns = [
            r"/folders/([a-zA-Z0-9_-]+)",
            r"id=([a-zA-Z0-9_-]+)",
            r"/drive/folders/([a-zA-Z0-9_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                folder_id = match.group(1)
                # Удаляем возможные дополнительные параметры
                if "?" in folder_id:
                    folder_id = folder_id.split("?")[0]
                return folder_id

        # Если паттерны не сработали, берем последнюю часть URL
        parts = url.strip("/").split("/")
        if parts:
            last_part = parts[-1]
            if "?" in last_part:
                last_part = last_part.split("?")[0]
            return last_part

        return None

    def _validate_file_id(
        self, file_id: str | None, target_filename: str, drive_link: str
    ) -> None:
        if not file_id:
            raise FileAppNotFoundError(
                error_code="GOOGLE_DRIVE_FILE_NOT_FOUND_ERROR",
                message=f"Файл '{target_filename}' не найден в папке",
                path=drive_link,
            )

    async def _download_file(self, file_id: str, output_path: Path) -> None:
        """
        Скачивает файл с Google Drive.

        Args:
            file_id: ID файла в Google Drive
            output_path: Путь для сохранения файла
        """
        try:
            await asyncio.to_thread(
                self._download_file_sync, file_id, output_path
            )
            logger.info(f"Файл успешно скачан: {output_path}")

        except Exception as e:
            raise DriveApiError(
                error_code="DOWNLOAD_GOOGLE_DRIVE_ERROR",
                message="Ошибка при скачивании файла",
                details=str(e),
            ) from e

    def _download_file_sync(self, file_id: str, output_path: Path) -> None:
        """
        Синхронный метод скачивания файла.
        """
        download_url = (
            f"https://drive.google.com/uc?id={file_id}&export=download"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        }

        try:
            response = requests.get(
                download_url, headers=headers, stream=True, timeout=30
            )
            response.raise_for_status()

            # Проверяем размер файла
            total_size = int(response.headers.get("content-length", 0))

            with Path.open(output_path, "wb") as file:
                if total_size == 0:
                    file.write(response.content)
                else:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
                            downloaded += len(chunk)

            # Проверяем, что файл скачан
            if output_path.exists() and output_path.stat().st_size > 0:
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                logger.info(
                    f"Файл скачан успешно. Размер: {file_size_mb:.2f} MB"
                )
            else:
                raise DriveApiError(
                    error_code="FILE_EMPTY_OR_NOT_FOUND",
                    message="Скачанный файл пуст или не существует",
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при скачивании файла: {e}")
            raise

    async def _get_supplier_data_async(self) -> pd.DataFrame:
        """
        Асинхронно получает данные поставщика.

        Returns:
            DataFrame с данными поставщика
        """
        try:
            supplier_data = await asyncio.to_thread(
                self.supplier_codes_repo.get_supplier_data, self.supplier_id
            )

            self._validate_supplier_data(supplier_data)

            # Обработка данных
            supplier_data["code"] = (
                supplier_data["code"].astype(str).str.strip()
            )
            logger.info(f"Загружено {len(supplier_data)} записей поставщика")

        except SupplierDataError:
            raise
        except Exception as e:
            raise SupplierDataError(
                message="Ошибка при получении данных поставщика",
                details=str(e),
            ) from e
        else:
            return supplier_data

    def _validate_supplier_data(self, supplier_data: pd.DataFrame) -> None:
        if supplier_data.empty:
            raise SupplierDataError(
                error_code="EMPTY_SUPPLIER_DATA",
                message=f"Нет данных для поставщика ID={self.supplier_id}",
                details="Проверьте наличие записей в базе данных",
            )

    async def _process_excel_file(
        self, file_path: Path, supplier_data: pd.DataFrame
    ) -> Path:
        """
        Обрабатывает Excel файл: чтение, объединение, обогащение данных.

        Args:
            file_path: Путь к Excel файлу
            supplier_data: DataFrame с данными поставщика

        Returns:
            Path: Путь к обработанному файлу
        """
        try:
            # 1. Чтение Excel файла
            logger.info(f"Чтение Excel файла: {file_path}")
            excel_df, header_row = await asyncio.to_thread(
                self._read_excel_with_header, file_path
            )

            logger.info(
                f"Загружено {len(excel_df)} строк. "
                f"Заголовок в строке: {header_row + 1}"
            )

            # 2. Объединение данных
            logger.info("Объединение данных Excel с данными поставщика...")
            merged_df = await asyncio.to_thread(
                self._merge_with_supplier_data, excel_df, supplier_data
            )

            # 3. Заполнение пропусков
            logger.info("Заполнение пропущенных данных...")
            filled_df = await asyncio.to_thread(
                self._fill_missing_data, merged_df
            )

            # 4. Применение правил обработки
            logger.info("Применение правил обработки...")
            processed_df = await asyncio.to_thread(
                self._apply_processing_rules, filled_df
            )

            # 5. Сохранение результата
            output_file = self._generate_output_filename(file_path)
            logger.info(f"Сохранение результата в: {output_file}")

            await asyncio.to_thread(
                self._save_to_excel_with_formatting,
                file_path,
                output_file,
                processed_df,
                header_row,
            )

            # 6. Логирование статистики
            self._log_processing_statistics(processed_df)

        except Exception as e:
            raise ExcelProcessingError(
                message="Ошибка при обработке Excel файла", details=str(e)
            ) from e
        else:
            return output_file

    def _read_excel_with_header(
        self, file_path: Path
    ) -> tuple[pd.DataFrame, int]:
        """
        Читает Excel файл, автоматически определяя строку с заголовками.

        Returns:
            Tuple[DataFrame, int]: DataFrame и номер строки заголовка
        """
        try:
            # Читаем первые строки для анализа
            preview_df = pd.read_excel(file_path, header=None, nrows=20)

            # Ищем строку с заголовком "Код"
            header_row = None
            for i in range(len(preview_df)):
                if "Код" in preview_df.iloc[i].astype(str).values:
                    header_row = i
                    logger.debug(f"Найден заголовок в строке {i}")
                    break

            self._validate_header_row(header_row)

            # Читаем с правильным заголовком
            df = pd.read_excel(file_path, header=header_row)

            # Стандартизация названий колонок
            column_mapping = self._standardize_column_names(df.columns)
            df = df.rename(columns=column_mapping)

            # Проверяем обязательные колонки
            required_columns = ["Код", "Наименование", "Цена"]
            missing_columns = [
                col for col in required_columns if col not in df.columns
            ]

            self._validate_missing_columns(missing_columns, df)

            # Очистка данных
            df["Код"] = df["Код"].astype(str).str.strip()

        except BaseAppException:
            raise

        except Exception as e:
            logger.error(f"Ошибка при чтении Excel: {e}")
            raise ExcelProcessingError(
                message="Ошибка при чтении Excel файла", details=str(e)
            ) from e
        else:
            return df, header_row  # type: ignore[return-value]

    def _validate_header_row(self, header_row: int | None) -> None:
        if header_row is None:
            raise ExcelProcessingError(
                error_code="HEAD_NOT_FOUND",
                message="Не найдена строка с заголовком 'Код'",
                details="Проверьте формат файла",
            )

    def _validate_missing_columns(
        self, missing_columns: list[str], df: pd.DataFrame
    ) -> None:
        if missing_columns:
            raise ExcelProcessingError(
                error_code="EXCEL_MISSING_COLUMS",
                message=(
                    f"Отсутствуют обязательные колонки: {missing_columns}"
                ),
                details=f"Доступные колонки: {list(df.columns)}",
            )

    def _standardize_column_names(self, columns: pd.Index) -> dict[str, str]:
        """
        Стандартизирует названия колонок.

        Args:
            columns: Исходные названия колонок

        Returns:
            Dict: Словарь для переименования
        """
        mapping: dict[str, str] = {}

        for col in columns:
            col_str = str(col).lower()

            if "код" in col_str:
                mapping[col] = "Код"
            elif "наимен" in col_str or "name" in col_str:
                mapping[col] = "Наименование"
            elif "цена" in col_str or "price" in col_str:
                mapping[col] = "Цена"
            elif "заказ" in col_str or "order" in col_str:
                mapping[col] = "заказ"
            elif "сумм" in col_str or "sum" in col_str:
                mapping[col] = "Сумма"
            else:
                mapping[col] = col  # Оставляем как есть

        return mapping

    def _merge_with_supplier_data(
        self, excel_df: pd.DataFrame, supplier_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Объединяет данные Excel с данными поставщика.

        Returns:
            DataFrame: Объединенные данные
        """
        try:
            merged_df = pd.merge(
                excel_df,
                supplier_data[["code", "category", "subcategory"]],
                left_on="Код",
                right_on="code",
                how="left",
            )

            # Удаляем вспомогательную колонку
            merged_df = merged_df.drop(columns=["code"])

            # Статистика совпадений
            matches = merged_df["category"].notna().sum()
            match_percentage = (matches / len(merged_df)) * 100

            logger.info(
                f"Совпадений найдено: {matches}/{len(merged_df)} "
                f"({match_percentage:.1f}%)"
            )

        except Exception as e:
            raise PriceProcessingError(
                error_code="MERGE_SUPPLIER_DATA_WITH_EXCEL_ERROR",
                message="Ошибка при объединении данных",
                details=str(e),
            ) from e
        else:
            return merged_df

    def _fill_missing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Заполняет пропущенные значения различными методами.

        Returns:
            DataFrame: Данные с заполненными пропусками
        """
        result_df = df.copy()

        # Добавляем колонки для отслеживания заполнения
        result_df["_filled_by_rule"] = False
        result_df["_filled_by_neighbors"] = False

        # 1. Заполнение на основе соседних строк
        # result_df = self._fill_by_neighbors(result_df)
        result_df = self._fill_missing_from_neighbors(result_df)

        # 2. Заполнение на основе наименования товара
        result_df = self._fill_by_product_name(result_df)

        return result_df

    def _fill_by_product_name(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Заполняет пропуски на основе наименования товара.
        """
        result_df = df.copy()

        for idx, row in result_df.iterrows():
            product_name = row.get("Наименование", "")

            if pd.notna(product_name):
                for condition, group, subgroup in self.PRODUCT_NAME_RULES:
                    if condition(product_name):
                        result_df.at[idx, "category"] = group
                        result_df.at[idx, "subcategory"] = subgroup
                        result_df.at[idx, "_filled_by_rule"] = True
                        break

        return result_df

    def _fill_from_product_name(self, df: pd.DataFrame) -> pd.DataFrame:
        def _update_row(row: pd.Series) -> pd.Series:
            name = row["Наименование"]
            if any(
                keyword in name.lower() for keyword in ["лицензия", "***"]
            ):
                row["category"] = "Элит Парфюм"
                row["subcategory"] = "Лицензия***"
            elif any(
                keyword in name.lower()
                for keyword in [
                    "vintag",
                    "винтаж",
                    "novaya zarya",
                    "косметика",
                ]
            ) or ("MONTALE" in name and "декодированный" in name):
                row["category"] = "NO"
                row["subcategory"] = "NO"
            return row

        return df.apply(_update_row, axis=1)

    def _fill_by_neighbors(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Заполняет пропуски на основе значений в соседних строках.
        Улучшенная версия: заполняет только если все строки в блоке одинаковы.
        """
        result_df = df.copy()

        # Векторизованный подход для производительности
        forward_filled = result_df[["category", "subcategory"]].ffill()
        backward_filled = result_df[["category", "subcategory"]].bfill()

        # Маска строк, где значения вперед и назад совпадают
        mask = (
            (forward_filled["category"] == backward_filled["category"])
            & (
                forward_filled["subcategory"]
                == backward_filled["subcategory"]
            )
            & (result_df["category"].isna() | result_df["subcategory"].isna())
        )

        # Заполняем совпадающие строки
        result_df.loc[mask, "category"] = forward_filled.loc[mask, "category"]
        result_df.loc[mask, "subcategory"] = forward_filled.loc[
            mask, "subcategory"
        ]
        result_df.loc[mask, "_filled_by_neighbors"] = True

        filled_count = mask.sum()
        if filled_count > 0:
            logger.info(
                f"Заполнено {filled_count} строк на основе соседних значений"
            )

        return result_df

    def _fill_missing_from_neighbors(
        self,
        df: pd.DataFrame,
        group_col: str = "category",
        subgroup_col: str = "subcategory",
    ) -> pd.DataFrame:
        """
        Заполняет пропущенные значения на основе совпадающих значений выше и
        ниже. Помечает строки, которые были заполнены.

        Args:
            df: Исходный DataFrame
            group_col: Название колонки с группой товаров
            subgroup_col: Название колонки с подгруппой

        Returns:
            DataFrame с заполненными значениями и пометками
        """
        # Создаем копию чтобы не изменять оригинал
        result_df = df.copy()

        # Создаем колонки для пометок
        # result_df['_group_filled'] = False
        # result_df['_subgroup_filled'] = False
        # result_df['_filled_from_neighbors'] = False
        #'_filled_by_neighbors'

        # Проходим по всем строкам
        for i in range(len(result_df)):
            # Проверяем, что текущая строка имеет пропуски
            current_group = result_df.at[i, group_col]
            current_subgroup = result_df.at[i, subgroup_col]

            if pd.isna(current_group) or pd.isna(current_subgroup):
                # Ищем ближайшие заполненные строки выше
                upper_group = None
                upper_subgroup = None
                for j in range(i - 1, -1, -1):
                    if not pd.isna(
                        result_df.at[j, group_col]
                    ) and not pd.isna(result_df.at[j, subgroup_col]):
                        upper_group = result_df.at[j, group_col]
                        upper_subgroup = result_df.at[j, subgroup_col]
                        break

                # Ищем ближайшие заполненные строки ниже
                lower_group = None
                lower_subgroup = None
                for j in range(i + 1, len(result_df)):
                    if not pd.isna(
                        result_df.at[j, group_col]
                    ) and not pd.isna(result_df.at[j, subgroup_col]):
                        lower_group = result_df.at[j, group_col]
                        lower_subgroup = result_df.at[j, subgroup_col]
                        break

                # Если значения сверху и снизу совпадают и не None
                if (
                    upper_group is not None
                    and lower_group is not None
                    and upper_group == lower_group
                    and upper_subgroup == lower_subgroup
                ):
                    # Заполняем пропуски
                    if pd.isna(current_group):
                        result_df.at[i, group_col] = upper_group
                        result_df.at[i, "_filled_by_neighbors"] = True
                        # result_df.at[i, '_group_filled'] = True

                    if pd.isna(current_subgroup):
                        result_df.at[i, subgroup_col] = upper_subgroup
                        result_df.at[i, "_filled_by_neighbors"] = True
                        # result_df.at[i, '_subgroup_filled'] = True

                    # Помечаем строку как заполненную
                    # if (
                    #     result_df.at[i, '_group_filled'] or
                    #     result_df.at[i, '_subgroup_filled']
                    # ):
                    #     result_df.at[i, '_filled_by_neighbors'] = True

        return result_df

    def _apply_processing_rules(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Применяет финальные правила обработки к данным.
        """
        result_df = df.copy()

        # Удаляем временные колонки если нужно
        if "_filled_by_rule" in result_df.columns:
            # Можно сохранить статистику перед удалением
            filled_by_rule = result_df["_filled_by_rule"].sum()
            filled_by_neighbors = result_df["_filled_by_neighbors"].sum()

            logger.debug(
                f"Заполнено правилами: {filled_by_rule}, "
                f"соседями: {filled_by_neighbors}"
            )

            # Удаляем временные колонки
            result_df = result_df.drop(
                columns=["_filled_by_rule", "_filled_by_neighbors"]
            )

        return result_df

    def _generate_output_filename(self, input_path: Path) -> Path:
        """
        Генерирует имя для выходного файла.

        Args:
            input_path: Путь к исходному файлу

        Returns:
            Path: Путь для сохранения результата
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        input_stem = input_path.stem

        output_name = f"{input_stem}_enriched_{timestamp}.xlsx"
        output_path = input_path.parent / output_name

        return output_path

    def _save_to_excel_with_formatting(
        self,
        original_file: Path,
        output_file: Path,
        df: pd.DataFrame,
        header_row: int,
    ) -> None:
        """
        Сохраняет DataFrame в Excel с сохранением форматирования оригинала.
        """
        try:
            # Загружаем оригинальную книгу
            wb = load_workbook(original_file)
            ws = wb.active

            # Находим позицию для вставки новых колонок
            # (после колонки "Сумма" или последней существующей)
            last_column = ws.max_column

            # Вставляем 2 новые колонки
            ws.insert_cols(last_column + 1, 2)

            # Записываем заголовки новых колонок
            group_col_letter = get_column_letter(last_column + 1)
            subgroup_col_letter = get_column_letter(last_column + 2)

            ws[f"{group_col_letter}{header_row + 1}"] = "Группа товара"
            ws[f"{subgroup_col_letter}{header_row + 1}"] = "Подгруппа"

            # Записываем данные
            for idx, row in df.iterrows():
                excel_row = header_row + 2 + idx

                # Записываем группу
                group_value = row.get("category")
                if pd.notna(group_value):
                    ws[f"{group_col_letter}{excel_row}"] = group_value

                # Записываем подгруппу
                subgroup_value = row.get("subcategory")
                if pd.notna(subgroup_value):
                    ws[f"{subgroup_col_letter}{excel_row}"] = subgroup_value

            # Сохраняем
            wb.save(output_file)
            logger.info(f"Файл успешно сохранен: {output_file}")

        except Exception as e:
            logger.error(f"Ошибка при сохранении Excel файла: {e}")
            raise

    def _write_to_excel_with_formatting(
        self,
        original_file: str,
        new_file: str,
        df_merged: pd.DataFrame,
        header_row: int,
    ) -> None:
        """
        Записывает данные обратно в Excel с сохранением оригинального
        форматирования
        """

        # Загружаем оригинальную книгу
        wb = load_workbook(original_file)
        ws = wb.active

        # Определяем колонки для новых данных
        category_col = get_column_letter(
            df_merged.columns.get_loc("category") + 1
        )
        subgroup_col = get_column_letter(
            df_merged.columns.get_loc("subcategory") + 1
        )

        # Записываем заголовки новых колонок
        ws[f"{category_col}{header_row + 1}"] = "Группа товара"
        ws[f"{subgroup_col}{header_row + 1}"] = "Подгруппа"

        # Записываем данные
        for idx, row in df_merged.iterrows():
            excel_row = (
                header_row + 2 + idx
            )  # +2 потому что заголовок на header_row+1

            # Записываем category
            category = row["category"]
            if pd.notna(category):
                ws[f"{category_col}{excel_row}"] = category

            # Записываем subgroup
            subgroup = row["subcategory"]
            if pd.notna(subgroup):
                ws[f"{subgroup_col}{excel_row}"] = subgroup

        # Сохраняем в новый файл
        wb.save(new_file)
        print(f"Файл сохранен: {new_file}")

    def _log_processing_statistics(self, df: pd.DataFrame) -> None:
        """
        Логирует статистику обработки данных.

        Args:
            df: Обработанный DataFrame
        """
        try:
            total_rows = len(df)
            group_missing = df["category"].isna().sum()
            subgroup_missing = df["subcategory"].isna().sum()

            group_fill_rate = (
                (total_rows - group_missing) / total_rows
            ) * 100
            subgroup_fill_rate = (
                (total_rows - subgroup_missing) / total_rows
            ) * 100

            logger.info(
                f"Статистика обработки:\n"
                f"  Всего строк: {total_rows}\n"
                f"  Заполнено category: {total_rows - group_missing} "
                f"({group_fill_rate:.1f}%)\n"
                f"  Заполнено subcategory: {total_rows - subgroup_missing} "
                f"({subgroup_fill_rate:.1f}%)\n"
                f"  Осталось пропусков category: {group_missing}\n"
                f"  Осталось пропусков subgroup: {subgroup_missing}"
            )

        except (KeyError, AttributeError, TypeError, ZeroDivisionError) as e:
            logger.warning(f"Не удалось собрать статистику: {e}")

    async def _cleanup_temp_files(self, file_paths: list[Path]) -> None:
        """
        Асинхронно удаляет временные файлы.

        Args:
            file_paths: Список путей к файлам для удаления
        """
        for file_path in file_paths:
            if file_path and file_path.exists():
                try:
                    # Асинхронное удаление файла
                    await asyncio.to_thread(os.remove, file_path)
                    logger.debug(f"Удален временный файл: {file_path}")

                    # Попробуем удалить пустую директорию если она существует
                    # parent_dir = file_path.parent
                    # if parent_dir.exists() and parent_dir.is_dir():
                    #     try:
                    #         # Проверяем, пуста ли директория
                    #         if not any(parent_dir.iterdir()):
                    #             await asyncio.to_thread(parent_dir.rmdir)
                    #             logger.debug(
                    #                 "Удалена пустая директория: "
                    #                 f"{parent_dir}"
                    #             )
                    #     except OSError as e:
                    #         # Игнорируем ошибки удаления директории
                    #         #  (может быть не пуста)
                    #         logger.debug(
                    #             "Не удалось удалить директорию "
                    #             f"{parent_dir}: {e}"
                    #         )

                except FileNotFoundError:
                    logger.debug(f"Файл уже удален: {file_path}")
                except PermissionError as e:
                    logger.warning(
                        f"Нет прав на удаление файла {file_path}: {e}"
                    )
                except OSError as e:
                    # Ловим все OS-специфичные ошибки
                    logger.warning(
                        f"Ошибка ОС при удалении файла {file_path}: {e}"
                    )
                except RuntimeError as e:
                    # Ошибки, связанные с asyncio.to_thread
                    logger.warning(
                        "Ошибка выполнения при удалении файла "
                        f"{file_path}: {e}"
                    )


# Dependency для FastAPI
def get_price_loader(
    settings: Annotated[Any, Depends(lambda: settings)],
    supplier_codes_repo: Annotated[
        SupplierCodesRepo, Depends(get_supplier_codes_repo)
    ],
    file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
    supplier_id: int = PriceLoader.DEFAULT_SUPPLIER_ID,
) -> PriceLoader:
    """
    Dependency для получения экземпляра PriceLoader.

    Args:
        settings: Настройки приложения
        supplier_codes_repo: Репозиторий данных поставщика
        supplier_id: ID поставщика

    Returns:
        PriceLoader: Экземпляр сервиса
    """
    return PriceLoader(
        settings=settings,
        supplier_codes_repo=supplier_codes_repo,
        file_uploader=file_uploader,
        supplier_id=supplier_id,
    )
