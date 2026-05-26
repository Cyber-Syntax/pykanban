"""Kanban board widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from pykanban.models import Status
from pykanban.store import AppState, BoardView
from pykanban.ui.kanban_column import KanbanColumn


class KanbanBoard(QWidget):
    """Container for all task columns."""

    def __init__(
        self, app_state: AppState, parent: QWidget | None = None
    ) -> None:
        """Initialize the board widget.

        Args:
            app_state: Application state instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app_state = app_state

        self.columns = {
            Status.BACKLOG: KanbanColumn(Status.BACKLOG, app_state),
            Status.TODO: KanbanColumn(Status.TODO, app_state),
            Status.DOING: KanbanColumn(Status.DOING, app_state),
            Status.DONE: KanbanColumn(Status.DONE, app_state),
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
