"""Exceptions raised by pykanban."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WriteError(Exception):
    """Raised when atomic write fails."""

    path: Path
    reason: str
