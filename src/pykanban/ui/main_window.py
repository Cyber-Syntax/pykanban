"""Main window for the PyKanban application."""

from PySide6.QtWidgets import QLabel, QMainWindow
from PySide6.QtGui import QGuiApplication


from pykanban.core.store import AppState


def center_window(window: QMainWindow) -> None:
    """Center the window on the screen."""
    screen = QGuiApplication.primaryScreen().availableGeometry()
    size = window.frameGeometry()

    x = (screen.width() - size.width()) // 2
    y = (screen.height() - size.height()) // 2
    window.move(x, y)


class MainWindow(QMainWindow):
    """Main application class."""

    def __init__(self, state: AppState) -> None:
        """Initialize the main app."""
        super().__init__()
        self.app_state = state

        self.setWindowTitle("PyKanban")
        self.resize(800, 600)
        center_window(self)
        self.setCentralWidget(
            QLabel(
                f"Projects directory:\n{self.app_state.settings.projects_dir}"
            )
        )
