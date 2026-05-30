"""Kanban board widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QWidget

from pykanban.app import KanbanApp
from pykanban.models import Status
from pykanban.ui.kanban_column import KanbanColumn

if TYPE_CHECKING:
    from pykanban.store import BoardView, KanbanApp


class KanbanBoard(QWidget):
    """Container for all task columns."""

    def __init__(self, app: KanbanApp, parent: QWidget | None = None) -> None:
        """Initialize the board widget.

        Args:
            app: Kanban application instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app: KanbanApp = app

        self.columns: dict[Status, KanbanColumn] = {
            Status.BACKLOG: KanbanColumn(Status.BACKLOG, self.app),
            Status.TODO: KanbanColumn(Status.TODO, self.app),
            Status.DOING: KanbanColumn(Status.DOING, self.app),
            Status.DONE: KanbanColumn(Status.DONE, self.app),
        }

        layout = QHBoxLayout(self)
        for column in self.columns.values():
            layout.addWidget(column)

    def refresh(self, board_view: BoardView) -> None:
        """Redistribute tasks to columns.

        Args:
            board_view: Board view mapping status to tasks.
        """
        for status, column in self.columns.items():
            column.refresh(board_view.columns.get(status, []))
