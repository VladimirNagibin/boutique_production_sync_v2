import html

from typing import Any


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


def _generate_table_html(docs: list[dict[str, Any]]) -> str:
    """Генерирует полный HTML таблицы."""
    rows_html = "".join(_render_row(doc) for doc in docs)
    empty_row = '<tr><td colspan="4" style="text-align:center">No data found</td></tr>'

    return f"""
    <table>
        <thead>
            <tr><th>ID</th><th>Key</th><th>Value</th><th>Actions</th></tr>
        </thead>
        <tbody>
            {rows_html if rows_html else empty_row}
        </tbody>
    </table>
    """


def _generate_edit_html(doc_id: int, key: str, value: Any) -> str:
    """Генерирует HTML для редактирования."""
    return f"""
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


def _get_attention(message: str) -> str:
    return f'<div style="color:red;">{message}</div>'


def _get_row(message: str) -> str:
    return f"<tr><td colspan='4'>{message}</td></tr>"
