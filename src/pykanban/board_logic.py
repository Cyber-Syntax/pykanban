from __future__ import annotations

from typing import TYPE_CHECKING

from pykanban.models import Project, Status, Task

if TYPE_CHECKING:
    from pykanban.store import TaskStore


def get_column(
    project: Project, status: Status, task_store: TaskStore
) -> list[Task]:
    """Return tasks in the column order for the given status."""
    column_ids = project.column_order.get(status.value, [])
    tasks: list[Task] = []
    for task_id in column_ids:
        task = task_store.tasks_by_id.get(task_id)
        if task and task.status == status:
            tasks.append(task)
    return tasks


def insert_at(
    column_order_list: list[str], task_id: str, position: int
) -> list[str]:
    """Return a new list with task_id inserted at position."""
    new_list = list(column_order_list)
    position = max(0, min(position, len(new_list)))
    new_list.insert(position, task_id)
    return new_list


def remove_from_column(
    column_order: dict[str, list[str]], task_id: str
) -> dict[str, list[str]]:
    """Return a new column_order without task_id."""
    new_order: dict[str, list[str]] = {}
    for key, ids in column_order.items():
        new_order[key] = [id for id in ids if id != task_id]
    return new_order
