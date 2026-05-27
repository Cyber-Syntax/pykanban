"""Config module unit tests for PyKanban."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pykanban.config import ConfigError, Settings, load_settings, save_settings


class TestLoadSettings:
    """Unit tests for config.load_settings."""

    def test_load_settings_raises_on_non_dict(self, tmp_path: Path) -> None:
        """Valid YAML that isn't a mapping raises ConfigError."""
        from pykanban.config import ConfigError, load_settings

        config_file = tmp_path / "config.yml"
        # Valid YAML but a list, not a dict
        config_file.write_text("- item1\n- item2\n")

        with (
            patch("pykanban.config.CONFIG_FILE", config_file),
            pytest.raises(ConfigError, match="doesn't contain mapping"),
        ):
            load_settings()

    def test_load_settings_raises_on_yaml_error(self, tmp_path: Path) -> None:
        """Malformed YAML causes a ConfigError with a helpful message."""
        config_file = tmp_path / "config.yml"
        # invalid yaml that wil trip the parser
        config_file.write_text("]\n")

        with (
            patch("pykanban.config.CONFIG_FILE", config_file),
            pytest.raises(ConfigError, match="is not valid YAML"),
        ):
            load_settings()

    def test_load_settings_raises_on_wrong_keys(self, tmp_path: Path) -> None:
        """Valid YAML but wrong keys raises ConfigError."""
        config_file = tmp_path / "config.yml"
        # Valid YAML but missing the expected 'projects_dir' key
        config_file.write_text("$0}projects_dir: /some/path\n")

        with (
            patch("pykanban.config.CONFIG_FILE", config_file),
            pytest.raises(ConfigError, match="doesn't contain mapping"),
        ):
            load_settings()

    def test_returns_defaults_when_no_config_file(
        self, tmp_path: Path
    ) -> None:
        """Returns the default Settings when the config file does not exist."""
        fake_path = tmp_path / "missing.yml"
        # guard: proves our fake path is truly absent
        assert not fake_path.exists()
        # config_file = tmp_path / "config.yml"
        # config_file.write_text("not: valid: yaml: [unclosed")

        with patch("pykanban.config.CONFIG_FILE", fake_path):
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
