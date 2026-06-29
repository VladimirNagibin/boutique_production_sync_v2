import math

from typing import Annotated, Any

from fastapi import Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from repositories.clothing_codes_repo import ClothingCodesRepo, get_clothing_code_repo
from schemas.supplier_schemas import ClothingCodeCreate, ImportResult
from services.file_service import FileService, get_file_service


class ClothingCodesService:

    def __init__(
        self,
        clothing_codes_repo: ClothingCodesRepo,
        file_service: FileService,
    ) -> None:
        self.clothing_codes_repo = clothing_codes_repo
        self.file_service = file_service

    async def export_clothing_codes(
        self,
        supplier_id: int | None = None,
        packing_format: str = "zip",
    ) -> StreamingResponse:
        # Получаем данные
        items = await self.clothing_codes_repo.get_all(
            supplier_id=supplier_id, limit=200000
        )

        if not items:
            raise HTTPException(status_code=404, detail="Нет данных для экспорта")

        # Конвертируем в формат для экспорта
        export_data: list[dict[str, Any]] = []
        for item in items:
            # Убираем служебные поля
            item_copy = dict(item)
            item_copy.pop('id', None)
            export_data.append(item_copy)

        # Упаковываем в зависимости от формата
        filename = f"clothing_codes_{supplier_id or 'all'}"

        if packing_format == "zip":
            buffer = FileService.pack_to_zip(export_data, filename)
            media_type = "application/zip"
            filename_ext = f"{filename}.zip"
        elif packing_format == "gzip":
            buffer = FileService.pack_to_gzip(export_data)
            media_type = "application/gzip"
            filename_ext = f"{filename}.json.gz"
        elif packing_format == "json":
            buffer = FileService.pack_to_json(export_data)
            media_type = "application/json"
            filename_ext = f"{filename}.json"
        else:  # csv
            buffer = FileService.pack_to_csv(export_data)
            media_type = "text/csv"
            filename_ext = f"{filename}.csv"

        # Отправляем файл
        return StreamingResponse(
            buffer,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename_ext}",
                "Content-Length": str(buffer.getbuffer().nbytes)
            }
        )

    async def import_clothing_codes(
        self,
        file: UploadFile,
        strategy: str,
        supplier_id_filter: int | None,
        # background_tasks: BackgroundTasks = None,
    ) -> ImportResult:
        """
        Импортировать данные из файла

        Стратегии:
        - **upsert**: обновлять существующие, создавать новые
        - **skip**: пропускать существующие, создавать только новые
        - **replace_supplier**: удалить все записи поставщика перед импортом
        - **replace_all**: очистить всю таблицу перед импортом
        - **validate_only**: только проверить данные, не сохранять
        """
        # Читаем файл
        content = await FileService.read_upload_file(file)

        if not content:
            raise HTTPException(status_code=400, detail="Пустой файл")

        # Распаковываем
        try:
            data = FileService.detect_format_and_unpack(content, file.filename)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка распаковки: {e!s}")

        if not data:
            raise HTTPException(status_code=400, detail="Нет данных для импорта")

        cleaned_data = []
        for item in data:
            clean_item = {}
            for key, value in item.items():
                # Если значение float и это NaN, заменяем на None
                if isinstance(value, float) and math.isnan(value):
                    clean_item[key] = None
                else:
                    clean_item[key] = value
            cleaned_data.append(clean_item)

        # Заменяем исходные данные на очищенные
        data = cleaned_data

        # Фильтруем по поставщику если нужно
        if supplier_id_filter:
            data = [
                item for item in data if item.get('supplier_id') == supplier_id_filter
            ]
            if not data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Нет данных для поставщика {supplier_id_filter}"
                )

        # Валидируем все записи
        validated_items: list[ClothingCodeCreate] = []
        validation_errors: list[dict[str, Any]] = []

        for idx, item in enumerate(data):
            try:
                validated = ClothingCodeCreate(**item)
                validated_items.append(validated)
            except Exception as e:
                validation_errors.append({
                    "row": idx,
                    "data": item,
                    "error": str(e)
                })

        # Если только валидация
        if strategy == "validate_only":
            return ImportResult(
                message="Валидация завершена",
                total_records=len(data),
                created=0,
                updated=0,
                skipped=0,
                errors=validation_errors,
                errors_count=len(validation_errors)
            )

        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Ошибки валидации",
                    "errors": validation_errors
                }
            )

        # Стратегия: очистка перед импортом
        deleted_count = 0
        if strategy == "replace_all":
            deleted_count = await self.clothing_codes_repo.delete_all()
        elif strategy == "replace_supplier" and supplier_id_filter:
            deleted_count = await self.clothing_codes_repo.delete_all_by_supplier(
                supplier_id_filter
            )

        # Импортируем
        created = 0
        updated = 0
        skipped = 0
        import_errors: list[dict[str, Any]] = []

        if strategy == "upsert":
            created, updated, import_errors = await self.clothing_codes_repo.upsert_bulk(
                validated_items
            )

        elif strategy == "skip":
            for idx, item in enumerate(validated_items):
                try:
                    existing = await self.clothing_codes_repo.get_by_supplier_code(
                        item.supplier_id, item.code
                    )
                    if existing:
                        skipped += 1
                    else:
                        await self.clothing_codes_repo.create(item)
                        created += 1
                except Exception as e:
                    import_errors.append({
                        "row": idx,
                        "data": item.model_dump(),
                        "error": str(e)
                    })

        else:  # replace_supplier или replace_all
            for idx, item in enumerate(validated_items):
                try:
                    await self.clothing_codes_repo.create(item)
                    created += 1
                except Exception as e:
                    import_errors.append({
                        "row": idx,
                        "data": item.model_dump(),
                        "error": str(e)
                    })

        # # Логируем импорт в фоне
        # if background_tasks:
        #     background_tasks.add_task(
        #         self.clothing_codes_repo.log_import,
        #         file.filename,
        #         strategy,
        #         len(data),
        #         created,
        #         updated,
        #         skipped,
        #         import_errors
        #     )

        return ImportResult(
            message="Импорт завершен",
            total_records=len(data),
            created=created,
            updated=updated,
            skipped=skipped,
            errors=import_errors,
            errors_count=len(import_errors)
        )


def get_clothing_codes_service(
    clothing_codes_repo: Annotated[ClothingCodesRepo, Depends(get_clothing_code_repo)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> ClothingCodesService:
    return ClothingCodesService(clothing_codes_repo, file_service)
