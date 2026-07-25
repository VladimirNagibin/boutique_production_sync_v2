"""
Административный роутер для управления TinyDB через HTMX.
"""

from __future__ import annotations

import html
import json

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from common.logger import logger
from core.settings import settings
from repositories.tinydb_repo import TinyDBRepository, get_tinydb_repo

from .helpers import (
    _generate_edit_html,
    _generate_table_html,
    _get_attention,
    _get_row,
    _render_row,
)


# ===== Константы =====
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ
TEMPLATES_DIR = f"{settings.base_dir}/templates"

router = APIRouter(prefix="/admin/db", tags=["admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ===== Публичные методы (Эндпоинты) / Public Endpoints =====


@router.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request) -> HTMLResponse:
    """Главная страница админки"""
    return templates.TemplateResponse(
        "tinydb.html",  # type: ignore[arg-type]
        {"request": request},  # type: ignore[arg-type]
    )


@router.get("/table/", response_class=HTMLResponse)
async def get_table_data(
    repo: TinyDBRepository = Depends(get_tinydb_repo),
) -> HTMLResponse:
    """Возвращает всю таблицу (используется при первой загрузке и после добавления)"""
    docs = await repo.get_all()
    return HTMLResponse(content=_generate_table_html(docs))


@router.post("/add/")
async def add_record(
    request: Request, repo: TinyDBRepository = Depends(get_tinydb_repo)
) -> HTMLResponse:
    """Обрабатывает добавление новой записи"""
    try:
        form = await request.form()
        key = str(form.get("key", "")).strip()
        value = str(form.get("value", "")).strip()

        if not key or not value:
            raise ValueError("Key and value are required")

        await repo.insert(key, value)
        logger.info("Record added successfully", extra={"key": key})

    except Exception as e:
        logger.error("Failed to add record", extra={"error": str(e)}, exc_info=True)
        return HTMLResponse(
            content=_get_attention(f"Error: {html.escape(str(e))}"),
            status_code=400,
        )

    docs = await repo.get_all()
    return HTMLResponse(content=_generate_table_html(docs))


@router.get("/edit/{doc_id}/", response_class=HTMLResponse)
async def edit_form(
    doc_id: int, repo: TinyDBRepository = Depends(get_tinydb_repo)
) -> HTMLResponse:
    """Возвращает инлайн-форму для редактирования конкретной строки"""
    doc = await repo.get_by_id(doc_id)
    if not doc:
        return HTMLResponse(content=_get_row("Не найдено"))

    # Обратите внимание: здесь мы НЕ экранируем значения, так как они подставляются в value="..."
    # и экранирование сломает ввод кавычек. TinyDB безопасно сохранит их как есть.
    key = str(doc.get("key", ""))
    value = str(doc.get("value", ""))

    return HTMLResponse(content=_generate_edit_html(doc_id, key, value))


@router.get("/row/{doc_id}/", response_class=HTMLResponse)
async def get_single_row(
    doc_id: int, repo: TinyDBRepository = Depends(get_tinydb_repo)
) -> HTMLResponse:
    """Возвращает обычную (не редактируемую) строку. Нужна для кнопки 'Отмена'"""
    doc = await repo.get_by_id(doc_id)
    if not doc:
        return HTMLResponse(content=_get_row("Не найдено"))
    return HTMLResponse(content=_render_row(doc))


@router.post("/update/{doc_id}/")
async def update_record(
    doc_id: int,
    request: Request,
    repo: TinyDBRepository = Depends(get_tinydb_repo),
) -> HTMLResponse:  # RedirectResponse:
    """Сохраняет отредактированные данные"""
    try:
        form = await request.form()
        key = str(form.get("key", "")).strip()
        value = str(form.get("value", "")).strip()

        if not key or not value:
            raise ValueError("Key and value are required")

        success = await repo.update(doc_id, key, value)
        if not success:
            raise ValueError("Record not found or not updated")

        logger.info("Record updated successfully", extra={"doc_id": doc_id})

    except Exception as e:
        logger.error(
            "Failed to update record",
            extra={"error": str(e), "doc_id": doc_id},
            exc_info=True,
        )
        return HTMLResponse(
            content=_get_attention(f"Error: {html.escape(str(e))}"),
            status_code=400,
        )

    doc = await repo.get_by_id(doc_id)
    if not doc:
        return HTMLResponse(content=_get_row("Record not found"))

    return HTMLResponse(content=_render_row(doc))


@router.delete("/delete/{doc_id}/")
async def delete_record(
    doc_id: int, repo: TinyDBRepository = Depends(get_tinydb_repo)
) -> HTMLResponse:
    """Удаляет запись"""
    try:
        await repo.remove(doc_id)
        logger.info("Record deleted successfully", extra={"doc_id": doc_id})
    except Exception as e:
        logger.error(
            "Failed to delete record",
            extra={"error": str(e), "doc_id": doc_id},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")

    return HTMLResponse(content="")


@router.get("/export/")
async def export_data(
    repo: TinyDBRepository = Depends(get_tinydb_repo),
) -> FileResponse:
    """Экспортирует все данные в JSON-файл"""
    try:
        docs = await repo.get_all()
        export_data = [{"doc_id": doc.get("doc_id"), **doc} for doc in docs]

        temp_file = "data/storage/tinydb_export.json"

        # Асинхронная запись файла для соблюдения strict async
        async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(export_data, ensure_ascii=False, indent=2))

        logger.info("Data exported successfully", extra={"file": temp_file})

        return FileResponse(
            temp_file,
            media_type="application/json",
            filename="tinydb_export.json",
        )
    except Exception as e:
        logger.error("Export failed", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")


@router.post("/import/")
async def import_data(
    file: UploadFile = File(...),
    repo: TinyDBRepository = Depends(get_tinydb_repo),
) -> HTMLResponse:
    """Импортирует данные из JSON-файла (полная замена)"""
    # Проверяем расширение и тип
    if not file.filename or not file.filename.endswith(".json"):
        logger.warning("Invalid file type uploaded", extra={"file_name": file.filename})
        return HTMLResponse(
            content=_get_attention("Error: JSON file required"),
            status_code=400,
        )

    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            logger.warning(
                "Import rejected: file too large", extra={"size": len(content)}
            )
            return HTMLResponse(
                content=(
                    _get_attention(
                        "Файл слишком большой "
                        f"(макс. {MAX_FILE_SIZE // (1024 * 1024)} МБ)"
                    )
                ),
                status_code=413,
            )
        data = json.loads(content.decode("utf-8"))

        if not isinstance(data, list):
            raise ValueError("Data must be a list of objects")

        # Строгая валидация схемы перед очисткой БД
        for item in data:
            if not isinstance(item, dict) or "key" not in item or "value" not in item:
                raise ValueError("Each item must contain 'key' and 'value'")

        # Очистка и вставка
        await repo.truncate()

        for item in data:
            await repo.insert(str(item["key"]), str(item["value"]))

        logger.info(
            "Data imported successfully",
            extra={"file_name": file.filename, "count": len(data)},
        )

        docs = await repo.get_all()
        return HTMLResponse(content=_generate_table_html(docs))

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON format", extra={"error": str(e)})
        return HTMLResponse(
            content=_get_attention("Error: Invalid JSON format"),
            status_code=400,
        )
    except ValueError as e:
        logger.error("Validation error during import", extra={"error": str(e)})
        return HTMLResponse(
            content=_get_attention(f"Error: {html.escape(str(e))}"),
            status_code=400,
        )
    except Exception as e:
        logger.error("Import failed", extra={"error": str(e)}, exc_info=True)
        return HTMLResponse(
            content=_get_attention("Internal server error during import"),
            status_code=500,
        )
