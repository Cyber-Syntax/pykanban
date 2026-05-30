"""Tests for task_utils module."""

from pykanban.models import Status
from pykanban.task_utils import (
    insert_into_column,
    remove_from_columns,
    reorder_in_column,
)


class TestInsertIntoColumn:
    """Unit tests for insert_into_column."""

    def test_returns_dict(self) -> None:
        """insert_into_column should return a dict[str, list[str]]."""
        column_order = {
            Status.TODO.value: ["task1", "task2", "task3"],
        }

        result = insert_into_column(
            column_order, Status.TODO.value, "new_task", 1
        )

        assert isinstance(result, dict)
        assert result[Status.TODO.value] == [
            "task1",
            "new_task",
            "task2",
            "task3",
        ]

    def test_inserts_at_given_index(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: ["a", "b", "c"]}, Status.TODO.value, "x", 1
        )
        assert result[Status.TODO.value] == ["a", "x", "b", "c"]

    def test_inserts_at_start(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: ["a", "b"]}, Status.TODO.value, "x", 0
        )
        assert result[Status.TODO.value] == ["x", "a", "b"]

    def test_inserts_at_end(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: ["a", "b"]}, Status.TODO.value, "x", 2
        )
        assert result[Status.TODO.value] == ["a", "b", "x"]

    def test_clamps_negative_position_to_zero(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: ["a", "b"]}, Status.TODO.value, "x", -99
        )
        assert result[Status.TODO.value] == ["x", "a", "b"]

    def test_clamps_overflow_position_to_end(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: ["a", "b"]}, Status.TODO.value, "x", 99
        )
        assert result[Status.TODO.value] == ["a", "b", "x"]

    def test_does_not_mutate_original_dict(self) -> None:
        original = {Status.TODO.value: ["a", "b"]}
        original_copy = {k: v.copy() for k, v in original.items()}
        insert_into_column(original, Status.TODO.value, "x", 1)
        assert original == original_copy

    def test_does_not_duplicate_task_id(self) -> None:
        """insert_into_column should not insert duplicate task_id if it already exists."""
        column_order = {
            Status.TODO.value: ["task1", "task2", "task3"],
        }

        result = insert_into_column(
            column_order, Status.TODO.value, "task2", 1
        )

        # Original order should be preserved since task2 already exists
        assert result[Status.TODO.value] == ["task1", "task2", "task3"]
        # title should not be duplicated
        assert result[Status.TODO.value].count("task2") == 1
        assert result is not column_order

    def test_inserts_into_empty_list(self) -> None:
        result = insert_into_column(
            {Status.TODO.value: []}, Status.TODO.value, "x", 0
        )
        assert result[Status.TODO.value] == ["x"]

    def test_inserts_with_none_position_appends(self) -> None:
        """insert_into_column with None position should append to end."""
        result = insert_into_column(
            {Status.TODO.value: ["a", "b"]}, Status.TODO.value, "x", None
        )
        assert result[Status.TODO.value] == ["a", "b", "x"]


class TestRemoveFromColumns:
    """Unit tests for remove_from_columns."""

    def test_accepts_dict(self) -> None:
        """remove_from_columns should accept a dict[str, list[str]]."""
        column_order = {
            Status.BACKLOG.value: ["task1", "task2", "task3"],
            Status.TODO.value: ["task4", "task5"],
            Status.DOING.value: ["task6"],
            Status.DONE.value: [],
        }

        result = remove_from_columns(column_order, "task2")

        assert isinstance(result, dict)

    def test_removes_task_from_column(self) -> None:
        """remove_from_columns should remove task_id from the correct column."""
        column_order = {
            Status.BACKLOG.value: ["task1", "task2", "task3"],
            Status.TODO.value: ["task4", "task5"],
            Status.DOING.value: ["task6"],
            Status.DONE.value: [],
        }

        result = remove_from_columns(column_order, "task2")

        assert result[Status.BACKLOG.value] == ["task1", "task3"]
        assert result[Status.TODO.value] == ["task4", "task5"]
        assert result[Status.DOING.value] == ["task6"]
        assert result[Status.DONE.value] == []

    def test_handles_missing_task(self) -> None:
        """remove_from_columns should handle task_id not in any column gracefully."""
        column_order = {
            Status.BACKLOG.value: ["task1", "task2"],
            Status.TODO.value: ["task4"],
        }

        result = remove_from_columns(column_order, "missing_task")

        assert result[Status.BACKLOG.value] == ["task1", "task2"]
        assert result[Status.TODO.value] == ["task4"]

    def test_returns_new_dict(self) -> None:
        """remove_from_columns should return a new dict, not modify the original."""
        original = {
            Status.BACKLOG.value: ["task1", "task2", "task3"],
        }
        original_copy = {k: v.copy() for k, v in original.items()}

        result = remove_from_columns(original, "task2")

        # Original should be unchanged
        assert original == original_copy
        # Result should be a different object
        assert result is not original

    def test_removes_task_id_from_its_column(self) -> None:
        result = remove_from_columns(
            {"todo": ["t1", "t2"], "doing": ["t3"]}, "t1"
        )
        assert result == {"todo": ["t2"], "doing": ["t3"]}

    def test_removes_id_appearing_in_multiple_columns(self) -> None:
        """Defensively removes duplicates across all columns."""
        result = remove_from_columns(
            {"todo": ["t1"], "doing": ["t1", "t2"]}, "t1"
        )
        assert "t1" not in result["todo"]
        assert "t1" not in result["doing"]
        assert result["doing"] == ["t2"]

    def test_noop_when_task_not_present(self) -> None:
        order = {"todo": ["t1"], "doing": []}
        result = remove_from_columns(order, "ghost")
        assert result == {"todo": ["t1"], "doing": []}

    def test_does_not_mutate_original_dict(self) -> None:
        original = {"todo": ["t1", "t2"]}
        original_copy = {k: v.copy() for k, v in original.items()}
        remove_from_columns(original, "t1")
        assert original == original_copy


class TestReorderInColumn:
    """Unit tests for reorder_in_column."""

    def test_task_not_found_returns_unchanged(self) -> None:
        """reorder_in_column should return unchanged if task_id is not found."""
        column_order = {
            Status.TODO.value: ["task1", "task2", "task3"],
        }

        result = reorder_in_column(column_order, "missing_task", 1)

        assert result == column_order

    def test_reorders_task_to_new_position(self) -> None:
        """reorder_in_column should move task to new position."""
        column_order = {Status.TODO.value: ["t1", "t2", "t3", "t4"]}
        result = reorder_in_column(column_order, "t4", 0)
        assert result[Status.TODO.value] == ["t4", "t1", "t2", "t3"]

    def test_moves_task_forward_in_column(self) -> None:
        """Task can be moved forward within a column."""
        column_order = {Status.TODO.value: ["t1", "t2", "t3"]}
        result = reorder_in_column(column_order, "t1", 2)
        assert result[Status.TODO.value] == ["t2", "t3", "t1"]

    def test_moves_task_backward_in_column(self) -> None:
        """Task can be moved backward within a column."""
        column_order = {Status.TODO.value: ["t1", "t2", "t3"]}
        result = reorder_in_column(column_order, "t3", 0)
        assert result[Status.TODO.value] == ["t3", "t1", "t2"]

    def test_clamps_negative_position(self) -> None:
        """Negative positions should be clamped to 0."""
        column_order = {Status.TODO.value: ["t1", "t2", "t3"]}
        result = reorder_in_column(column_order, "t3", -5)
        assert result[Status.TODO.value] == ["t3", "t1", "t2"]

    def test_clamps_overflow_position(self) -> None:
        """Positions beyond length should be clamped to end."""
        column_order = {Status.TODO.value: ["t1", "t2", "t3"]}
        result = reorder_in_column(column_order, "t1", 99)
        assert result[Status.TODO.value] == ["t2", "t3", "t1"]

    def test_does_not_mutate_original(self) -> None:
        """reorder_in_column should not mutate the original dict."""
        original = {Status.TODO.value: ["t1", "t2", "t3"]}
        original_copy = {k: v.copy() for k, v in original.items()}
        reorder_in_column(original, "t1", 2)
        assert original == original_copy

    def test_keeps_task_in_same_column(self) -> None:
        """reorder_in_column should only reorder within the same column."""
        column_order = {
            Status.TODO.value: ["t1", "t2"],
            Status.DOING.value: ["t3"],
        }
        result = reorder_in_column(column_order, "t1", 1)
        assert result[Status.TODO.value] == ["t2", "t1"]
        assert result[Status.DOING.value] == ["t3"]
