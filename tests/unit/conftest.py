"""Fixtures for unit tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pykanban.models import Priority, Project, Status, Task


def make_project(folder_path: Path, **overrides) -> Project:
    """Return a Project with sensible defaults, accepting field overrides."""
    defaults = dict(
        project_id="p_test1234",
        schema=1,
        title="Test Project",
        description="A test project",
        created=datetime(2026, 1, 1, 12, 0),
        updated=datetime(2026, 1, 1, 12, 0),
        archived=False,
        column_order={s.value: [] for s in Status},
        folder_path=folder_path,
    )
    defaults.update(overrides)
    return Project(**defaults)


def make_task(**overrides) -> Task:
    """Return a Task with sensible defaults, accepting field overrides."""
    defaults = dict(
        id="a1b2c3d4",
        schema=1,
        title="Test Task",
        status=Status.TODO,
        priority=Priority.MEDIUM,
        raw_body="# Description\n\nA task.\n",
        created=datetime(2026, 1, 1, 12, 0),
        updated=datetime(2026, 1, 1, 12, 0),
    )
    defaults.update(overrides)
    return Task(**defaults)
