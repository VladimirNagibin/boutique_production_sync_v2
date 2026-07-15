from pydantic import BaseModel


class ErrorMixin(BaseModel):
    error: str | None = None


class UpdTable(ErrorMixin):
    table: str
    rows: int


class UpdPortal(BaseModel):
    upd_tables: list[UpdTable]
    upd_portal: str


class EtlTable(ErrorMixin):
    tables: list[str]
    page: int | None
    upd: bool


class ExportTable(ErrorMixin):
    part: int
    result: int | None = None
    file: str | None = None


class UpdFilesDropbox(ErrorMixin):
    filename: str
    load: bool | None = None
    del_dropbox: bool | None = None
    del_lockal: bool | None = None
