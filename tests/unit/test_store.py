"""Unit tests for store.py module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pykanban.config import Settings
from pykanban.models import Status
from pykanban.store import AppState
from tests.unit.conftest import make_project, make_task


class TestAppStateStartupScan:
    """Integration tests for AppState.startup_scan."""

    def test_loads_projects_and_tasks_from_disk(self, tmp_path: Path) -> None:
        """Populates stores by scanning a real directory tree."""
        settings = Settings(projects_dir=tmp_path / "projects")
        settings.projects_dir.mkdir(parents=True)

        proj_folder = settings.projects_dir / "p1"
        proj_folder.mkdir()
        proj = make_project(proj_folder, project_id="p_scan1234")
        task = make_task(id="scan1111", status=Status.TODO)

        # Write actual files via the model write methods
        proj.write()
        task.write(proj_folder / f"scan-task--{task.id}.md")

        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)

        assert "p_scan1234" in state.projects.projects_by_id
        assert "scan1111" in state.tasks.tasks_by_id

    def test_handles_empty_projects_dir(self, tmp_path: Path) -> None:
        """Does not crash when the projects directory contains no project folders."""
        settings = Settings(projects_dir=tmp_path / "projects")
        settings.projects_dir.mkdir()
        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)
        assert state.projects.projects_by_id == {}

    def test_handles_nonexistent_projects_dir(self, tmp_path: Path) -> None:
        """Returns gracefully when the projects directory does not exist yet."""
        settings = Settings(projects_dir=tmp_path / "does-not-exist")
        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)  # must not raise

    def test_bad_metadata_is_recorded_as_error(self, tmp_path: Path) -> None:
        """Records a ParseError for project folders with invalid metadata.yml."""
        settings = Settings(projects_dir=tmp_path / "projects")
        settings.projects_dir.mkdir(parents=True)
        bad_folder = settings.projects_dir / "bad-project"
        bad_folder.mkdir()
        (bad_folder / "metadata.yml").write_text("not: valid: yaml: [unclosed")

        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)

        assert len(state.errors) > 0

    def test_nonexistent_projects_dir_is_recorded_as_error(
        self, tmp_path: Path
    ) -> None:
        """Records a ParseError when a projects_dir is missing during scan.

        This simulates the case where the directory was deleted/removed
        by external process.
        """

        # setup config.yml to point projects_dir
        settings = Settings(projects_dir=tmp_path / "missing-projects")

        # do not create the projects_dir to simulate missing directory
        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)

        # assert ParseError recorded for missing projects_dir
        assert len(state.errors) > 0
        assert any(
            "Projects directory not found" in e.reason for e in state.errors
        )

        # assert projects_dir is created after error to allow recovery
        assert settings.projects_dir.exists()

    def test_empty_projects_dir_adds_error(self, tmp_path: Path) -> None:
        """Adds a error when projects_dir exists but is empty."""
        settings = Settings(projects_dir=tmp_path / "empty-projects")
        settings.projects_dir.mkdir(parents=True)

        state = AppState.create(settings)
        state.startup_scan(settings.projects_dir)

        assert len(state.errors) == 1
        assert any("No projects found" in e.reason for e in state.errors)

    @patch("pykanban.store.Path.mkdir")
    @patch("pykanban.store.QMessageBox.critical")
    @patch("pykanban.store.sys.exit")
    def test_startup_scan_permission_error_and_exists(
        self, mock_exit, mock_critical, mock_mkdir_error, tmp_path: Path
    ) -> None:
        """Records a critical error if the app does not have permissions to read/write the projects_dir."""
        settings = Settings(projects_dir=tmp_path / "no-permissions")
        state = AppState.create(settings)

        mock_exit.side_effect = SystemExit

        # patch mkdir to raise permission error
        mock_mkdir_error.side_effect = PermissionError("Permission denied")

        # call it with side effect to raise systemexit
        with pytest.raises(SystemExit):
            state.startup_scan(settings.projects_dir)

        mock_critical.assert_called_once()
        mock_exit.assert_called_once_with(1)
