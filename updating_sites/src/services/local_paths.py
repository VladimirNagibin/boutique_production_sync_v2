"""Абсолютные пути к файлам под settings.base_dir (не cwd контейнера)."""

from pathlib import Path

from core.settings import settings


PRICES_SUBDIR = Path("data") / "prices"


def resolve_local_path(
    stored: str, base_dir: str | Path | None = None
) -> Path:
    """
    Собирает абсолютный путь к локальному файлу.

    Относительные пути считаются от settings.base_dir
    (/app/src в контейнере), а не от cwd (/app).
    """
    root = Path(base_dir if base_dir is not None else settings.base_dir)
    path = Path(stored)
    if path.is_absolute():
        return path
    joined = root / path
    if joined.exists() or path.parent != Path("."):
        return joined
    return root / PRICES_SUBDIR / path.name
