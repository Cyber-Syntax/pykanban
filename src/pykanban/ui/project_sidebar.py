"""Project sidebar widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pykanban.models import Project
from pykanban.store import AppState, KanbanApp


class ProjectSidebar(QWidget):
    """Sidebar for active and archived projects."""

    project_selected = Signal(str)
    new_project_requested = Signal()
    project_delete_requested = Signal(str)
    project_archive_requested = Signal(str)
    project_unarchive_requested = Signal(str)

    def __init__(
        self, app: KanbanApp, parent: QWidget | None = None
    ) -> None:
        """Initialize the sidebar.

        Args:
            app: Kanban application instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app: KanbanApp = app

        self.active_list = QListWidget()
        self.archived_list = QListWidget()

        self.archived_box = QGroupBox("Archived")

        archived_layout = QVBoxLayout(self.archived_box)
        archived_layout.addWidget(self.archived_list)

        self.new_button = QPushButton("New project")

        layout = QVBoxLayout(self)
        layout.addWidget(self.active_list)
        layout.addWidget(self.archived_box)
        layout.addWidget(self.new_button)

        # enable custom context menus on both lists
        self.active_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.archived_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.active_list.itemClicked.connect(self._on_item_clicked)
        self.archived_list.itemClicked.connect(self._on_item_clicked)
        self.active_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self.active_list)
        )
        self.archived_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self.archived_list)
        )
        self.new_button.clicked.connect(self.new_project_requested)

    def refresh(self, projects: list[Project]) -> None:
        """Refresh the list of projects.

        Args:
            projects: Projects to display.
        """
        self.active_list.clear()
        self.archived_list.clear()

        for project in projects:
            item = QListWidgetItem(project.title)
            item.setData(0x0100, project.project_id)

            if project.archived:
                self.archived_list.addItem(item)
            else:
                self.active_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Emit project selection signal.

        Args:
            item: Clicked list item.
        """
        project_id = item.data(0x0100)
        self.project_selected.emit(project_id)

    def _on_context_menu(self, pos: QPoint, list_widget: QListWidget) -> None:
        """Show a right-click context menu on a hovered project item.

        Args:
            pos: Position of the context menu request.
            list_widget: List widget that triggered the context menu.
        """
        item = list_widget.itemAt(pos)
        # right-click on empty space; ignore
        if item is None:
            return

        project_id = item.data(0x0100)

        # get project and check if archived
        project = self.app.state.projects.projects_by_id[project_id]
        is_archived = project.archived

        menu = QMenu(self)
        delete_action = menu.addAction("Delete project")

        archive_action = None
        unarchive_action = None

        if is_archived:
            unarchive_action = menu.addAction("Unarchive project")
        else:
            archive_action = menu.addAction("Archive project")

        # skip if no action was selected
        action = menu.exec(list_widget.mapToGlobal(pos))
        if action is None:
            return

        # emit signal based on selected action
        if action == delete_action:
            self.project_delete_requested.emit(project_id)
        elif action == archive_action:
            self.project_archive_requested.emit(project_id)
        elif action == unarchive_action:
            self.project_unarchive_requested.emit(project_id)
