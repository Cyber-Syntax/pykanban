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
    """Write content to a file atomically."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # TODO replace to path.replace (if work for like os.replace)
        os.replace(tmp_path, path)
    except OSError as e:
        # Best effort cleanup; do not mask the error if cleanup fails.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise WriteError(path=path, reason=str(e)) from e
