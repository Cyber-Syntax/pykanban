"""Main entry point for pykanban."""

import sys

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


def main() -> int:
    """Main entry point for pykanban."""
    app = QApplication(sys.argv)
    settings = bootstrap_settings()
    app_state = AppState(settings)
    window = MainWindow(app_state)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
