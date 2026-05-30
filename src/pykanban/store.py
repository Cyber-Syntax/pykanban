"""In-memory store classes for PyKanban."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pykanban.models import Project, Status, Task


@dataclass
class TaskStore:
    """In-memory store for tasks."""

    tasks_by_id: dict[str, Task] = field(default_factory=dict)

    def get(self, task_id: str) -> Task:
        """Get a task by ID."""
        return self.tasks_by_id[task_id]

    def put(self, task: Task) -> None:
        """Add or update a task."""
        self.tasks_by_id[task.id] = task

    def remove(self, task_id: str) -> None:
        """Remove a task by ID."""
        self.tasks_by_id.pop(task_id, None)

    def all(self) -> list[Task]:
        """Return all tasks."""
        return list(self.tasks_by_id.values())


@dataclass
class ProjectStore:
    """In-memory store for projects."""

    projects_by_id: dict[str, Project] = field(default_factory=dict)
    active_project_id: str | None = None

    def get_active(self) -> Project:
        """Get the active project."""
        # TODO: better to show on error_banner
        if self.active_project_id is None:
            raise KeyError("active_project_id is not set")
        return self.projects_by_id[self.active_project_id]

    def set_active(self, project_id: str) -> None:
        """Set the active project by ID."""
        self.active_project_id = project_id

    def put(self, project: Project) -> None:
        """Add or update a project."""
        self.projects_by_id[project.project_id] = project


@dataclass
class BoardView:
    """Board view mapping each status to its ordered tasks."""

    columns: dict[Status, list[Task]]
