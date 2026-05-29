"""Tests for id_gen module."""

import pytest

from pykanban.store import (
    ProjectStore,
    TaskStore,
    generate_project_id,
    generate_task_id,
)


def test_generate_task_id_returns_string():
    """generate_task_id should return a string."""
    store = TaskStore()

    task_id = generate_task_id(store)

    assert isinstance(task_id, str)


def test_generate_task_id_returns_unique_ids():
    """generate_task_id should return different IDs when called multiple times."""
    store = TaskStore()

    id1 = generate_task_id(store)
    id2 = generate_task_id(store)

    assert id1 != id2


def test_generate_task_id_avoids_existing_ids():
    """generate_task_id should not return an ID that already exists in the store."""
    store = TaskStore()
    existing_id = "abc123"
    store.tasks_by_id[existing_id] = None  # Add a dummy entry

    task_id = generate_task_id(store)

    assert task_id != existing_id


def test_generate_project_id_returns_string():
    """generate_project_id should return a string."""
    store = ProjectStore()

    project_id = generate_project_id(store)

    assert isinstance(project_id, str)


def test_generate_project_id_returns_unique_ids():
    """generate_project_id should return different IDs when called multiple times."""
    store = ProjectStore()

    id1 = generate_project_id(store)
    id2 = generate_project_id(store)

    assert id1 != id2


def test_generate_project_id_avoids_existing_ids():
    """generate_project_id should not return an ID that already exists in the store."""
    store = ProjectStore()
    existing_id = "p_abc123"
    store.projects_by_id[existing_id] = None  # Add a dummy entry

    project_id = generate_project_id(store)

    assert project_id != existing_id


def test_generate_project_id_prefixed_with_p():
    """generate_project_id should return IDs prefixed with 'p_'."""
    store = ProjectStore()

    project_id = generate_project_id(store)

    assert project_id.startswith("p_")


def test_generate_task_id_is_8_hex_chars():
    """generate_task_id should return exactly 8 hexadecimal characters."""
    store = TaskStore()

    task_id = generate_task_id(store)

    assert len(task_id) == 8
    # Verify all characters are valid hex
    try:
        int(task_id, 16)
    except ValueError:
        pytest.fail(f"Task ID '{task_id}' is not valid hexadecimal")


def test_generate_project_id_is_p_8_hex_chars():
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


def test_generate_task_id_collision_retry():
    """generate_task_id should retry up to 10 times on collision."""
    store = TaskStore()

    # Generate 20 IDs to test collision detection and retry logic
    task_ids = set()
    for _ in range(20):
        task_id = generate_task_id(store)
        assert task_id not in task_ids
        task_ids.add(task_id)
        store.tasks_by_id[task_id] = None  # Mark as used for next iteration

    # All 20 IDs should be unique
    assert len(task_ids) == 20


def test_generate_project_id_collision_retry():
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


def test_generate_task_id_fails_after_10_collisions():
    """generate_task_id should raise RuntimeError after 10 failed attempts."""
    from unittest.mock import patch

    store = TaskStore()

    # Pre-fill store with known hex values
    for i in range(10):
        store.tasks_by_id[f"{i:08x}"] = None

    # Mock uuid4().hex to always return one of the pre-filled values
    with patch("pykanban.store.uuid4") as mock_uuid:

        def hex_side_effect(*args, **kwargs):
            class MockUUID:
                hex = "00000000"

            return MockUUID()

        mock_uuid.side_effect = hex_side_effect

        with pytest.raises(
            RuntimeError, match="Failed to generate a unique task ID"
        ):
            generate_task_id(store)
