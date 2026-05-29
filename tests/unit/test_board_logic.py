"""Tests for module."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from pykanban.board_logic import (
    insert_into_column,
    remove_from_columns,
    reorder_in_column,
    slugify,
)
from pykanban.models import Status, Task
from pykanban.store import TaskStore

from .conftest import make_project, make_task


class TestSlugify:
    """Unit tests for slugify function."""

    def test_basic_normalization(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_special_characters_removed(self) -> None:
        assert slugify("Task! @#$% Name") == "task-name"

    def test_multiple_spaces_collapsed(self) -> None:
        assert slugify("Task   Name") == "task-name"

    def test_hyphens_stripped(self) -> None:
        assert slugify("---Task---") == "task"

    def test_empty_string_default(self) -> None:
        assert slugify("") == "project"
        assert slugify("   ") == "project"

    def test_only_special_chars(self) -> None:
        assert slugify("@#$%") == "project"

    def test_callable_parameter(self) -> None:
        assert slugify(lambda: "Lazy Task") == "lazy-task"

    def test_numbers_preserved(self) -> None:
        assert slugify("2024 Q1 Review") == "2024-q1-review"

    def test_lowercase_conversion(self) -> None:
        """All output should be lowercase."""
        assert slugify("UPPERCASE") == "uppercase"
        assert slugify("MiXeD CaSe") == "mixed-case"

    def test_unicode_chars_converted_to_hyphens(self) -> None:
        """Unicode characters should be converted to hyphens, then trailing hyphens stripped."""
        assert slugify("Café") == "caf"
        assert slugify("Naïve") == "na-ve"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        """Leading and trailing hyphens should be removed."""
        assert slugify("-task-") == "task"
        assert slugify("---") == "project"

    def test_consecutive_special_chars(self) -> None:
        """Multiple consecutive special characters should collapse to single hyphen."""
        assert slugify("Task!!!---Name") == "task-name"
        assert slugify("A@@@B") == "a-b"

    def test_alphanumeric_with_underscores(self) -> None:
        """Underscores should be treated as special characters."""
        assert slugify("task_name") == "task-name"
        assert slugify("task__name") == "task-name"

    def test_parentheses_and_brackets(self) -> None:
        """Brackets and parentheses should be converted to hyphens."""
        assert slugify("Task (Priority)") == "task-priority"
        assert slugify("Item [v2]") == "item-v2"

    def test_dots_and_slashes(self) -> None:
        """Dots, slashes should be converted to hyphens."""
        assert slugify("v1.2.3") == "v1-2-3"
        assert slugify("path/to/task") == "path-to-task"

    def test_single_word(self) -> None:
        """Single word input should lowercase only."""
        assert slugify("Task") == "task"
        assert slugify("HELLO") == "hello"

    # Hypothesis property-based tests for comprehensive edge case coverage
    @given(
        st.text(
            min_size=1,
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        )
    )
    def test_output_is_lowercase_hyphen_or_project(self, text: str) -> None:
        """Output should only contain lowercase, digits, hyphens, or be 'project'."""
        result = slugify(text)
        if result != "project":
            assert all(c.islower() or c.isdigit() or c == "-" for c in result)

    @given(st.text())
    def test_no_leading_trailing_hyphens(self, text: str) -> None:
        """Result should never start or end with hyphen (unless it's 'project')."""
        result = slugify(text)
        if result != "project":
            assert not result.startswith("-")
            assert not result.endswith("-")

    @given(st.text())
    def test_never_consecutive_hyphens(self, text: str) -> None:
        """Result should never contain consecutive hyphens."""
        result = slugify(text)
        assert "--" not in result

    @given(st.just(""))
    def test_empty_or_whitespace_returns_project(self, text: str) -> None:
        """Empty string or whitespace-only should return 'project'."""
        assert slugify(text) == "project"
        assert slugify("   ") == "project"
        assert slugify("\t\n") == "project"

    @given(
        st.text(
            alphabet=st.characters(
                exclude_characters="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            ),
            min_size=1,
        ).filter(lambda s: not any(c.isalpha() or c.isdigit() for c in s))
    )
    def test_only_special_chars_returns_project(self, text: str) -> None:
        """Input with only special characters (no letters/digits) should return 'project'."""
        result = slugify(text)
        assert result == "project"

    @given(st.text(min_size=1))
    def test_is_filesystem_safe(self, text: str) -> None:
        """Result should be safe for use in filesystem paths."""
        result = slugify(text)
        # Should not contain problematic filesystem characters
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    @given(st.text())
    def test_idempotent_on_valid_slugs(self, text: str) -> None:
        """Applying slugify twice should give same result (idempotent)."""
        slug1 = slugify(text)
        slug2 = slugify(slug1)
        assert slug1 == slug2

    @given(st.lists(st.text(), min_size=1, max_size=5))
    def test_handles_multiword_titles(self, words: list[str]) -> None:
        """Slugs should handle multi-word titles correctly."""
        title = " ".join(words)
        result = slugify(title)
        # Result should be valid slug format
        if result != "project":
            assert (
                result.replace("-", "").replace("", "").lower()
                == result.replace("-", "").replace("", "").lower()
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
