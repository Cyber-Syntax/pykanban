"""Settings dialog for PyKanban."""

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from pykanban.config import Settings, save_settings
from pykanban.logger import _LOG_FILE, get_logger

logger = get_logger(__name__)

_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


class SettingsDialog(QDialog):
    """Dialog for selecting the projects directory and log level.

    Accepts an optional "settings" argument so it can be used both on
    first run (no exist config) and when the user reopens it later
    (pre-populated with current values).

    Args:
        settings: Current settings to pre-populate the form. If None,
            the dataclass defaults are used.
        parent: Optional parent widget.
    """

    def __init__(self, settings: Settings | None = None, parent=None) -> None:
        """Initialize the settings dialog."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(800, 180)

        # default value (always shown, user can change)
        current = settings or Settings()
        self.settings: Settings = current

        # Project directory
        self.projects_dir_edit = QLineEdit(str(current.projects_dir))

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.select_projects_dir)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.projects_dir_edit)
        path_layout.addWidget(browse_button)

        # log level
        self._log_level_combo = QComboBox()
        for level in _LOG_LEVELS:
            self._log_level_combo.addItem(level)
        self._log_level_combo.setCurrentText(current.log_level.upper())

        level_hint = QLabel("DEBUG records everything -- recommended.")
        level_hint.setWordWrap(True)
        level_hint.setStyleSheet("color: grey; font-size: 11px;")

        # log file path - read-only
        log_path_edit = QLineEdit(str(_LOG_FILE))
        log_path_edit.setReadOnly(True)
        log_path_edit.setToolTip("Attach this file when reporting a bug")

        open_logs_btn = QPushButton("Open Folder")
        open_logs_btn.setToolTip("Reveal the logs folder in your file manager")
        open_logs_btn.clicked.connect(self._open_logs_folder)

        log_row = QHBoxLayout()
        log_row.addWidget(log_path_edit)
        log_row.addWidget(open_logs_btn)

        # form
        form = QFormLayout()
        form.addRow("Projects directory:", path_layout)
        form.addRow("Log level:", self._log_level_combo)
        form.addRow("", level_hint)
        form.addRow("Log file:", log_row)

        # buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        logger.debug(
            "SettingsDialog opened with projects_dir=%s", current.projects_dir
        )

    def select_projects_dir(self) -> None:
        """Open Folder picker."""

        directory = QFileDialog.getExistingDirectory(
            self, "Select Projects Directory", self.projects_dir_edit.text()
        )
        if directory:
            self.projects_dir_edit.setText(directory)

        logger.info("Projects directory changed to: %s", directory)

    def _open_logs_folder(self) -> None:
        """Reveal the logs folder in the system file manager."""
        logs_dir = _LOG_FILE.parent
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("Opening logs folder: %s", logs_dir)

        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", str(logs_dir)])

    # QDialog overrides
    def accept(self) -> None:
        """Save the settings and close the dialog."""
        settings = Settings(
            projects_dir=Path(self.projects_dir_edit.text())
            .expanduser()
            .resolve()
        )
        save_settings(settings)
        self.settings = settings
        super().accept()
        logger.info("Settings saved: %s", settings)

    def get_settings(self) -> Settings:
        """Return the selected settings."""
        return Settings(
            projects_dir=Path(self.projects_dir_edit.text())
            .expanduser()
            .resolve()
        )
