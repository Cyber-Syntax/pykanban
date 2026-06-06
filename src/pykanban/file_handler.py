"""File I/O utilities for atomic writes."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pykanban.exceptions import WriteError
from pykanban.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


def atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically.

    Writes to a sibling ".tmp" file first, calls "fsync" to flush
    kernel buffers to disk, then uses "Path.replace" (eqivalent to os.replace on POSIX)
    for an atomic rename. The temp file is cleaned up on failure so no partial
    writes are left behind.

    Args:
        path: Final destination path. Parent dirs are created auto if they don't exist.
        content: utf-8 text content to write.

    Raises:
        WriteError: Wraps any OSError that occurs during the write or rename step.
    """
    logger.debug(
        "atomic_write: path=%s, content_size=%s",
        path,
        len(content),
    )
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "atomic_write: created parent dir: path=%s",
            tmp_path.parent,
        )

        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            logger.debug(
                "atomic_write: wrote content to tmp file: path=%s",
                tmp_path,
            )
            # fsync ensures the data survives a power loss before the rename
            os.fsync(f.fileno())

        # Path.replace() is the pathlib eqivalent of os.replace
        tmp_path.replace(path)
        logger.debug(
            "atomic_write: replaced original file: path=%s",
            path,
        )
    except OSError as e:
        logger.exception(
            "atomic_write: path=%s, content_size=%s",
            path,
            len(content),
        )
        # try to remove tmp file if it exists - best practice
        try:
            if tmp_path.exists():
                logger.debug(
                    "atomic_write: removing tmp file: path=%s",
                    tmp_path,
                )
                tmp_path.unlink()
        except OSError:
            logger.exception(
                "atomic_write: failed to remove tmp file: path=%s",
                tmp_path,
            )
            # cleanup failure shouldn't prevent the WriteError from being raised

        raise WriteError(path=path, reason=str(e)) from e
