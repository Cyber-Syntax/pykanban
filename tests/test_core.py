from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pykanban.app import KanbanApp
from pykanban.config import Settings
from pykanban.models import Priority, Project, Status, Task
from pykanban.store import BoardView, ProjectStore, TaskStore

# ── Factories ─────────────────────────────────────────────────────────────────


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


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def project_folder(tmp_path: Path) -> Path:
    """Temporary project folder on disk."""
    folder = tmp_path / "test-project"
    folder.mkdir()
    return folder


@pytest.fixture
def project(project_folder: Path) -> Project:
    """In-memory project backed by a real temp folder."""
    return make_project(project_folder)


@pytest.fixture
def task() -> Task:
    """In-memory task with default values."""
    return make_task()


@pytest.fixture
def app(tmp_path: Path) -> KanbanApp:
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


# ── store: TaskStore ──────────────────────────────────────────────────────────


class TestTaskStore:
    """Unit tests for store.TaskStore."""

    def test_put_then_get(self, task: Task) -> None:
        store = TaskStore()
        store.put(task)
        assert store.get(task.id) is task

    def test_get_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            TaskStore().get("nonexistent")

    def test_remove_deletes_task(self, task: Task) -> None:
        store = TaskStore()
        store.put(task)
        store.remove(task.id)
        assert task.id not in store.tasks_by_id

    def test_remove_nonexistent_is_noop(self) -> None:
        TaskStore().remove("ghost")  # must not raise

    def test_all_returns_every_task(self) -> None:
        store = TaskStore()
        t1, t2 = make_task(id="t1"), make_task(id="t2")
        store.put(t1)
        store.put(t2)
        assert {t.id for t in store.all()} == {"t1", "t2"}

    def test_put_overwrites_existing(self, task: Task) -> None:
        store = TaskStore()
        store.put(task)
        updated = make_task(id=task.id, title="Updated")
        store.put(updated)
        assert store.get(task.id).title == "Updated"


# ── store: ProjectStore ───────────────────────────────────────────────────────


class TestProjectStore:
    """Unit tests for store.ProjectStore."""

    def test_get_active_raises_when_none_set(self) -> None:
        with pytest.raises(KeyError):
            ProjectStore().get_active()

    def test_set_and_get_active(self, project: Project) -> None:
        store = ProjectStore()
        store.put(project)
        store.set_active(project.project_id)
        assert store.get_active() is project

    def test_put_stores_by_id(self, project: Project) -> None:
        store = ProjectStore()
        store.put(project)
        assert project.project_id in store.projects_by_id


# ── store: KanbanApp.create_task ───────────────────────────────────────────────


class TestAppManagerCreateTask:
    """Unit tests for KanbanApp.create_task."""

    def test_task_added_to_in_memory_store(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.HIGH, "")
        assert app.get_task(task.id) is not None

    def test_title_is_stripped(self, app: KanbanApp) -> None:
        task = app.create_task("  Spaced  ", Status.TODO, Priority.LOW, "")
        assert task.title == "Spaced"

    def test_task_appears_in_correct_column_order(
        self, app: KanbanApp
    ) -> None:
        task = app.create_task("T", Status.DOING, Priority.MEDIUM, "")
        project = app.get_active_project()
        assert task.id in project.column_order["doing"]

    def test_task_file_is_written_to_disk(self, app: KanbanApp) -> None:
        task = app.create_task("My Task", Status.TODO, Priority.LOW, "")
        project = app.get_active_project()
        expected = project.folder_path / f"my-task--{task.id}.md"
        assert expected.exists()


# ── store: KanbanApp.update_task ───────────────────────────────────────────────


class TestAppManagerUpdateTask:
    """Unit tests for KanbanApp.update_task."""

    def test_updates_title_field(self, app: KanbanApp) -> None:
        task = app.create_task("Old", Status.TODO, Priority.LOW, "")
        app.update_task(task.id, {"title": "New"})
        assert app.get_task(task.id).title == "New"

    def test_updates_priority_field(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.update_task(task.id, {"priority": Priority.HIGH})
        assert app.get_task(task.id).priority == Priority.HIGH

    def test_updates_raw_body_field(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.update_task(task.id, {"raw_body": "New body"})
        assert app.get_task(task.id).raw_body == "New body"

    def test_moves_task_to_new_status(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.update_task(task.id, {"status": Status.DOING})
        project = app.get_active_project()
        assert task.id in project.column_order["doing"]
        assert task.id not in project.column_order["todo"]

    def test_reorders_within_same_column(self, app: KanbanApp) -> None:
        t1 = app.create_task("T1", Status.TODO, Priority.LOW, "")
        t2 = app.create_task("T2", Status.TODO, Priority.LOW, "")  # noqa: F841
        app.update_task(t1.id, {"position": 1})
        project = app.get_active_project()
        assert project.column_order["todo"].index(t1.id) == 1


# ── store: KanbanApp.move_task ─────────────────────────────────────────────────


class TestAppManagerMoveTask:
    """Unit tests for KanbanApp.move_task."""

    def test_moves_task_to_destination_column(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.move_task(task.id, Status.DONE, position=0)
        project = app.get_active_project()
        assert task.id in project.column_order["done"]
        assert task.id not in project.column_order["todo"]

    def test_updates_task_status_attribute(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.move_task(task.id, Status.DOING, position=0)
        assert app.get_task(task.id).status == Status.DOING

    def test_respects_position_argument(self, app: KanbanApp) -> None:
        """Task is placed at the requested index inside the destination column."""
        existing = app.create_task("Existing", Status.DONE, Priority.LOW, "")
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.move_task(task.id, Status.DONE, position=0)
        project = app.get_active_project()
        assert project.column_order["done"][0] == task.id


# ── store: KanbanApp.delete_task ───────────────────────────────────────────────


class TestAppManagerDeleteTask:
    """Unit tests for KanbanApp.delete_task."""

    def test_removes_task_from_in_memory_store(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.delete_task(task.id)
        assert app.get_task(task.id) is None

    def test_removes_task_from_all_column_orders(self, app: KanbanApp) -> None:
        task = app.create_task("T", Status.TODO, Priority.LOW, "")
        app.delete_task(task.id)
        project = app.get_active_project()
        assert all(task.id not in ids for ids in project.column_order.values())

    def test_task_file_is_deleted_from_disk(self, app: KanbanApp) -> None:
        task = app.create_task("Del Me", Status.TODO, Priority.LOW, "")
        project = app.get_active_project()
        task_file = project.folder_path / f"del-me--{task.id}.md"
        assert task_file.exists(), (
            "pre-condition: file must exist before delete"
        )
        app.delete_task(task.id)
        assert not task_file.exists()


# ── store: KanbanApp.get_board ─────────────────────────────────────────────────


class TestAppStateGetBoard:
    """Unit tests for KanbanApp.get_board."""

    def test_returns_board_view_with_all_four_statuses(
        self, app: KanbanApp
    ) -> None:
        board = app.get_board()
        assert isinstance(board, BoardView)
        assert set(board.columns.keys()) == set(Status)

    def test_board_column_contains_created_task(self, app: KanbanApp) -> None:
        task = app.create_task("Board T", Status.DOING, Priority.LOW, "")
        board = app.get_board()
        assert task.id in [t.id for t in board.columns[Status.DOING]]
