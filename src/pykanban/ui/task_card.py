"""Compact task card widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDrag,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
)

from pykanban.models import Task

# TODO: improve cards
# use QTQuick.Controls.ComboBox for selecting status, priority... directly from card
# title can be changed directly from card via QtQuick.Controls.TextInput
#
# you check those and implement the basic, no need to fancy design
# need to be useful
# https://doc.qt.io/qt-6/stylesheet-examples.html
# https://doc.qt.io/qt-6/qtwidgets-index.html

# this good looking for it is QML only, need to write qml language?
# this isn't for good for begginers, so maybe later
# More better found: https://doc.qt.io/qt-6/qtquickcontrols-material.html
# 	import QtQuick.Controls.Material


# Matches task list checkbox: "- [ ]" or "- [x]"
TASK_CHECKBOX_RE = re.compile(r"- \[(x| )\]", re.IGNORECASE)


class TaskCard(QFrame):
    """Compact card widget for a task."""

    clicked = Signal(str)
    # emits task_id
    delete_requested = Signal(str)

    def __init__(self, task: Task, parent: QFrame | None = None) -> None:
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
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.setStyleSheet("""
                TaskCard {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 12px;
                    min-width: 280px;
                }
                QLabel#TitleLabel {
                    font-size: 15px;
                    font-weight: bold;
                    color: #1a1a1a;
                    padding: 8px 12px 4px 12px;
                }
                QLabel#DescriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 0px 12px 8px 12px;
                }
                QLabel#StatusLabel {
                    font-size: 11px;
                    color: #666666;
                    background-color: #f0f0f0;
                    padding: 3px 8px;
                    border-radius: 6px;
                }
                QLabel#PriorityLabel {
                    font-size: 11px;
                    font-weight: bold;
                    padding: 3px 8px;
                    border-radius: 6px;
                    color: white;
                }
                QLabel#Priority-High {
                    background-color: #ff4d4d;
                }
                QLabel#Priority-Medium {
                    background-color: #ffb84d;
                }
                QLabel#Priority-Low {
                    background-color: #4da6ff;
                }
                QProgressBar {
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    text-align: center;
                    font-size: 11px;
                    color: #666666;
                    background-color: #f5f5f5;
                }
                QProgressBar::chunk {
                    background-color: #4caf50;
                    border-radius: 3px;
                }
            """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        title = QLabel(task.title)
        title.setObjectName("TitleLabel")
        title.setWordWrap(True)
        title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        main_layout.addWidget(title)

        body_preview = self._prepare_body_preview(task.raw_body, max_chars=140)
        description = QLabel(body_preview or "No description")
        description.setObjectName("DescriptionLabel")
        description.setWordWrap(True)
        description.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        description.setMaximumHeight(40)
        main_layout.addWidget(description)

        footer = QHBoxLayout()
        footer.setContentsMargins(8, 6, 8, 8)
        footer.setSpacing(8)

        status_label = QLabel(task.status.value.upper())
        status_label.setObjectName("StatusLabel")
        footer.addWidget(status_label)

        priority = QLabel(task.priority.value.upper())
        priority.setObjectName(f"PriorityLabel Priority-{task.priority.value}")
        footer.addWidget(priority)

        checked, total = self._count_subtasks(task.raw_body)
        if total > 0:
            progress_bar = QProgressBar()
            progress_bar.setRange(0, total)
            progress_bar.setValue(checked)
            progress_bar.setFixedHeight(16)
            progress_bar.setFixedWidth(80)
            progress_bar.setTextVisible(False)
            footer.addWidget(progress_bar)

            subtasks_label = QLabel(f"{checked}/{total}")
            subtasks_label.setStyleSheet("font-size: 11px; color: #666666;")
            footer.addWidget(subtasks_label)
        else:
            footer.addStretch()

        footer.addStretch()
        main_layout.addLayout(footer)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle right-click context menu event.

        Args:
            event: The context menu event.
        """
        menu = QMenu(self)
        delete_action = menu.addAction("Delete task")
        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_requested.emit(self.task.id)

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
            # Start the drag operation immediately
            # to avoid issues with delayed drag start
            # and state changes (e.g., mouse release)
            self._start_drag()

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

        # Create a semi-transparent pixmap of the card
        pixmap = self.grab()
        blurred = QPixmap(pixmap.size())
        blurred.fill(Qt.transparent)
        painter = QPainter(blurred)
        painter.setOpacity(0.5)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        # Set the pixmap and hot spot for the drag operation
        drag.setPixmap(blurred)
        drag.setHotSpot(self._press_pos)

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

    def _prepare_body_preview(
        self, raw_body: str, max_chars: int = 120
    ) -> str:
        """Extract the description section from the task body and truncate it."""
        # Split at "# Subtasks" (case-insensitive)
        parts = re.split(r"#\s*Subtasks", raw_body, flags=re.IGNORECASE)
        description_section = parts[0] if parts else raw_body

        # Remove the "# Description" heading itself and any leading/trailing whitespace
        description_section = re.sub(
            r"#\s*Description", "", description_section, flags=re.IGNORECASE
        )
        description_section = description_section.strip()

        # Strip remaining markdown formatting and extra whitespace
        cleaned = re.sub(
            r"[#*_~`>]", "", description_section
        )  # remove common symbols
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) <= max_chars:
            return cleaned
        # Truncate at the last space before max_chars
        truncated = cleaned[:max_chars].rsplit(" ", 1)[0]
        return truncated + "..."
