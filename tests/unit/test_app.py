"""Unit tests for store.py module."""

from __future__ import annotations

from pathlib import Path

from pykanban.app import get_column
from pykanban.models import Status, Task
from pykanban.store import TaskStore
from tests.unit.conftest import make_project, make_task


class TestGetColumn:
    """Unit tests for get_column."""

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
