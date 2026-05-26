"""Project sidebar widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pykanban.core.models import Project
from pykanban.core.store import AppState


class ProjectSidebar(QWidget):
    """Sidebar for active and archived projects."""

    project_selected = Signal(str)
    new_project_requested = Signal()

    def __init__(
        self, app_state: AppState, parent: QWidget | None = None
    ) -> None:
        """Initialize the sidebar.

        Args:
            app_state: Application state instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app_state = app_state

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

        self.active_list.itemClicked.connect(self._on_item_clicked)
        self.archived_list.itemClicked.connect(self._on_item_clicked)
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
