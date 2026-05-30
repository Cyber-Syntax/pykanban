"""Fixtures for unit tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pykanban.app import KanbanApp
from pykanban.config import Settings
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


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    """Fixture that provides a temporary projects directory."""
    projects_path = tmp_path / "projects"
    projects_path.mkdir(parents=True)
    return projects_path


@pytest.fixture
def app(projects_dir: Path) -> KanbanApp:
    """Fixture that returns a KanbanApp initialized with an empty projects directory."""
    settings = Settings(projects_dir=projects_dir)
    return KanbanApp(settings)


@pytest.fixture
def app_with_active_project(tmp_path: Path) -> KanbanApp:
    """KanbanApp with one active project pointing to a real temp directory."""
    settings = Settings(projects_dir=tmp_path / "projects")
    settings.projects_dir.mkdir(parents=True)
    app = KanbanApp(settings)

    proj_folder = settings.projects_dir / "test-project"
    proj_folder.mkdir()
    proj = make_project(proj_folder)
    app.put_project(proj)
    app.set_active_project(proj.project_id)
    return app
