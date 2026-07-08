import asyncio
from functools import partial
import os

import aiofiles.os as aios
import pandas as pd

from core.logger import logger
from core.settings import settings


async def convert_xlsx_to_xls(file_name: str) -> None:
    """
    Преобразует XLSX файл в XLS.

    :param file_name: str.
    """
    pd.set_option("io.excel.xls.writer", "xlwt")

    file = os.path.join(settings.BASE_DIR, settings.UPLOAD_DIR, "%s", file_name)
    input_file = file % ("in")
    output_file = file % ("out")
    if not await aios.path.exists(input_file):
        logger.error(f"Файл {input_file} не найден")
        return

    loop = asyncio.get_event_loop()

    df = None
    try:
        df = await loop.run_in_executor(None, pd.read_excel, input_file)
    except Exception as e:
        logger.error(f"Файл {input_file} не прочитан. Ошибка: {e}")
    if df is not None:
        try:
            await loop.run_in_executor(
                None,
                partial(df.to_excel, output_file, index=False, engine="xlwt"),
            )
        except Exception as e:
            logger.error(f"Файл {output_file} не записан. Ошибка: {e}")
