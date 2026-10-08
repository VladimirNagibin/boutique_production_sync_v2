import asyncio
import os
import time
from functools import partial

import aiofiles.os as aios
import pandas as pd

from common.exceptions.file import FileAppNotFoundError
from common.exceptions.processing import ExcelProcessingError
from core.logger import get_logger
from core.settings import settings


logger = get_logger(__name__)

pd.set_option("io.excel.xls.writer", "xlwt")


async def convert_xlsx_to_xls(file_name: str) -> None:
    """
    Преобразует XLSX файл в XLS.

    Args:
        file_name: Идентификатор файла (UUID) в каталогах in/out.

    Raises:
        FileAppNotFoundError: Если входной файл отсутствует.
        ExcelProcessingError: Если чтение или запись файла не удались.
    """
    started = time.perf_counter()
    extra_base: dict[str, str | int | float] = {
        "file_id": file_name,
        "stage": "start",
    }
    logger.info("File conversion started", extra=extra_base)

    file = os.path.join(
        settings.BASE_DIR, settings.UPLOAD_DIR, "%s", file_name
    )
    input_file = file % ("in")
    output_file = file % ("out")
    if not await aios.path.exists(input_file):
        logger.error(
            "File conversion input not found",
            extra={
                "file_id": file_name,
                "stage": "input_validation",
                "duration_ms": _duration_ms(started),
            },
        )
        raise FileAppNotFoundError(path=input_file)

    input_bytes = (await aios.stat(input_file)).st_size
    loop = asyncio.get_running_loop()

    try:
        df = await loop.run_in_executor(None, pd.read_excel, input_file)
    except Exception as error:
        _log_stage_failure(file_name, "read", input_bytes, started, error)
        raise ExcelProcessingError(
            message="Failed to read XLSX file",
            details={
                "file_id": file_name,
                "error_type": type(error).__name__,
            },
        ) from error

    try:
        await loop.run_in_executor(
            None,
            partial(df.to_excel, output_file, index=False, engine="xlwt"),
        )
    except Exception as error:
        _log_stage_failure(file_name, "write", input_bytes, started, error)
        await _remove_partial_output(output_file, file_name)
        raise ExcelProcessingError(
            message="Failed to write XLS file",
            details={
                "file_id": file_name,
                "error_type": type(error).__name__,
            },
        ) from error

    output_bytes = (await aios.stat(output_file)).st_size
    logger.info(
        "File conversion completed",
        extra={
            "file_id": file_name,
            "stage": "complete",
            "duration_ms": _duration_ms(started),
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
        },
    )


def _log_stage_failure(
    file_id: str,
    stage: str,
    input_bytes: int,
    started: float,
    error: Exception,
) -> None:
    """Логирует неудачу этапа конвертации с трассировкой."""
    logger.error(
        "File conversion stage failed",
        extra={
            "file_id": file_id,
            "stage": stage,
            "error_type": type(error).__name__,
            "input_bytes": input_bytes,
            "duration_ms": _duration_ms(started),
        },
        exc_info=True,
    )


async def _remove_partial_output(output_file: str, file_id: str) -> None:
    """Удаляет частично записанный выходной файл после ошибки записи."""
    try:
        await aios.remove(output_file)
    except FileNotFoundError:
        return
    except OSError:
        logger.exception(
            "Partial output file cleanup failed",
            extra={"file_id": file_id, "path": output_file},
        )


def _duration_ms(started: float) -> float:
    """Возвращает длительность в миллисекундах от started."""
    return round((time.perf_counter() - started) * 1000, 2)
