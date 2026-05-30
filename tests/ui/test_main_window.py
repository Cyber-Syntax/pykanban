"""Tests for the main window UI logic."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pykanban.app import KanbanApp
from pykanban.error import ParseError
from pykanban.models import Project
from pykanban.ui.main_window import MainWindow


@pytest.fixture
def mock_app():
    """Fixture for creating a mock KanbanApp instance with sane defaults for UI tests."""
    mock_app = MagicMock(spec=KanbanApp)

    # Basic attrs MainWindow expects during __init__/_initial_load()
    mock_app.projects = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.projects = MagicMock()
    mock_app.state.projects.active_project_id = None
    mock_app.state.errors = []

    # Default board used by _refresh_from_state()
    mock_board = MagicMock()
    mock_board.columns = {}
    mock_app.get_board.return_value = mock_board

    # Provide a stable "created project" object so create_project().project_id is predictable
    created_project = MagicMock()
    created_project.project_id = "test-project-123"
    created_project.title = "Test Project"
    created_project.archived = False
    mock_app.projects.create_project.return_value = created_project

    # Sidebar and project helpers that tests often override per-case
    mock_app.projects_list = []
    mock_app.switch_project = MagicMock()
    mock_app.projects.rename_project = MagicMock()
    mock_app.projects.startup_scan = MagicMock()

    return mock_app


@pytest.fixture
def mock_project():
    """Fixture for creating a mock Project instance."""
    mock_project = MagicMock(spec=Project)
    mock_project.project_id = "test-project-123"
    mock_project.title = "Test Project"
    mock_project.archived = False
    return mock_project


def test_main_window_create_project_does_not_crash(
    mock_app, mock_project, mocker
):
    """Test that creating a project successfully updates the UI without crashing.

    This guards against regression of the bug where switch_project returning None
    would crash the KanBan board's refresh routine.

    Args:
        mock_app: A MagicMock instance of KanbanApp with necessary attributes mocked.
        mock_project: A MagicMock instance of Project with necessary attributes mocked.
        mocker: pytest-mock fixture for patching dependencies.
    """
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


def test_main_window_rename_project_refreshes_board(mock_app, mocker) -> None:
    """Renaming a project should refresh the main window state.

    This guards against the bug where the side bar update but the error
    banner stayed stale until another ui action occured.
    """
    # Build a mock project to return when a project is fetched
    mock_project = MagicMock(spec=Project)
    mock_project.project_id = "test-project-123"
    mock_project.title = "Existing Project"
    mock_project.archived = False
    mock_app.get_project.return_value = mock_project

    # State flags required for rendering UI transitions
    mock_app.state.projects.active_project_id = "test-project-123"
    mock_app.state.errors = []

    # Mock PySide6 Dialogs so they simulate a user filling in the new title
    # and don't natively block test execution.
    mocker.patch(
        "pykanban.ui.main_window.QInputDialog.getText",
        return_value=("Renamed Project", True),
    )

    window = MainWindow(mock_app)

    # Reset call counts after initialization so we only verify calls from _rename_project()
    mock_app.projects.rename_project.reset_mock()
    mock_app.get_board.reset_mock()

    # Act
    window._rename_project("test-project-123")

    # Assert
    # Ensure the rename method was called with the new title from the dialog
    mock_app.projects.rename_project.assert_called_once_with(
        "test-project-123", "Renamed Project"
    )

    # Ensure get_board is called to refresh the board state after renaming
    mock_app.get_board.assert_called_once()


def test_rename_project_shows_error_banner_immediately(mock_app, mocker):
    """When rename produces an error, MainWindow must refresh and show the banner immediately."""
    mock_project = MagicMock(spec=Project)
    mock_project.project_id = "p1"
    mock_project.title = "Old"
    mock_project.archived = False
    mock_app.get_project.return_value = mock_project

    mock_app.state.projects.active_project_id = "p1"
    mock_app.state.errors = []

    mocker.patch(
        "pykanban.ui.main_window.QInputDialog.getText",
        return_value=("New Title", True),
    )

    window = MainWindow(mock_app)

    # Make the rename operation append a ParseError into state.errors
    def fake_rename(pid, title):
        mock_app.state.errors.append(
            ParseError(path=Path("conflict.md"), reason="conflict")
        )

    mock_app.projects.rename_project.side_effect = fake_rename

    spy = mocker.spy(window.error_banner, "set_errors")
    window._rename_project("p1")

    # ensure the banner was refreshed with the app state errors
    spy.assert_called()
    assert spy.call_args[0][0] is mock_app.state.errors
    assert isinstance(mock_app.state.errors[0], ParseError)


def test_open_task_loads_existing_task_into_editor(mock_app, mocker):
    """Opening a task should load it into the editor instead of clearing it."""
    # Setup a mock task with expected attributes
    mock_task = MagicMock()
    mock_task.id = "t1"
    mock_app.get_task.return_value = mock_task

    window = MainWindow(mock_app)

    load_task = mocker.patch.object(window.editor, "load_task")
    clear = mocker.patch.object(window.editor, "clear")

    window._open_task("t1")

    # should load existing task, not clear editor
    mock_app.get_task.assert_called_once_with("t1")
    load_task.assert_called_once_with(mock_task)
    clear.assert_not_called()


def test_open_task_clears_previous_task_before_loading_new_task(
    mock_app, mocker
) -> None:
    """Opening a task should clear the previous editor state before loading the new task.

    This guards against the bug where user change so fast a task status/title
    that the editor would load the new task on top of the old one without clearing,
    ending with not updated status/title for that current task.
    """
    old_task = MagicMock()
    old_task.id = "old-task"

    new_task = MagicMock()
    new_task.id = "new-task"
    mock_app.get_task.return_value = new_task

    window = MainWindow(mock_app)
    window.editor._task = old_task

    call_order: list[str] = []

    def record_clear() -> None:
        call_order.append("clear")

    def record_load(task) -> None:
        call_order.append(f"load:{task.id}")

    mocker.patch.object(window.editor, "clear", side_effect=record_clear)
    mocker.patch.object(window.editor, "load_task", side_effect=record_load)

    window._open_task("new-task")

    mock_app.get_task.assert_called_once_with("new-task")
    assert call_order == ["clear", "load:new-task"]


def test_open_task_handles_missing_task(mock_app, mocker) -> None:
    """Opening a missing task should clear the editor and not load anything."""
    mock_app.get_task.return_value = None

    window = MainWindow(mock_app)

    clear = mocker.patch.object(window.editor, "clear")
    load_task = mocker.patch.object(window.editor, "load_task")

    window._open_task("missing-task")

    mock_app.get_task.assert_called_once_with("missing-task")
    clear.assert_called_once()
    load_task.assert_not_called()


# TODO: write tests for unarchive and switch project,delete task

# rename_project if not exist?
# rename_project with empty title?
# rename_project with same title as another project?
# create_project with empty title?
# create_project with same title as another project?
# unarchive_project that doesn't exist?
# unarchive_project that isn't archived?
# switch_project that doesn't exist?
# switch_project with unsaved changes in the editor?
# delete_task that doesn't exist?
# delete_task with unsaved changes in the editor?
# delete_task that is currently being edited?
# delete_task that is in a different project than the active one?
# delete_task that is in the active project but not currently visible on the board?
# delete_task that is in the active project and currently visible on the board?

# need to cover for all of them for extarnal file changes:
# might be lose by user deleted the file via neovim or terminal while our
# app is running.
