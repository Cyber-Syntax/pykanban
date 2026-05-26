"""Config module unit tests for PyKanban."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pykanban.config import Settings, load_settings, save_settings


class TestLoadSettings:
    """Unit tests for config.load_settings."""

    def test_returns_defaults_when_no_config_file(
        self, tmp_path: Path
    ) -> None:
        """Returns the default Settings when the config file does not exist."""
        with patch("pykanban.config.CONFIG_FILE", tmp_path / "missing.yml"):
            result = load_settings()
        assert result.projects_dir == Settings().projects_dir

    def test_reads_projects_dir_from_file(self, tmp_path: Path) -> None:
        """Picks up projects_dir from an existing config YAML file."""
        expected = tmp_path / "my-projects"
        config_file = tmp_path / "config.yml"
        config_file.write_text(f"projects_dir: {expected}\n")

        with patch("pykanban.config.CONFIG_FILE", config_file):
            result = load_settings()

        assert result.projects_dir == expected.resolve()


class TestSaveSettings:
    """Unit tests for config.save_settings."""

    def test_creates_config_dir_and_file(self, tmp_path: Path) -> None:
        """Creates the config directory and writes a YAML file."""
        config_dir = tmp_path / ".config" / "pykanban"
        config_file = config_dir / "config.yml"
        settings = Settings(projects_dir=tmp_path / "projects")

        with (
            patch("pykanban.config.CONFIG_DIR", config_dir),
            patch("pykanban.config.CONFIG_FILE", config_file),
        ):
            save_settings(settings)

        assert config_file.exists()
        assert "projects_dir" in config_file.read_text()

    def test_creates_projects_directory(self, tmp_path: Path) -> None:
        """Also creates the projects_dir folder when it does not exist."""
        config_dir = tmp_path / ".config" / "pykanban"
        config_file = config_dir / "config.yml"
        projects_dir = tmp_path / "new-projects"
        settings = Settings(projects_dir=projects_dir)

        with (
            patch("pykanban.config.CONFIG_DIR", config_dir),
            patch("pykanban.config.CONFIG_FILE", config_file),
        ):
            save_settings(settings)

        assert projects_dir.exists()