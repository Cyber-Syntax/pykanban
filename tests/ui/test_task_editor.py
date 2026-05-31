"""Tests for the task editor panel."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from PySide6.QtGui import QCloseEvent, QTextCursor

from pykanban.app import KanbanApp
from pykanban.models import Priority, Status, Task
from pykanban.ui.task_editor import TaskEditorPanel


def _make_task(task_id: str, raw_body: str) -> Task:
    return Task(
        id=task_id,
        schema=1,
        title="Example Task",
        status=Status.DOING,
        priority=Priority.MEDIUM,
        raw_body=raw_body,
        created=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
        updated=datetime(2026, 5, 31, 11, 0, tzinfo=UTC),
    )


def _select_combo_value(combo, value) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return


def _long_body(line_count: int = 50) -> str:
    return "\n".join(f"Line {index}" for index in range(line_count)) + "\n"


def test_load_task_populates_editor_and_shows_it() -> None:
    """Loading a task should refresh all widgets and show the editor."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    task = _make_task(
        "task-1",
        "# Description\n\nFirst line\nSecond line\n",
    )

    editor.load_task(task)

    assert editor._task is task
    assert editor.isVisible() is True
    assert editor.title_edit.text() == task.title
    assert editor.status_combo.currentData() == task.status
    assert editor.priority_combo.currentData() == task.priority
    assert editor.body_edit.toPlainText() == task.raw_body


def test_load_task_preserves_body_cursor_for_same_task_reload() -> None:
    """Refreshing the same task should not jump the body cursor to the top."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    initial_task = _make_task(
        "task-1",
        "# Description\n\nFirst line\nSecond line\nThird line\n",
    )
    editor.load_task(initial_task)

    cursor = editor.body_edit.textCursor()
    cursor.setPosition(18)
    editor.body_edit.setTextCursor(cursor)

    refreshed_task = _make_task(
        "task-1",
        "# Description\n\nFirst line updated\nSecond line\nThird line\n",
    )
    editor.load_task(refreshed_task)

    assert editor.body_edit.textCursor().position() == 18


def test_load_task_preserves_body_selection_for_same_task_reload() -> None:
    """Reloading the same task should preserve a text selection, not collapse it."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    initial_task = _make_task(
        "task-1",
        "# Description\n\nFirst line\nSecond line\nThird line\n",
    )
    editor.load_task(initial_task)

    cursor = editor.body_edit.textCursor()
    cursor.setPosition(18)
    cursor.setPosition(29, QTextCursor.MoveMode.KeepAnchor)
    editor.body_edit.setTextCursor(cursor)

    refreshed_task = _make_task(
        "task-1",
        "# Description\n\nFirst line updated\nSecond line\nThird line\n",
    )
    editor.load_task(refreshed_task)

    restored_cursor = editor.body_edit.textCursor()
    assert restored_cursor.selectionStart() == 18
    assert restored_cursor.selectionEnd() == 29


def test_load_task_does_not_preserve_cursor_for_different_task() -> None:
    """Switching to another task should not reuse the old cursor position."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    first_task = _make_task(
        "task-1",
        "# Description\n\nFirst line\nSecond line\nThird line\n",
    )
    editor.load_task(first_task)

    cursor = editor.body_edit.textCursor()
    cursor.setPosition(18)
    editor.body_edit.setTextCursor(cursor)

    second_task = _make_task(
        "task-2",
        "# Description\n\nDifferent task body\nAnother line\n",
    )
    editor.load_task(second_task)

    assert editor.body_edit.textCursor().position() == 0


def test_load_task_flushes_pending_changes_before_switching_tasks(
    mocker,
) -> None:
    """Loading a new task should persist edits from the current task first."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    current_task = _make_task("task-1", "# Description\n\nOld body\n")
    editor.load_task(current_task)
    editor.title_edit.setText("  Updated title  ")
    editor.body_edit.setPlainText("# Description\n\nUpdated body\n")

    update_task = mocker.patch.object(
        app.tasks, "update_task", return_value=current_task
    )

    next_task = _make_task("task-2", "# Description\n\nNext body\n")
    editor.load_task(next_task)

    update_task.assert_called_once_with(
        "task-1",
        {
            "title": "Updated title",
            "status": Status.DOING,
            "priority": Priority.MEDIUM,
            "raw_body": "# Description\n\nUpdated body\n",
        },
    )
    assert editor._task is next_task
    assert editor.title_edit.text() == next_task.title
    assert editor.body_edit.toPlainText() == next_task.raw_body


def test_load_task_does_not_reflush_same_task_after_status_save(
    mocker,
) -> None:
    """Reloading the same task after a status change should not save twice."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    task = _make_task("task-1", "# Description\n\nBody\n")
    editor.load_task(task)

    update_task = mocker.patch.object(
        app.tasks, "update_task", return_value=task
    )

    _select_combo_value(editor.status_combo, Status.DONE)
    editor._flush_changes()

    refreshed_task = _make_task("task-1", "# Description\n\nBody\n")
    refreshed_task.status = Status.DONE
    editor.load_task(refreshed_task)

    assert update_task.call_count == 1
    update_task.assert_called_once_with(
        "task-1",
        {
            "title": "Example Task",
            "status": Status.DONE,
            "priority": Priority.MEDIUM,
            "raw_body": "# Description\n\nBody\n",
        },
    )


def test_load_task_clamps_selection_when_body_shrinks() -> None:
    """Reloading a shorter body should keep the selection within bounds."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    initial_task = _make_task("task-1", _long_body(80))
    editor.load_task(initial_task)

    cursor = editor.body_edit.textCursor()
    cursor.setPosition(10)
    cursor.setPosition(60, QTextCursor.MoveMode.KeepAnchor)
    editor.body_edit.setTextCursor(cursor)

    refreshed_task = _make_task("task-1", _long_body(6))
    editor.load_task(refreshed_task)

    restored_cursor = editor.body_edit.textCursor()
    assert restored_cursor.selectionStart() == 10
    assert restored_cursor.selectionEnd() == len(refreshed_task.raw_body)


def test_load_task_clamps_scroll_when_body_shrinks() -> None:
    """Reloading a shorter body should not restore an out-of-range scroll."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    initial_task = _make_task("task-1", _long_body(120))
    editor.load_task(initial_task)

    scroll_bar = editor.body_edit.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    previous_scroll = scroll_bar.value()

    refreshed_task = _make_task("task-1", _long_body(8))
    editor.load_task(refreshed_task)

    restored_scroll = editor.body_edit.verticalScrollBar().value()
    restored_maximum = editor.body_edit.verticalScrollBar().maximum()

    assert restored_scroll <= restored_maximum
    assert restored_scroll <= previous_scroll


def test_schedule_flush_ignores_missing_task() -> None:
    """Typing before a task is loaded should not start any save timer."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)

    editor._schedule_flush()

    assert editor._timer.isActive() is False


def test_schedule_flush_starts_timer_for_loaded_task() -> None:
    """Typing in a loaded editor should start the debounce timer."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    editor._task = _make_task("task-1", "# Description\n\nBody\n")

    editor._schedule_flush()

    assert editor._timer.isActive() is True


def test_flush_changes_strips_title_updates_task_and_emits_signal(
    mocker,
) -> None:
    """Saving should trim the title, persist the task, and emit task_saved."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    task = _make_task("task-1", "# Description\n\nBody\n")
    editor._task = task
    editor.title_edit.setText("  Updated title  ")
    _select_combo_value(editor.status_combo, Status.DONE)
    _select_combo_value(editor.priority_combo, Priority.HIGH)
    editor.body_edit.setPlainText("# Description\n\nUpdated body\n")

    update_task = mocker.patch.object(
        app.tasks, "update_task", return_value=task
    )
    saved_calls: list[int] = []
    editor.task_saved.connect(lambda: saved_calls.append(1))

    editor._flush_changes()

    update_task.assert_called_once_with(
        "task-1",
        {
            "title": "Updated title",
            "status": Status.DONE,
            "priority": Priority.HIGH,
            "raw_body": "# Description\n\nUpdated body\n",
        },
    )
    assert saved_calls == [1]


def test_flush_changes_without_task_does_nothing(mocker) -> None:
    """An empty editor should not try to persist anything."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    update_task = mocker.patch.object(app.tasks, "update_task")
    saved_calls: list[int] = []
    editor.task_saved.connect(lambda: saved_calls.append(1))

    editor._flush_changes()

    update_task.assert_not_called()
    assert saved_calls == []


def test_close_event_flushes_pending_changes(mocker) -> None:
    """Closing the editor should flush the current task before shutting down."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    editor._task = _make_task("task-1", "# Description\n\nBody\n")
    flush_spy = mocker.patch.object(editor, "_flush_changes")
    event = QCloseEvent()

    editor.closeEvent(event)

    flush_spy.assert_called_once()


def test_clear_flushes_pending_changes_and_hides_editor(mocker) -> None:
    """Clearing should persist the draft while the task still exists."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    task = _make_task("task-1", "# Description\n\nBody\n")
    editor._task = task
    editor.title_edit.setText("  Clear me  ")
    update_task = mocker.patch.object(
        app.tasks, "update_task", return_value=task
    )

    editor.clear()

    update_task.assert_called_once()
    assert editor._task is None
    assert editor.isVisible() is False


def test_discard_drops_task_without_persisting_changes(mocker) -> None:
    """Discarding should hide the editor without saving the draft."""
    app = MagicMock(spec=KanbanApp)
    app.tasks = MagicMock()

    editor = TaskEditorPanel(app)
    task = _make_task("task-1", "# Description\n\nBody\n")
    editor._task = task
    editor.title_edit.setText("  Ignore me  ")
    update_task = mocker.patch.object(app.tasks, "update_task")

    editor.discard()

    update_task.assert_not_called()
    assert editor._task is None
    assert editor.isVisible() is False
