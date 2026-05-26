"""Kanban column widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pykanban.core.models import Priority, Status, Task
from pykanban.core.store import AppState, BoardView


class KanbanColumn(QWidget):
    """A single Kanban Column (Backlog / Todo / Doing / Done).

    Signals:
        task_selected: Emitted with the task_id when a card is clicked.
        board_changed: Emitted with the updated BoardView after a drop.
    """

    task_selected = Signal(str)
    board_changed = Signal(BoardView)

    def __init__(
        self,
        status: Status,
        app_state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.status = status
        self.app_state = app_state
        self._show_all_done = False
        self._tasks: list[Task] = []

        self.setAcceptDrops(True)

        # ── header row: label + add button ──────────────────────────────
        self.header = QLabel()
        self.header.setObjectName("ColumnHeader")

        self.add_btn = QPushButton("+")
        self.add_btn.setFixedWidth(28)
        self.add_btn.setToolTip(f"Add task to {status.value}")
        self.add_btn.clicked.connect(self._on_add_task)

        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.header)
        header_layout.addStretch()
        header_layout.addWidget(self.add_btn)

        # ── cards area ───────────────────────────────────────────────────
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cards_container)

        self.show_more = QPushButton("Show More")
        self.show_more.clicked.connect(self._toggle_done_list)
        self.show_more.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(header_row)
        layout.addWidget(scroll)
        layout.addWidget(self.show_more)

    # ── public ───────────────────────────────────────────────────────────

    def refresh(self, tasks: list[Task]) -> None:
        self._tasks = tasks
        self._rebuild_cards()

    # ── drag & drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-task-id"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if not mime.hasFormat("application/x-task-id"):
            return

        task_id = mime.data("application/x-task-id").data().decode("utf-8")
        src_status = (
            mime.data("application/x-task-status").data().decode("utf-8")
        )
        drop_pos = event.position().toPoint()
        cards_pos = self.cards_container.mapFrom(self, drop_pos)
        position = self._drop_position_index(cards_pos)

        if src_status == self.status.value:
            self.app_state.update_task(task_id, {"position": position})
        else:
            self.app_state.move_task(task_id, self.status, position=position)

        board = self.app_state.get_board()
        self.board_changed.emit(board)
        event.acceptProposedAction()

    # ── private ──────────────────────────────────────────────────────────

    def _on_add_task(self) -> None:
        """Open the new-task prompt and create a task in this column."""
        from PySide6.QtWidgets import QInputDialog

        title, ok = QInputDialog.getText(
            self, "New Task", f"Task title ({self.status.value}):"
        )
        if not ok or not title.strip():
            return

        self.app_state.create_task(
            title=title.strip(),
            status=self.status,
            priority=Priority.MEDIUM,
            body="",
        )
        board = self.app_state.get_board()
        self.board_changed.emit(board)

    def _drop_position_index(self, pos: QPoint) -> int:
        """Calculate the index to insert a dropped task based on mouse position.

        Args:
            pos: The position of the drop event relative to the cards container.

        Returns:
            The index at which to insert the dropped task.
        """
        count = self.cards_layout.count()
        for i in range(count):
            item = self.cards_layout.itemAt(i)
            widget = item.widget()
            if not widget:
                continue

            if pos.y() < widget.geometry().center().y():
                return i
        return count

    def _toggle_done_list(self) -> None:
        """Toggle visibility of done tasks."""
        self._show_all_done = not self._show_all_done
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        """Rebuild the card widgets."""
        # Remove all items from layout including stretches using takeAt
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # For done status, show either all tasks or just the most recent 20
        tasks = self._tasks
        if self.status == Status.DONE and not self._show_all_done:
            tasks = self._tasks[-20:]

        # Create a card widget for each task and add it to the layout
        for task in tasks:
            from pykanban.ui.task_card import TaskCard

            card = TaskCard(task)
            card.clicked.connect(self.task_selected.emit)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch(1)

        if self.status == Status.DONE and len(self._tasks) > 20:
            self.show_more.setVisible(True)
            self.show_more.setText(
                "Show less" if self._show_all_done else "Show more"
            )
        else:
            self.show_more.setVisible(False)

        count = len(self._tasks)
        self.header.setText(f"{self.status.value.upper()} ({count})")
