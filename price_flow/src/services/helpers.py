import zipfile

from pathlib import Path
from typing import Final

from core.exceptions.file import FileAppNotFoundError, ZipExtractionError
from core.logger import logger


# ===== Константы =====
MAX_FILES_TO_LOG: Final[int] = 10


def extract_zip(
    zip_path: str | Path,
    extract_to: str | Path | None = None,
    password: str | None = None,
) -> bool:
    """
    Распаковывает ZIP файл

    Args:
        zip_path: Путь к ZIP файлу
        extract_to: Директория для распаковки (None = рядом с ZIP)
        password: Пароль для защищенных архивов

    Returns:
        True если распаковка успешна, False в случае ошибки

    Raises:
        ZipFileNotFoundError: Если файл не найден
        ZipExtractionError: Если произошла ошибка при распаковке
    """
    zip_path_obj = Path(zip_path)
    logger.info(
        "Starting ZIP extraction", extra={"zip_path": str(zip_path_obj)}
    )

    # Валидация входных данных
    _validate_file(zip_path_obj)

    # Определяем директорию для распаковки
    extract_to_obj = _resolve_extract_path(zip_path_obj, extract_to)
    logger.debug(
        "Extraction target", extra={"extract_to": str(extract_to_obj)}
    )

    # Создаем директорию, если не существует
    extract_to_obj.mkdir(parents=True, exist_ok=True)

    # Выполняем распаковку
    _perform_extraction(zip_path_obj, extract_to_obj, password)

    # Логируем результат
    _log_success(zip_path_obj, extract_to_obj)
    return True


# ===== Приватные вспомогательные функции =====


def _validate_file(path: Path) -> None:
    """
    Проверяет существование файла и его тип.

    Raises:
        FileAppNotFoundError: Если файл отсутствует или не является файлом.
    """
    if not path.exists():
        raise FileAppNotFoundError(path, f"Файл не найден: {path}")
    if not path.is_file():
        raise FileAppNotFoundError(path, f"Путь не является файлом: {path}")


def _resolve_extract_path(
    zip_path: Path, extract_to: str | Path | None
) -> Path:
    """
    Определяет конечную директорию для распаковки.

    Если `extract_to` не задан, создаёт папку рядом с архивом с именем архива
    (без расширения).
    """
    if extract_to is not None:
        return Path(extract_to)
    # Распаковываем в папку с именем архива (без расширения)
    return zip_path.parent / zip_path.stem


def _perform_extraction(
    zip_path: Path, extract_to: Path, password: str | None
) -> None:
    """
    Выполняет непосредственную распаковку архива.

    Raises:
        ZipExtractionError: При любых ошибках распаковки.
    """
    try:
        # Открываем ZIP файл
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            pwd_bytes = (
                password.encode("utf-8") if password is not None else None
            )
            try:
                zip_ref.extractall(extract_to, pwd=pwd_bytes)
            except RuntimeError as e:
                _handle_runtime_error(zip_path, e)
            except zipfile.BadZipFile as e:
                _raise_extraction_error(zip_path, f"Bad ZIP file: {e}")
    except zipfile.BadZipFile as e:
        _raise_extraction_error(
            zip_path,
            f"Bad ZIP file: {e}",
        )


def _handle_runtime_error(zip_path: Path, error: RuntimeError) -> None:
    """
    Обрабатывает RuntimeError, возникающий при распаковке.
    Обычно это связано с паролем или повреждённым архивом.
    """
    error_msg = str(error).lower()

    if any(keyword in error_msg for keyword in ["password", "encrypted"]):
        _raise_extraction_error(
            zip_path, "Archive is encrypted or password is incorrect."
        )

    _raise_extraction_error(zip_path, f"Extraction error: {error}")


def _raise_extraction_error(zip_path: Path, detail: str) -> None:
    """
    Вспомогательная функция для единообразного вызова ZipExtractionError.
    """
    logger.error(
        "ZIP extraction failed",
        extra={"zip_path": str(zip_path), "detail": detail},
    )
    raise ZipExtractionError(zip_path, detail)


def _log_success(zip_path: Path, extract_to: Path) -> None:
    """
    Логирует информацию об успешной распаковке: количество файлов, список
    (первые несколько).
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            file_list = zip_ref.namelist()
            file_count = len(file_list)
            logger.info(
                "ZIP extraction successful",
                extra={
                    "extract_to": str(extract_to),
                    "file_count": file_count,
                },
            )
            if file_count:
                # Логируем первые несколько файлов для отладки
                sample = file_list[:MAX_FILES_TO_LOG]
                logger.debug(
                    "Extracted files (sample)",
                    extra={"sample": sample, "total": file_count},
                )
    except zipfile.BadZipFile as e:
        # Это крайний случай – если архив испортился после успешной распаковки
        # (маловероятно)
        logger.warning(
            "Could not read ZIP for logging after extraction",
            extra={"zip_path": str(zip_path), "error": str(e)},
        )
