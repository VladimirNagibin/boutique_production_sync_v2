import asyncio
from functools import partial
import os

import aiofiles.os as aios
import pandas as pd

from core.logger import get_logger
from core.settings import settings

logger = get_logger(__name__)


async def convert_xlsx_to_xls(file_name: str) -> None:
    """
    Преобразует XLSX файл в XLS.

    :param file_name: str.
    """
    logger.info(
        "File conversion started",
        extra={"token": file_name, "stage": "start"},
    )
    pd.set_option("io.excel.xls.writer", "xlwt")

    file = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "%s", file_name)
    input_file = file % ("in")
    output_file = file % ("out")
    if not await aios.path.exists(input_file):
        logger.error(
            "File conversion input not found",
            extra={"token": file_name, "stage": "input_validation"},
        )
        return

    loop = asyncio.get_running_loop()

    df = None
    try:
        df = await loop.run_in_executor(None, pd.read_excel, input_file)
    except Exception as error:
        logger.error(
            "File conversion read stage failed",
            extra={
                "token": file_name,
                "stage": "read",
                "error_type": type(error).__name__,
            },
        )
    if df is not None:
        try:
            await loop.run_in_executor(
                None,
                partial(df.to_excel, output_file, index=False, engine="xlwt"),
            )
        except Exception as error:
            logger.error(
                "File conversion write stage failed",
                extra={
                    "token": file_name,
                    "stage": "write",
                    "error_type": type(error).__name__,
                },
            )
        else:
            logger.info(
                "File conversion completed",
                extra={"token": file_name, "stage": "complete"},
            )
