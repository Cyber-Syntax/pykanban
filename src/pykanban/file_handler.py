"""File I/O utilities for atomic writes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class WriteError(Exception):
    """Raised when atomic write fails."""

    path: Path
    reason: str


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
    except OSError as e:
        # Best effort cleanup; do not mask the error if cleanup fails.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise WriteError(path=path, reason=str(e)) from e
