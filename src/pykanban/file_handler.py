"""File I/O utilities for atomic writes."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pykanban.exceptions import WriteError

if TYPE_CHECKING:
    from pathlib import Path


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
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            # fsync ensures the data survives a power loss before the rename
            os.fsync(f.fileno())
        # Path.replace() is the pathlib eqivalent of os.replace
        tmp_path.replace(path)
    # TODO: add it to logging when logger is implemented
    except OSError as e:
        # try to cleanup tmp file if it exists
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            # ignore cleanup failure to be able to report the WriteError
            # We try to delete it, but if we can't, we accept the failure and move on.
            pass
        raise WriteError(path=path, reason=str(e)) from e
