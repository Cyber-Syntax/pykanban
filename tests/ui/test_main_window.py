"""Tests for the main window UI logic."""

from unittest.mock import MagicMock

from pykanban.models import Project
from pykanban.store import KanbanApp
from pykanban.ui.main_window import MainWindow


def test_main_window_create_project_does_not_crash(mocker):
    """Test that creating a project successfully updates the UI without crashing.

    This guards against regression of the bug where switch_project returning None
    would crash the KanBan board's refresh routine.

    Args:
        mocker: pytest-mock fixture for patching dependencies.
    """
    # Arrange
    # Create the top-level app context
    mock_app = MagicMock(spec=KanbanApp)
    
    # Explicitly mock instance attributes that spec=KanbanApp misses
    mock_app.projects = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.projects = MagicMock()

    # Build a mock project to return when a new project is created
    mock_project = MagicMock(spec=Project)
    mock_project.project_id = "test-project-123"
    mock_project.title = "New Project"
    mock_project.archived = False
    mock_app.projects.create_project.return_value = mock_project

    # Needed by sidebar.refresh() after active project switches
    mock_app.projects_list = [mock_project]

    # Needed by _refresh_from_state() to successfully render the board
    mock_board = MagicMock()
    mock_board.columns = {}
    mock_app.get_board.return_value = mock_board

    # State flags required for rendering UI transitions
    mock_app.state.projects.active_project_id = "test-project-123"
    mock_app.state.errors = []

    # Mock PySide6 Dialogs so they simulate a user filling in title & desc
    # and don't natively block test execution.
    mocker.patch(
        "pykanban.ui.main_window.QInputDialog.getText",
        side_effect=[
            ("New Project", True),  # First prompt: Title
            ("A description here", True),  # Second prompt: Description
        ],
    )

    # Initialize the target class - the `qapp` auto-fixture handles Qt instantiation
    window = MainWindow(mock_app)

    # Reset call counts after initialization so we only verify calls from _create_project()
    mock_app.projects.create_project.reset_mock()
    mock_app.switch_project.reset_mock()
    mock_app.get_board.reset_mock()

    # Act
    # Execute the command. If the UI refresh mechanism breaks here, this will raise.
    window._create_project()

    # Assert
    # Ensure our internal App dependencies were called with accurate extracted dialog string data
    mock_app.projects.create_project.assert_called_once_with(
        "New Project", "A description here"
    )

    # Ensure switch_project uses the new parsed `project_id`.
    mock_app.switch_project.assert_called_once_with("test-project-123")

    # Asserts that the new process accesses `self.app.get_board()` correctly
    # instead of passing in a bad internal variable to KanbanBoard's internal refresh.
    mock_app.get_board.assert_called_once()