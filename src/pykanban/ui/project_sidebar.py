"""Project sidebar widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pykanban.logger import get_logger

if TYPE_CHECKING:
    from PySide6.QtGui import QAction

    from pykanban.app import KanbanApp
    from pykanban.models import Project


logger = get_logger(__name__)


class ProjectSidebar(QWidget):
    """Sidebar for active and archived projects."""

    project_selected: Signal = Signal(str)
    new_project_requested: Signal = Signal()
    project_delete_requested: Signal = Signal(str)
    project_archive_requested: Signal = Signal(str)
    project_unarchive_requested: Signal = Signal(str)
    project_rename_requested: Signal = Signal(str)

    def __init__(self, app: KanbanApp, parent: QWidget | None = None) -> None:
        """Initialize the sidebar.

        Args:
            app: Kanban application instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app: KanbanApp = app

        self.tabs: QTabWidget = QTabWidget()

        self.active_list: QListWidget = QListWidget()
        self.archived_list: QListWidget = QListWidget()

        _ = self.tabs.addTab(self.active_list, "Projects")
        _ = self.tabs.addTab(self.archived_list, "Archived")

        self.new_button: QPushButton = QPushButton("New project")

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.new_button)
        content_layout.addWidget(self.tabs)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content_widget)

        # Enable custom context menus on both lists.
        self.active_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.archived_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        _ = self.active_list.itemClicked.connect(self._on_item_clicked)
        _ = self.archived_list.itemClicked.connect(self._on_item_clicked)
        _ = self.active_list.customContextMenuRequested.connect(
            self._on_active_context_menu_requested
        )
        _ = self.archived_list.customContextMenuRequested.connect(
            self._on_archived_context_menu_requested
        )
        _ = self.new_button.clicked.connect(self.new_project_requested)

    def refresh(self, projects: list[Project]) -> None:
        """Refresh the list of projects.

        Args:
            projects: Projects to display.
        """
        logger.debug("Refreshing sidebar: %d project(s)", len(projects))
        self.active_list.clear()
        self.archived_list.clear()

        for project in projects:
            item = QListWidgetItem(project.title)
            item.setData(Qt.ItemDataRole.UserRole, project.project_id)

            if project.archived:
                self.archived_list.addItem(item)
            else:
                self.active_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Emit project selection signal.

        Args:
            item: Clicked list item.
        """
        project_id = cast("str", item.data(Qt.ItemDataRole.UserRole))
        logger.info(
            "Project selected: id=%s title=%r", project_id, item.text()
        )
        self.project_selected.emit(project_id)

    def _on_active_context_menu_requested(self, pos: QPoint) -> None:
        """Show a context menu for the active project list."""
        self._on_context_menu(pos, self.active_list)

    def _on_archived_context_menu_requested(self, pos: QPoint) -> None:
        """Show a context menu for the archived project list."""
        self._on_context_menu(pos, self.archived_list)

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

        project_id = cast("str", item.data(Qt.ItemDataRole.UserRole))

        # get project and check if archived
        project = self.app.state.projects.projects_by_id[project_id]
        is_archived = project.archived
        logger.debug(
            "Context menu opened for project id=%s title=%r",
            project_id,
            project.title,
        )

        menu = QMenu(self)
        delete_action = menu.addAction("Delete project")

        archive_action = None
        unarchive_action = None
        rename_action = menu.addAction("Rename project")
        if is_archived:
            unarchive_action = menu.addAction("Unarchive project")
        else:
            archive_action = menu.addAction("Archive project")

        action = cast(
            "QAction | None", menu.exec(list_widget.mapToGlobal(pos))
        )

        if action is None:
            logger.debug("Context menu dismissed with no action")
            return

        # emit signal based on selected action
        if action == delete_action:
            logger.info(
                "Context menu: delete requested for project id=%s", project_id
            )
            self.project_delete_requested.emit(project_id)
        elif action == archive_action:
            logger.info(
                "Context menu: archive requested for project id=%s", project_id
            )
            self.project_archive_requested.emit(project_id)
        elif action == unarchive_action:
            logger.info(
                "Context menu: unarchive requested for project id=%s",
                project_id,
            )
            self.project_unarchive_requested.emit(project_id)
        elif action == rename_action:
            logger.info(
                "Context menu: rename requested for project id=%s", project_id
            )
            self.project_rename_requested.emit(project_id)
