"""Main window for the PyKanban application.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from pykanban.core.store import AppState
from pykanban.ui.error_banner import ErrorBanner
from pykanban.ui.kanban_board import KanbanBoard
from pykanban.ui.project_sidebar import ProjectSidebar
from pykanban.ui.task_editor import TaskEditorPanel


def center_window(window: QMainWindow) -> None:
    """Center the window on the screen."""
    screen = QGuiApplication.primaryScreen().availableGeometry()
    size = window.frameGeometry()

    x = (screen.width() - size.width()) // 2
    y = (screen.height() - size.height()) // 2
    window.move(x, y)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, state: AppState) -> None:
        """Initialize the main app."""
        super().__init__()
        self.app_state = state

        self.error_banner = ErrorBanner()
        self.sidebar = ProjectSidebar(self.app_state)
        self.board = KanbanBoard(self.app_state)
        self.editor = TaskEditorPanel(self.app_state)

        self._build_layout()
        self._wire_signals()

        self.setWindowTitle("PyKanban")
        self.resize(1200, 720)
        center_window(self)

        self._initial_load()

    def _build_layout(self) -> None:
        center = QWidget()
        main_layout = QVBoxLayout(center)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.addWidget(self.sidebar, 1)
        content_layout.addWidget(self.board, 3)
        content_layout.addWidget(self.editor, 2)

        main_layout.addWidget(self.error_banner)
        main_layout.addWidget(content)

        self.setCentralWidget(center)

    def _wire_signals(self) -> None:
        for column in self.board.columns.values():
            column.task_selected.connect(self._open_task)
            column.task_deleted.connect(self._delete_task)
            column.board_changed.connect(self._refresh_board)

        self.editor.task_saved.connect(self._refresh_from_state)
        self.sidebar.project_selected.connect(self._switch_project)
        self.sidebar.new_project_requested.connect(self._create_project)

    def _initial_load(self) -> None:
        self.app_state.startup_scan(self.app_state.settings.projects_dir)
        self.sidebar.refresh(
            list(self.app_state.projects.projects_by_id.values())
        )
        self._refresh_from_state()

    def _open_task(self, task_id: str) -> None:
        task = self.app_state.tasks.get(task_id)
        self.editor.load_task(task)

    def _delete_task(self, task_id: str) -> None:
        """Confirm and delete the task, then refresh the board.

        Shows a confirmation dialog before deleting the task. If the deleted
        task is currently open in the editor, the editor is cleared first
        so it doesn't hold a stale reference to the deleted task.

        Args:
            task_id: The ID of the task to delete.
        """
        task = self.app_state.tasks.get(task_id)
        if task is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the task '{task.title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        # clear the editor if it is showing the task being deleted
        if self.editor._task and self.editor._task.id == task_id:
            self.editor.clear()

        self.app_state.delete_task(task_id)
        self._refresh_from_state()

    def _refresh_from_state(self) -> None:
        """Refresh board from AppState — no-op when no project is active yet."""
        if self.app_state.projects.active_project_id is None:
            # Nothing to render; show empty banner state
            self.error_banner.set_errors(self.app_state.errors)
            return
        board = self.app_state.get_board()
        self._refresh_board(board)

    def _refresh_board(self, board) -> None:
        self.board.refresh(board)
        self.error_banner.set_errors(self.app_state.errors)

    def _switch_project(self, project_id: str) -> None:
        # clear any open task in the editor
        # so it doesn't show stale data when switching projects
        self.editor.clear()

        # switch to the new project and refresh the board
        board = self.app_state.switch_project(project_id)
        self._refresh_board(board)

    def _create_project(self) -> None:
        """Handle the 'New project' button from the sidebar."""

        title, ok = QInputDialog.getText(self, "New Project", "Project title:")
        if not ok or not title.strip():
            return

        desc, _ = QInputDialog.getText(
            self, "New Project", "Description (optional):"
        )

        # create the project
        project = self.app_state.create_project(title.strip(), desc.strip())

        # clear the editor and switch to the new project
        self.editor.clear()

        # switch to the new project and refresh the board
        board = self.app_state.switch_project(project.project_id)
        self._refresh_board(board)

        # refresh the sidebar to show the new project
        self.sidebar.refresh(
            list(self.app_state.projects.projects_by_id.values())
        )
        self._refresh_from_state()
