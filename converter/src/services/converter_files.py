import asyncio
import os
import time
from functools import partial

import aiofiles.os as aios
import pandas as pd

from core.logger import get_logger
from core.settings import settings


logger = get_logger(__name__)

pd.set_option("io.excel.xls.writer", "xlwt")


async def convert_xlsx_to_xls(file_name: str) -> bool:
    """
    Преобразует XLSX файл в XLS.

    Args:
        file_name: Идентификатор файла (UUID) в каталогах in/out.

    Returns:
        True, если файл успешно прочитан и записан в out, иначе False.
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
        return False

    input_bytes = (await aios.stat(input_file)).st_size
    loop = asyncio.get_running_loop()

    try:
        df = await loop.run_in_executor(None, pd.read_excel, input_file)
    except Exception as error:
        logger.error(
            "File conversion read stage failed",
            extra={
                "file_id": file_name,
                "stage": "read",
                "error_type": type(error).__name__,
                "input_bytes": input_bytes,
                "duration_ms": _duration_ms(started),
            },
            exc_info=True,
        )
        return False

    try:
        await loop.run_in_executor(
            None,
            partial(df.to_excel, output_file, index=False, engine="xlwt"),
        )
    except Exception as error:
        logger.error(
            "File conversion write stage failed",
            extra={
                "file_id": file_name,
                "stage": "write",
                "error_type": type(error).__name__,
                "input_bytes": input_bytes,
                "duration_ms": _duration_ms(started),
            },
            exc_info=True,
        )
        return False

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
    return True


def _duration_ms(started: float) -> float:
    """Возвращает длительность в миллисекундах от started."""
    return round((time.perf_counter() - started) * 1000, 2)
