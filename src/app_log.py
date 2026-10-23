from __future__ import annotations

import logging
from datetime import date

from paths import log_path, logs_dir

_LOGGER_NAME = "pos"
_configured = False
_app_name = "pos"


class _AppNameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.app = _app_name
        return True


class _DailyFileHandler(logging.FileHandler):
    """Append to YYYYDDMM.log; reopen when the local calendar day changes."""

    def __init__(self) -> None:
        self._day = date.today()
        super().__init__(log_path(), mode="a", encoding="utf-8", delay=True)

    def emit(self, record: logging.LogRecord) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self.close()
            self.baseFilename = str(log_path())
            self.stream = self._open()
        super().emit(record)


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def setup_logging(app_name: str) -> logging.Logger:
    """Configure a daily file log shared by Config and Launcher."""
    global _configured, _app_name
    _app_name = app_name
    logger = get_logger()
    if _configured:
        return logger

    logs_dir().mkdir(parents=True, exist_ok=True)
    handler = _DailyFileHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(app)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(_AppNameFilter())

    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True

    logger.info("Logging started → %s", log_path())
    return logger


def log_exception(message: str, exc: BaseException | None = None) -> None:
    logger = get_logger()
    if exc is not None:
        logger.exception("%s: %s", message, exc)
    else:
        logger.exception("%s", message)
