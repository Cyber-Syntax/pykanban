"""Pure utility functions for project operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pykanban.error import ConflictWarning, ParseError
from pykanban.logger import get_logger
from pykanban.models import Project, Status, Task
from pykanban.parser import parse_task

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


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
    projects_dict: Mapping[str, Project],
) -> Project | None:
    """Choose an initial active project.

    Prioritizes non-archived projects. If all are archived or none exist,
    returns the first project in the dictionary, or None if empty.

    Args:
        projects_dict: Dictionary of projects by ID.

    Returns:
        The selected project or None if no projects exist.
    """
    logger.debug(
        "Choosing active project from %s projects", len(projects_dict)
    )
    if not projects_dict:
        logger.debug("No projects found")
        return None

    for project in projects_dict.values():
        if not project.archived:
            logger.debug("Found active project: %s", project.project_id)
            return project
        logger.debug("Project %s is archived", project.project_id)

    logger.info("No active projects found")
    return next(iter(projects_dict.values())) if projects_dict else None


def find_sync_conflicts(folder: Path) -> list[ConflictWarning]:
    """Find all sync-conflict files in a folder.

    Args:
        folder: The folder to scan for conflict files.

    Returns:
        A list of ConflictWarning objects for each conflict file found.
    """
    logger.debug("Finding sync conflicts in %s", folder)
    conflicts: list[ConflictWarning] = [
        ConflictWarning(path=path) for path in folder.rglob(".sync-conflict-*")
    ]
    if conflicts:
        logger.debug("Found %s sync conflicts", len(conflicts))

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
    logger.debug("Finding all project conflicts")
    all_conflicts: list[ConflictWarning] = []
    for project in projects_dict.values():
        all_conflicts.extend(find_sync_conflicts(project.folder_path))
    if all_conflicts:
        logger.warning("Found %s project conflicts", len(all_conflicts))
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
    logger.debug("Reconciling order for %s known IDs", len(known_ids))
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
    logger.info("Appended %s missing IDs", len(known_ids) - len(present))

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
    logger.debug("Loading tasks for project %s", project.project_id)
    cache: dict[Path, float] = mtime_cache or {}
    loaded_tasks: list[Task] = []
    loaded_task_ids: set[str] = set()
    errors: list[ParseError] = []

    for md_file in project.folder_path.rglob("*.md"):
        task = parse_task(md_file)
        if isinstance(task, ParseError):
            logger.error("Failed to parse task %s: %s", md_file, task.reason)
            errors.append(task)
            continue

        loaded_tasks.append(task)
        loaded_task_ids.add(task.id)

        # Seed the mtime cache while we have the file in hand
        try:
            cache[md_file] = md_file.stat().st_mtime
        except OSError:
            # File disappeared between rglob and stat; log and skip
            logger.debug("Failed to stat file %s", md_file, exc_info=True)

    logger.info(
        "Loaded %d tasks from project %s",
        len(loaded_tasks),
        project.project_id,
    )

    return ProjectTasksLoadResult(
        loaded_tasks=loaded_tasks,
        loaded_task_ids=loaded_task_ids,
        parse_errors=errors,
        updated_mtime_cache=cache,
    )
