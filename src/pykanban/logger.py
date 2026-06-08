"""Logging setup for PyKanban."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path.home() / ".config" / "pykanban" / "logs"
_LOG_FILE = _LOG_DIR / "main.log"

# how many backup rotations to keep (main.log, main.log.1 etc.)
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 5


def setup_logging(level: str = "DEBUG") -> None:
    """Configure the root pykanban logger.

        Call this ONCE, early in main() before any other module uses
    get_logger()

    This is a GUI app, there is no terminal output. The rotating file
    handler is the one destination for all log records. "level" constrols
    what gets writte; defaults to DEBUG so new installs capture everything
    without any config change.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR. Case-insensitive
               Defaults to DEBUG.
    """
    # make sure log dir exist
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric = logging.getLevelName(level.upper())
    # guard against typos in config
    if not isinstance(numeric, int):
        numeric = logging.DEBUG

    root = logging.getLogger("pykanban")
    # capture everything; handlers filter
    root.setLevel(numeric)

    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # safe to call setup_logging again
    root.handlers.clear()
    root.addHandler(file_handler)
    root.info(
        "Logging initialised - level=%s file=%s", level.upper(), _LOG_FILE
    )


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the pykanban hierarchy.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A logger scoped to the pykanban namespace.
    """
    # if the caller already passes "pykanban.foo", use it directly.
    # otherwise prefix so all loggers are children of the root "pykanban" logger.
    if name.startswith("pykanban"):
        return logging.getLogger(name)
    return logging.getLogger(f"pykanban.{name}")
