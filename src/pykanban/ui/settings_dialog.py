"""Settings dialog for PyKanban."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from pykanban.config import Settings, save_settings


class SettingsDialog(QDialog):
    """Dialog for selecting the projects directory."""

    def __init__(self, parent=None) -> None:
        """Initialize the settings dialog."""
        super().__init__(parent)

        self.setWindowTitle("Settings")

        # default value (always shown, user can change)
        self.default_settings = Settings()

        self.projects_dir_edit = QLineEdit(
            str(self.default_settings.projects_dir)
        )

        # Make the dialog resizable
        self.setMinimumSize(500, 100)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.select_projects_dir)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.projects_dir_edit)
        path_layout.addWidget(browse_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Projects Directory:"))
        layout.addLayout(path_layout)
        layout.addWidget(buttons)

    def select_projects_dir(self) -> None:
        """Open Folder picker."""

        directory = QFileDialog.getExistingDirectory(
            self, "Select Projects Directory", self.projects_dir_edit.text()
        )
        if directory:
            self.projects_dir_edit.setText(directory)

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

    def get_settings(self) -> Settings:
        """Return the selected settings."""
        return Settings(
            projects_dir=Path(self.projects_dir_edit.text())
            .expanduser()
            .resolve()
        )
