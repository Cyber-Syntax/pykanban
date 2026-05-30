"""In-memory state class for PyKanban."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pykanban.store import ProjectStore, TaskStore

if TYPE_CHECKING:
    from pathlib import Path

    from pykanban.config import Settings
    from pykanban.error import ConflictWarning, ParseError


@dataclass
class AppState:
    """Pure data container for the in-memory application state."""

    tasks: TaskStore
    projects: ProjectStore
    errors: list[ParseError | ConflictWarning]
    settings: Settings
    scan_mtime_cache: dict[Path, float] = field(default_factory=dict)

    @classmethod
    def create(cls, settings: Settings) -> AppState:
        """Create a new AppState with empty stores.

        Args:
            settings: Resolved application settings.

        Returns:
            A new AppState with empty stores and error list.
        """
        return cls(
            tasks=TaskStore(),
            projects=ProjectStore(),
            errors=[],
            settings=settings,
        )
