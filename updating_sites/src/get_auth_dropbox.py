from core.logger import get_logger
from services.dropbox_ import get_dropbox


logger = get_logger(__name__)


if __name__ == "__main__":
    logger.info("Dropbox OAuth CLI started")
    try:
        dropbox_service = get_dropbox()
        dropbox_service.authorize()
    except Exception as error:
        logger.error(
            "Dropbox OAuth CLI failed",
            extra={"error": str(error)},
            exc_info=True,
        )
        raise
    logger.info("Dropbox OAuth CLI completed")
