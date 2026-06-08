"""Unit tests for project_utils module."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from pykanban.error import ConflictWarning, ParseError
from pykanban.models import Project, Status, Task
from pykanban.project_utils import (
    choose_active_project,
    empty_column_order,
    find_all_project_conflicts,
    find_sync_conflicts,
    load_project_tasks,
    reconcile_order,
)


class TestEmptyColumnOrder:
    """Tests for empty_column_order()."""

    def test_returns_empty_dict_with_all_statuses(self):
        """Should return dict with all Status values as keys."""
        result = empty_column_order()

        assert isinstance(result, dict)
        assert set(result.keys()) == {
            Status.BACKLOG.value,
            Status.TODO.value,
            Status.DOING.value,
            Status.DONE.value,
        }

    def test_all_columns_empty_lists(self):
        """Should return empty lists for each status."""
        result = empty_column_order()

        for status_value, tasks in result.items():
            assert isinstance(tasks, list)
            assert len(tasks) == 0


class TestChooseActiveProject:
    """Tests for choose_active_project()."""

    def test_empty_dict_returns_none(self):
        """Should return None if no projects exist."""
        result = choose_active_project({})
        assert result is None

    def test_single_non_archived_project(self):
        """Should return the only non-archived project."""
        project = Mock(spec=Project, archived=False, project_id="p_123")
        projects_dict = {"p_123": project}

        result = choose_active_project(projects_dict)

        assert result == project

    def test_prefers_non_archived_over_archived(self):
        """Should prefer non-archived projects."""
        archived_project = Mock(
            spec=Project, archived=True, project_id="p_arch"
        )
        active_project = Mock(
            spec=Project, archived=False, project_id="p_active"
        )
        projects_dict = {
            "p_arch": archived_project,
            "p_active": active_project,
        }

        result = choose_active_project(projects_dict)

        assert result == active_project

    def test_all_archived_returns_first(self):
        """Should return first project if all are archived."""
        project1 = Mock(spec=Project, archived=True, project_id="p_1")
        project2 = Mock(spec=Project, archived=True, project_id="p_2")
        # Use list iteration order for consistency
        projects_dict = {"p_1": project1, "p_2": project2}

        result = choose_active_project(projects_dict)

        assert result in (project1, project2)

    def test_multiple_non_archived_returns_first_found(self):
        """Should return first non-archived project when multiple exist."""
        active1 = Mock(spec=Project, archived=False, project_id="p_1")
        active2 = Mock(spec=Project, archived=False, project_id="p_2")
        projects_dict = {"p_1": active1, "p_2": active2}

        result = choose_active_project(projects_dict)

        assert result == active1


class TestFindSyncConflicts:
    """Tests for find_sync_conflicts()."""

    def test_no_conflicts_returns_empty_list(self):
        """Should return empty list if no conflict files exist."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)

            result = find_sync_conflicts(folder)

            assert result == []

    def test_finds_single_conflict_file(self):
        """Should find a single conflict file."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            conflict_file = folder / ".sync-conflict-1234"
            conflict_file.touch()

            result = find_sync_conflicts(folder)

            assert len(result) == 1
            assert isinstance(result[0], ConflictWarning)
            assert result[0].path == conflict_file

    def test_finds_multiple_conflict_files(self):
        """Should find all conflict files in folder."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            conflict1 = folder / ".sync-conflict-abc123"
            conflict2 = folder / ".sync-conflict-def456"
            conflict1.touch()
            conflict2.touch()

            result = find_sync_conflicts(folder)

            assert len(result) == 2
            paths = {w.path for w in result}
            assert conflict1 in paths
            assert conflict2 in paths

    def test_finds_conflicts_in_subfolders(self):
        """Should find conflict files in nested subdirectories."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            subfolder = folder / "subdir"
            subfolder.mkdir()
            conflict_file = subfolder / ".sync-conflict-nested"
            conflict_file.touch()

            result = find_sync_conflicts(folder)

            assert len(result) == 1
            assert result[0].path == conflict_file

    def test_ignores_non_conflict_files(self):
        """Should ignore files that don't match conflict pattern."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            regular_file = folder / "regular.md"
            regular_file.touch()
            not_conflict = folder / "sync-conflict-abc"  # missing leading dot
            not_conflict.touch()

            result = find_sync_conflicts(folder)

            assert result == []


class TestFindAllProjectConflicts:
    """Tests for find_all_project_conflicts()."""

    def test_empty_projects_dict_returns_empty_list(self):
        """Should return empty list if no projects exist."""
        result = find_all_project_conflicts({})
        assert result == []

    def test_single_project_no_conflicts(self):
        """Should return empty list if project has no conflicts."""
        with TemporaryDirectory() as tmpdir:
            project = Mock(
                spec=Project,
                folder_path=Path(tmpdir),
                project_id="p_test",
            )
            projects_dict = {"p_1": project}

            result = find_all_project_conflicts(projects_dict)

            assert result == []

    def test_aggregates_conflicts_from_multiple_projects(self):
        """Should aggregate conflicts from all projects."""
        with TemporaryDirectory() as tmpdir1:
            with TemporaryDirectory() as tmpdir2:
                folder1 = Path(tmpdir1)
                folder2 = Path(tmpdir2)

                # Create conflict in first project
                (folder1 / ".sync-conflict-1").touch()
                # Create conflicts in second project
                (folder2 / ".sync-conflict-2").touch()
                (folder2 / ".sync-conflict-3").touch()

                project1 = Mock(
                    spec=Project, project_id="p_1", folder_path=folder1
                )
                project2 = Mock(
                    spec=Project, project_id="p_2", folder_path=folder2
                )
                projects_dict = {"p_1": project1, "p_2": project2}

                result = find_all_project_conflicts(projects_dict)

                assert len(result) == 3


class TestLoadProjectTasks:
    """Tests for load_project_tasks()."""

    def test_empty_project_folder(self):
        """Should return empty result for project with no task files."""
        with TemporaryDirectory() as tmpdir:
            project = Mock(
                spec=Project, folder_path=Path(tmpdir), project_id="p_1"
            )

            result = load_project_tasks(project)

            assert result.loaded_task_ids == set()
            assert result.parse_errors == []
            assert result.updated_mtime_cache == {}

    def test_seeds_mtime_cache_from_files(self):
        """Should populate mtime cache for successfully loaded files."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            task_file = folder / "task.md"
            task_file.write_text("# Task")

            project = Mock(spec=Project, folder_path=folder, project_id="p_1")

            with patch("pykanban.project_utils.parse_task") as mock_parse_task:
                task = Mock(spec=Task, id="task_123")
                mock_parse_task.return_value = task

                result = load_project_tasks(project)

                assert task_file in result.updated_mtime_cache
                assert isinstance(result.updated_mtime_cache[task_file], float)

    def test_collects_parse_errors(self):
        """Should collect ParseError results without raising."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            bad_file = folder / "bad.md"
            bad_file.write_text("content")

            project = Mock(spec=Project, folder_path=folder, project_id="p_1")

            with patch("pykanban.project_utils.parse_task") as mock_parse_task:
                error = ParseError(path=bad_file, reason="Invalid YAML")
                mock_parse_task.return_value = error

                result = load_project_tasks(project)

                assert error in result.parse_errors
                assert result.loaded_task_ids == set()

    def test_collects_loaded_task_ids(self):
        """Should collect IDs of successfully loaded tasks."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            file1 = folder / "task1.md"
            file2 = folder / "task2.md"
            file1.write_text("# Task 1")
            file2.write_text("# Task 2")

            project = Mock(spec=Project, folder_path=folder, project_id="p_1")

            with patch("pykanban.project_utils.parse_task") as mock_parse_task:
                task1 = Mock(spec=Task, id="t_001")
                task2 = Mock(spec=Task, id="t_002")
                mock_parse_task.side_effect = [task1, task2]

                result = load_project_tasks(project)

                assert result.loaded_task_ids == {"t_001", "t_002"}

    def test_preserves_existing_mtime_cache(self):
        """Should preserve and update existing mtime cache."""
        with TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            task_file = folder / "task.md"
            task_file.write_text("# Task")

            existing_cache = {Path("/some/other/file.md"): 1234.5}
            project = Mock(spec=Project, folder_path=folder, project_id="p_1")

            with patch("pykanban.project_utils.parse_task") as mock_parse_task:
                task = Mock(spec=Task, id="t_123")
                mock_parse_task.return_value = task

                result = load_project_tasks(project, existing_cache)

                assert (
                    Path("/some/other/file.md") in result.updated_mtime_cache
                )
                assert task_file in result.updated_mtime_cache

    def test_handles_mtime_read_errors_gracefully(self):
        """Should skip files that disappear during stat call."""
        mock_file = Mock(spec=Path)
        mock_file.stat.side_effect = OSError("File not found")

        mock_folder = Mock(spec=Path)
        mock_folder.rglob.return_value = [mock_file]

        project = Mock(spec=Project, folder_path=mock_folder, project_id="p_1")

        with patch("pykanban.project_utils.parse_task") as mock_parse_task:
            task = Mock(spec=Task, id="t_123")
            mock_parse_task.return_value = task

            result = load_project_tasks(project)

            # Should still load the task, just without mtime
            assert result.loaded_task_ids == {"t_123"}
            assert mock_file not in result.updated_mtime_cache


class TestReconcileOrder:
    def test_removes_stale_ids(self):
        column_order = {"todo": ["a", "stale"], "doing": []}
        known_ids = {"a"}
        tasks_by_id = {"a": Mock(status=Status.TODO)}

        result = reconcile_order(column_order, known_ids, tasks_by_id)

        assert result["todo"] == ["a"]
        assert result["doing"] == []

    def test_appends_missing_ids_to_task_status(self):
        column_order = {"todo": [], "doing": []}
        known_ids = {"b"}
        tasks_by_id = {"b": Mock(status=Status.DOING)}

        result = reconcile_order(column_order, known_ids, tasks_by_id)

        assert result["doing"] == ["b"]

    def test_is_pure_and_does_not_mutate_inputs(self):
        column_order = {
            "backlog": ["a"],
            "todo": ["b", "stale"],
            "doing": [],
            "done": [],
        }
        original = {
            "backlog": ["a"],
            "todo": ["b", "stale"],
            "doing": [],
            "done": [],
        }
        known_ids = {"a", "b"}
        tasks_by_id = {
            "a": Mock(status=Status.BACKLOG),
            "b": Mock(status=Status.TODO),
        }

        result = reconcile_order(column_order, known_ids, tasks_by_id)

        assert column_order == original
        assert result is not column_order
        assert result["todo"] == ["b"]

    def test_ignores_known_ids_missing_in_tasks_lookup(self):
        column_order = {"todo": []}
        known_ids = {"ghost"}
        tasks_by_id = {}

        result = reconcile_order(column_order, known_ids, tasks_by_id)

        assert result == {"todo": []}

    def test_creates_missing_status_bucket_when_appending(self):
        column_order = {"todo": []}
        known_ids = {"a"}
        tasks_by_id = {"a": Mock(status=Status.DONE)}

        result = reconcile_order(column_order, known_ids, tasks_by_id)

        assert result["done"] == ["a"]
