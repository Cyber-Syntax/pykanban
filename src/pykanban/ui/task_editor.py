"""Task editor panel widget.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
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

from pykanban.core.models import Priority, Status, Task
from pykanban.core.store import AppState


class TaskEditorPanel(QWidget):
    """Editor panel for a single task."""

    task_saved = Signal()

    def __init__(
        self, app_state: AppState, parent: QWidget | None = None
    ) -> None:
        """Initialize the editor panel.

        Args:
            app_state: Application state instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.app_state = app_state
        self._task: Task | None = None

        self.title_edit = QLineEdit()
        self.status_combo = QComboBox()
        self.priority_combo = QComboBox()
        self.body_edit = QPlainTextEdit()
        self.checklist_view = QTextBrowser()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._flush_changes)

        self._build_form()
        self._wire_signals()

        self.setVisible(False)

    def load_task(self, task: Task) -> None:
        """Load a task into the editor.

        Args:
            task: Task to edit.
        """
        self._task = task
        self.title_edit.setText(task.title)
        self._set_combo_value(self.status_combo, task.status)
        self._set_combo_value(self.priority_combo, task.priority)
        self.body_edit.setPlainText(task.raw_body)
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
        # writes while task still exists in store
        self._flush_changes()
        # clear task reference to avoid writing to stale task
        self._task = None
        # make sure editor is hidden after clearing
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
        if self._task is None:
            return

        status = self.status_combo.currentData()
        priority = self.priority_combo.currentData()

        fields = {
            "title": self.title_edit.text().strip(),
            "status": status,
            "priority": priority,
            "raw_body": self.body_edit.toPlainText(),
        }
        self.app_state.update_task(self._task.id, fields)
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
