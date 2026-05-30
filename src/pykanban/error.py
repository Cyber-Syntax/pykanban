"""Error and warning models for PyKanban."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class ParseError:
    """Error parsing a task."""

    path: Path
    reason: str


@dataclass(frozen=True)
class ConflictWarning:
    """Sync-conflict warning surfaced in the UI."""

    path: Path
    reason: str = "Sync conflict detected"
