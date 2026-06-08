from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock

from PySide6.QtCore import QPoint

from pykanban.app import KanbanApp
from pykanban.models import Priority, Status, Task
from pykanban.store import BoardView
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


class TestDropPositionMapping:
    """Tests for drop position mapping to cards_container coordinates."""

    def test_drop_position_index_maps_to_container_coordinates(self):
        """Test that drop position is correctly mapped to cards_container."""

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
