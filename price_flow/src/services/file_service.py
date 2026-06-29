import gzip
import io
import json
import zipfile

from typing import Any

import aiofiles
import pandas as pd

from fastapi import HTTPException, UploadFile


class FileService:
    """Асинхронный сервис для упаковки/распаковки данных"""

    @staticmethod
    async def read_upload_file(file: UploadFile) -> bytes:
        """Асинхронно прочитать загруженный файл"""
        return await file.read()

    @staticmethod
    async def write_download_file(data: bytes, filename: str) -> None:
        """Асинхронно записать файл"""
        async with aiofiles.open(filename, 'wb') as f:
            await f.write(data)

    @staticmethod
    def pack_to_zip(
        data: list[dict[str, Any]], filename: str = "data"
    ) -> io.BytesIO:
        """
        Упаковывает данные в ZIP архив с JSON и CSV файлами
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Сохраняем как JSON
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            zip_file.writestr(f"{filename}.json", json_data)

            # Также сохраняем как CSV для удобства
            if data:
                df = pd.DataFrame(data)
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8')
                zip_file.writestr(f"{filename}.csv", csv_buffer.getvalue())

        zip_buffer.seek(0)
        return zip_buffer

    @staticmethod
    def pack_to_gzip(data: list[dict[str, Any]]) -> io.BytesIO:
        """
        Упаковывает данные в GZIP архив с JSON
        """
        gzip_buffer = io.BytesIO()
        json_data = json.dumps(data, ensure_ascii=False)

        with gzip.GzipFile(fileobj=gzip_buffer, mode='wb') as gz_file:
            gz_file.write(json_data.encode('utf-8'))

        gzip_buffer.seek(0)
        return gzip_buffer

    @staticmethod
    def pack_to_csv(data: list[dict[str, Any]]) -> io.BytesIO:
        """
        Упаковывает данные в CSV файл (без сжатия)
        """
        if not data:
            raise HTTPException(status_code=400, detail="Нет данных для экспорта")

        csv_buffer = io.BytesIO()
        df = pd.DataFrame(data)
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        return csv_buffer

    @staticmethod
    def pack_to_json(data: list[dict[str, Any]]) -> io.BytesIO:
        """
        Упаковывает данные в JSON файл
        """
        json_buffer = io.BytesIO()
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        json_buffer.write(json_data.encode('utf-8'))
        json_buffer.seek(0)
        return json_buffer

    @staticmethod
    def unpack_from_zip(file_content: bytes) -> list[dict[str, Any]]:
        """
        Распаковывает ZIP архив и читает JSON/CSV
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_file:
                # Ищем JSON файл
                json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                if json_files:
                    with zip_file.open(json_files[0]) as json_file:
                        return json.load(json_file)

                # Ищем CSV файл
                csv_files = [f for f in zip_file.namelist() if f.endswith('.csv')]
                if csv_files:
                    with zip_file.open(csv_files[0]) as csv_file:
                        df = pd.read_csv(csv_file)
                        return df.to_dict('records')

                raise HTTPException(
                    status_code=400,
                    detail="В архиве нет JSON или CSV файла"
                )
        except zipfile.BadZipFile as e:
            raise HTTPException(
                status_code=400, detail="Некорректный ZIP файл"
            ) from e
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail="Некорректный JSON файл"
            ) from e

    @staticmethod
    def unpack_from_gzip(file_content: bytes) -> list[dict[str, Any]]:
        """
        Распаковывает GZIP архив
        """
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(file_content), mode='rb') as gz_file:
                json_data = gz_file.read().decode('utf-8')
                return json.loads(json_data)
        except gzip.BadGzipFile as e:
            raise HTTPException(
                status_code=400, detail="Некорректный GZIP файл"
            ) from e
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail="Некорректный JSON"
            ) from e

    @staticmethod
    def unpack_from_csv(file_content: bytes) -> list[dict[str, Any]]:
        """
        Читает CSV файл
        """
        try:
            df = pd.read_csv(io.BytesIO(file_content))
            return df.to_dict('records')
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Ошибка чтения CSV: {e!s}"
            ) from e

    @staticmethod
    def unpack_from_json(file_content: bytes) -> list[dict[str, Any]]:
        """
        Читает JSON файл
        """
        try:
            return json.loads(file_content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail="Некорректный JSON файл"
            ) from e

    @staticmethod
    def detect_format_and_unpack(
        file_content: bytes, filename: str
    ) -> list[dict[str, Any]]:
        """
        Определяет формат по содержимому и имени файла и распаковывает
        """
        # По расширению файла
        if filename.endswith('.zip'):
            return FileService.unpack_from_zip(file_content)
        elif filename.endswith('.gz'):
            return FileService.unpack_from_gzip(file_content)
        elif filename.endswith('.csv'):
            return FileService.unpack_from_csv(file_content)
        elif filename.endswith('.json'):
            return FileService.unpack_from_json(file_content)

        # По magic bytes
        if file_content[:2] == b'\x1f\x8b':  # GZIP magic number
            return FileService.unpack_from_gzip(file_content)
        elif file_content[:4] == b'PK\x03\x04':  # ZIP magic number
            return FileService.unpack_from_zip(file_content)
        elif file_content[:1] == b'{' or file_content[:1] == b'[':  # JSON
            return FileService.unpack_from_json(file_content)
        else:
            # Пробуем как CSV
            return FileService.unpack_from_csv(file_content)


def get_file_service() -> FileService:
    return FileService()
