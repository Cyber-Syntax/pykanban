"""Task editor panel widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pykanban.app import KanbanApp
from pykanban.models import Priority, Status, Task


class TaskEditorPanel(QWidget):
    """Editor panel for a single task."""

    task_saved = Signal()

    def __init__(self, app: KanbanApp, parent: QWidget | None = None) -> None:
        """Initialize the editor panel.

        Args:
            app: Kanban application instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app: KanbanApp = app
        self._task: Task | None = None

        self.title_edit = QLineEdit()
        self.status_combo = QComboBox()
        self.priority_combo = QComboBox()
        self.body_edit = QPlainTextEdit()
        self.checklist_view = QTextBrowser()

        # Use a single-shot timer so edits are written after the user pauses.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._flush_changes)

        self._build_form()
        self._wire_signals()

        self.setVisible(False)

    def load_task(self, task: Task) -> None:
        """Load a task into the editor.

        Args:
            task: Task to edit.
        """
        # Stop any pending save for the current task before we swap editors.
        self._timer.stop()

        previous_task = self._task
        if (
            previous_task is not None
            and previous_task.id != task.id
            and self.isVisible()
            and self._has_unsaved_changes(previous_task)
        ):
            self._flush_changes()

        preserve_body_cursor = (
            previous_task is not None and previous_task.id == task.id
        )
        body_cursor = self.body_edit.textCursor()
        body_position = body_cursor.position()
        body_anchor = body_cursor.anchor()
        body_scroll_value = self.body_edit.verticalScrollBar().value()

        # Replace the current model reference before populating the widgets.
        self._task = task

        widgets = (
            self.title_edit,
            self.status_combo,
            self.priority_combo,
            self.body_edit,
        )

        # Block signals so programmatic updates do not look like user edits.
        blocked_states = [widget.blockSignals(True) for widget in widgets]

        try:
            self.title_edit.setText(task.title)
            self._set_combo_value(self.status_combo, task.status)
            self._set_combo_value(self.priority_combo, task.priority)
            self.body_edit.setPlainText(task.raw_body)
            if preserve_body_cursor:
                self._restore_body_cursor(
                    body_position,
                    body_anchor,
                    body_scroll_value,
                    len(task.raw_body),
                )
        finally:
            for widget, blocked in zip(widgets, blocked_states):
                widget.blockSignals(blocked)

        # Refresh the preview after the body text is in place.
        self._render_checklist(task.raw_body)
        self.setVisible(True)

    def closeEvent(self, event) -> None:
        """Flush pending edits on close.

        Args:
            event: Close event.
        """
        self._flush_changes()
        super().closeEvent(event)

    def clear(self) -> None:
        """Stop the debounce timer, flush any pending edit, then hide."""
        self._timer.stop()
        # Persist first so the task still has a valid identity in storage.
        self._flush_changes()
        self._task = None
        self.setVisible(False)

    def discard(self) -> None:
        """Hide the editor without writing current widget state back."""
        self._timer.stop()
        self._task = None
        self.setVisible(False)

    def _build_form(self) -> None:
        """Build the editor form layout."""
        self._populate_combo(self.status_combo, list(Status))
        self._populate_combo(self.priority_combo, list(Priority))

        form = QFormLayout()
        form.addRow("Title", self.title_edit)
        form.addRow("Status", self.status_combo)
        form.addRow("Priority", self.priority_combo)

        body_layout = QHBoxLayout()
        body_layout.addWidget(self.body_edit)
        body_layout.addWidget(self.checklist_view)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Body"))
        layout.addLayout(body_layout)

    def _wire_signals(self) -> None:
        """Wire input changes to debounce logic."""
        self.title_edit.textChanged.connect(self._schedule_flush)
        self.status_combo.currentIndexChanged.connect(self._schedule_flush)
        self.priority_combo.currentIndexChanged.connect(self._schedule_flush)
        self.body_edit.textChanged.connect(self._schedule_flush)

    def _schedule_flush(self) -> None:
        """Schedule a debounced write."""
        if self._task is None:
            return
        self._timer.start()

    def _flush_changes(self) -> None:
        """Write changes through AppState."""
        task = self._task
        if task is None:
            return

        status = self.status_combo.currentData()
        priority = self.priority_combo.currentData()

        fields = {
            "title": self.title_edit.text().strip(),
            "status": status,
            "priority": priority,
            "raw_body": self.body_edit.toPlainText(),
        }
        self.app.tasks.update_task(task.id, fields)
        self._render_checklist(fields["raw_body"])
        self.task_saved.emit()

    def _populate_combo(self, combo: QComboBox, values: list) -> None:
        """Populate a combo box with enum values.

        Args:
            combo: Combo box to populate.
            values: Enum values to add.
        """
        combo.clear()
        for value in values:
            combo.addItem(value.value.upper(), value)

    def _set_combo_value(self, combo: QComboBox, value) -> None:
        """Select a value in a combo box.

        Args:
            combo: Combo box to update.
            value: Value to select.
        """
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _has_unsaved_changes(self, task: Task) -> bool:
        """Return whether the editor differs from the loaded task."""
        return any(
            (
                self.title_edit.text().strip() != task.title,
                self.status_combo.currentData() != task.status,
                self.priority_combo.currentData() != task.priority,
                self.body_edit.toPlainText() != task.raw_body,
            )
        )

    def _render_checklist(self, raw_body: str) -> None:
        """Render a markdown checklist view.

        Args:
            raw_body: Raw markdown body.
        """
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            self.checklist_view.setPlainText(raw_body)
            return

        md = MarkdownIt()
        html = md.render(raw_body)
        self.checklist_view.setHtml(html)

    def _restore_body_cursor(
        self,
        position: int,
        anchor: int,
        scroll_value: int,
        body_length: int,
    ) -> None:
        """Restore the body cursor and scroll position after a reload."""

        # Clamp restored positions so shorter bodies stay in range.
        cursor = self.body_edit.textCursor()

        cursor.setPosition(min(position, body_length))

        if anchor != position:
            cursor.setPosition(
                min(anchor, body_length),
                QTextCursor.MoveMode.KeepAnchor,
            )
        self.body_edit.setTextCursor(cursor)
        scroll_bar = self.body_edit.verticalScrollBar()
        scroll_bar.setValue(min(scroll_value, scroll_bar.maximum()))
