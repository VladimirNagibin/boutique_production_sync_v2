import html

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from tinydb import TinyDB  # type: ignore[import-not-found]

from core.settings import settings


router = APIRouter(prefix="/admin/db", tags=["Admin"])

db = TinyDB(f"data/storage/{settings.tiny_db_path}")


def _render_row(doc: dict[str, Any]) -> str:
    """Вспомогательная функция для генерации HTML одной строки таблицы."""
    doc_id = doc.doc_id  # type: ignore[attr-defined]

    # ОБЯЗАТЕЛЬНО экранируем данные, чтобы кавычки не сломали HTML
    key = html.escape(str(doc.get("key", "")))
    value = html.escape(str(doc.get("value", "")))

    # Обрезаем длинные значения для отображения
    display_value = (value[:80] + "...") if len(value) > 80 else value

    return f"""
    <tr>
        <td>{doc_id}</td>
        <td><code>{key}</code></td>
        <td title="{value}">{display_value}</td>
        <td>
            <button class="btn btn-edit"
                    hx-get="/api/v1/tiny/admin/db/edit/{doc_id}/"
                    hx-target="closest tr"
                    hx-swap="outerHTML">
                Ред.
            </button>
            <button class="btn btn-del"
                    hx-delete="/api/v1/tiny/admin/db/delete/{doc_id}/"
                    hx-target="closest tr"
                    hx-swap="outerHTML"
                    onclick="return confirm('Точно удалить?')">
                Удалить
            </button>
        </td>
    </tr>
    """


@router.get("/", response_class=HTMLResponse)
async def admin_panel() -> HTMLResponse:
    """Главная страница админки"""
    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>TinyDB Admin</title>
        <script src="https://unpkg.com/htmx.org@1.9.10"></script>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #f4f4f9; }
            .container { max-width: 900px; margin: auto; }
            table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #007bff; color: white; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .btn { border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; margin-right: 5px; color: white;}
            .btn-edit { background: #ffc107; color: black; }
            .btn-edit:hover { background: #e0a800; }
            .btn-del { background: #dc3545; }
            .btn-del:hover { background: #c82333; }
            .btn-save { background: #28a745; }
            .btn-cancel { background: #6c757d; }

            /* Стили для формы добавления */
            .add-form { background: white; padding: 15px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; display: flex; gap: 10px;}
            .add-form input { padding: 8px; border: 1px solid #ccc; border-radius: 4px; flex-grow: 1;}
            .add-form button { padding: 8px 15px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;}
            .add-form button:hover { background: #0056b3; }

            /* Стили для инлайн-формы редактирования */
            .edit-form input { width: 100%; padding: 4px; box-sizing: border-box; }
            .edit-grid {
                display: grid;
                grid-template-columns: 50px 1fr 1fr auto;
                gap: 10px;
                align-items: center;
            }
            .edit-grid input {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            .edit-id {
                font-weight: bold;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Управление состоянием (TinyDB)</h2>

            <!-- Форма добавления новой записи -->
            <form class="add-form" hx-post="/api/v1/tiny/admin/db/add/" hx-target="#table-container" hx-swap="innerHTML" hx-on::after-request="this.reset()">
                <input type="text" name="key" placeholder="Ключ (например, my_state)" required>
                <input type="text" name="value" placeholder="Значение" required>
                <button type="submit">+ Добавить</button>
            </form>

            <!-- Контейнер с таблицей -->
            <div id="table-container" hx-get="/api/v1/tiny/admin/db/table/" hx-trigger="load">
                Загрузка данных...
            </div>
        </div>
    </body>
    </html>
    """
    )


@router.get("/table/", response_class=HTMLResponse)
async def get_table_data() -> HTMLResponse:
    """Возвращает всю таблицу (используется при первой загрузке и после добавления)"""
    rows_html = "".join(_render_row(doc) for doc in db.all())

    return HTMLResponse(
        content=f"""
    <table>
        <thead>
            <tr><th>ID</th><th>Key</th><th>Value</th><th>Действия</th></tr>
        </thead>
        <tbody>
            {rows_html if rows_html else '<tr><td colspan="4" style="text-align:center">Нет данных</td></tr>'}
        </tbody>
    </table>
    """
    )


@router.post("/add/")
async def add_record(request: Request) -> HTMLResponse:  # RedirectResponse:
    """Обрабатывает добавление новой записи"""
    form = await request.form()
    key = form.get("key")
    value = form.get("value")

    if key and value:
        db.insert({"key": key, "value": value})
    # Генерируем HTML таблицы заново
    rows_html = "".join(_render_row(doc) for doc in db.all())

    table_html = f"""
    <table>
        <thead>
            <tr><th>ID</th><th>Key</th><th>Value</th><th>Действия</th></tr>
        </thead>
        <tbody>
            {rows_html if rows_html else '<tr><td colspan="4" style="text-align:center">Нет данных</td></tr>'}
        </tbody>
    </table>
    """
    return HTMLResponse(content=table_html)

    # Возвращаем редирект на HTMX. Это заставит HTMX запросить таблицу заново
    # и заменить её в контейнере, а форма очистится благодаря hx-on::after-request="this.reset()"
    return RedirectResponse(url="/api/v1/tiny/admin/db/table/", status_code=303)


@router.get("/edit/{doc_id}/", response_class=HTMLResponse)
async def edit_form(doc_id: int) -> HTMLResponse:
    """Возвращает инлайн-форму для редактирования конкретной строки"""
    doc = db.get(doc_id=doc_id)
    if not doc:
        return HTMLResponse(content="<tr><td colspan='4'>Не найдено</td></tr>")

    # Обратите внимание: здесь мы НЕ экранируем значения, так как они подставляются в value="..."
    # и экранирование сломает ввод кавычек. TinyDB безопасно сохранит их как есть.
    key = str(doc.get("key", ""))
    value = str(doc.get("value", ""))

    return HTMLResponse(
        content=f"""
    <tr>
        <td colspan="4">
            <form class="edit-form" hx-post="/api/v1/tiny/admin/db/update/{doc_id}/" hx-target="closest tr" hx-swap="outerHTML">
                <div class="edit-grid">
                    <span class="edit-id">{doc_id}</span>
                    <input type="text" name="key" value="{key}" required placeholder="Ключ">
                    <input type="text" name="value" value="{value}" required placeholder="Значение">
                    <div>
                        <button type="submit" class="btn btn-save">Сохранить</button>
                        <button type="button" class="btn btn-cancel"
                                hx-get="/admin/db/row/{doc_id}/"
                                hx-target="closest tr"
                                hx-swap="outerHTML">
                            Отмена
                        </button>
                    </div>
                </div>
            </form>
        </td>
    </tr>
    """
    )


@router.get("/row/{doc_id}/", response_class=HTMLResponse)
async def get_single_row(doc_id: int) -> HTMLResponse:
    """Возвращает обычную (не редактируемую) строку. Нужна для кнопки 'Отмена'"""
    doc = db.get(doc_id=doc_id)
    if not doc:
        return HTMLResponse(content="<tr><td colspan='4'>Не найдено</td></tr>")
    return HTMLResponse(content=_render_row(doc))


@router.post("/update/{doc_id}/")
async def update_record(
    doc_id: int, request: Request
) -> HTMLResponse:  # RedirectResponse:
    """Сохраняет отредактированные данные"""
    form = await request.form()
    key = form.get("key")
    value = form.get("value")

    if key and value:
        db.update({"key": key, "value": value}, doc_ids=[doc_id])

    # Получаем обновлённый документ
    doc = db.get(doc_id=doc_id)
    if not doc:
        return HTMLResponse(content="<tr><td colspan='4'>Не найдено</td></tr>")

    # Возвращаем готовую строку
    return HTMLResponse(content=_render_row(doc))

    # Возвращаем редирект на получение одной строки (превратит форму обратно в текст)
    return RedirectResponse(url=f"/api/v1/tiny/admin/db/row/{doc_id}/", status_code=303)


@router.delete("/delete/{doc_id}/")
async def delete_record(doc_id: int) -> HTMLResponse:
    """Удаляет запись"""
    db.remove(doc_ids=[doc_id])
    return HTMLResponse(content="")
