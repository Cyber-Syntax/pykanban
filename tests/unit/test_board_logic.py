"""Tests for board_logic module."""

from pathlib import Path

from pykanban import board_logic
from pykanban.board_logic import get_column, insert_at, remove_from_column
from pykanban.models import Status, Task
from pykanban.store import TaskStore

from .conftest import make_project, make_task

# TODO: remove duplicates, use conftest.py shared fixtures
# use classes to group related tests


def test_remove_from_column_accepts_dict():
    """remove_from_column should accept a dict[str, list[str]]."""
    column_order = {
        Status.BACKLOG.value: ["task1", "task2", "task3"],
        Status.TODO.value: ["task4", "task5"],
        Status.DOING.value: ["task6"],
        Status.DONE.value: [],
    }

    result = board_logic.remove_from_column(column_order, "task2")

    assert isinstance(result, dict)


def test_remove_from_column_removes_task_from_column():
    """remove_from_column should remove task_id from the correct column."""
    column_order = {
        Status.BACKLOG.value: ["task1", "task2", "task3"],
        Status.TODO.value: ["task4", "task5"],
        Status.DOING.value: ["task6"],
        Status.DONE.value: [],
    }

    result = board_logic.remove_from_column(column_order, "task2")

    assert result[Status.BACKLOG.value] == ["task1", "task3"]
    assert result[Status.TODO.value] == ["task4", "task5"]
    assert result[Status.DOING.value] == ["task6"]
    assert result[Status.DONE.value] == []


def test_remove_from_column_handles_missing_task():
    """remove_from_column should handle task_id not in any column gracefully."""
    column_order = {
        Status.BACKLOG.value: ["task1", "task2"],
        Status.TODO.value: ["task4"],
    }

    result = board_logic.remove_from_column(column_order, "missing_task")

    assert result[Status.BACKLOG.value] == ["task1", "task2"]
    assert result[Status.TODO.value] == ["task4"]


def test_remove_from_column_returns_new_dict():
    """remove_from_column should return a new dict, not modify the original."""
    original = {
        Status.BACKLOG.value: ["task1", "task2", "task3"],
    }
    original_copy = dict(original)

    result = board_logic.remove_from_column(original, "task2")

    # Original should be unchanged
    assert original == original_copy
    # Result should be a different object
    assert result is not original


def test_insert_at_returns_list():
    """insert_at should return a list[str]."""
    column_list = ["task1", "task2", "task3"]

    result = board_logic.insert_at(column_list, "new_task", 1)

    assert isinstance(result, list)
    assert result == ["task1", "new_task", "task2", "task3"]


def test_insert_at_handles_negative_position():
    """insert_at should clamp negative position to 0."""
    column_list = ["task1", "task2"]

    result = board_logic.insert_at(column_list, "new_task", -5)

    assert result[0] == "new_task"
    assert result == ["new_task", "task1", "task2"]


def test_insert_at_handles_position_beyond_length():
    """insert_at should clamp position beyond length to the end."""
    column_list = ["task1", "task2"]

    result = board_logic.insert_at(column_list, "new_task", 100)

    assert result[-1] == "new_task"
    assert result == ["task1", "task2", "new_task"]


def test_insert_at_does_not_modify_original():
    """insert_at should not modify the original list."""
    original = ["task1", "task2", "task3"]
    original_copy = list(original)

    result = board_logic.insert_at(original, "new_task", 1)

    assert original == original_copy
    assert result is not original


def test_get_column_returns_tasks_in_order():
    """get_column should return tasks in column_order sequence."""
    from datetime import datetime

    from pykanban.models import Priority, Project, Task
    from pykanban.store import TaskStore

    # Create tasks
    task1 = Task(
        id="task1",
        schema=1,
        title="Task 1",
        status=Status.TODO,
        priority=Priority.MEDIUM,
        raw_body="",
        created=datetime.now(),
        updated=datetime.now(),
    )
    task2 = Task(
        id="task2",
        schema=1,
        title="Task 2",
        status=Status.TODO,
        priority=Priority.MEDIUM,
        raw_body="",
        created=datetime.now(),
        updated=datetime.now(),
    )
    task3 = Task(
        id="task3",
        schema=1,
        title="Task 3",
        status=Status.TODO,
        priority=Priority.MEDIUM,
        raw_body="",
        created=datetime.now(),
        updated=datetime.now(),
    )

    # Create task store and add tasks
    task_store = TaskStore()
    task_store.put(task1)
    task_store.put(task2)
    task_store.put(task3)

    # Create project with column_order
    project = Project(
        project_id="p_proj1",
        schema=1,
        title="Test Project",
        description="",
        created=datetime.now(),
        updated=datetime.now(),
        archived=False,
        column_order={
            Status.BACKLOG.value: [],
            Status.TODO.value: ["task2", "task1", "task3"],
            Status.DOING.value: [],
            Status.DONE.value: [],
        },
        folder_path=None,
    )

    # Get column should return tasks in column_order sequence
    result = board_logic.get_column(project, Status.TODO, task_store)

    assert len(result) == 3
    assert result[0].id == "task2"
    assert result[1].id == "task1"
    assert result[2].id == "task3"


def test_get_column_skips_missing_tasks():
    """get_column should skip task IDs that don't exist in the task store."""
    from datetime import datetime

    from pykanban.models import Priority, Project, Task
    from pykanban.store import TaskStore

    # Create only one task
    task1 = Task(
        id="task1",
        schema=1,
        title="Task 1",
        status=Status.TODO,
        priority=Priority.MEDIUM,
        raw_body="",
        created=datetime.now(),
        updated=datetime.now(),
    )

    task_store = TaskStore()
    task_store.put(task1)

    # Create project with column_order referencing tasks that don't exist
    project = Project(
        project_id="p_proj1",
        schema=1,
        title="Test Project",
        description="",
        created=datetime.now(),
        updated=datetime.now(),
        archived=False,
        column_order={
            Status.BACKLOG.value: [],
            Status.TODO.value: ["task1", "missing_task", "also_missing"],
            Status.DOING.value: [],
            Status.DONE.value: [],
        },
        folder_path=None,
    )

    result = board_logic.get_column(project, Status.TODO, task_store)

    assert len(result) == 1
    assert result[0].id == "task1"


def test_get_column_returns_empty_list_for_empty_column():
    """get_column should return empty list for column with no tasks."""
    from datetime import datetime

    from pykanban.models import Project
    from pykanban.store import TaskStore

    task_store = TaskStore()

    project = Project(
        project_id="p_proj1",
        schema=1,
        title="Test Project",
        description="",
        created=datetime.now(),
        updated=datetime.now(),
        archived=False,
        column_order={
            Status.BACKLOG.value: [],
            Status.TODO.value: [],
            Status.DOING.value: [],
            Status.DONE.value: [],
        },
        folder_path=None,
    )

    result = board_logic.get_column(project, Status.TODO, task_store)

    assert result == []


class TestGetColumn:
    """Unit tests for board_logic.get_column."""

    def _store(self, tasks: list[Task]) -> TaskStore:
        s = TaskStore()
        for t in tasks:
            s.put(t)
        return s

    def test_returns_tasks_in_column_order(self) -> None:
        """Preserves the ordering defined in project.column_order."""
        t1 = make_task(id="t1", status=Status.TODO)
        t2 = make_task(id="t2", status=Status.TODO)
        proj = make_project(
            Path("/fake"),
            column_order={
                "todo": ["t2", "t1"],
                "backlog": [],
                "doing": [],
                "done": [],
            },
        )
        result = get_column(proj, Status.TODO, self._store([t1, t2]))
        assert [t.id for t in result] == ["t2", "t1"]

    def test_skips_ids_missing_from_store(self) -> None:
        """Silently ignores task IDs that are not in the task store."""
        t1 = make_task(id="t1", status=Status.TODO)
        proj = make_project(
            Path("/fake"),
            column_order={
                "todo": ["t1", "ghost"],
                "backlog": [],
                "doing": [],
                "done": [],
            },
        )
        result = get_column(proj, Status.TODO, self._store([t1]))
        assert len(result) == 1 and result[0].id == "t1"

    def test_skips_tasks_with_wrong_status(self) -> None:
        """Excludes tasks whose .status does not match the requested column."""
        t1 = make_task(id="t1", status=Status.DOING)
        proj = make_project(
            Path("/fake"),
            column_order={
                "todo": ["t1"],
                "backlog": [],
                "doing": [],
                "done": [],
            },
        )
        result = get_column(proj, Status.TODO, self._store([t1]))
        assert result == []

    def test_returns_empty_for_empty_column(self) -> None:
        """Returns [] when no task IDs are registered in the column."""
        proj = make_project(Path("/fake"))
        result = get_column(proj, Status.BACKLOG, self._store([]))
        assert result == []


class TestInsertAt:
    """Unit tests for board_logic.insert_at."""

    def test_inserts_at_given_index(self) -> None:
        assert insert_at(["a", "b", "c"], "x", 1) == ["a", "x", "b", "c"]

    def test_inserts_at_start(self) -> None:
        assert insert_at(["a", "b"], "x", 0) == ["x", "a", "b"]

    def test_inserts_at_end(self) -> None:
        assert insert_at(["a", "b"], "x", 2) == ["a", "b", "x"]

    def test_clamps_negative_position_to_zero(self) -> None:
        assert insert_at(["a", "b"], "x", -99) == ["x", "a", "b"]

    def test_clamps_overflow_position_to_end(self) -> None:
        assert insert_at(["a", "b"], "x", 99) == ["a", "b", "x"]

    def test_does_not_mutate_original_list(self) -> None:
        original = ["a", "b"]
        insert_at(original, "x", 1)
        assert original == ["a", "b"]

    def test_inserts_into_empty_list(self) -> None:
        assert insert_at([], "x", 0) == ["x"]


class TestRemoveFromColumn:
    """Unit tests for board_logic.remove_from_column."""

    def test_removes_task_id_from_its_column(self) -> None:
        result = remove_from_column(
            {"todo": ["t1", "t2"], "doing": ["t3"]}, "t1"
        )
        assert result == {"todo": ["t2"], "doing": ["t3"]}

    def test_removes_id_appearing_in_multiple_columns(self) -> None:
        """Defensively removes duplicates across all columns."""
        result = remove_from_column(
            {"todo": ["t1"], "doing": ["t1", "t2"]}, "t1"
        )
        assert "t1" not in result["todo"]
        assert "t1" not in result["doing"]
        assert result["doing"] == ["t2"]

    def test_noop_when_task_not_present(self) -> None:
        order = {"todo": ["t1"], "doing": []}
        result = remove_from_column(order, "ghost")
        assert result == {"todo": ["t1"], "doing": []}

    def test_does_not_mutate_original_dict(self) -> None:
        original = {"todo": ["t1", "t2"]}
        remove_from_column(original, "t1")
        assert original == {"todo": ["t1", "t2"]}
