"""Pure utility functions for project operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pykanban.error import ConflictWarning, ParseError
from pykanban.models import Project, Status, Task

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class ProjectTasksLoadResult:
    """Result of loading project tasks from disk."""

    loaded_tasks: list[Task]
    loaded_task_ids: set[str]
    parse_errors: list[ParseError]
    updated_mtime_cache: dict[Path, float]


def empty_column_order() -> dict[str, list[str]]:
    """Initialize an empty column order structure.

    Returns:
        A dictionary with empty lists for each Status value.
    """
    return {
        Status.BACKLOG.value: [],
        Status.TODO.value: [],
        Status.DOING.value: [],
        Status.DONE.value: [],
    }


def choose_active_project(
    projects_dict: dict[str, Project],
) -> Project | None:
    """Choose an initial active project.

    Prioritizes non-archived projects. If all are archived or none exist,
    returns the first project in the dictionary, or None if empty.

    Args:
        projects_dict: Dictionary of projects by ID.

    Returns:
        The selected project or None if no projects exist.
    """
    if not projects_dict:
        return None

    for project in projects_dict.values():
        if not project.archived:
            return project

    return next(iter(projects_dict.values())) if projects_dict else None


def find_sync_conflicts(folder: Path) -> list[ConflictWarning]:
    """Find all sync-conflict files in a folder.

    Args:
        folder: The folder to scan for conflict files.

    Returns:
        A list of ConflictWarning objects for each conflict file found.
    """
    conflicts = []
    for path in folder.rglob(".sync-conflict-*"):
        conflicts.append(ConflictWarning(path=path))
    return conflicts


def find_all_project_conflicts(
    projects_dict: dict[str, Project],
) -> list[ConflictWarning]:
    """Find sync-conflict files from all projects.

    Args:
        projects_dict: Dictionary of projects by ID.

    Returns:
        A list of ConflictWarning objects from all projects.
    """
    all_conflicts = []
    for project in projects_dict.values():
        all_conflicts.extend(find_sync_conflicts(project.folder_path))
    return all_conflicts


def reconcile_order(
    column_order: dict[str, list[str]],
    known_ids: set[str],
    tasks_by_id: dict[str, Task],
) -> dict[str, list[str]]:
    """Return a corrected column_order: stale IDs removed, missing IDs appended.

    This is a pure function — it never mutates its inputs.

    Args:
        column_order: Current column order mapping (may contain stale IDs).
        known_ids: Task IDs that actually exist (loaded from disk).
        tasks_by_id: Task lookup used to find the correct column for orphaned IDs.

    Returns:
        New column_order with stale IDs dropped and missing IDs appended to
        the column matching each task's status.
    """
    # Drop IDs that no longer exist on disk
    result: dict[str, list[str]] = {}
    for status_key, id_list in column_order.items():
        # TODO: make this a list comprehension for efficiency
        clean_list: list[str] = []
        for task_id in id_list:
            if task_id in known_ids:
                clean_list.append(task_id)
        result[status_key] = clean_list

    # Append IDs that exist on disk but are absent from column_order
    present = {i for ids in result.values() for i in ids}
    for task_id in known_ids - present:
        task = tasks_by_id.get(task_id)
        if task:
            result.setdefault(task.status.value, []).append(task_id)

    return result


def load_project_tasks(
    project: Project, mtime_cache: dict[Path, float] | None = None
) -> ProjectTasksLoadResult:
    """Load tasks from a project folder and return results without mutations.

    Also seeds mtime_cache so the first switch_project call treats
    unchanged files as already seen instead of re-parsing everything.

    Args:
        project: The project to load tasks from.
        mtime_cache: Optional cache of file modification times. If provided,
            it will be updated with new mtime values.

    Returns:
        ProjectTasksLoadResult containing loaded task IDs, parse errors,
        and an updated mtime cache.
    """
    from pykanban.parser import parse_task

    cache: dict[Path, float] = mtime_cache or {}
    loaded_tasks: list[Task] = []
    loaded_task_ids: set[str] = set()
    errors: list[ParseError] = []

    for md_file in project.folder_path.rglob("*.md"):
        task = parse_task(md_file)
        if isinstance(task, ParseError):
            errors.append(task)
            continue

        loaded_tasks.append(task)
        loaded_task_ids.add(task.id)

        # Seed the mtime cache while we have the file in hand
        try:
            cache[md_file] = md_file.stat().st_mtime
        except OSError:
            # File disappeared between rglob and stat; skip silently
            pass

    return ProjectTasksLoadResult(
        loaded_tasks=loaded_tasks,
        loaded_task_ids=loaded_task_ids,
        parse_errors=errors,
        updated_mtime_cache=cache,
    )
