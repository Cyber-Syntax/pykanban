"""Main window for the PyKanban application.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pykanban.app import KanbanApp
from pykanban.models import Status
from pykanban.store import BoardView
from pykanban.ui.error_banner import ErrorBanner
from pykanban.ui.kanban_board import KanbanBoard
from pykanban.ui.project_sidebar import ProjectSidebar
from pykanban.ui.task_editor import TaskEditorPanel
from pykanban.watcher import Watcher

if TYPE_CHECKING:
    from pathlib import Path

    from pykanban.app import KanbanApp


def center_window(window: QMainWindow) -> None:
    """Center the window on the screen."""
    screen = QGuiApplication.primaryScreen().availableGeometry()
    size = window.frameGeometry()

    x = (screen.width() - size.width()) // 2
    y = (screen.height() - size.height()) // 2
    window.move(x, y)


# TODO: write proper tests
# TODO: can we make privates methods to public
# to decrease complexity of testing and increase test coverage?
# Are we violeting SRP by having all these methods in the main window instead of a controller?


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, app: KanbanApp) -> None:
        """Initialize the main app."""
        super().__init__()
        self.app: KanbanApp = app

        self._watcher = Watcher(self)
        self.error_banner = ErrorBanner()
        self.sidebar = ProjectSidebar(self.app)
        self.board = KanbanBoard(self.app)
        self.editor = TaskEditorPanel(self.app)
        self._sidebar_hidden = False

        self._build_layout()
        self._wire_signals()

        self.setWindowTitle("PyKanban")
        self.resize(1200, 720)
        center_window(self)

        self._initial_load()

    def _build_layout(self) -> None:
        center = QWidget()
        main_layout = QVBoxLayout(center)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar_toggle = QPushButton("<")
        self.sidebar_toggle.setFixedWidth(28)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)

        top_bar_layout.addWidget(self.sidebar_toggle)
        top_bar_layout.addStretch(1)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.board, 3)
        content_layout.addWidget(self.editor, 2)

        main_layout.addWidget(top_bar)
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
        self.sidebar.project_rename_requested.connect(self._rename_project)
        self.sidebar.project_delete_requested.connect(self._delete_project)
        self.sidebar.project_archive_requested.connect(self._archive_project)
        self.sidebar.project_unarchive_requested.connect(
            self._unarchive_project
        )
        self._watcher.changes_detected.connect(self._on_external_changes)
        self._watcher.project_folder_deleted.connect(
            self._on_project_folder_deleted
        )

    def _toggle_sidebar(self) -> None:
        """Hide or show the whole project sidebar."""
        self._sidebar_hidden = not self._sidebar_hidden
        self.sidebar.content_widget.setVisible(not self._sidebar_hidden)
        self.sidebar_toggle.setText(">" if self._sidebar_hidden else "<")

    def _initial_load(self) -> None:
        self.app.projects.startup_scan(self.app.state.settings.projects_dir)
        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )
        self.sidebar.refresh(
            list(self.app.state.projects.projects_by_id.values())
        )
        self._refresh_from_state()

    def _on_external_changes(
        self, changed: list[Path], deleted: list[Path]
    ) -> None:
        """React to files modified or removed outside the app."""
        if not changed and not deleted:
            return
        try:
            self.app.apply_external_changes(changed, deleted)
        except KeyError:
            # no active project (e.g all archived); nothing to refresh
            return
        self._refresh_from_state()

    def _on_project_folder_deleted(self, folder_path: Path) -> None:
        self.app.handle_project_folder_deleted(folder_path)
        # clear from editor and refresh sidebar to clear stale
        self.editor.clear()
        self.sidebar.refresh(list(self.app.projects_list))
        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )
        # refresh the state
        self._refresh_from_state()

    def _open_task(self, task_id: str) -> None:
        """Commit any open draft, then load the selected task.

        Args:
            task_id: The ID of the task to open.
        """

        # If the editor has an open task that is different from the one being
        # selected, flush changes and clear the editor to avoid showing stale data.
        current_task = self.editor._task
        if current_task is not None and current_task.id != task_id:
            self.editor.clear()

        # if it doesn't exist, just clear the editor
        task = self.app.get_task(task_id)
        if task is None:
            self.editor.clear()
            return

        # load the new task into the editor
        self.editor.load_task(task)

    def _delete_task(self, task_id: str) -> None:
        """Confirm and delete the task, then refresh the board.

        Shows a confirmation dialog before deleting the task. If the deleted
        task is currently open in the editor, the editor is cleared first
        so it doesn't hold a stale reference to the deleted task.

        Args:
            task_id: The ID of the task to delete.
        """
        task = self.app.get_task(task_id)
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

        self.app.tasks.delete_task(task_id)
        self._refresh_from_state()

    def _refresh_from_state(self) -> None:
        """Refresh board from MemoryStateManager."""
        if self.app.state.projects.active_project_id is None:
            # No active project: force an explicit empty board
            # so we don't show stale data from the previously active project.
            empty_board = BoardView(columns={status: [] for status in Status})
            self._refresh_board(empty_board)
            return

        board = self.app.get_board()
        self._refresh_board(board)

    def _refresh_board(self, board) -> None:
        self.board.refresh(board)
        current_task = self.editor._task

        # if the currently open task was deleted or moved to a different column,
        # we want to refresh the editor to show the latest data
        # or clear if it no longer exists
        if current_task is not None:
            fresh_task = self.app.get_task(current_task.id)
            if fresh_task is None:
                self.editor.discard()
            else:
                self.editor.load_task(fresh_task)
        self.error_banner.set_errors(self.app.state.errors)

    def _delete_project(self, project_id: str) -> None:
        """Confirm and permanently delete a project, then refresh the UI.

        Clears the editor and board first so neither holds a reference to
        tasks that are about to be removed from memory and disk.

        Args:
            project_id: ID of the project to delete.
        """
        project = self.app.state.projects.projects_by_id.get(project_id)
        if project is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete project",
            f'Delete "{project.title}" and all its tasks?\n'
            "This connot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # clear editor and board before mutating state
        self.editor.clear()
        self.app.delete_project(project_id)

        # refresh sidebar; board will show empty state if no project remains
        self.sidebar.refresh(list(self.app.projects_list))
        # set projects to watcher
        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )
        self._refresh_from_state()

    def _archive_project(self, project_id: str) -> None:
        """Confirm and move a project to archive, then refresh the UI.

        Tasks are dropped from memory after archiving (handled by
        MemoryStateManager.archive_project) while the project metadata stays in the
        store so the sidebar can still display the title under archived.

        Args:
            project_id: ID of the project to archive.
        """
        project = self.app.get_project(project_id)
        if project is None:
            return

        reply = QMessageBox.question(
            self,
            "Archive project",
            f'Archive "{project.title}" and all its tasks?\n'
            "This can be undone later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear editor and board before mutating state
        self.editor.clear()
        self.app.archive_project(project_id)

        # Sidebar refresh moves the item from active -> archived section
        self.sidebar.refresh(list(self.app.projects_list))

        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )

        # boards shows empty state since active_project_id is now None
        self._refresh_from_state()

    def _unarchive_project(self, project_id: str) -> None:
        """Unarchive the project and refresh the UI."""
        self.app.unarchive_project(project_id)
        self.sidebar.refresh(list(self.app.projects_list))
        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )

        self._refresh_from_state()

    def _switch_project(self, project_id: str) -> None:
        # clear any open task in the editor
        # so it doesn't show stale data when switching projects
        self.editor.clear()

        # switch to the new project and refresh the board
        self.app.switch_project(project_id)
        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )
        self._refresh_from_state()

    def _create_project(self) -> None:
        """Handle the 'New project' button from the sidebar."""

        title, ok = QInputDialog.getText(self, "New Project", "Project title:")
        if not ok or not title.strip():
            return

        desc, _ = QInputDialog.getText(
            self, "New Project", "Description (optional):"
        )

        # create the project
        project = self.app.projects.create_project(title.strip(), desc.strip())

        # clear the editor and switch to the new project
        self.editor.clear()

        # switch to the new project and refresh the board
        self.app.switch_project(project.project_id)

        # refresh the sidebar
        self.sidebar.refresh(list(self.app.projects_list))

        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )

        # refresh from state handles fetching and redering the board
        self._refresh_from_state()

    def _rename_project(self, project_id: str) -> None:
        """Handle renaming a project from the sidebar."""
        project = self.app.get_project(project_id)
        # TODO: is that code unreachable ?
        if project is None:
            return

        new_title, ok = QInputDialog.getText(
            self, "Rename Project", "New project title:", text=project.title
        )
        if not ok or not new_title.strip():
            return

        self.app.projects.rename_project(project_id, new_title.strip())

        # refresh the sidebar to show the updated title
        self.sidebar.refresh(list(self.app.projects_list))

        self._watcher.set_projects(
            list(self.app.state.projects.projects_by_id.values()),
            self.app.state.settings.projects_dir,
        )

        # refresh the board state to see the error_banner
        # if there is an error with the project after renaming
        self._refresh_from_state()
