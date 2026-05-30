"""TaskManager utility functions for managing task columns and file paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pykanban.utils import slugify

if TYPE_CHECKING:
    from pathlib import Path


def build_task_file_path(
    project_folder: Path, task_title: str, task_id: str
) -> Path:
    """Build a task file path for a project.

    The filename follows the "title-slug--id.md" pattern.

    Args:
        project_folder: The folder path of the project.
        task_title: The title of the task to build the slug from.
        task_id: The task ID to build the path for.

    Returns:
        The full path to the task file.
    """
    slug = slugify(task_title)
    return project_folder / f"{slug}--{task_id}.md"


def insert_into_column(
    column_order: dict[str, list[str]],
    status_value: str,
    task_id: str,
    position: int | None = None,
) -> dict[str, list[str]]:
    """Return a new column_order with task ID inserted into the specified column.

    Args:
        column_order: The current column order mapping.
        status_value: The status value (column key).
        task_id: The task ID to insert.
        position: Optional position to insert at. If None, appends to end.

    Returns:
        A new column_order dict with the task ID inserted.
    """
    # Create a copy of the column_order dict and nested lists
    new_column_order = {k: v.copy() for k, v in column_order.items()}

    # Get or create the column list for the status value
    column = new_column_order.setdefault(status_value, [])

    # Task ID already exists in the column, return unchanged
    if task_id in column:
        return new_column_order

    # Insert the task ID at the specified position
    # or append to the end if no position is given
    if position is None:
        column.append(task_id)
    else:
        position = max(0, min(position, len(column)))
        column.insert(position, task_id)

    return new_column_order


def remove_from_columns(
    column_order: dict[str, list[str]], task_id: str
) -> dict[str, list[str]]:
    """Return a new column_order with task ID removed from all columns.

    Args:
        column_order: The current column order mapping.
        task_id: The task ID to remove.

    Returns:
        A new column_order dict with the task ID removed.
    """
    # Create a copy of the column_order dict and nested lists
    new_column_order = {}

    for status_value, ids in column_order.items():
        new_ids = ids.copy()
        if task_id in new_ids:
            new_ids.remove(task_id)
        new_column_order[status_value] = new_ids

    return new_column_order


def reorder_in_column(
    column_order: dict[str, list[str]], task_id: str, position: int
) -> dict[str, list[str]]:
    """Return a new column_order with task ID reordered within its column.

    Args:
        column_order: The current column order mapping.
        task_id: The task ID to reorder.
        position: The new position in the column.

    Returns:
        A new column_order dict with the task ID reordered.
    """
    # Create a copy of the column_order dict and nested lists
    new_column_order = {k: v.copy() for k, v in column_order.items()}

    # Find the column that contains the task ID and reorder it
    for ids in new_column_order.values():
        if task_id in ids:
            # Remove the task ID from its current position
            ids.remove(task_id)
            # Insert the task ID at the new position, ensuring it's within bounds
            position = max(0, min(position, len(ids)))
            ids.insert(position, task_id)
            return new_column_order

    # Task ID not found, return unchanged
    return new_column_order
