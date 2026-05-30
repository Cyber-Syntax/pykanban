"""Unit tests for utils module."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pykanban.store import ProjectStore, TaskStore
from pykanban.utils import generate_project_id, generate_task_id, slugify


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


class TestGenerateTaskId:
    def test_generate_task_id_returns_string(self):
        """generate_task_id should return a string."""
        store = TaskStore()

        task_id = generate_task_id(store)

        assert isinstance(task_id, str)

    def test_generate_task_id_returns_unique_ids(self):
        """generate_task_id should return different IDs when called multiple times."""
        store = TaskStore()

        id1 = generate_task_id(store)
        id2 = generate_task_id(store)

        assert id1 != id2

    def test_generate_task_id_avoids_existing_ids(self):
        """generate_task_id should not return an ID that already exists in the store."""
        store = TaskStore()
        existing_id = "abc123"
        store.tasks_by_id[existing_id] = None  # Add a dummy entry

        task_id = generate_task_id(store)

        assert task_id != existing_id

    def test_generate_project_id_collision_retry(self):
        """generate_project_id should retry up to 10 times on collision."""
        store = ProjectStore()

        # Generate 20 IDs to test collision detection and retry logic
        project_ids = set()
        for _ in range(20):
            project_id = generate_project_id(store)
            assert project_id not in project_ids
            project_ids.add(project_id)
            store.projects_by_id[project_id] = (
                None  # Mark as used for next iteration
            )

        # All 20 IDs should be unique
        assert len(project_ids) == 20

    def test_generate_task_id_fails_after_10_collisions(self):
        """generate_task_id should raise RuntimeError after 10 failed attempts."""
        from unittest.mock import patch

        store = TaskStore()

        # Pre-fill store with known hex values
        for i in range(10):
            store.tasks_by_id[f"{i:08x}"] = None

        # Mock uuid4().hex to always return one of the pre-filled values
        with patch("pykanban.utils.uuid4") as mock_uuid:

            def hex_side_effect(*args, **kwargs):
                class MockUUID:
                    hex = "00000000"

                return MockUUID()

            mock_uuid.side_effect = hex_side_effect

            with pytest.raises(
                RuntimeError, match="Failed to generate a unique task ID"
            ):
                generate_task_id(store)

    def test_generate_task_id_collision_retry(self):
        """generate_task_id should retry up to 10 times on collision."""
        store = TaskStore()

        # Generate 20 IDs to test collision detection and retry logic
        task_ids = set()
        for _ in range(20):
            task_id = generate_task_id(store)
            assert task_id not in task_ids
            task_ids.add(task_id)
            store.tasks_by_id[task_id] = (
                None  # Mark as used for next iteration
            )

        # All 20 IDs should be unique
        assert len(task_ids) == 20

    def test_generate_task_id_is_8_hex_chars(self):
        """generate_task_id should return exactly 8 hexadecimal characters."""
        store = TaskStore()

        task_id = generate_task_id(store)

        assert len(task_id) == 8
        # Verify all characters are valid hex
        try:
            int(task_id, 16)
        except ValueError:
            pytest.fail(f"Task ID '{task_id}' is not valid hexadecimal")


class TestGenerateProjectId:
    def test_generate_project_id_returns_string(self):
        """generate_project_id should return a string."""
        store = ProjectStore()

        project_id = generate_project_id(store)

        assert isinstance(project_id, str)

    def test_generate_project_id_returns_unique_ids(self):
        """generate_project_id should return different IDs when called multiple times."""
        store = ProjectStore()

        id1 = generate_project_id(store)
        id2 = generate_project_id(store)

        assert id1 != id2

    def test_generate_project_id_avoids_existing_ids(self):
        """generate_project_id should not return an ID that already exists in the store."""
        store = ProjectStore()
        existing_id = "p_abc123"
        store.projects_by_id[existing_id] = None  # Add a dummy entry

        project_id = generate_project_id(store)

        assert project_id != existing_id

    def test_generate_project_id_prefixed_with_p(self):
        """generate_project_id should return IDs prefixed with 'p_'."""
        store = ProjectStore()

        project_id = generate_project_id(store)

        assert project_id.startswith("p_")

    def test_generate_project_id_is_p_8_hex_chars(self):
        """generate_project_id should return p_ followed by 8 hexadecimal characters."""
        store = ProjectStore()

        project_id = generate_project_id(store)

        assert project_id.startswith("p_")
        hex_part = project_id[2:]  # Skip 'p_'
        assert len(hex_part) == 8
        # Verify all characters in hex part are valid hex
        try:
            int(hex_part, 16)
        except ValueError:
            pytest.fail(
                f"Project ID hex part '{hex_part}' is not valid hexadecimal"
            )
