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

from pykanban.app import KanbanApp
from pykanban.logger import get_logger
from pykanban.models import Priority, Status, Task
from pykanban.store import BoardView

logger = get_logger(__name__)


_DONE_DEFAULT_LIMIT: int = 10


class KanbanColumn(QWidget):
    """A single Kanban Column (Backlog / Todo / Doing / Done).

    Signals:
        task_selected: Emitted with the task_id when a card is clicked.
        task_deleted: Emitted with the task_id when a card is deleted.
        board_changed: Emitted with the updated BoardView after a drop.
    """

    task_selected = Signal(str)
    task_deleted = Signal(str)
    board_changed = Signal(BoardView)

    def __init__(
        self,
        status: Status,
        app: KanbanApp,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the column widget.

        Args:
            status: The workflow status this column represents
            app: Kanban application instance
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.status: Status = status
        self.app: KanbanApp = app

        # Whether the DONE column has been fully expanded by user.
        self._show_all_done = False

        # Full task list for this column (set by refresh())
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

        self.setMinimumWidth(200)

    # public
    def refresh(self, tasks: list[Task]) -> None:
        """Repopulate the column with a new ordered task list.

        Called by KanbanBoard.refresh() wheneve the board state changes

        Args:
            tasks: Ordered list of tasks for this column.
        """
        logger.debug(
            "Refreshing column '%s' with %d task(s)",
            self.status.value,
            len(tasks),
        )
        self._tasks = tasks
        self._rebuild_cards()

    # drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drag events that carry a task-id MIME payload.

        Only our custom MIME type is accepted so that foreign drags
        (e.g files from a file manager) are ignored.

        Args:
            event: The drag-enter event provided by Qt.
        """
        if event.mimeData().hasFormat("application/x-task-id"):
            logger.debug(
                "dragEnterEvent accepted on column '%s'", self.status.value
            )
            event.acceptProposedAction()
        else:
            logger.debug(
                "dragEnterEvent ignored on column '%s': unexpected MIME type",
                self.status.value,
            )

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle a task card being dropped into this column.

        Decides between two cases:
        - Same column drop -> reorder only (writes metadata.yml)
        - Cross column drop -> status change (writes task file + metadata.yml)

        After a succesfull mutation the updated BoardView is emitted so
        MainWindow can refresh all columns atomically.

        Args:
            event: The drag-move event provided by Qt.
        """
        mime = event.mimeData()
        if not mime.hasFormat("application/x-task-id"):
            logger.warning(
                "dropEvent on column '%s': missing task-id MIME data, ignoring",
                self.status.value,
            )
            event.ignore()
            return

        # wrapping in bytes() guarantees we always have a bytes object with .decode()
        task_id = bytes(mime.data("application/x-task-id").data()).decode(
            "utf-8"
        )
        src_status = bytes(
            mime.data("application/x-task-status").data()
        ).decode("utf-8")
        drop_pos = event.position().toPoint()
        cards_pos = self.cards_container.mapFrom(self, drop_pos)
        position = self._drop_position_index(cards_pos)

        logger.debug(
            "dropEvent: task_id=%s src_status=%s -> dst_status=%s position=%d",
            task_id,
            src_status,
            self.status.value,
            position,
        )

        try:
            if src_status == self.status.value:
                logger.info(
                    "Reordering task '%s' within column '%s' to position %d",
                    task_id,
                    self.status.value,
                    position,
                )
                self.app.update_task(task_id, {"position": position})
            else:
                logger.info(
                    "Moving task '%s' from '%s' to '%s' at position %d",
                    task_id,
                    src_status,
                    self.status.value,
                    position,
                )
                self.app.move_task(task_id, self.status, position=position)
        except KeyError:
            logger.warning(
                "dropEvent: task '%s' no longer exists (deleted externally), ignoring drop",
                task_id,
            )
            event.ignore()
            return

        event.acceptProposedAction()

        # Retrieve fresh board state and notify MainWindow
        board = self.app.get_board()
        self.board_changed.emit(board)

    def _on_add_task(self) -> None:
        """Open the new-task prompt and create a task in this column."""
        from PySide6.QtWidgets import QInputDialog

        title, ok = QInputDialog.getText(
            self, "New Task", f"Task title ({self.status.value}):"
        )
        if not ok or not title.strip():
            logger.debug("_on_add_task: user cancelled or entered blank title")
            return

        logger.info(
            "Creating new task '%s' in column '%s'",
            title.strip(),
            self.status.value,
        )
        self.app.create_task(
            title=title.strip(),
            status=self.status,
            priority=Priority.MEDIUM,
            body="",
        )
        board: BoardView = self.app.get_board()
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
            # itemAt returns QLayoutItem | None - guard before use
            item = self.cards_layout.itemAt(i)
            # guard for none
            if item is None:
                continue

            widget = item.widget()

            if not widget:
                continue

            if pos.y() < widget.geometry().center().y():
                logger.debug("_drop_position_index: resolved to index %d", i)
                return i
        return count

    def _toggle_done_list(self) -> None:
        """Toggle visibility of done tasks."""
        self._show_all_done = not self._show_all_done
        logger.debug(
            "_toggle_done_list: _show_all_done=%s for column '%s'",
            self._show_all_done,
            self.status.value,
        )
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        """Clear existing card widgets and recreate them from self._tasks.

        Also updates the header count and the "show more" button
        visibility (done column only).

        Each card's delete_requested signal is forwarded as task_deleted
        so MainWindow can handle deletion without knowing about columns.
        """
        # Remove every widget currently in the card layout
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is None:
                continue

            widget = item.widget()

            if widget:
                widget.deleteLater()

        # For done status, show either all tasks or just the most recent 10
        tasks = self._tasks
        if self.status == Status.DONE and not self._show_all_done:
            tasks = self._tasks[-_DONE_DEFAULT_LIMIT:]

        logger.debug(
            "_rebuild_cards: rendering %d/%d task(s) in column '%s'",
            len(tasks),
            len(self._tasks),
            self.status.value,
        )

        # Create a card widget for each task and add it to the layout
        for task in tasks:
            from pykanban.ui.task_card import TaskCard

            card = TaskCard(task)
            card.clicked.connect(self.task_selected.emit)
            # forward delete requestes upward to MainWindow
            card.delete_requested.connect(self.task_deleted.emit)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch(1)

        if (
            self.status == Status.DONE
            and len(self._tasks) > _DONE_DEFAULT_LIMIT
        ):
            self.show_more.setVisible(True)
            self.show_more.setText(
                "Show less" if self._show_all_done else "Show more"
            )
        else:
            self.show_more.setVisible(False)

        # header always reflects the total task count not the visible count
        count = len(self._tasks)
        self.header.setText(f"{self.status.value.upper()} ({count})")
