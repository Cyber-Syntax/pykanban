"""unittest for main functions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pykanban.config import ConfigError, Settings
from pykanban.main import bootstrap_settings, ensure_config_dir, main

if TYPE_CHECKING:
    from pathlib import Path


class TestMain:
    """unit test for main parts like QApplication, MainWindow."""

    @patch("pykanban.main.QApplication")
    @patch("pykanban.main.bootstrap_settings")
    @patch("pykanban.main.KanbanApp")
    @patch("pykanban.main.MainWindow")
    @patch("pykanban.main.seed_template")
    def test_main_returns_app_exec(
        self,
        mock_seed_template,
        mock_main_window,
        mock_kanban_app_cls,
        mock_bootstrap,
        mock_qapplication,
        tmp_path: Path,
    ) -> None:
        # mock QApplication to return a fake app instance
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_qapplication.return_value = mock_app

        # mock settings and KanbanApp initialization
        mock_settings = Settings(projects_dir=tmp_path / "projects")
        mock_kanban_app = MagicMock()
        mock_kanban_app_cls.return_value = mock_kanban_app
        mock_bootstrap.return_value = (mock_settings, False)

        # call main
        result = main()

        # verify app.exec() was called and returned 0(success)
        assert result == 0
        mock_app.exec.assert_called_once()

    @patch("pykanban.main.QApplication")
    @patch("pykanban.main.bootstrap_settings")
    @patch("pykanban.main.KanbanApp")
    @patch("pykanban.main.MainWindow")
    @patch("pykanban.main.seed_template")
    def test_main_calls_seed_template_on_first_run(
        self,
        mock_seed_template,
        mock_window,
        mock_kanban_app_cls,
        mock_bootstrap,
        mock_qapplication,
        tmp_path: Path,
    ) -> None:

        # create mocks for QT app and window
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_qapplication.return_value = mock_app

        # setup mocks for settings and KanbanApp
        mock_settings = Settings(projects_dir=tmp_path / "projects")
        mock_kanban_app = MagicMock()
        mock_kanban_app_cls.return_value = mock_kanban_app
        mock_bootstrap.return_value = (
            mock_settings,
            True,
        )  # is_first_run=True

        # call main
        main()

        # check if seed_template was called
        mock_seed_template.assert_called_once_with(mock_settings)

    @patch("pykanban.main.QApplication")
    @patch("pykanban.main.bootstrap_settings")
    @patch("pykanban.main.KanbanApp")
    @patch("pykanban.main.MainWindow")
    @patch("pykanban.main.seed_template")
    def test_main_creates_window_and_state(
        self,
        mock_seed_template,
        mock_main_window,
        mock_kanban_app_cls,
        mock_bootstrap,
        mock_qapplication,
        tmp_path: Path,
    ) -> None:

        # create mocks for QT app
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_qapplication.return_value = mock_app

        # setup mocks for settings and KanbanApp
        mock_settings = Settings(projects_dir=tmp_path / "projects")
        mock_kanban_app = MagicMock()
        mock_bootstrap.return_value = (
            mock_settings,
            False,
        )  # is_first_run=False
        mock_kanban_app_cls.return_value = mock_kanban_app

        # call main
        main()

        # verify KanbanApp was instantiated with settings
        mock_kanban_app_cls.assert_called_once_with(mock_settings)
        # verify MainWindow was instantiated with the KanbanApp facade
        mock_main_window.assert_called_once_with(mock_kanban_app)
        # verify window was shown
        mock_main_window.return_value.show.assert_called_once()


class TestEnsureConfig:
    """unit tests for ensure_config_dir."""

    def test_ensure_config_dir_creates_dir(self, tmp_path: Path) -> None:
        """Create ~/.config if doesn't exists."""

        # patch CONFIG_DIR to a nonexistent path
        config_dir = tmp_path / "config"
        with patch("pykanban.main.CONFIG_DIR", config_dir):
            ensure_config_dir()

        # check if the directory was created
        assert config_dir.exists()

    def test_ensure_config_dir_does_nothing_if_exists(
        self, tmp_path: Path
    ) -> None:
        """Do nothing if ~/.config exists."""

        # create the config dir first
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with patch("pykanban.main.CONFIG_DIR", config_dir):
            ensure_config_dir()

        # no error, directory still exists
        assert config_dir.exists()


class TestSeedTemplate:
    """Unit tests for main.seed_template."""

    def test_copies_template_into_empty_projects_dir(
        self, tmp_path: Path
    ) -> None:
        """Copies the bundled learn-pykanban template on a fresh install."""
        from pykanban.main import seed_template

        # Create a fake template folder
        data_dir: Path = tmp_path / "data"
        template_src: Path = data_dir / "learn-pykanban"
        template_src.mkdir(parents=True)
        (template_src / "metadata.yml").write_text("project_id: p_demo\n")

        # create an empty projects folder
        projects_dir: Path = tmp_path / "projects"
        projects_dir.mkdir()
        settings = Settings(projects_dir=projects_dir)

        # call seed_template with the fake data
        with patch("pykanban.main._DATA_DIR", data_dir):
            seed_template(settings)

        # check if the template was copied
        assert (projects_dir / "learn-pykanban" / "metadata.yml").exists()

    def test_skips_when_project_already_exists(self, tmp_path: Path) -> None:
        """Doesn't move data when the user already has projects."""
        from pykanban.main import seed_template

        data_dir = tmp_path / "data"
        (data_dir / "learn-pykanban").mkdir(parents=True)
        (data_dir / "learn-pykanban" / "metadata.yml").write_text(
            "projects_id: p_demo\n"
        )

        # mock user deleted learn-pykanban and created their own project
        projects_dir = tmp_path / "projects"
        existing = projects_dir / "existing-project"
        existing.mkdir(parents=True)
        (existing / "metadata.yml").write_text("projects_id: p_existing\n")
        settings = Settings(projects_dir=projects_dir)

        with patch("pykanban.main._DATA_DIR", data_dir):
            seed_template(settings)

        # don't copy template if user already has existing project
        assert not (projects_dir / "learn-pykanban").exists()

    def test_raise_error_when_template_missing(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when the bundled template is absent."""
        from pykanban.main import seed_template

        # create a fake data dir with no template
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        settings = Settings(projects_dir=projects_dir)

        # Check if FileNotFoundError is raised
        with (
            patch("pykanban.main._DATA_DIR", data_dir),
            pytest.raises(FileNotFoundError, match="installed incorrectly"),
        ):
            seed_template(settings)


class TestBootstrapSettings:
    """Unit tests for main.bootstrap_settings."""

    def test_returns_saved_settings_without_dialog(
        self, tmp_path: Path
    ) -> None:

        # create a fake config file
        config_file = tmp_path / "config.yml"
        config_file.write_text(f"projects_dir: {tmp_path / 'projects'}\n")

        # call bootstrap_settings
        with (
            patch("pykanban.main.ensure_config_dir"),
            patch("pykanban.main.CONFIG_FILE", config_file),
            patch("pykanban.config.CONFIG_FILE", config_file),
        ):
            settings, is_first_run = bootstrap_settings()

        # check if settings are loaded and is_first_run is false
        assert not is_first_run
        assert isinstance(settings, Settings)

    def test_shows_dialog_on_first_run(self, tmp_path: Path) -> None:
        """Opens SettingsDialog and returns (settings, True) when no config exists."""

        # mock the SettingsDialog
        missing_config = tmp_path / "nonexistent.yml"
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_settings.return_value = Settings(
            projects_dir=tmp_path
        )

        with (
            patch("pykanban.main.ensure_config_dir"),
            patch("pykanban.main.CONFIG_FILE", missing_config),
            patch("pykanban.main.SettingsDialog", mock_dialog_cls),
        ):
            settings, is_first_run = bootstrap_settings()

        # check if dialog was shown and is_first_run is True
        assert is_first_run
        mock_dialog_cls.assert_called_once()

    def test_exits_when_dialog_is_rejected(self, tmp_path: Path) -> None:
        """Calls sys.exit(0) when the user cancels the first run dialog."""

        # mock the SettingsDialog to return False(user cancel)
        missing_config = tmp_path / "nonexistent.yml"
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False

        # check if sys.exit(0) called
        with (
            patch("pykanban.main.ensure_config_dir"),
            patch("pykanban.main.CONFIG_FILE", missing_config),
            patch("pykanban.main.SettingsDialog", mock_dialog_cls),
            pytest.raises(SystemExit),
        ):
            bootstrap_settings()

    @patch("pykanban.main.CONFIG_FILE")
    @patch("pykanban.main.ensure_config_dir")
    @patch("pykanban.main.load_settings")
    @patch("pykanban.main.QMessageBox.critical")
    @patch("pykanban.main.sys.exit")
    def test_corrupted_config_shows_error_and_exists(
        self,
        mock_exit,
        mock_critical,
        mock_load,
        mock_ensure,
        mock_config_file,
    ) -> None:
        """App shows a critical dialog and exist if the config file is corrupted."""
        # must raise systemexit to prevent freeze in test because of the dialog
        mock_exit.side_effect = SystemExit

        # config exists but loading fails
        mock_config_file.exists.return_value = True
        mock_load.side_effect = ConfigError("Test Config Error Message")

        # act: call it with side effect to raise SystemExit and catch it with pytest.raises
        with pytest.raises(SystemExit):
            bootstrap_settings()

        # assert: dialog should open, and app should exit with error code 1
        mock_critical.assert_called_once()

        # check that the error message is included in the dialog
        dialog_args = mock_critical.call_args[0]
        assert "Configuration Error" in dialog_args[1]
        assert "Test Config Error Message" in dialog_args[2]

        mock_exit.assert_called_once_with(1)

    @patch("pykanban.main.CONFIG_FILE")
    @patch("pykanban.main.ensure_config_dir")
    @patch("pykanban.main.SettingsDialog")
    @patch("pykanban.main.sys.exit")
    def test_dialog_cancellation_exits_app(
        self, mock_exit, mock_dialog_cls, mock_ensure, mock_config_file
    ) -> None:
        """If the user closes/cancels the first-run settings dialog, the app exits gracefully."""
        mock_exit.side_effect = SystemExit
        # Arrange: config file doesn't exist
        mock_config_file.exists.return_value = False

        # Setup mock dialog behavior (user rejects/cancels)
        mock_dialog_instance = mock_dialog_cls.return_value
        mock_dialog_instance.exec.return_value = False

        # Act
        with pytest.raises(SystemExit):
            bootstrap_settings()

        # Assert: Application gracefully exits with 0
        mock_exit.assert_called_once_with(0)

    @patch("pykanban.main.CONFIG_FILE")
    @patch("pykanban.main.ensure_config_dir")
    @patch("pykanban.main.SettingsDialog")
    def test_missing_config_shows_settings_dialog(
        self, mock_dialog_cls, mock_ensure, mock_config_file
    ) -> None:
        """First run (missing config) prompts the dialog and returns settings."""
        # Arrange
        mock_config_file.exists.return_value = False

        # Setup mock dialog behavior (user accepts)
        mock_dialog_instance = mock_dialog_cls.return_value
        mock_dialog_instance.exec.return_value = True

        expected_settings = Settings()
        mock_dialog_instance.get_settings.return_value = expected_settings

        # Act
        settings, is_first_run = bootstrap_settings()

        # Assert
        mock_dialog_instance.exec.assert_called_once()
        assert settings is expected_settings
        assert is_first_run is True
