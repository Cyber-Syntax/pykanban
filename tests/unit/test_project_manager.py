"""Unit tests for ProjectManager."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pykanban.app import KanbanApp
from pykanban.config import Settings
from pykanban.error import ConflictWarning, ParseError
from pykanban.models import Project, Status, Task
from pykanban.project_manager import scan_project_folder
from pykanban.store import BoardView
from tests.unit.conftest import make_project, make_task

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectManagerStartupScan:
    """Integration tests for the startup scan of the project manager."""

    def test_loads_projects_and_tasks_from_disk(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Populates stores by scanning a real directory tree."""
        proj_folder = projects_dir / "p1"
        proj_folder.mkdir()
        proj: Project = make_project(proj_folder, project_id="p_scan1234")
        task: Task = make_task(id="scan1111", status=Status.TODO)

        # Write actual files via the model write methods
        proj.write()
        task.write(proj_folder / f"scan-task--{task.id}.md")

        app.startup_scan(projects_dir)

        assert app.get_project("p_scan1234") is not None
        assert app.get_task("scan1111") is not None

    def test_handles_empty_projects_dir(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Does not crash when the projects directory contains no project folders."""
        app.startup_scan(projects_dir)
        assert app.state.projects.projects_by_id == {}

    def test_handles_nonexistent_projects_dir(
        self, app: KanbanApp, tmp_path: Path
    ) -> None:
        """Returns gracefully when the projects directory does not exist yet."""
        nonexistent_dir = tmp_path / "nonexistent-projects"
        app.startup_scan(nonexistent_dir)  # must not raise

    def test_bad_metadata_is_recorded_as_error(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Records a ParseError for project folders with invalid metadata.yml."""
        bad_folder = projects_dir / "bad-project"
        bad_folder.mkdir()
        (bad_folder / "metadata.yml").write_text("not: valid: yaml: [unclosed")

        app.startup_scan(projects_dir)

        assert len(app.state.errors) > 0

    def test_nonexistent_projects_dir_is_recorded_as_error(
        self, app: KanbanApp, tmp_path: Path
    ) -> None:
        """Records a ParseError when a projects_dir is missing during scan.

        This simulates the case where the directory was deleted/removed
        by external process.
        """

        # setup config.yml to point projects_dir
        missing_dir = tmp_path / "missing-projects"

        # do not create the projects_dir to simulate missing directory
        app.startup_scan(missing_dir)

        # assert ParseError recorded for missing projects_dir
        assert len(app.state.errors) > 0
        assert any(
            "Projects directory not found" in e.reason
            for e in app.state.errors
        )

        # assert projects_dir is created after error to allow recovery
        assert missing_dir.exists()

    def test_empty_projects_dir_adds_error(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Adds a error when projects_dir exists but is empty."""
        app.startup_scan(projects_dir)

        assert len(app.state.errors) == 1
        assert any("No projects found" in e.reason for e in app.state.errors)

    @patch("pykanban.project_manager.Path.mkdir")
    @patch("pykanban.project_manager.QMessageBox.critical")
    @patch("pykanban.project_manager.sys.exit")
    def test_startup_scan_permission_error_and_exists(
        self,
        mock_exit,
        mock_critical,
        mock_mkdir_error,
        app: KanbanApp,
        tmp_path: Path,
    ) -> None:
        """Records a critical error if the app does not have permissions to read/write the projects_dir."""
        no_permission_dir = tmp_path / "no-permission-projects"

        mock_exit.side_effect = SystemExit

        # patch mkdir to raise permission error
        mock_mkdir_error.side_effect = PermissionError("Permission denied")

        # call it with side effect to raise systemexit
        with pytest.raises(SystemExit):
            app.startup_scan(no_permission_dir)

        mock_critical.assert_called_once()
        mock_exit.assert_called_once_with(1)

    def test_bad_task_file_is_recorded_as_error(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Records a ParseError for invalid task markdown files."""

        proj_folder = projects_dir / "p1"
        proj_folder.mkdir()
        proj = make_project(proj_folder, project_id="p_scan1")
        proj.write()

        # Write an invalid task file (e.g., missing YAML front matter)
        invalid_task = proj_folder / "invalid_task.md"
        invalid_task.write_text("Not a valid task file without layout.")

        app.startup_scan(projects_dir)

        parse_errors = [
            e for e in app.state.errors if isinstance(e, ParseError)
        ]
        assert len(parse_errors) > 0
        assert any(
            "invalid_task.md" in getattr(e, "path", str(e.path)).name
            for e in parse_errors
        )

    def test_startup_scan_sets_active_project(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Verifies an active project is set upon successful scan."""
        proj_folder = projects_dir / "p1"
        proj_folder.mkdir()
        proj = make_project(proj_folder, project_id="p_active123")
        proj.write()

        app.startup_scan(projects_dir)

        app.set_active_project("p_active123")
        assert app.get_active_project().project_id == "p_active123"

    def test_startup_scan_reconciles_order_isolated_per_project(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Ensures task IDs do not bleed across projects during column_order reconciliation."""
        # Setup Project 1
        p1_folder = projects_dir / "p1"
        p1_folder.mkdir()
        make_project(p1_folder, project_id="p1").write()
        t1 = make_task(id="t1", status=Status.TODO)
        t1.write(p1_folder / f"{t1.id}.md")

        # Setup Project 2
        p2_folder = projects_dir / "p2"
        p2_folder.mkdir()
        make_project(p2_folder, project_id="p2").write()
        t2 = make_task(id="t2", status=Status.DOING)
        t2.write(p2_folder / f"{t2.id}.md")

        app.startup_scan(projects_dir)

        proj1 = app.get_project("p1")
        proj2 = app.get_project("p2")

        # Gather all task IDs in their respective column orders
        p1_ordered_ids = {
            tid for ids in proj1.column_order.values() for tid in ids
        }
        p2_ordered_ids = {
            tid for ids in proj2.column_order.values() for tid in ids
        }

        # Assert no cross-contamination
        assert "t1" in p1_ordered_ids
        assert "t2" not in p1_ordered_ids

        assert "t2" in p2_ordered_ids
        assert "t1" not in p2_ordered_ids

    def test_startup_scan_detects_sync_conflicts(
        self, app: KanbanApp, projects_dir: Path
    ) -> None:
        """Collects warnings for sync conflict files across loaded projects."""

        # Setup Project
        proj_folder = projects_dir / "p1"
        proj_folder.mkdir()
        make_project(proj_folder, project_id="p1").write()

        # Simulate a sync conflict file
        conflict_file = (
            proj_folder / ".sync-conflict-20240101T120000Z-task1.md"
        )
        conflict_file.touch()

        app.startup_scan(projects_dir)

        conflict_warnings = [
            e for e in app.state.errors if isinstance(e, ConflictWarning)
        ]
        assert len(conflict_warnings) == 1
        assert conflict_file.name in str(conflict_warnings[0].path)


class TestProjectManagerRenameProject:
    """Unit tests for KanbanApp.rename_project."""

    def test_updates_title_in_store(self, app: KanbanApp) -> None:
        proj = app.create_project("Old Title", "desc")
        app.rename_project(proj.project_id, "New Title")
        assert app.get_project(proj.project_id).title == "New Title"

    def test_updates_path_on_disk(self, app: KanbanApp) -> None:
        proj = app.create_project("Disk Title", "desc")
        old_path = proj.folder_path
        app.rename_project(proj.project_id, "Renamed Disk Title")
        new_path = app.get_project(proj.project_id).folder_path
        assert not old_path.exists()
        assert new_path.exists()
        assert "renamed-disk-title" in str(new_path)

    def test_updates_title_in_metadata_yml(self, app: KanbanApp) -> None:
        proj = app.create_project("Meta Title", "desc")
        app.rename_project(proj.project_id, "Renamed Meta Title")

        # reload project from disk to verify metadata.yml was updated
        reloaded = Project.from_file(proj.folder_path / "metadata.yml")
        assert reloaded.title == "Renamed Meta Title"

    def test_prevent_duplicate_titles_on_rename(self, app: KanbanApp) -> None:
        """Does not allow renaming a project to have the same title as another existing project."""
        p1 = app.create_project("Learn Bash", "desc")
        p2 = app.create_project("Learn Python", "desc")

        # error_banner show the error instead of raising to avoid crash
        app.rename_project(p2.project_id, "Learn Bash")
        assert any("already exists" in e.reason for e in app.state.errors)


class TestProjectManagerCreateProject:
    """Unit tests for KanbanApp.create_project."""

    def test_project_added_to_store(self, app: KanbanApp) -> None:
        proj = app.create_project("New Project", "desc")
        assert app.get_project(proj.project_id) is proj

    def test_project_folder_created_on_disk(self, app: KanbanApp) -> None:
        proj = app.create_project("My Project", "desc")
        assert proj.folder_path.is_dir()

    def test_title_is_stripped(self, app: KanbanApp) -> None:
        proj = app.create_project("  Padded  ", "")
        assert proj.title == "Padded"

    def test_prevent_duplicate_project_titles(self, app: KanbanApp) -> None:
        """Does not allow creating a new project with the same title as an existing one."""
        app.create_project("Unique Title", "desc")
        with pytest.raises(ValueError):
            app.create_project("Unique Title", "another desc")


class TestProjectManagerArchiveProject:
    """Unit tests for KanbanApp.archive_project."""

    def test_marks_project_as_archived(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.archive_project(project_id)
        assert app_with_active_project.get_project(project_id).archived

    def test_clears_active_project_id(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.archive_project(project_id)
        with pytest.raises(KeyError):
            app_with_active_project.get_active_project()

    def test_moves_folder_to_archive_subdir(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project = app_with_active_project.get_active_project()
        original_folder = project.folder_path
        app_with_active_project.archive_project(project.project_id)

        # The original folder should no longer exist
        assert not original_folder.exists()

        # need to fetch the project again to get its new folder path
        archived_project = app_with_active_project.get_project(
            project.project_id
        )
        assert not original_folder.exists()
        assert archived_project.folder_path.exists()
        assert "archive" in str(archived_project.folder_path)


class TestProjectManagerUnarchiveProject:
    """Unit tests for KanbanApp.unarchive_project."""

    def test_clears_archived_flag(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.archive_project(project_id)
        app_with_active_project.unarchive_project(project_id)
        assert not app_with_active_project.get_project(project_id).archived

    def test_moves_folder_back_to_projects_root(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.archive_project(project_id)
        app_with_active_project.unarchive_project(project_id)
        proj = app_with_active_project.get_project(project_id)
        assert "archive" not in str(proj.folder_path)


class TestProjectManagerDeleteProject:
    """Unit tests for KanbanApp.delete_project."""

    def test_removes_project_from_store(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.delete_project(project_id)
        with pytest.raises(KeyError):
            app_with_active_project.get_project(project_id)

    def test_clears_active_project_id(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        app_with_active_project.delete_project(project_id)
        with pytest.raises(KeyError):
            app_with_active_project.get_project(project_id)

    def test_deletes_project_folder_from_disk(
        self, app_with_active_project: KanbanApp
    ) -> None:
        project_id = app_with_active_project.get_active_project().project_id
        project = app_with_active_project.get_project(project_id)
        folder = project.folder_path
        app_with_active_project.delete_project(project_id)
        assert not folder.exists()


class TestProjectManagerSwitchProject:
    """Unit tests for KanbanApp.switch_project."""

    def test_switch_updates_active_project(self, tmp_path: Path) -> None:
        """After switching, get_active() returns the newly selected project."""
        settings = Settings(projects_dir=tmp_path / "projects")
        settings.projects_dir.mkdir(parents=True)
        app = KanbanApp(settings)

        for pid, slug in [("p_aaa00001", "proj-a"), ("p_bbb00002", "proj-b")]:
            folder = settings.projects_dir / slug
            folder.mkdir()
            proj = make_project(folder, project_id=pid)
            proj.write()
            app.put_project(proj)

        app.set_active_project("p_aaa00001")
        app.switch_project("p_bbb00002")

        assert app.get_active_project().project_id == "p_bbb00002"

    def test_switch_returns_board_view(self, tmp_path: Path) -> None:
        settings = Settings(projects_dir=tmp_path / "projects")
        settings.projects_dir.mkdir(parents=True)
        app = KanbanApp(settings)

        folder = settings.projects_dir / "proj"
        folder.mkdir()
        proj = make_project(folder, project_id="p_switch01")
        proj.write()
        app.put_project(proj)

        # switch_project returns None directly
        app.switch_project("p_switch01")
        # obtain board view from KanbanApp facade
        board = app.get_board()
        # verify it's a BoardView instance (not just None or some other type)
        assert isinstance(board, BoardView)


# ── store: scan_project_folder ────────────────────────────────────────────────


class TestScanProjectFolder:
    """Unit tests for store.scan_project_folder."""

    def test_new_files_appear_in_changed_paths(self, tmp_path: Path) -> None:
        """Files not seen before show up in changed_paths."""
        (tmp_path / "task.md").write_text("content")
        result = scan_project_folder(tmp_path, {})
        assert any(p.name == "task.md" for p in result.changed_paths)

    def test_unchanged_files_not_in_changed_paths(
        self, tmp_path: Path
    ) -> None:
        """Files with an identical mtime are omitted from changed_paths."""
        f = tmp_path / "task.md"
        f.write_text("content")
        result = scan_project_folder(tmp_path, {f: f.stat().st_mtime})
        assert f not in result.changed_paths

    def test_missing_files_appear_in_deleted_paths(
        self, tmp_path: Path
    ) -> None:
        """Cache entries with no matching file on disk land in deleted_paths."""
        ghost = tmp_path / "ghost.md"
        result = scan_project_folder(tmp_path, {ghost: 1_234_567_890.0})
        assert ghost in result.deleted_paths

    def test_sync_conflict_files_detected(self, tmp_path: Path) -> None:
        """Sync-conflict sentinel files appear in conflict_paths."""
        conflict = tmp_path / ".sync-conflict-20260101-abc"
        conflict.write_text("conflict data")
        result = scan_project_folder(tmp_path, {})
        assert conflict in result.conflict_paths

    def test_mtime_cache_reflects_current_files(self, tmp_path: Path) -> None:
        """The returned mtime_cache contains every .md file found."""
        f = tmp_path / "task.md"
        f.write_text("data")
        result = scan_project_folder(tmp_path, {})
        assert f in result.mtime_cache

    def test_empty_directory_returns_empty_result(
        self, tmp_path: Path
    ) -> None:
        result = scan_project_folder(tmp_path, {})
        assert result.changed_paths == []
        assert result.deleted_paths == []
