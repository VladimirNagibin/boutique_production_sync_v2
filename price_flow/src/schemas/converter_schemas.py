from pydantic import BaseModel


class UploadResult(BaseModel):
    """
    Модель ответа API converter.
    """

    filename: str
    token: str
    message: str
    success: bool
    error: str | None = None
