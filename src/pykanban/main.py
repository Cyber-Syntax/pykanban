"""Main entry point for pykanban."""

import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from pykanban.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    Settings,
    load_settings,
    save_settings,
)
from pykanban.core.store import AppState
from pykanban.ui.main_window import MainWindow
from pykanban.ui.settings_dialog import SettingsDialog

# Bundled template lives next to this file inside the `data` directory
_DATA_DIR = Path(__file__).parent / "data"


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)


def bootstrap_settings() -> Settings:
    """Bootstrap the settings from the config file.

    If the config file does not exist, show the settings dialog
    and save the settings if the user accepts.
    """

    ensure_config_dir()
    settings: Settings = load_settings()

    # If the config file exists, return the settings
    if CONFIG_FILE.exists():
        return settings

    # If the config file does not exist, show the settings dialog
    # and save the settings if the user accepts
    dialog = SettingsDialog()
    if not dialog.exec():
        sys.exit(0)

    settings = dialog.get_settings()
    save_settings(settings)

    return settings


def seed_template(settings: Settings) -> None:
    """Copy the bundled template to the projects directory.

    Runs only when projects_dir contains no project folders yet, so
    it never overwrites existing projects.
    """
    projects_dir = settings.projects_dir
    projects_dir.mkdir(parents=True, exist_ok=True)

    # skip if the user already has at least one project
    has_projects = any(
        (d / "metadata.yml").exists()
        for d in projects_dir.iterdir()
        if d.is_dir()
    )
    if has_projects:
        return

    template_src = _DATA_DIR / "learn-pykanban"
    # template not bundled - skip silently, don't crash
    if not template_src.exists():
        return

    destination = projects_dir / "learn-pykanban"
    if not destination.exists():
        shutil.copytree(template_src, destination)


def main() -> int:
    """Main entry point for pykanban."""
    app = QApplication(sys.argv)
    settings = bootstrap_settings()
    seed_template(settings)
    app_state = AppState.create(settings)
    window = MainWindow(app_state)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
