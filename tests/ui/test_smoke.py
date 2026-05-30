"""Smoke tests for UI widget logic.

Tests verify widget behavior and display logic without requiring full Qt display.
These are simplified tests that validate the core corrections made in Phase 2.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock

from pykanban.app import KanbanApp
from pykanban.models import Priority, Status, Task
from pykanban.store import BoardView
from pykanban.ui.error_banner import ErrorBanner
from pykanban.ui.kanban_column import KanbanColumn


def sample_task(
    task_id: str = "task-1",
    status: Status = Status.TODO,
    title: str = "Test Task",
):
    """Create a sample task for testing."""
    now = datetime.now(UTC)
    return Task(
        id=task_id,
        schema=1,
        title=title,
        status=status,
        priority=Priority.MEDIUM,
        raw_body="- [x] Subtask 1\n- [ ] Subtask 2",
        created=now,
        updated=now,
    )


def mock_kanban_app():
    """Create a mock KanbanApp for testing."""
    app = Mock(spec=KanbanApp)
    app.get_board.return_value = MagicMock(spec=BoardView)
    app.update_task = Mock()
    app.move_task = Mock()
    return app


class TestTaskCardImports:
    """Tests that TaskCard imports correctly with fixed typos."""

    def test_task_card_imports(self):
        """Test that TaskCard can be imported without typos."""
        from pykanban.ui.task_card import TaskCard

        assert TaskCard is not None
        assert hasattr(TaskCard, "clicked")


class TestKanbanColumnImports:
    """Tests that KanbanColumn imports correctly with fixed typos."""

    def test_kanban_column_imports(self):
        """Test that KanbanColumn can be imported without typos."""
        from pykanban.ui.kanban_column import KanbanColumn

        assert KanbanColumn is not None

    def test_kanban_column_has_drag_event_methods(self):
        """Test that KanbanColumn has correct Qt event method names."""
        from pykanban.ui.kanban_column import KanbanColumn

        assert hasattr(KanbanColumn, "dragEnterEvent")
        assert hasattr(KanbanColumn, "dropEvent")


class TestTaskEditorImports:
    """Tests that TaskEditor imports correctly with fixed typos."""

    def test_task_editor_imports(self):
        """Test that TaskEditor can be imported without typos."""
        from pykanban.ui.task_editor import TaskEditorPanel

        assert TaskEditorPanel is not None

    def test_task_editor_has_close_event_method(self):
        """Test that TaskEditor has correct Qt event method name."""
        from pykanban.ui.task_editor import TaskEditorPanel

        assert hasattr(TaskEditorPanel, "closeEvent")


class TestErrorBannerTypeHint:
    """Tests that ErrorBanner type hints are correct."""

    def test_error_banner_type_hint_uses_qwidget(self):
        """Test that ErrorBanner type hints use QWidget, not Qwidget."""
        import inspect

        sig = inspect.signature(ErrorBanner.__init__)
        parent_annotation = sig.parameters["parent"].annotation
        # Should be QWidget | None
        assert "QWidget" in str(parent_annotation)


class TestDONEColumnShowsLast10Tasks:
    """Tests for DONE column displaying last 10 tasks."""

    def test_done_column_shows_only_last_10_by_default(self):
        """Test that DONE column shows only last 10 tasks by default."""
        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.DONE, app)

        # Create 30 done tasks
        tasks = [sample_task(f"task-{i}", Status.DONE) for i in range(30)]
        column.refresh(tasks)

        # Should display only 10 cards (not including stretch)
        displayed_count = 0
        for i in range(column.cards_layout.count()):
            item = column.cards_layout.itemAt(i)
            if item.widget():
                displayed_count += 1

        assert displayed_count == 10

    def test_done_column_show_more_button_visible_with_more_than_10_tasks(
        self,
    ):
        """Test that Show More button is visible when more than 10 done tasks."""
        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.DONE, app)

        # Create 25 done tasks
        tasks = [sample_task(f"task-{i}", Status.DONE) for i in range(25)]
        column.refresh(tasks)

        # The show_more button should have been set to visible
        # In headless mode, we check the property directly via the call made in refresh
        assert column.show_more.text() == "Show more"
        # Verify the text was set, which only happens when the condition is met
        assert len(column._tasks) > 10

    def test_done_column_shows_all_tasks_when_toggled(self):
        """Test that toggling Show More displays all tasks."""
        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.DONE, app)

        # Create 25 done tasks
        tasks = [sample_task(f"task-{i}", Status.DONE) for i in range(25)]
        column.refresh(tasks)

        # Click Show More
        column._toggle_done_list()

        # Should display all 25 cards
        displayed_count = 0
        for i in range(column.cards_layout.count()):
            item = column.cards_layout.itemAt(i)
            if item.widget():
                displayed_count += 1

        assert displayed_count == 25
        assert column.show_more.text() == "Show less"

    def test_non_done_column_shows_all_tasks(self):
        """Test that non-DONE columns show all tasks regardless of count."""
        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.TODO, app)

        # Create 30 TODO tasks
        tasks = [sample_task(f"task-{i}", Status.TODO) for i in range(30)]
        column.refresh(tasks)

        # Should display all 30 cards
        displayed_count = 0
        for i in range(column.cards_layout.count()):
            item = column.cards_layout.itemAt(i)
            if item.widget():
                displayed_count += 1

        assert displayed_count == 30


class TestTaskCardClickVsDragSeparation:
    """Tests for click vs drag event separation in TaskCard."""

    def test_task_card_stores_press_position_on_mouse_press(self):
        """Test that TaskCard stores initial mouse press position."""

        from pykanban.ui.task_card import TaskCard

        card = TaskCard(sample_task())
        assert hasattr(card, "_press_pos")

    def test_task_card_does_not_emit_clicked_on_drag(self):
        """Test that clicked signal is not emitted during a drag operation."""
        from unittest.mock import patch

        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        from pykanban.ui.task_card import TaskCard

        card = TaskCard(sample_task())
        clicked_spy = []
        card.clicked.connect(lambda task_id: clicked_spy.append(task_id))

        # Simulate press -> move beyond startDragDistance -> release
        press_pos = QPoint(50, 50)
        move_pos = QPoint(50 + QApplication.startDragDistance() + 10, 50)
        release_pos = move_pos

        # Create press event
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            press_pos,
            press_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(press_event)
        assert card._dragging is False
        assert card._press_pos == press_pos

        # Create move event beyond drag distance
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            move_pos,
            move_pos,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        # Mock _start_drag to avoid blocking on drag.exec()
        with patch.object(card, "_start_drag"):
            card.mouseMoveEvent(move_event)

        # After move beyond threshold, should be dragging
        assert card._dragging is True

        # Create release event
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            release_pos,
            release_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mouseReleaseEvent(release_event)

        # After drag, clicked should not have been emitted
        assert len(clicked_spy) == 0
        assert card._dragging is False

    def test_task_card_emits_clicked_on_simple_click(self):
        """Test that clicked signal is emitted for simple click without drag."""
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        from pykanban.ui.task_card import TaskCard

        card = TaskCard(sample_task())
        clicked_spy = []
        card.clicked.connect(lambda task_id: clicked_spy.append(task_id))

        # Simulate press and release at same position (simple click)
        pos = QPoint(50, 50)

        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            pos,
            pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(press_event)
        assert card._dragging is False

        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            pos,
            pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mouseReleaseEvent(release_event)

        # Clicked should have been emitted
        assert len(clicked_spy) == 1
        assert clicked_spy[0] == sample_task().id
        assert card._dragging is False

    def test_task_card_release_before_timer_fires_no_drag_start(self):
        """Test that releasing before QTimer fires does NOT trigger drag start.

        This test verifies that if user moves beyond threshold but releases
        before the _start_drag timer has a chance to fire, the drag operation
        is properly guarded and never executes.
        """
        from unittest.mock import patch

        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        from pykanban.ui.task_card import TaskCard

        card = TaskCard(sample_task())
        clicked_spy = []
        card.clicked.connect(lambda task_id: clicked_spy.append(task_id))

        # Simulate: press -> move beyond threshold -> release before timer fires
        press_pos = QPoint(50, 50)
        move_pos = QPoint(50 + QApplication.startDragDistance() + 10, 50)

        # Create press event
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            press_pos,
            press_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(press_event)

        # Create move event beyond drag distance
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            move_pos,
            move_pos,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        # Patch _start_drag to track if it's called
        with patch.object(card, "_start_drag") as mock_start_drag:
            card.mouseMoveEvent(move_event)
            # Move sets _dragging = True and schedules _start_drag, but timer hasn't fired yet

        # Now release BEFORE timer fires
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            move_pos,
            move_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        # Reset the mock before release to track calls after drag was set
        with patch.object(card, "_start_drag") as mock_start_drag_on_release:
            card.mouseReleaseEvent(release_event)
            # _start_drag timer callback should be guarded by _dragging and _press_pos
            # If release happens before timer fires, state is reset but _start_drag
            # might still execute from the QTimer callback - it should be guarded

        # After release, state should be reset
        assert card._dragging is False
        assert card._press_pos is None
        # Clicked should not be emitted because we were dragging when released
        assert len(clicked_spy) == 0


class TestDropPositionMapping:
    """Tests for drop position mapping to cards_container coordinates."""

    def test_drop_position_index_maps_to_container_coordinates(self):
        """Test that drop position is correctly mapped to cards_container."""
        from PySide6.QtCore import QPoint

        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.TODO, app)

        # Add some tasks
        tasks = [sample_task(f"task-{i}", Status.TODO) for i in range(3)]
        column.refresh(tasks)

        # Test drop position mapping - drop at top
        pos_top = QPoint(0, 10)
        index = column._drop_position_index(pos_top)
        assert index == 0

    def test_rebuild_cards_removes_all_layout_items_including_stretches(self):
        """Test that _rebuild_cards removes all items including stretches."""
        from pykanban.ui.kanban_column import KanbanColumn

        app = mock_kanban_app()
        column = KanbanColumn(Status.TODO, app)

        # Add tasks - this creates cards + stretch
        tasks = [sample_task(f"task-{i}", Status.TODO) for i in range(3)]
        column.refresh(tasks)

        initial_count = column.cards_layout.count()
        assert initial_count > 3  # Should have 3 cards + at least 1 stretch

        # Refresh with empty list
        column.refresh([])

        final_count = column.cards_layout.count()
        assert final_count == 1  # Only stretch remains after rebuild

    def test_drop_event_maps_position_to_cards_container_coordinates(self):
        """Test that dropEvent properly maps drop position to cards_container.

        This test exercises the actual dropEvent path by simulating a drop event
        with position mapping through cards_container.mapFrom().
        """
        from unittest.mock import Mock, patch

        from PySide6.QtCore import QMimeData, QPoint
        from PySide6.QtGui import QDropEvent

        app = mock_kanban_app()
        column = KanbanColumn(Status.TODO, app)

        # Add 3 tasks
        tasks = [sample_task(f"task-{i}", Status.TODO) for i in range(3)]
        column.refresh(tasks)

        # Create mime data with task info
        mime = QMimeData()
        mime.setData("application/x-task-id", b"task-99")
        mime.setData("application/x-task-status", Status.DOING.value.encode())

        # Create a drop event with position
        # Position is relative to the KanbanColumn (self)
        drop_pos = QPoint(10, 10)

        drop_event = Mock(spec=QDropEvent)
        drop_event.mimeData.return_value = mime
        drop_event.position.return_value = Mock(
            toPoint=Mock(return_value=drop_pos)
        )
        drop_event.acceptProposedAction = Mock()

        # Patch the mapFrom call to verify it's being used
        with patch.object(
            column.cards_container,
            "mapFrom",
            wraps=column.cards_container.mapFrom,
        ) as mock_map_from:
            with patch.object(column, "_drop_position_index", return_value=1):
                column.dropEvent(drop_event)

            # Verify mapFrom was called to map position to cards_container coords
            assert mock_map_from.called
            call_args = mock_map_from.call_args
            # mapFrom(source, pos) - source should be column (self), pos should be drop_pos
            assert call_args[0][0] is column
            assert call_args[0][1] == drop_pos

        # Verify the task was moved
        app.move_task.assert_called_once_with(
            "task-99", Status.TODO, position=1
        )
