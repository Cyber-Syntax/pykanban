"""Compact task card widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pykanban.core.models import Task

# Matches task list checkbox: "- [ ]" or "- [x]"
TASK_CHECKBOX_RE = re.compile(r"- \[(x| )\]", re.IGNORECASE)


class TaskCard(QWidget):
    """Compact card widget for a task."""

    clicked = Signal(str)

    def __init__(self, task: Task, parent: QWidget | None = None) -> None:
        """Initialize the task card.

        Args:
            task: The task to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.task = task
        self._press_pos: QPoint | None = None
        self._dragging = False
        self.setObjectName("TaskCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        title = QLabel(task.title)
        title.setWordWrap(True)

        priority = QLabel(task.priority.value.upper())
        priority.setObjectName(f"Priority-{task.priority.value}")

        checked, total = self._count_subtasks(task.raw_body)
        subtasks = QLabel(f"{checked}/{total} subtasks")

        header = QHBoxLayout()
        header.addWidget(priority)
        header.addWidget(subtasks)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(title)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to store position for drag detection.

        Args:
            event: The mouse press event.
        """
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        self._press_pos = event.position().toPoint()
        self._dragging = False

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to detect drag and start drag operation.

        Args:
            event: The mouse move event.
        """
        if self._press_pos is None:
            return

        if self._dragging:
            return

        # Check if movement exceeds drag threshold
        delta = event.position().toPoint() - self._press_pos
        distance = (delta.x() ** 2 + delta.y() ** 2) ** 0.5

        if distance > QApplication.startDragDistance():
            self._dragging = True
            # Schedule the actual drag operation asynchronously to avoid blocking
            QTimer.singleShot(0, self._start_drag)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to emit clicked if no drag occurred.

        Args:
            event: The mouse release event.
        """
        if not self._dragging and self._press_pos is not None:
            self.clicked.emit(self.task.id)

        self._press_pos = None
        self._dragging = False

    def _start_drag(self) -> None:
        """Start a drag operation for this task.

        This method is called asynchronously from mouseMoveEvent via QTimer.
        Guards prevent drag start if state was reset (e.g., by mouseReleaseEvent
        before timer fires).
        """
        # Guard: only start drag if still in dragging state and press position is set
        if not self._dragging or self._press_pos is None:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-task-id", self.task.id.encode("utf-8"))
        mime.setData(
            "application/x-task-status", self.task.status.value.encode("utf-8")
        )
        drag.setMimeData(mime)
        # Use start() for non-blocking drag, or exec() for blocking drag
        # start() returns immediately but exec() waits for drop
        drag.exec(Qt.DropAction.MoveAction)

    def _count_subtasks(self, raw_body: str) -> tuple[int, int]:
        """Count completed and total subtasks in the task body.

        Args:
            raw_body: The raw markdown body of the task.

        Returns:
            A tuple of (completed, total) subtasks.
        """
        matches = TASK_CHECKBOX_RE.findall(raw_body)
        total = len(matches)
        completed = sum(1 for m in matches if m.lower() == "x")
        return completed, total
