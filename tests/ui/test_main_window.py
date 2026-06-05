"""Tests for the main window UI logic."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from pykanban.app import KanbanApp
from pykanban.error import ParseError
from pykanban.models import Priority, Project, Status
from pykanban.ui.main_window import MainWindow


@pytest.fixture
def mock_app():
    """Fixture for creating a mock KanbanApp instance with sane defaults for UI tests."""
    mock_app = MagicMock(spec=KanbanApp)

    # Basic attrs MainWindow expects during __init__/_initial_load()
    mock_app.projects = MagicMock()
    mock_app.tasks = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.projects = MagicMock()
    mock_app.state.projects.active_project_id = None
    mock_app.state.errors = []

    # Provide settings with a valid projects_dir (Path)
    mock_app.state.settings = MagicMock()
    mock_app.state.settings.projects_dir = Path("/fake/projects")

    # Default board used by _refresh_from_state()
    mock_board = MagicMock()
    mock_board.columns = {}
    mock_app.get_board.return_value = mock_board

    # Provide a stable "created project" object so create_project().project_id is predictable
    created_project = MagicMock()
    created_project.project_id = "test-project-123"
    created_project.title = "Test Project"
    created_project.archived = False
    created_project.folder_path = Path("/fake/project_folder")
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
    mock_project.folder_path = Path("/fake/project_folder")
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
    mock_project.folder_path = Path("/fake/project_folder")
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
    mock_project.folder_path = Path("/fake/project_folder")
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


def test_refresh_board_resyncs_open_editor_task(mock_app, mocker) -> None:
    """Refreshing the board should reload the open task from current state."""
    open_task = MagicMock()
    open_task.id = "t1"

    fresh_task = MagicMock()
    fresh_task.id = "t1"
    fresh_task.title = "Task One"
    fresh_task.status = Status.DOING
    fresh_task.priority = Priority.LOW
    fresh_task.raw_body = "# Description\n\nUpdated body."

    mock_app.get_task.return_value = fresh_task

    window = MainWindow(mock_app)
    window.editor._task = open_task

    load_spy = mocker.spy(window.editor, "load_task")

    window._refresh_board(MagicMock())

    mock_app.get_task.assert_called_once_with("t1")
    load_spy.assert_called_once_with(fresh_task)
    assert window.editor._task is fresh_task


def test_refresh_board_discards_deleted_open_task(mock_app, mocker) -> None:
    """Refreshing the board should drop an editor task that no longer exists."""
    open_task = MagicMock()
    open_task.id = "t1"

    mock_app.get_task.return_value = None

    window = MainWindow(mock_app)
    window.editor._task = open_task

    discard_spy = mocker.spy(window.editor, "discard")

    window._refresh_board(MagicMock())

    mock_app.get_task.assert_called_once_with("t1")
    discard_spy.assert_called_once()
    assert window.editor._task is None


def test_refresh_from_state_clears_board_when_no_active_project(
    mock_app, mocker
) -> None:
    """No active project must render an empty board to avoid stale cards."""
    window = MainWindow(mock_app)

    # Ignore calls done during MainWindow.__init__()
    mock_app.get_board.reset_mock()

    refresh_spy = mocker.spy(window.board, "refresh")
    banner_spy = mocker.spy(window.error_banner, "set_errors")

    mock_app.state.projects.active_project_id = None
    mock_app.state.errors = []

    window._refresh_from_state()

    # Should not try reading a board from app when no active project.
    mock_app.get_board.assert_not_called()

    # Should refresh board exactly once with an explicit empty BoardView.
    refresh_spy.assert_called_once()
    rendered_board = refresh_spy.call_args[0][0]

    assert set(rendered_board.columns.keys()) == set(Status)
    assert all(rendered_board.columns[status] == [] for status in Status)

    # Error banner still updates as usual.
    banner_spy.assert_called_once_with(mock_app.state.errors)


def test_delete_last_project_clears_board_when_no_replacement(
    mock_app, mocker
) -> None:
    """Deleting the only active project must clear board cards (no stale UI)."""
    # Arrange: one active project in sidebar/state
    only_project = MagicMock(spec=Project)
    only_project.project_id = "p1"
    only_project.title = "Only Project"
    only_project.archived = False
    only_project.folder_path = Path("/fake/project_folder")

    mock_app.state.projects.projects_by_id = {"p1": only_project}
    mock_app.state.projects.active_project_id = "p1"
    mock_app.projects_list = [only_project]
    mock_app.state.errors = []

    # Simulate user confirms the delete dialog
    mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )

    # Simulate backend result: no replacement project exists
    def fake_delete_project(project_id: str) -> None:
        del mock_app.state.projects.projects_by_id[project_id]
        mock_app.state.projects.active_project_id = None
        mock_app.projects_list = []

    mock_app.delete_project.side_effect = fake_delete_project

    window = MainWindow(mock_app)

    # Ignore refresh calls done during __init__
    refresh_spy = mocker.spy(window.board, "refresh")
    refresh_spy.reset_mock()

    # Act
    window._delete_project("p1")

    # Assert: mutation called
    mock_app.delete_project.assert_called_once_with("p1")

    # Assert: board was explicitly refreshed to empty state
    refresh_spy.assert_called_once()
    rendered_board = refresh_spy.call_args[0][0]

    assert set(rendered_board.columns.keys()) == set(Status)
    assert all(rendered_board.columns[status] == [] for status in Status)

    # Assert: sidebar reflects empty project list
    assert mock_app.projects_list == []


def test_delete_task_missing_task_returns_without_dialog(
    mock_app, mocker
) -> None:
    """If task does not exist, dialog is not shown and nothing is deleted."""
    mock_app.get_task.return_value = None

    question = mocker.patch("pykanban.ui.main_window.QMessageBox.question")
    window = MainWindow(mock_app)

    delete_spy = mocker.spy(mock_app.tasks, "delete_task")
    refresh_spy = mocker.spy(window, "_refresh_from_state")

    window._delete_task("missing-task")

    question.assert_not_called()
    delete_spy.assert_not_called()
    refresh_spy.assert_not_called()


def test_delete_task_cancel_keeps_task_and_does_not_refresh(
    mock_app, mocker
) -> None:
    """When user clicks No, task is kept and UI refresh is skipped."""
    task = MagicMock()
    task.id = "t1"
    task.title = "Task One"
    mock_app.get_task.return_value = task

    question = mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )

    window = MainWindow(mock_app)

    delete_spy = mocker.spy(mock_app.tasks, "delete_task")
    clear_spy = mocker.spy(window.editor, "clear")
    refresh_spy = mocker.spy(window, "_refresh_from_state")

    window._delete_task("t1")

    question.assert_called_once()
    args = question.call_args[0]
    assert args[1] == "Confirm Delete"
    assert "Task One" in args[2]

    delete_spy.assert_not_called()
    clear_spy.assert_not_called()
    refresh_spy.assert_not_called()


def test_delete_task_confirm_deletes_clears_editor_and_refreshes(
    mock_app, mocker
) -> None:
    """When user confirms, task is deleted, editor clears if open, and UI refreshes."""
    task = MagicMock()
    task.id = "t1"
    task.title = "Task One"
    mock_app.get_task.return_value = task

    mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )

    window = MainWindow(mock_app)

    # Simulate editor currently showing the same task being deleted.
    open_task = MagicMock()
    open_task.id = "t1"
    window.editor._task = open_task

    delete_spy = mocker.spy(mock_app.tasks, "delete_task")
    clear_mock = mocker.spy(window.editor, "clear")
    refresh_spy = mocker.spy(window, "_refresh_from_state")

    window._delete_task("t1")

    clear_mock.assert_called_once()
    delete_spy.assert_called_once_with("t1")
    assert refresh_spy.call_count == 2


def test_delete_project_missing_project_returns_without_side_effects(
    mock_app, mocker
) -> None:
    """If project is missing, delete flow should exit early and do nothing."""
    # Guard case: project may already be gone (external FS change, race, stale click).
    mock_app.state.projects.projects_by_id = {}

    question = mocker.patch("pykanban.ui.main_window.QMessageBox.question")
    window = MainWindow(mock_app)

    delete_spy = mocker.spy(mock_app, "delete_project")
    sidebar_spy = mocker.spy(window.sidebar, "refresh")
    refresh_spy = mocker.spy(window, "_refresh_from_state")

    window._delete_project("missing-project-id")

    question.assert_not_called()
    delete_spy.assert_not_called()
    sidebar_spy.assert_not_called()
    refresh_spy.assert_not_called()


def test_delete_project_cancel_returns_without_mutating_state(
    mock_app, mocker
) -> None:
    """If user cancels confirmation, no delete or UI refresh should happen."""
    project = MagicMock(spec=Project)
    project.project_id = "p1"
    project.title = "Project One"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.state.projects.projects_by_id = {"p1": project}
    mock_app.projects_list = [project]

    question = mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    )
    window = MainWindow(mock_app)

    delete_spy = mocker.spy(mock_app, "delete_project")
    sidebar_spy = mocker.spy(window.sidebar, "refresh")
    refresh_spy = mocker.spy(window, "_refresh_from_state")

    window._delete_project("p1")

    # User canceled a destructive action, so flow must stop here.
    question.assert_called_once()
    delete_spy.assert_not_called()
    sidebar_spy.assert_not_called()
    refresh_spy.assert_not_called()


def test_archive_project_confirm_clears_editor_refreshes_sidebar_and_board(
    mock_app, mocker
) -> None:
    """Archiving a project should clear the editor and refresh the empty board."""
    project = MagicMock(spec=Project)
    project.project_id = "p1"
    project.title = "Project One"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.projects_list = [project]
    mock_app.state.projects.projects_by_id = {"p1": project}
    mock_app.state.projects.active_project_id = "p1"
    mock_app.state.errors = []

    mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )

    def fake_archive(project_id: str) -> None:
        assert project_id == "p1"
        project.archived = True
        mock_app.state.projects.active_project_id = None

    mock_app.archive_project.side_effect = fake_archive

    window = MainWindow(mock_app)

    mock_app.archive_project.reset_mock()
    mock_app.get_board.reset_mock()

    clear_spy = mocker.spy(window.editor, "clear")
    sidebar_spy = mocker.spy(window.sidebar, "refresh")
    board_spy = mocker.spy(window.board, "refresh")
    banner_spy = mocker.spy(window.error_banner, "set_errors")

    window._archive_project("p1")

    clear_spy.assert_called_once()
    mock_app.archive_project.assert_called_once_with("p1")
    sidebar_spy.assert_called_once_with([project])
    board_spy.assert_called_once()
    rendered_board = board_spy.call_args[0][0]
    assert set(rendered_board.columns.keys()) == set(Status)
    assert all(rendered_board.columns[status] == [] for status in Status)
    banner_spy.assert_called_once_with(mock_app.state.errors)


def test_archive_project_cancel_does_not_mutate_state(
    mock_app, mocker
) -> None:
    """Canceling archive should leave editor, sidebar, and board untouched."""
    project = MagicMock(spec=Project)
    project.project_id = "p1"
    project.title = "Project One"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.projects_list = [project]
    mock_app.state.projects.projects_by_id = {"p1": project}
    mock_app.state.projects.active_project_id = "p1"
    mock_app.state.errors = []

    mocker.patch(
        "pykanban.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    )

    window = MainWindow(mock_app)

    delete_spy = mocker.spy(mock_app, "archive_project")
    clear_spy = mocker.spy(window.editor, "clear")
    sidebar_spy = mocker.spy(window.sidebar, "refresh")
    board_spy = mocker.spy(window.board, "refresh")

    window._archive_project("p1")

    delete_spy.assert_not_called()
    clear_spy.assert_not_called()
    sidebar_spy.assert_not_called()
    board_spy.assert_not_called()


def test_unarchive_project_refreshes_sidebar_and_board(
    mock_app, mocker
) -> None:
    """Unarchiving should update project state and refresh the current UI."""
    project = MagicMock(spec=Project)
    project.project_id = "p1"
    project.title = "Archived Project"
    project.archived = True
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.projects_list = [project]
    mock_app.state.projects.projects_by_id = {"p1": project}
    mock_app.state.projects.active_project_id = None
    mock_app.state.errors = []

    def fake_unarchive(project_id: str) -> None:
        assert project_id == "p1"
        project.archived = False

    mock_app.unarchive_project.side_effect = fake_unarchive

    window = MainWindow(mock_app)

    mock_app.unarchive_project.reset_mock()
    mock_app.get_board.reset_mock()

    sidebar_spy = mocker.spy(window.sidebar, "refresh")
    board_spy = mocker.spy(window.board, "refresh")
    banner_spy = mocker.spy(window.error_banner, "set_errors")

    window._unarchive_project("p1")

    mock_app.unarchive_project.assert_called_once_with("p1")
    sidebar_spy.assert_called_once_with([project])
    board_spy.assert_called_once()
    rendered_board = board_spy.call_args[0][0]
    assert set(rendered_board.columns.keys()) == set(Status)
    assert all(rendered_board.columns[status] == [] for status in Status)
    banner_spy.assert_called_once_with(mock_app.state.errors)


# -- switch project tests --


def test_switch_project_clears_editor_calls_switch_and_refreshes_board(
    mock_app, mocker
) -> None:
    """Switching projects clears editor, calls app.switch_project and refreshes board."""
    # Arrange
    project = MagicMock(spec=Project)
    project.project_id = "p1"
    project.title = "Project P1"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.state.projects.projects_by_id = {"p1": project}
    mock_app.state.errors = []

    # Make switch_project set the active id so _refresh_from_state will call get_board()
    def set_active(pid):
        mock_app.state.projects.active_project_id = pid

    mock_app.switch_project.side_effect = set_active

    mock_board = MagicMock()
    mock_board.columns = {}
    mock_app.get_board.return_value = mock_board

    window = MainWindow(mock_app)

    # Reset counts from ctor
    mock_app.switch_project.reset_mock()
    mock_app.get_board.reset_mock()

    clear_spy = mocker.spy(window.editor, "clear")
    switch_spy = mocker.spy(mock_app, "switch_project")
    board_refresh_spy = mocker.spy(window.board, "refresh")

    # Act
    window._switch_project("p1")

    # Assert
    clear_spy.assert_called_once()
    switch_spy.assert_called_once_with("p1")
    mock_app.get_board.assert_called_once()
    board_refresh_spy.assert_called_once()


def test_switch_project_shows_empty_board_when_no_active_project_after_switch(
    mock_app, mocker
) -> None:
    """If switch clears active project, UI must render an explicit empty board (no get_board)."""
    project = MagicMock(spec=Project)
    project.project_id = "p2"
    project.title = "Project P2"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.state.projects.projects_by_id = {"p2": project}
    mock_app.state.errors = []

    # Simulate switch_project leaving no active project
    def clear_active(pid):
        mock_app.state.projects.active_project_id = None

    mock_app.switch_project.side_effect = clear_active

    window = MainWindow(mock_app)

    # Reset ctor side-effects
    mock_app.get_board.reset_mock()

    board_refresh_spy = mocker.spy(window.board, "refresh")
    banner_spy = mocker.spy(window.error_banner, "set_errors")

    # Act
    window._switch_project("p2")

    # Assert: get_board not called, empty BoardView rendered
    mock_app.get_board.assert_not_called()
    board_refresh_spy.assert_called_once()
    rendered = board_refresh_spy.call_args[0][0]
    assert set(rendered.columns.keys()) == set(Status)
    assert all(rendered.columns[s] == [] for s in Status)
    banner_spy.assert_called_once_with(mock_app.state.errors)


def test_switch_project_clears_editor_before_switch_call(
    mock_app, mocker
) -> None:
    """Editor must be cleared before delegating to app.switch_project (order guarantees)."""
    project = MagicMock(spec=Project)
    project.project_id = "p3"
    project.title = "Project P3"
    project.archived = False
    project.folder_path = Path("/fake/project_folder")

    mock_app.get_project.return_value = project
    mock_app.state.projects.projects_by_id = {"p3": project}
    mock_app.state.errors = []

    call_order = []

    def record_clear():
        call_order.append("clear")

    def record_switch(pid):
        call_order.append(f"switch:{pid}")
        mock_app.state.projects.active_project_id = pid

    window = MainWindow(mock_app)

    # Patch methods to record order
    mocker.patch.object(window.editor, "clear", side_effect=record_clear)
    mock_app.switch_project.side_effect = record_switch

    # Reset side effects from ctor
    mock_app.get_board.reset_mock()

    window._switch_project("p3")

    assert call_order == ["clear", "switch:p3"]
