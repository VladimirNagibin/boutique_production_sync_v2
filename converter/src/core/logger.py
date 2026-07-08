"""Logging configuration for the shop list bot application."""

import logging
import logging.config

from pathlib import Path
from typing import Any

from core.settings import settings


def create_directory(path: str) -> None:
    """Create directory if it doesn't exist.

    Args:
        path: Directory path to create.
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)


# --- LOGGING CONFIGURATION ---

# Constants for better readability
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE_PATH = Path(settings.BASE_DIR) / "logs" / "app.log"

# Ensure log directory exists
create_directory(str(LOG_FILE_PATH.parent))

# Centralized logging configuration
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,  # Don't disable library loggers
    "formatters": {
        "verbose": {"format": LOG_FORMAT},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_FILE_PATH,
            "maxBytes": settings.LOGGING_FILE_MAX_BYTES,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Configuration for root logger (name "")
        # It will catch all messages if not caught by a more specific logger
        "": {
            "level": settings.LOG_LEVEL,
            # Explicitly specify which handlers to use
            "handlers": ["console", "file"],
        },
        # Configuration for specific logger 'email_worker'
        "email_worker": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console", "file"],
            # Messages won't be passed to root logger
            "propagate": False,
        },
    },
}

# Apply configuration
logging.config.dictConfig(LOGGING_CONFIG)

# Get logger instance. No more manual configuration needed.
logger = logging.getLogger("converter")
