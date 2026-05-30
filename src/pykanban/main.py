"""Main entry point for pykanban."""

import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from pykanban.app import KanbanApp
from pykanban.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    ConfigError,
    Settings,
    load_settings,
)
from pykanban.ui.main_window import MainWindow
from pykanban.ui.settings_dialog import SettingsDialog

# Bundled template lives next to this file inside the `data` directory
_DATA_DIR = Path(__file__).parent / "data"


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap_settings() -> tuple[Settings, bool]:
    """Bootstrap the settings from the config file.

    If the config file does not exist, show the settings dialog
    and save the settings if the user accepts.
    """
    ensure_config_dir()

    # If the config file exists, return the settings
    if CONFIG_FILE.exists():
        try:
            return load_settings(), False
        except ConfigError as e:
            # show a modal error dialog before exiting:
            QMessageBox.critical(
                None, "Configuration Error", str(e), QMessageBox.Ok
            )
            sys.exit(1)

    # If the config file does not exist, show the settings dialog
    # and save the settings if the user accepts
    dialog = SettingsDialog()
    if not dialog.exec():
        sys.exit(0)

    # Save the settings and return
    # dialog would save the settings
    return dialog.get_settings(), True


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
    # raise if bundled template not found
    if not template_src.exists():
        raise FileNotFoundError(
            f"Bundled template not found at {template_src}."
            "The package may be installed incorrectly."
        )

    destination = projects_dir / "learn-pykanban"
    if not destination.exists():
        shutil.copytree(template_src, destination)


def main() -> int:
    """Main entry point for pykanban."""
    app_qt = QApplication(sys.argv)

    # Bootstrap the settings and determine if this is the first run
    settings, is_first_run = bootstrap_settings()

    # Seed the template if this is the first run
    if is_first_run:
        seed_template(settings)

    kanban_app = KanbanApp(settings)
    window = MainWindow(kanban_app)
    window.show()

    return app_qt.exec()


if __name__ == "__main__":
    raise SystemExit(main())
