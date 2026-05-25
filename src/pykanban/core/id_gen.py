from __future__ import annotations

from uuid import uuid4

from pykanban.core.store import ProjectStore, TaskStore


def generate_task_id(store: TaskStore) -> str:
    """Generate a unique task ID."""
    for _ in range(10):
        candidate = uuid4().hex[:8]
        if candidate not in store.tasks_by_id:
            return candidate

    raise RuntimeError(
        "Failed to generate a unique task ID after 10 attempts."
    )


def generate_project_id(store: ProjectStore) -> str:
    """Generate a unique project ID."""
    for _ in range(10):
        candidate = f"p_{uuid4().hex[:8]}"
        if candidate not in store.projects_by_id:
            return candidate

    raise RuntimeError(
        "Failed to generate a unique project ID after 10 attempts."
    )
