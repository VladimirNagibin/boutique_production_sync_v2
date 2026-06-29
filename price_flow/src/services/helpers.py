import zipfile

from pathlib import Path

from core.exceptions import FileAppNotFoundError, ZipExtractionError
from core.logger import logger


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
    try:
        zip_path_obj = Path(zip_path)
        logger.info(f"Начало распаковки архива: {zip_path_obj}")

        # Проверка существования файла
        _validate_file_exists(zip_path_obj)

        # Определяем директорию для распаковки
        extract_to_obj = _get_extraction_directory(zip_path_obj, extract_to)
        logger.debug(f"Директория для распаковки: {extract_to_obj}")

        # Создаем директорию, если не существует
        extract_to_obj.mkdir(parents=True, exist_ok=True)

        return _perform_extraction(zip_path_obj, extract_to_obj, password)

    # Ловим кастомные исключения приложения
    except (FileAppNotFoundError, ZipExtractionError) as e:
        logger.error(e)
        raise


def _validate_file_exists(path: Path) -> None:
    """
    Проверяет существование файла и выбрасывает исключение.
    Это позволяет сделать основной код чище и избежать абстракции raise.
    """
    if not path.exists():
        raise FileAppNotFoundError(path, f"Файл не найден: {path}")
    if not path.is_file():
        raise FileAppNotFoundError(path, f"Путь не является файлом: {path}")


def _get_extraction_directory(zip_path: Path, extract_to: str | Path | None) -> Path:
    """Определяет директорию для распаковки."""
    if extract_to:
        return Path(extract_to)
    # Распаковываем в папку с именем архива (без расширения)
    return zip_path.parent / zip_path.stem


def _perform_extraction(zip_path: Path, extract_to: Path, password: str | None) -> bool:
    """Выполняет распаковку ZIP архива."""
    try:
        # Открываем ZIP файл
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            pwd_bytes = password.encode("utf-8") if password else None

            # Пробуем распаковать
            try:
                zip_ref.extractall(extract_to, pwd=pwd_bytes)
            except RuntimeError as e:
                _handle_runtime_error(zip_path, e)
                return False
            except zipfile.BadZipFile as e:
                _handle_zip_extraction_error(zip_path, f"Ошибка при чтении архива: {e}")
                return False
            # Логируем успешную распаковку
            _log_extraction_success(extract_to, zip_ref)
            return True

    except zipfile.BadZipFile as e:
        _handle_zip_extraction_error(
            zip_path, f"Файл поврежден или не является ZIP архивом: {zip_path}: {e}"
        )
        return False


def _handle_runtime_error(zip_path: Path, error: RuntimeError) -> None:
    """Обрабатывает RuntimeError при распаковке."""
    error_msg = str(error).lower()

    if any(keyword in error_msg for keyword in ["password", "encrypted"]):
        _handle_zip_extraction_error(
            zip_path, "Архив защищен паролем или пароль неверен."
        )

    _handle_zip_extraction_error(zip_path, f"Ошибка распаковки: {error}")


def _log_extraction_success(extract_to: Path, zip_ref: zipfile.ZipFile) -> None:
    """Логирует информацию об успешной распаковке."""
    file_list = zip_ref.namelist()
    file_count = len(file_list)

    logger.info(f"Успешно распаковано в: {extract_to}")
    logger.info(f"Файлов в архиве: {file_count}")

    if file_list:
        logger.info("Содержимое архива:")

        # Показываем первые 10 файлов
        max_files_to_show = 10
        for i, filename in enumerate(file_list[:max_files_to_show], 1):
            logger.info(f"  {i:3d}. {filename}")

        # Если файлов больше, показываем только количество
        if file_count > max_files_to_show:
            remaining = file_count - max_files_to_show
            logger.info(f"  ... и еще {remaining} файлов")


def _handle_zip_extraction_error(zip_path: Path, message: str) -> bool:
    raise ZipExtractionError(zip_path, message)
